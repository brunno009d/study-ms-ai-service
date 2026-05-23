import os
import tempfile
from google.genai import types
from fastapi import HTTPException

from app.core.config import gemini_client, settings
from app.models.schemas import CurriculumParseResponse


# Prompt optimizado para extracción de malla curricular
CURRICULUM_PROMPT = """
Actúa como un experto en gestión curricular académica universitaria.
Analiza el archivo adjunto (puede ser un PDF o una imagen) que contiene una malla curricular y extrae TODA la información estructurada.

INSTRUCCIONES ESTRICTAS:
1. Extrae los datos generales de la carrera: nombre del plan, institución, carrera, total de créditos y total de semestres.
2. Para CADA asignatura extrae: nombre completo, código, créditos, número de semestre, tipo de área (si es visible), y los códigos de sus prerrequisitos.
3. Si el total de créditos no aparece explícitamente en el documento, déjalo como null (NO lo calcules tú).
4. Si el tipo de área (area_type) no es claro, déjalo como null.
5. Los prerrequisitos deben ser los CÓDIGOS de las asignaturas, no los nombres.
6. Asegúrate de capturar TODAS las asignaturas de TODOS los semestres.
7. Los códigos de asignaturas deben coincidir exactamente entre las asignaturas y sus referencias en prerrequisitos.
"""


# System prompt para el chat inteligente con notas (RAG)
NOTES_CHAT_SYSTEM_PROMPT = """
Eres un asistente académico inteligente del estudiante. Tu rol es ayudarle a estudiar, comprender y repasar el contenido de sus notas de clase.

CONTEXTO: El estudiante tiene notas guardadas de un ramo universitario. Recibirás TODAS sus notas como contexto y deberás responder su pregunta basándote ÚNICAMENTE en esa información.

REGLAS ESTRICTAS:
1. SOLO usa información que esté presente en las notas del estudiante. NO inventes datos, definiciones, fórmulas ni conceptos que no aparezcan en las notas.
2. Si el estudiante pregunta algo que NO está cubierto en sus notas, dile explícitamente: "Esa información no aparece en tus notas de este ramo."
3. Cuando hagas referencia a información, menciona de qué nota proviene (usa el título de la nota).
4. Responde en español y en formato Markdown para que sea fácil de leer.
5. Sé conciso pero completo. Usa listas, negritas y encabezados cuando sea apropiado.

CAPACIDADES — Puedes responder a pedidos como:
- Resúmenes generales del ramo o de notas específicas
- Explicar conceptos que aparezcan en las notas
- Comparar temas entre distintas notas
- Listar conceptos clave, fórmulas o definiciones
- Filtrar por fechas ("las últimas 3 notas", "notas de marzo")
- Filtrar por etiquetas/tags ("notas con tag importante")
- Identificar temas que necesitan más estudio
- Crear guías de estudio basadas en el contenido

FORMATO DE LAS NOTAS:
Cada nota tiene: título, contenido, fecha de creación y etiquetas (tags) opcionales. Usa esos metadatos para filtrar cuando el estudiante lo pida.
"""


class GeminiService:
    """Servicio para interactuar con la API de Google Gemini."""

    @staticmethod
    async def parse_curriculum_file(file_bytes: bytes, mime_type: str) -> dict:
        """
        Envía un archivo de malla curricular (PDF o imagen) a Gemini y retorna JSON estructurado.
        
        Usa Structured Outputs para garantizar que la respuesta sea JSON válido
        que coincide con el schema CurriculumParseResponse.
        """
        temp_path = None
        uploaded_file = None

        try:
            # Guardamos el archivo de forma temporal para que Gemini lo pueda procesar
            import mimetypes
            extension = mimetypes.guess_extension(mime_type) or ".pdf"
            
            with tempfile.NamedTemporaryFile(
                suffix=extension, delete=False
            ) as tmp:
                tmp.write(file_bytes)
                temp_path = tmp.name

            # Subida a la File API de Google Gemini
            uploaded_file = gemini_client.files.upload(
                file=temp_path,
                config=types.UploadFileConfig(
                    display_name="Malla Curricular",
                    mime_type=mime_type
                )
            )

            # Solicitud estructurada a Gemini usando el schema de validación
            response = gemini_client.models.generate_content(
                model=settings.VISION_MODEL_NAME,
                contents=[
                    types.Part.from_uri(
                        file_uri=uploaded_file.uri,
                        mime_type=mime_type
                    ),
                    CURRICULUM_PROMPT
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CurriculumParseResponse,
                    temperature=0.1,  # Baja temperatura para mayor precisión en extracción
                )
            )

            parsed: CurriculumParseResponse = response.parsed
            if parsed is None:
                raise HTTPException(
                    status_code=500,
                    detail="Gemini no pudo extraer datos del archivo. Verifica que sea una malla curricular válida."
                )

            result = parsed.model_dump()

            # Si el total de créditos no viene explícito, lo calculamos sumando las materias
            if result["curriculum"]["total_credits"] is None:
                total = sum(s["credits"] for s in result["subjects"])
                result["curriculum"]["total_credits"] = total

            return result

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error al procesar el archivo con Gemini: {str(e)}"
            )
        finally:
            # Limpieza de archivos temporales
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

            # Intentar eliminar archivo de la File API para no consumir almacenamiento
            if uploaded_file:
                try:
                    gemini_client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass

    @staticmethod
    async def chat_with_notes(notes: list, user_message: str) -> str:
        """
        Recibe las notas del ramo como contexto y el mensaje del usuario,
        y genera una respuesta en lenguaje natural usando Gemini.
        
        Este es un enfoque RAG (Retrieval-Augmented Generation):
        - Las notas son el "retrieval" (información real del usuario)
        - Gemini es el "generation" (genera la respuesta)
        - La IA SOLO puede usar información de las notas
        
        Args:
            notes: Lista de dicts con id, title, content_text, created_at, note_tags
            user_message: El mensaje/pregunta del estudiante
            
        Returns:
            str: Respuesta de la IA en formato Markdown
        """
        # Construir el bloque de contexto con todas las notas
        notes_context = f"Total de notas disponibles en este ramo: {len(notes)}\n"
        
        for i, note in enumerate(notes, 1):
            # Extraer nombres de tags
            tags_str = ""
            if note.get("note_tags"):
                tag_names = [
                    nt.get("tags", {}).get("name", "")
                    for nt in note["note_tags"]
                    if nt.get("tags")
                ]
                tag_names = list(filter(None, tag_names))
                if tag_names:
                    tags_str = f"  |  Tags: {', '.join(tag_names)}"

            notes_context += f"\n{'='*60}\n"
            notes_context += f"📄 NOTA {i}: {note['title']}\n"
            notes_context += f"Fecha: {note.get('created_at', 'Sin fecha')}{tags_str}\n"
            notes_context += f"{'='*60}\n"
            notes_context += f"{note.get('content_text', '(sin contenido)')}\n"

        # Construir el prompt completo: system + contexto + pregunta del usuario
        full_prompt = f"""{NOTES_CHAT_SYSTEM_PROMPT}

========== NOTAS DEL RAMO ==========
{notes_context}
========== FIN DE LAS NOTAS ==========

MENSAJE DEL ESTUDIANTE:
{user_message}
"""

        try:
            response = gemini_client.models.generate_content(
                model=settings.TEXT_MODEL_NAME,
                contents=[full_prompt],
                config=types.GenerateContentConfig(
                    temperature=0.4,  # Equilibrio: creativo para redactar, preciso para no inventar
                )
            )

            # Extraer el texto de la respuesta
            answer = response.text

            if not answer or not answer.strip():
                raise HTTPException(
                    status_code=500,
                    detail="Gemini no generó una respuesta. Intenta reformular tu pregunta."
                )

            return answer.strip()

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error al generar respuesta con Gemini: {str(e)}"
            )

    # -> Módulo IA - Consejero academico

    # Herramientas disponibles para el consejero
    ADVISOR_TOOLS = [
        types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name="get_student_profile",
                description="Obtiene el nombre y datos básicos del estudiante",
                parameters=types.Schema(type="OBJECT", properties={})
            ),
            types.FunctionDeclaration(
                name="get_full_curriculum",
                description=(
                    "Obtiene la malla curricular COMPLETA: carrera, institución, "
                    "TODOS los ramos de TODOS los semestres con código/créditos/semestre/área, "
                    "prerrequisitos entre ramos (IDs), y el estado de cada uno "
                    "(aprobado, cursando, pendiente). Útil para: aconsejar sobre "
                    "ramos importantes, analizar cadenas de prerrequisitos, "
                    "sugerir qué tomar el próximo semestre, visión global de la carrera."
                ),
                parameters=types.Schema(type="OBJECT", properties={})
            ),
            types.FunctionDeclaration(
                name="get_current_subjects",
                description=(
                    "Obtiene SOLO las materias que el estudiante está cursando actualmente "
                    "(status='cursando'). Más liviano que get_full_curriculum. "
                    "Útil cuando la pregunta es solo sobre el semestre actual."
                ),
                parameters=types.Schema(type="OBJECT", properties={})
            ),
            types.FunctionDeclaration(
                name="get_all_grades",
                description=(
                    "Obtiene TODAS las calificaciones del estudiante en TODAS sus materias: "
                    "por cada materia devuelve su árbol de categorías (certámenes, tareas, etc.) "
                    "con peso, cada evaluación individual con nota/peso/simulación, y el resumen "
                    "(promedio real, proyectado, aprobación). Útil para: visión global del rendimiento, "
                    "comparar entre materias, detectar tendencias."
                ),
                parameters=types.Schema(type="OBJECT", properties={})
            ),
            types.FunctionDeclaration(
                name="get_current_grades",
                description=(
                    "Obtiene las calificaciones SOLO de las materias que el estudiante "
                    "está cursando actualmente. Más liviano que get_all_grades. "
                    "Útil para: detectar ramos en riesgo este semestre, calcular qué nota "
                    "necesita para aprobar, foco en lo inmediato."
                ),
                parameters=types.Schema(type="OBJECT", properties={})
            ),
            types.FunctionDeclaration(
                name="get_calendar_events",
                description=(
                    "Obtiene los calendarios + TODOS los eventos de los próximos 30 días: "
                    "exámenes, entregas, tareas, con fechas, tipo, color y nombre del calendario. "
                    "Útil para: organizar plan de estudio, priorizar por cercanía, "
                    "advertir sobre acumulación de entregas."
                ),
                parameters=types.Schema(type="OBJECT", properties={})
            ),
            types.FunctionDeclaration(
                name="get_notes_overview",
                description=(
                    "Obtiene metadatos de TODAS las notas/apuntes: título, ramo al que "
                    "pertenece (nombre y código), tags/etiquetas, fechas de creación. "
                    "NO incluye contenido completo de las notas. "
                    "Útil para: saber qué temas ha estudiado, cruzar con calificaciones "
                    "para detectar lagunas de estudio, sugerir qué repasar."
                ),
                parameters=types.Schema(type="OBJECT", properties={})
            ),
        ])
    ]

    # System prompt del consejero
    ADVISOR_SYSTEM_PROMPT = """
Eres un consejero académico inteligente y empático de PopStudy.

ROL: Asesor de estudios personalizado. Ayudas al estudiante a tomar mejores
decisiones académicas basándote en SU información real.

REGLAS:
1. SOLO LECTURA: No puedes crear, modificar ni eliminar datos. Solo consultas y aconsejas.
2. USA LAS HERRAMIENTAS: Consulta la información que necesites. No inventes datos.
   Si la pregunta es sobre el semestre actual, usa las herramientas "current" (más livianas).
   Si necesitas la visión completa de la carrera, usa las herramientas completas.
3. SÉ ESPECÍFICO: Usa nombres de ramos, notas reales, fechas exactas.
4. CRUZA INFORMACIÓN: Tu valor está en conectar datos de distintas fuentes:
   - Calendario + calificaciones → priorizar estudio por urgencia + riesgo
   - Prerrequisitos + progreso → aconsejar qué ramos tomar
   - Notas/apuntes + calificaciones bajas → sugerir qué repasar
5. Responde en español, Markdown, conciso pero completo.
6. Sé motivador pero honesto. Si un ramo está en riesgo, dilo con datos.
"""

    @staticmethod
    async def advisor_chat(user_message: str, token: str, student_id: str, session_id: str = None) -> dict:
        """
        Consejero académico con Function Calling y memoria de sesión.
        
        - Si session_id es None → crea una nueva sesión
        - Si session_id existe → carga el historial y continúa la conversación
        
        Gemini recibe el historial de mensajes anteriores para mantener el contexto.
        """
        from app.services.microservices_client import MicroservicesClient
        from app.repository.chat_repository import ChatRepository

        # Mapa: nombre de la función → handler que la ejecuta
        tool_handlers = {
            "get_student_profile": lambda: MicroservicesClient.get_user_profile(token),
            "get_full_curriculum": lambda: MicroservicesClient.get_curriculum(token),
            "get_current_subjects": lambda: MicroservicesClient.get_current_subjects(token),
            "get_all_grades": lambda: MicroservicesClient.get_grades(token),
            "get_current_grades": lambda: MicroservicesClient.get_current_grades(token),
            "get_calendar_events": lambda: MicroservicesClient.get_calendar(token),
            "get_notes_overview": lambda: MicroservicesClient.get_notes(token),
        }

        # --- Gestión de sesión ---

        if session_id:
            # Verificar que la sesión existe y pertenece al estudiante
            session = await ChatRepository.get_session_by_id(session_id)
            if not session or session["student_id"] != student_id:
                raise HTTPException(
                    status_code=404,
                    detail="Sesión de chat no encontrada o no pertenece a este usuario."
                )
            # Actualizar timestamp de la sesión
            await ChatRepository.update_session(session_id, {})
        else:
            # Creamos una sesión nueva si no existe
            title = user_message[:80] + ("..." if len(user_message) > 80 else "")
            session = await ChatRepository.create_session(student_id, title)
            session_id = session["id"]

        # Cargar los mensajes anteriores del chat para mantener el contexto
        contents = []
        if session_id:
            history = await ChatRepository.get_recent_messages(session_id, limit=20)
            for msg in history:
                role = msg["role"]
                
                if role == "user":
                    contents.append(
                        types.Content(role="user", parts=[types.Part.from_text(text=msg["content"])])
                    )
                elif role == "model":
                    contents.append(
                        types.Content(role="model", parts=[types.Part.from_text(text=msg["content"])])
                    )

        # Agregar el mensaje actual del usuario
        contents.append(
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
        )

        # Guardar mensaje del usuario
        await ChatRepository.add_message(session_id, "user", user_message)

        tools_used = []

        config = types.GenerateContentConfig(
            system_instruction=GeminiService.ADVISOR_SYSTEM_PROMPT,
            tools=GeminiService.ADVISOR_TOOLS,
            temperature=0.4,
        )

        try:
            # Loop de seguridad para controlar llamadas recursivas de Function Calling
            for _ in range(5):
                response = gemini_client.models.generate_content(
                    model=settings.TEXT_MODEL_NAME,
                    contents=contents,
                    config=config,
                )

                if response.text:
                    answer = response.text.strip()
                    # Guardar respuesta de la IA en la sesión
                    await ChatRepository.add_message(session_id, "model", answer)
                    return {
                        "answer": answer,
                        "tools_used": tools_used,
                        "session_id": session_id
                    }

                # Si Gemini pide llamar una función → ejecutarla
                candidate = response.candidates[0]
                part = candidate.content.parts[0]

                if hasattr(part, "function_call") and part.function_call:
                    fn_name = part.function_call.name
                    handler = tool_handlers.get(fn_name)

                    if handler:
                        tools_used.append(fn_name)
                        result = await handler()

                        # Agregar al historial: respuesta de Gemini + resultado de la función
                        contents.append(candidate.content)
                        contents.append(
                            types.Content(
                                role="user",
                                parts=[types.Part.from_function_response(
                                    name=fn_name,
                                    response={"result": result or "Sin datos disponibles para este estudiante."}
                                )]
                            )
                        )
                    else:
                        break
                else:
                    # En caso de que no haya texto directo ni llamada de función
                    if candidate.content and candidate.content.parts:
                        text_parts = [p.text for p in candidate.content.parts if hasattr(p, 'text') and p.text]
                        if text_parts:
                            answer = "\n".join(text_parts).strip()
                            await ChatRepository.add_message(session_id, "model", answer)
                            return {
                                "answer": answer,
                                "tools_used": tools_used,
                                "session_id": session_id
                            }
                    break

            raise HTTPException(
                status_code=500,
                detail="La IA no pudo generar una respuesta. Intenta reformular tu pregunta."
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error al generar respuesta del consejero: {str(e)}"
            )
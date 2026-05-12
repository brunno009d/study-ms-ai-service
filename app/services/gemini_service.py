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
            # 1. Guardar bytes en archivo temporal
            import mimetypes
            extension = mimetypes.guess_extension(mime_type) or ".pdf"
            
            with tempfile.NamedTemporaryFile(
                suffix=extension, delete=False
            ) as tmp:
                tmp.write(file_bytes)
                temp_path = tmp.name

            # 2. Subir archivo a la File API de Gemini
            uploaded_file = gemini_client.files.upload(
                file=temp_path,
                config=types.UploadFileConfig(
                    display_name="Malla Curricular",
                    mime_type=mime_type
                )
            )

            # 3. Generar contenido con Structured Output
            response = gemini_client.models.generate_content(
                model=settings.MODEL_NAME,
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

            # 4. El SDK parsea automáticamente al schema Pydantic
            parsed: CurriculumParseResponse = response.parsed

            if parsed is None:
                raise HTTPException(
                    status_code=500,
                    detail="Gemini no pudo extraer datos del archivo. Verifica que sea una malla curricular válida."
                )

            # 5. Post-procesamiento: calcular total_credits si no vino del documento
            result = parsed.model_dump()

            # Calcular total_credits si no vino del documento
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
            # Limpiar archivo temporal
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

            # Intentar eliminar archivo de la File API para no consumir almacenamiento
            if uploaded_file:
                try:
                    gemini_client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass  # No es crítico si falla la limpieza

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
                model=settings.MODEL_NAME,
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
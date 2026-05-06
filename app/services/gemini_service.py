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
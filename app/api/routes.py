from fastapi import APIRouter, HTTPException, Depends
from app.models.schemas import ParseCurriculumRequest, CurriculumParseResponse
from app.services.pdf_service import download_file_from_url
from app.services.gemini_service import GeminiService
from app.api.dependencies import require_auth

router = APIRouter()


@router.post("/parse-curriculum", response_model=CurriculumParseResponse, status_code=201)
async def parse_curriculum(request: ParseCurriculumRequest, user_id: str = Depends(require_auth)):
    """
    Recibe la URL de un archivo de malla curricular (PDF o imagen, almacenado en Supabase Storage),
    lo descarga, lo envía a Gemini para extraer la información y retorna un JSON
    estructurado que el frontend puede editar antes de guardarlo.
    """
    # 1. Descargar el archivo desde la URL de Supabase
    file_bytes, mime_type = await download_file_from_url(request.file_url)

    # 2. Procesar con Gemini AI
    result = await GeminiService.parse_curriculum_file(file_bytes, mime_type)

    return result
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.models.schemas import (
    ParseCurriculumRequest, CurriculumParseResponse,
    ChatNotesRequest, ChatNotesResponse
)
from app.services.pdf_service import download_file_from_url
from app.services.gemini_service import GeminiService
from app.services.notes_client import NotesServiceClient
from app.api.dependencies import require_auth

router = APIRouter()

# Necesitamos acceder al token raw para reenviarlo al notes-service
security = HTTPBearer()


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


@router.post("/chat-notes", response_model=ChatNotesResponse, status_code=200)
async def chat_notes(
    request: ChatNotesRequest,
    user_id: str = Depends(require_auth),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Chat inteligente con las notas de un ramo.
    
    El usuario escribe un mensaje libre (pregunta, pedido de resumen, etc.)
    y la IA responde basándose SOLO en las notas del ramo indicado.
    
    La IA puede interpretar pedidos como:
    - "Resúmeme las últimas 3 notas"
    - "¿Qué temas cubren las notas con tag 'importante'?"
    - "Explícame el concepto de X que aparece en mis notas"
    - "Hazme una guía de estudio con todo el contenido"
    
    Opcionalmente, la respuesta se puede guardar como una nueva nota en el ramo.
    """
    token = credentials.credentials

    # 1. Obtener TODAS las notas del ramo (la IA decide qué es relevante)
    notes = await NotesServiceClient.get_note_contents(
        subject_id=request.subject_id,
        token=token
    )

    if not notes:
        raise HTTPException(
            status_code=404,
            detail="Este ramo no tiene notas con contenido. Crea algunas notas primero."
        )

    # 2. Enviar las notas + mensaje del usuario a Gemini
    answer = await GeminiService.chat_with_notes(
        notes=notes,
        user_message=request.message
    )

    # 3. Guardar como nota si el usuario lo solicitó
    saved_note_id = None
    if request.save_as_note:
        saved_note = await NotesServiceClient.save_summary_as_note(
            subject_id=request.subject_id,
            summary_text=answer,
            token=token
        )
        saved_note_id = saved_note.get("id")

    return ChatNotesResponse(
        answer=answer,
        notes_used=len(notes),
        saved_note_id=saved_note_id
    )
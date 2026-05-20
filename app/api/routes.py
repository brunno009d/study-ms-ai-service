from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.models.schemas import (
    ParseCurriculumRequest, CurriculumParseResponse,
    ChatNotesRequest, ChatNotesResponse,
    AdvisorRequest, AdvisorResponse,
    ChatSessionResponse, ChatSessionDetailResponse, ChatMessageResponse,
    UpdateSessionRequest
)
from app.services.pdf_service import download_file_from_url
from app.services.gemini_service import GeminiService
from app.services.notes_client import NotesServiceClient
from app.repository.chat_repository import ChatRepository
from app.api.dependencies import require_auth

router = APIRouter()

# Necesitamos acceder al token raw para reenviarlo al notes-service y microservicios
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


# Modulo IA - Consejero academico

@router.post("/advisor", response_model=AdvisorResponse, status_code=200)
async def advisor_chat(
    request: AdvisorRequest,
    user_id: str = Depends(require_auth),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Recibe el id de la sesion y el mensaje del usuario.
    
    - Sin session_id → crea una nueva sesión de chat
    - Con session_id → continúa la conversación (la IA recuerda el contexto)
    
    Consulta los microservicios (malla, calificaciones, calendario, notas)
    mediante Function Calling para dar consejos personalizados.
    """
    token = credentials.credentials

    # Deriva todo el trabajo al servicio inteligente
    result = await GeminiService.advisor_chat(
        user_message=request.message,
        token=token,
        student_id=user_id,
        session_id=request.session_id
    )

    return result


# Gestion de sesiones de chat

@router.get("/sessions", response_model=list[ChatSessionResponse], status_code=200)
async def list_sessions(user_id: str = Depends(require_auth)):
    """
    Lista todas las sesiones de chat del estudiante, ordenadas por más recientes.
    Útil para que el frontend muestre el historial de conversaciones.
    """
    sessions = await ChatRepository.get_sessions_by_student(user_id)
    return sessions


@router.get("/sessions/{session_id}", response_model=ChatSessionDetailResponse, status_code=200)
async def get_session_detail(session_id: str, user_id: str = Depends(require_auth)):
    """
    Obtiene una sesión de chat con todos sus mensajes.
    Útil para cargar una conversación anterior en el frontend.
    """
    session = await ChatRepository.get_session_by_id(session_id)

    if not session or session["student_id"] != user_id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")

    messages = await ChatRepository.get_messages_by_session(session_id)

    return ChatSessionDetailResponse(
        session=ChatSessionResponse(**session),
        messages=[ChatMessageResponse(**msg) for msg in messages]
    )


@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse, status_code=200)
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    user_id: str = Depends(require_auth)
):
    """Actualiza el título de una sesión de chat."""
    session = await ChatRepository.get_session_by_id(session_id)

    if not session or session["student_id"] != user_id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")

    updated = await ChatRepository.update_session(session_id, {"title": request.title})
    return updated


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, user_id: str = Depends(require_auth)):
    """Elimina una sesión de chat y todos sus mensajes (CASCADE)."""
    session = await ChatRepository.get_session_by_id(session_id)

    if not session or session["student_id"] != user_id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")

    await ChatRepository.delete_session(session_id)
    return None
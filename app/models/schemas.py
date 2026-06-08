from pydantic import BaseModel, Field
from typing import List, Optional


# Schemas para el parsing de PDF de malla curricular

class SubjectSchema(BaseModel):
    """Una asignatura extraída del PDF de la malla curricular."""
    name: str = Field(description="Nombre completo de la asignatura")
    code: str = Field(description="Código único de la asignatura (ej: MAT101)")
    credits: int = Field(description="Cantidad de créditos de la asignatura")
    semester_number: int = Field(description="Número del semestre al que pertenece (1, 2, 3...)")
    area_type: Optional[str] = Field(
        default=None,
        description="Área o tipo de formación: Formación General, Especialidad, Electivo, Ciencias Básicas, etc."
    )
    prerequisites: List[str] = Field(
        default_factory=list,
        description="Lista de códigos de asignaturas que son prerrequisito de esta asignatura"
    )


class CurriculumSchema(BaseModel):
    """Datos generales del plan de estudios extraídos del PDF."""
    name: str = Field(description="Nombre del plan de estudios o malla curricular")
    institution: str = Field(description="Nombre de la universidad o institución educativa")
    career: str = Field(description="Nombre de la carrera profesional")
    total_credits: Optional[int] = Field(
        default=None,
        description="Total de créditos de toda la carrera. Si no aparece en el PDF, será null."
    )
    total_semester: Optional[int] = Field(
        default=None,
        description="Número total de semestres de la carrera"
    )


class CurriculumParseResponse(BaseModel):
    """Respuesta completa del parsing de un PDF de malla curricular."""
    curriculum: CurriculumSchema
    subjects: List[SubjectSchema]


# Schemas para los request bodies

class ParseCurriculumRequest(BaseModel):
    """Body del request para parsear una malla curricular."""
    file_url: str = Field(description="URL pública del archivo (PDF o imagen) almacenado en Supabase Storage")


# --- Schemas para chat inteligente con notas del ramo ---

class ChatNotesRequest(BaseModel):
    """
    Body del request para chatear con la IA usando las notas del ramo como contexto.
    El usuario escribe un mensaje libre y la IA responde basándose SOLO en las notas del ramo.
    """
    subject_id: int = Field(
        description="ID del ramo/asignatura. La IA usará todas las notas de este ramo como contexto."
    )
    message: str = Field(
        description="Mensaje del usuario. Puede ser una pregunta, pedido de resumen, consulta sobre conceptos, etc.",
        min_length=1,
        max_length=2000
    )
    save_as_note: bool = Field(
        default=False,
        description="Si es true, guarda la respuesta de la IA como una nueva nota dentro del ramo"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="ID de sesión RAG existente. Si es null se crea una nueva sesión."
    )


class ChatNotesResponse(BaseModel):
    """Respuesta de la IA basada en las notas del ramo."""
    answer: str = Field(
        description="Respuesta de la IA en formato Markdown, basada en las notas del ramo"
    )
    notes_used: int = Field(
        description="Cantidad de notas del ramo que se usaron como contexto"
    )
    saved_note_id: Optional[int] = Field(
        default=None,
        description="ID de la nota guardada (solo si save_as_note fue true)"
    )
    session_id: str = Field(
        description="ID de la sesión RAG (nueva o existente)"
    )


# --- Schemas para el consejero académico IA ---

class AdvisorRequest(BaseModel):
    """Pregunta libre al consejero académico IA."""
    message: str = Field(
        description="Pregunta del estudiante al consejero IA. "
                    "Puede ser sobre calificaciones, materias, plan de estudio, etc.",
        min_length=1,
        max_length=2000
    )
    session_id: Optional[str] = Field(
        default=None,
        description="ID de la sesión de chat. Si es null, se crea una nueva sesión. "
                    "Si se proporciona, continúa la conversación existente."
    )


class AdvisorResponse(BaseModel):
    """Respuesta del consejero IA con metadata de herramientas consultadas."""
    answer: str = Field(
        description="Respuesta del consejero en formato Markdown"
    )
    tools_used: List[str] = Field(
        default_factory=list,
        description="Lista de herramientas que la IA consultó para generar la respuesta"
    )
    session_id: str = Field(
        description="ID de la sesión de chat (nueva o existente)"
    )


# --- Schemas para gestión de sesiones de chat ---

class ChatSessionResponse(BaseModel):
    """Sesión de chat (consejero o RAG)."""
    id: str
    student_id: str
    title: Optional[str] = None
    subject_id: Optional[int] = None
    created_at: str
    updated_at: str


class ChatMessageResponse(BaseModel):
    """Mensaje individual de una sesión de chat."""
    id: str
    session_id: str
    role: str
    content: str
    token_count: int = 0
    created_at: str


class ChatSessionDetailResponse(BaseModel):
    """Sesión de chat con todos sus mensajes."""
    session: ChatSessionResponse
    messages: List[ChatMessageResponse]


class UpdateSessionRequest(BaseModel):
    """Actualizar el título de una sesión."""
    title: str = Field(
        description="Nuevo título para la sesión",
        min_length=1,
        max_length=200
    )
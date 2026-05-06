from pydantic import BaseModel, Field, AliasChoices
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
    file_url: str = Field(
        validation_alias=AliasChoices("file_url", "pdf_url"),
        description="URL pública del archivo (PDF o imagen) almacenado en Supabase Storage"
    )
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from app.services.gemini_service import GeminiService
from app.models.schemas import CurriculumParseResponse, CurriculumSchema, SubjectSchema


# ─── parse_curriculum_file ────────────────────────────────────────────────────

class TestParseCurriculumFile:

    async def test_extraccion_exitosa_retorna_dict(self):
        # Arrange
        fake_parsed = CurriculumParseResponse(
            curriculum=CurriculumSchema(
                name="Plan 2020",
                institution="Universidad Ejemplo",
                career="Ingeniería Informática",
                total_credits=240,
                total_semester=10
            ),
            subjects=[
                SubjectSchema(name="Cálculo I", code="MAT101", credits=6, semester_number=1)
            ]
        )

        mock_gemini = MagicMock()
        mock_gemini.files.upload.return_value = MagicMock(uri="gs://fake/uri", name="files/fake")
        mock_gemini.models.generate_content.return_value = MagicMock(parsed=fake_parsed)

        # Act
        with patch("app.services.gemini_service.gemini_client", mock_gemini):
            result = await GeminiService.parse_curriculum_file(b"fake pdf bytes", "application/pdf")

        # Assert
        assert result["curriculum"]["career"] == "Ingeniería Informática"
        assert len(result["subjects"]) == 1
        assert result["subjects"][0]["code"] == "MAT101"

    async def test_calcula_total_credits_cuando_es_none(self):
        # Arrange — total_credits es None, debe sumarse de las materias
        fake_parsed = CurriculumParseResponse(
            curriculum=CurriculumSchema(
                name="Plan 2020",
                institution="UNAB",
                career="Ingeniería Civil",
                total_credits=None,
                total_semester=10
            ),
            subjects=[
                SubjectSchema(name="Matemáticas", code="MAT101", credits=6, semester_number=1),
                SubjectSchema(name="Física", code="FIS101", credits=5, semester_number=1),
            ]
        )

        mock_gemini = MagicMock()
        mock_gemini.files.upload.return_value = MagicMock(uri="gs://fake/uri", name="files/fake")
        mock_gemini.models.generate_content.return_value = MagicMock(parsed=fake_parsed)

        # Act
        with patch("app.services.gemini_service.gemini_client", mock_gemini):
            result = await GeminiService.parse_curriculum_file(b"pdf bytes", "application/pdf")

        # Assert — 6 + 5 = 11
        assert result["curriculum"]["total_credits"] == 11

    async def test_parsed_none_lanza_500(self):
        # Arrange — Gemini retorna parsed=None (no pudo extraer datos)
        mock_gemini = MagicMock()
        mock_gemini.files.upload.return_value = MagicMock(uri="gs://fake/uri", name="files/fake")
        mock_gemini.models.generate_content.return_value = MagicMock(parsed=None)

        # Act & Assert
        with patch("app.services.gemini_service.gemini_client", mock_gemini):
            with pytest.raises(HTTPException) as exc:
                await GeminiService.parse_curriculum_file(b"pdf bytes", "application/pdf")
        assert exc.value.status_code == 500

    async def test_excepcion_gemini_lanza_500(self):
        # Arrange — Gemini lanza excepción inesperada
        mock_gemini = MagicMock()
        mock_gemini.files.upload.side_effect = Exception("API error")

        # Act & Assert
        with patch("app.services.gemini_service.gemini_client", mock_gemini):
            with pytest.raises(HTTPException) as exc:
                await GeminiService.parse_curriculum_file(b"pdf bytes", "application/pdf")
        assert exc.value.status_code == 500

    async def test_limpia_archivo_gemini_aunque_falle(self):
        # Arrange — generate_content falla pero el archivo fue subido
        uploaded_file = MagicMock()
        uploaded_file.uri = "gs://fake/uri"
        uploaded_file.name = "files/fake-123"
        mock_gemini = MagicMock()
        mock_gemini.files.upload.return_value = uploaded_file
        mock_gemini.models.generate_content.side_effect = Exception("API error")

        # Act
        with patch("app.services.gemini_service.gemini_client", mock_gemini):
            with pytest.raises(HTTPException):
                await GeminiService.parse_curriculum_file(b"pdf bytes", "application/pdf")

        # Assert — debe intentar borrar el archivo aunque haya fallado
        mock_gemini.files.delete.assert_called_once_with(name="files/fake-123")


# ─── chat_with_notes ─────────────────────────────────────────────────────────

FAKE_NOTES = [
    {
        "id": 1,
        "title": "Introducción a Python",
        "content_text": "Python es un lenguaje interpretado...",
        "created_at": "2024-01-01",
        "note_tags": [{"tags": {"name": "importante"}}]
    }
]


class TestChatWithNotes:

    async def test_respuesta_exitosa_de_gemini(self):
        # Arrange
        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.return_value = MagicMock(
            text="Python es un lenguaje de programación interpretado."
        )

        # Act
        with patch("app.services.gemini_service.gemini_client", mock_gemini):
            result = await GeminiService.chat_with_notes(FAKE_NOTES, "¿Qué es Python?")

        # Assert
        assert "Python" in result
        assert isinstance(result, str)

    async def test_respuesta_vacia_de_gemini_lanza_500(self):
        # Arrange
        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.return_value = MagicMock(text="   ")

        # Act & Assert
        with patch("app.services.gemini_service.gemini_client", mock_gemini):
            with pytest.raises(HTTPException) as exc:
                await GeminiService.chat_with_notes(FAKE_NOTES, "¿Qué es Python?")
        assert exc.value.status_code == 500

    async def test_fallback_a_openrouter_cuando_gemini_falla(self):
        # Arrange — Gemini falla, OpenRouter responde correctamente
        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.side_effect = Exception("Gemini error")

        mock_openrouter = MagicMock()
        mock_openrouter.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Respuesta desde OpenRouter"))]
        )

        # Act
        with patch("app.services.gemini_service.gemini_client", mock_gemini):
            with patch("app.services.gemini_service.openrouter_client", mock_openrouter):
                result = await GeminiService.chat_with_notes(FAKE_NOTES, "¿Qué es Python?")

        # Assert
        assert result == "Respuesta desde OpenRouter"

    async def test_error_cuota_gemini_lanza_429(self):
        # Arrange — error de cuota (429), OpenRouter también falla
        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED quota exceeded")

        mock_openrouter = MagicMock()
        mock_openrouter.chat.completions.create.side_effect = Exception("OpenRouter error")

        # Act & Assert
        with patch("app.services.gemini_service.gemini_client", mock_gemini):
            with patch("app.services.gemini_service.openrouter_client", mock_openrouter):
                with pytest.raises(HTTPException) as exc:
                    await GeminiService.chat_with_notes(FAKE_NOTES, "¿Qué es Python?")
        assert exc.value.status_code == 429

    async def test_ambos_fallan_sin_cuota_lanza_500(self):
        # Arrange — error genérico, OpenRouter también falla
        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.side_effect = Exception("Internal error")

        mock_openrouter = MagicMock()
        mock_openrouter.chat.completions.create.side_effect = Exception("OpenRouter error")

        # Act & Assert
        with patch("app.services.gemini_service.gemini_client", mock_gemini):
            with patch("app.services.gemini_service.openrouter_client", mock_openrouter):
                with pytest.raises(HTTPException) as exc:
                    await GeminiService.chat_with_notes(FAKE_NOTES, "¿Qué es Python?")
        assert exc.value.status_code == 500

    async def test_construye_contexto_con_tags(self):
        # Arrange — verificar que los tags de las notas se incluyen en el prompt
        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.return_value = MagicMock(text="Respuesta OK")

        captured_prompt = {}

        def capture_call(**kwargs):
            captured_prompt["contents"] = kwargs.get("contents", "")
            return MagicMock(text="Respuesta OK")

        mock_gemini.models.generate_content.side_effect = capture_call

        # Act
        with patch("app.services.gemini_service.gemini_client", mock_gemini):
            await GeminiService.chat_with_notes(FAKE_NOTES, "¿Qué hay en las notas?")

        # Assert — el tag "importante" debe aparecer en el contenido enviado a Gemini
        assert "importante" in captured_prompt["contents"]

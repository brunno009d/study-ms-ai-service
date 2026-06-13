import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import HTTPException

from app.services.gemini_service import GeminiService


# ─── helpers ─────────────────────────────────────────────────────────────────

def _session(student_id="test-user"):
    return {"id": "s1", "student_id": student_id, "title": "Mi sesión"}


def _text_response(text="Aquí está tu consejo."):
    """Mock de openrouter que devuelve texto directamente (sin tool_calls)."""
    msg = MagicMock()
    msg.content = text
    msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


def _tool_response(tool_name="get_student_profile"):
    """Mock de openrouter que pide ejecutar una herramienta."""
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = tool_name
    tool_call.function.arguments = "{}"

    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tool_call]

    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


# ─── nueva sesión (sin session_id) ───────────────────────────────────────────

class TestAdvisorChatNewSession:

    async def test_crea_sesion_nueva_y_retorna_respuesta(self):
        # Arrange
        mock_repo = MagicMock()
        mock_repo.create_session = AsyncMock(return_value=_session())
        mock_repo.get_recent_messages = AsyncMock(return_value=[])
        mock_repo.add_message = AsyncMock(return_value=None)

        mock_openrouter = MagicMock()
        mock_openrouter.chat.completions.create.return_value = _text_response("Hola, soy tu consejero.")

        # Act
        with patch("app.repository.chat_repository.ChatRepository", mock_repo), \
             patch("app.services.gemini_service.openrouter_client", mock_openrouter):
            result = await GeminiService.advisor_chat(
                user_message="¿Cómo voy en mis ramos?",
                token="fake-token",
                student_id="test-user"
            )

        # Assert
        assert result["answer"] == "Hola, soy tu consejero."
        assert result["session_id"] == "s1"
        mock_repo.create_session.assert_called_once()

    async def test_titulo_de_sesion_usa_primeros_80_caracteres(self):
        # Arrange — mensaje largo
        long_message = "A" * 100
        mock_repo = MagicMock()
        mock_repo.create_session = AsyncMock(return_value=_session())
        mock_repo.get_recent_messages = AsyncMock(return_value=[])
        mock_repo.add_message = AsyncMock(return_value=None)

        mock_openrouter = MagicMock()
        mock_openrouter.chat.completions.create.return_value = _text_response()

        with patch("app.repository.chat_repository.ChatRepository", mock_repo), \
             patch("app.services.gemini_service.openrouter_client", mock_openrouter):
            await GeminiService.advisor_chat(long_message, "tok", "test-user")

        # El título debe ser los primeros 80 caracteres + "..."
        title_used = mock_repo.create_session.call_args[0][1]
        assert title_used == "A" * 80 + "..."


# ─── sesión existente (con session_id) ────────────────────────────────────────

class TestAdvisorChatExistingSession:

    async def test_continua_sesion_existente_valida(self):
        # Arrange
        mock_repo = MagicMock()
        mock_repo.get_session_by_id = AsyncMock(return_value=_session("test-user"))
        mock_repo.update_session = AsyncMock(return_value=None)
        mock_repo.get_recent_messages = AsyncMock(return_value=[
            {"role": "user", "content": "Hola"},
            {"role": "model", "content": "Hola, ¿en qué te ayudo?"}
        ])
        mock_repo.add_message = AsyncMock(return_value=None)

        mock_openrouter = MagicMock()
        mock_openrouter.chat.completions.create.return_value = _text_response("Tu siguiente paso es...")

        with patch("app.repository.chat_repository.ChatRepository", mock_repo), \
             patch("app.services.gemini_service.openrouter_client", mock_openrouter):
            result = await GeminiService.advisor_chat(
                user_message="¿Qué hago?",
                token="tok",
                student_id="test-user",
                session_id="s1"
            )

        assert result["answer"] == "Tu siguiente paso es..."
        mock_repo.get_session_by_id.assert_called_once_with("s1")
        mock_repo.update_session.assert_called_once()

    async def test_lanza_404_cuando_la_sesion_no_existe(self):
        mock_repo = MagicMock()
        mock_repo.get_session_by_id = AsyncMock(return_value=None)

        with patch("app.repository.chat_repository.ChatRepository", mock_repo):
            with pytest.raises(HTTPException) as exc:
                await GeminiService.advisor_chat("msg", "tok", "test-user", "s-inexistente")
        assert exc.value.status_code == 404

    async def test_lanza_404_cuando_la_sesion_pertenece_a_otro_usuario(self):
        mock_repo = MagicMock()
        mock_repo.get_session_by_id = AsyncMock(return_value=_session("otro-user"))

        with patch("app.repository.chat_repository.ChatRepository", mock_repo):
            with pytest.raises(HTTPException) as exc:
                await GeminiService.advisor_chat("msg", "tok", "test-user", "s1")
        assert exc.value.status_code == 404


# ─── function calling ─────────────────────────────────────────────────────────

class TestAdvisorChatFunctionCalling:

    async def test_ejecuta_herramienta_y_luego_retorna_respuesta(self):
        # Arrange — primera llamada pide tool, segunda devuelve texto
        mock_repo = MagicMock()
        mock_repo.create_session = AsyncMock(return_value=_session())
        mock_repo.get_recent_messages = AsyncMock(return_value=[])
        mock_repo.add_message = AsyncMock(return_value=None)

        mock_microservices = MagicMock()
        mock_microservices.get_user_profile = AsyncMock(return_value={"name": "Ana"})

        mock_openrouter = MagicMock()
        mock_openrouter.chat.completions.create.side_effect = [
            _tool_response("get_student_profile"),
            _text_response("Hola Ana, tu perfil está completo.")
        ]

        with patch("app.repository.chat_repository.ChatRepository", mock_repo), \
             patch("app.services.microservices_client.MicroservicesClient", mock_microservices), \
             patch("app.services.gemini_service.openrouter_client", mock_openrouter):
            result = await GeminiService.advisor_chat("¿Quién soy?", "tok", "test-user")

        # Assert
        assert "Ana" in result["answer"]
        assert "get_student_profile" in result["tools_used"]
        assert mock_openrouter.chat.completions.create.call_count == 2

    async def test_lanza_500_si_supera_5_iteraciones_sin_respuesta(self):
        # Arrange — siempre pide tool_calls, nunca da respuesta de texto
        mock_repo = MagicMock()
        mock_repo.create_session = AsyncMock(return_value=_session())
        mock_repo.get_recent_messages = AsyncMock(return_value=[])
        mock_repo.add_message = AsyncMock(return_value=None)

        mock_microservices = MagicMock()
        mock_microservices.get_user_profile = AsyncMock(return_value={})

        mock_openrouter = MagicMock()
        # Siempre devuelve tool_calls — nunca texto
        mock_openrouter.chat.completions.create.return_value = _tool_response("get_student_profile")

        with patch("app.repository.chat_repository.ChatRepository", mock_repo), \
             patch("app.services.microservices_client.MicroservicesClient", mock_microservices), \
             patch("app.services.gemini_service.openrouter_client", mock_openrouter):
            with pytest.raises(HTTPException) as exc:
                await GeminiService.advisor_chat("msg", "tok", "test-user")

        assert exc.value.status_code == 500
        assert mock_openrouter.chat.completions.create.call_count == 5

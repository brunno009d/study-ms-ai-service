import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock, MagicMock

from app.main import app
from app.api.dependencies import require_auth

FAKE_USER = "test-user-id"
AUTH = {"Authorization": "Bearer fake-token"}

# Datos mínimos válidos que satisfacen los schemas de respuesta
FAKE_SESSION = {
    "id": "s1", "student_id": FAKE_USER, "title": "Mi sesión",
    "subject_id": None, "created_at": "2026-01-01T10:00:00", "updated_at": "2026-01-01T10:00:00"
}
FAKE_MESSAGE = {
    "id": "m1", "session_id": "s1", "role": "user", "content": "Hola",
    "token_count": 1, "created_at": "2026-01-01T10:00:00"
}


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[require_auth] = lambda: FAKE_USER
    yield
    app.dependency_overrides.clear()


# ─── POST /parse-curriculum ───────────────────────────────────────────────────

class TestParseCurriculum:

    async def test_retorna_201_con_el_curriculo_extraido(self):
        # Arrange
        fake_result = {
            "curriculum": {"name": "Plan", "institution": "UNAB", "career": "Ing", "total_credits": 240, "total_semester": 10},
            "subjects": [{"name": "Cálculo", "code": "MAT101", "credits": 6, "semester_number": 1, "area_type": None, "prerequisites": []}]
        }
        with patch("app.api.routes.download_file_from_url", new=AsyncMock(return_value=(b"bytes", "application/pdf"))), \
             patch("app.api.routes.GeminiService.parse_curriculum_file", new=AsyncMock(return_value=fake_result)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post("/parse-curriculum", json={"file_url": "https://fake.supabase.co/file.pdf"}, headers=AUTH)

        assert res.status_code == 201
        assert res.json()["curriculum"]["career"] == "Ing"

    async def test_propaga_error_cuando_gemini_falla(self):
        from fastapi import HTTPException
        with patch("app.api.routes.download_file_from_url", new=AsyncMock(return_value=(b"bytes", "application/pdf"))), \
             patch("app.api.routes.GeminiService.parse_curriculum_file",
                   new=AsyncMock(side_effect=HTTPException(status_code=500, detail="Error Gemini"))):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post("/parse-curriculum", json={"file_url": "https://fake.supabase.co/file.pdf"}, headers=AUTH)

        assert res.status_code == 500


# ─── POST /chat-notes ────────────────────────────────────────────────────────

class TestChatNotes:

    async def test_retorna_200_con_la_respuesta_del_chat(self):
        # Arrange
        mock_repo = MagicMock()
        mock_repo.create_session = AsyncMock(return_value=FAKE_SESSION)
        mock_repo.add_message = AsyncMock(return_value=None)

        with patch("app.api.routes.ChatRepository", mock_repo), \
             patch("app.api.routes.NotesServiceClient.get_note_contents",
                   new=AsyncMock(return_value=[{"title": "Nota", "content_text": "Contenido"}])), \
             patch("app.api.routes.GeminiService.chat_with_notes",
                   new=AsyncMock(return_value="Aquí está el resumen.")):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post(
                    "/chat-notes",
                    json={"subject_id": 7, "message": "Resúmeme las notas"},
                    headers=AUTH
                )

        assert res.status_code == 200
        body = res.json()
        assert body["answer"] == "Aquí está el resumen."
        assert body["notes_used"] == 1

    async def test_retorna_404_cuando_el_ramo_no_tiene_notas(self):
        mock_repo = MagicMock()
        mock_repo.create_session = AsyncMock(return_value=FAKE_SESSION)
        mock_repo.add_message = AsyncMock(return_value=None)

        with patch("app.api.routes.ChatRepository", mock_repo), \
             patch("app.api.routes.NotesServiceClient.get_note_contents",
                   new=AsyncMock(return_value=[])):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post(
                    "/chat-notes",
                    json={"subject_id": 7, "message": "Resúmeme las notas"},
                    headers=AUTH
                )

        assert res.status_code == 404

    async def test_continua_sesion_existente_cuando_session_id_es_valido(self):
        mock_repo = MagicMock()
        mock_repo.get_session_by_id = AsyncMock(return_value=FAKE_SESSION)
        mock_repo.update_session = AsyncMock(return_value=None)
        mock_repo.add_message = AsyncMock(return_value=None)

        with patch("app.api.routes.ChatRepository", mock_repo), \
             patch("app.api.routes.NotesServiceClient.get_note_contents",
                   new=AsyncMock(return_value=[{"title": "N", "content_text": "X"}])), \
             patch("app.api.routes.GeminiService.chat_with_notes",
                   new=AsyncMock(return_value="Respuesta.")):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post(
                    "/chat-notes",
                    json={"subject_id": 7, "message": "Hola", "session_id": "s1"},
                    headers=AUTH
                )

        assert res.status_code == 200
        mock_repo.get_session_by_id.assert_called_once_with("s1")


# ─── POST /advisor ────────────────────────────────────────────────────────────

class TestAdvisor:

    async def test_retorna_200_con_la_respuesta_del_consejero(self):
        advisor_result = {"answer": "Mi consejo es...", "tools_used": ["get_grades"], "session_id": "s1"}
        with patch("app.api.routes.GeminiService.advisor_chat", new=AsyncMock(return_value=advisor_result)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post("/advisor", json={"message": "¿Cómo voy?"}, headers=AUTH)

        assert res.status_code == 200
        body = res.json()
        assert body["answer"] == "Mi consejo es..."
        assert body["session_id"] == "s1"


# ─── GET /sessions ────────────────────────────────────────────────────────────

class TestListSessions:

    async def test_retorna_200_con_lista_de_sesiones(self):
        mock_repo = MagicMock()
        mock_repo.get_sessions_by_student = AsyncMock(return_value=[FAKE_SESSION])

        with patch("app.api.routes.ChatRepository", mock_repo):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.get("/sessions", headers=AUTH)

        assert res.status_code == 200
        assert len(res.json()) == 1


# ─── GET /sessions/{session_id} ──────────────────────────────────────────────

class TestGetSessionDetail:

    async def test_retorna_200_con_sesion_y_mensajes(self):
        mock_repo = MagicMock()
        mock_repo.get_session_by_id = AsyncMock(return_value=FAKE_SESSION)
        mock_repo.get_messages_by_session = AsyncMock(return_value=[FAKE_MESSAGE])

        with patch("app.api.routes.ChatRepository", mock_repo):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.get("/sessions/s1", headers=AUTH)

        assert res.status_code == 200
        body = res.json()
        assert body["session"]["id"] == "s1"
        assert len(body["messages"]) == 1

    async def test_retorna_404_cuando_la_sesion_no_existe(self):
        mock_repo = MagicMock()
        mock_repo.get_session_by_id = AsyncMock(return_value=None)

        with patch("app.api.routes.ChatRepository", mock_repo):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.get("/sessions/no-existe", headers=AUTH)

        assert res.status_code == 404

    async def test_retorna_404_cuando_la_sesion_pertenece_a_otro_usuario(self):
        other_session = {**FAKE_SESSION, "student_id": "otro-user"}
        mock_repo = MagicMock()
        mock_repo.get_session_by_id = AsyncMock(return_value=other_session)

        with patch("app.api.routes.ChatRepository", mock_repo):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.get("/sessions/s1", headers=AUTH)

        assert res.status_code == 404


# ─── PATCH /sessions/{session_id} ────────────────────────────────────────────

class TestUpdateSession:

    async def test_retorna_200_con_la_sesion_actualizada(self):
        updated = {**FAKE_SESSION, "title": "Nuevo título"}
        mock_repo = MagicMock()
        mock_repo.get_session_by_id = AsyncMock(return_value=FAKE_SESSION)
        mock_repo.update_session = AsyncMock(return_value=updated)

        with patch("app.api.routes.ChatRepository", mock_repo):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.patch("/sessions/s1", json={"title": "Nuevo título"}, headers=AUTH)

        assert res.status_code == 200
        assert res.json()["title"] == "Nuevo título"

    async def test_retorna_404_cuando_la_sesion_no_le_pertenece(self):
        other_session = {**FAKE_SESSION, "student_id": "otro-user"}
        mock_repo = MagicMock()
        mock_repo.get_session_by_id = AsyncMock(return_value=other_session)

        with patch("app.api.routes.ChatRepository", mock_repo):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.patch("/sessions/s1", json={"title": "X"}, headers=AUTH)

        assert res.status_code == 404


# ─── DELETE /sessions/{session_id} ───────────────────────────────────────────

class TestDeleteSession:

    async def test_retorna_204_al_eliminar_correctamente(self):
        mock_repo = MagicMock()
        mock_repo.get_session_by_id = AsyncMock(return_value=FAKE_SESSION)
        mock_repo.delete_session = AsyncMock(return_value=True)

        with patch("app.api.routes.ChatRepository", mock_repo):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.delete("/sessions/s1", headers=AUTH)

        assert res.status_code == 204
        mock_repo.delete_session.assert_called_once_with("s1")

    async def test_retorna_404_cuando_la_sesion_no_le_pertenece(self):
        other_session = {**FAKE_SESSION, "student_id": "otro-user"}
        mock_repo = MagicMock()
        mock_repo.get_session_by_id = AsyncMock(return_value=other_session)

        with patch("app.api.routes.ChatRepository", mock_repo):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.delete("/sessions/s1", headers=AUTH)

        assert res.status_code == 404

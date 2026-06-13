import pytest
from unittest.mock import patch, MagicMock

from app.repository.chat_repository import ChatRepository


def _chain(data):
    """Mock de supabase_client con métodos encadenados — execute() retorna data."""
    m = MagicMock()
    for method in ['from_', 'select', 'insert', 'update', 'delete',
                   'eq', 'is_', 'in_', 'order', 'limit', 'maybe_single']:
        getattr(m, method).return_value = m
    m.execute.return_value = MagicMock(data=data)
    return m


# ─── create_session ───────────────────────────────────────────────────────────

class TestCreateSession:

    async def test_crea_sesion_sin_subject_id(self):
        # Arrange
        row = {"id": "s1", "student_id": "u1", "title": "Mi sesión"}
        mock_sb = _chain([row])
        # Act
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.create_session("u1", "Mi sesión")
        # Assert
        assert result == row
        mock_sb.insert.assert_called_once()

    async def test_crea_sesion_con_subject_id(self):
        # Arrange — RAG session con subject_id
        row = {"id": "s2", "student_id": "u1", "subject_id": 7}
        mock_sb = _chain([row])
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.create_session("u1", "RAG", subject_id=7)
        assert result == row

    async def test_retorna_none_cuando_supabase_no_devuelve_data(self):
        mock_sb = _chain([])
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.create_session("u1")
        assert result is None


# ─── get_sessions_by_student ──────────────────────────────────────────────────

class TestGetSessionsByStudent:

    async def test_retorna_lista_de_sesiones(self):
        rows = [{"id": "s1"}, {"id": "s2"}]
        mock_sb = _chain(rows)
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.get_sessions_by_student("u1")
        assert result == rows

    async def test_retorna_lista_vacia_cuando_data_es_none(self):
        mock_sb = _chain(None)
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.get_sessions_by_student("u1")
        assert result == []


# ─── get_session_by_id ────────────────────────────────────────────────────────

class TestGetSessionById:

    async def test_retorna_la_sesion_cuando_existe(self):
        row = {"id": "s1", "student_id": "u1"}
        mock_sb = _chain(row)
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.get_session_by_id("s1")
        assert result == row

    async def test_retorna_none_cuando_no_existe(self):
        mock_sb = _chain(None)
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.get_session_by_id("no-existe")
        assert result is None


# ─── update_session ───────────────────────────────────────────────────────────

class TestUpdateSession:

    async def test_agrega_updated_at_automaticamente(self):
        # Arrange
        updated_row = {"id": "s1", "title": "Nuevo"}
        mock_sb = _chain([updated_row])
        captured_updates = {}

        def capture_update(updates):
            captured_updates.update(updates)
            return mock_sb

        mock_sb.update.side_effect = capture_update

        # Act
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.update_session("s1", {"title": "Nuevo"})

        # Assert — updated_at fue agregado automáticamente
        assert "updated_at" in captured_updates
        assert result == updated_row

    async def test_retorna_none_cuando_no_hay_data(self):
        mock_sb = _chain([])
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.update_session("s1", {})
        assert result is None


# ─── delete_session ───────────────────────────────────────────────────────────

class TestDeleteSession:

    async def test_elimina_la_sesion_y_retorna_true(self):
        mock_sb = _chain(None)
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.delete_session("s1")
        assert result is True
        mock_sb.delete.assert_called_once()


# ─── add_message ─────────────────────────────────────────────────────────────

class TestAddMessage:

    async def test_inserta_mensaje_y_retorna_el_registro(self):
        # Arrange
        row = {"id": "m1", "session_id": "s1", "role": "user", "content": "Hola"}
        mock_sb = _chain([row])
        # Act
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.add_message("s1", "user", "Hola")
        # Assert
        assert result == row
        call_data = mock_sb.insert.call_args[0][0]
        assert call_data["session_id"] == "s1"
        assert call_data["role"] == "user"
        assert call_data["content"] == "Hola"
        assert "token_count" in call_data


# ─── get_recent_messages ──────────────────────────────────────────────────────

class TestGetRecentMessages:

    async def test_invierte_el_orden_cronologico_de_supabase(self):
        # Arrange — Supabase devuelve DESC (más reciente primero)
        rows_desc = [
            {"role": "model", "content": "Respuesta", "created_at": "2026-01-02"},
            {"role": "user",  "content": "Pregunta",  "created_at": "2026-01-01"},
        ]
        mock_sb = _chain(rows_desc)
        # Act
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.get_recent_messages("s1")
        # Assert — debe quedar en orden cronológico (ASC)
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "model"

    async def test_retorna_lista_vacia_cuando_no_hay_mensajes(self):
        mock_sb = _chain(None)
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            result = await ChatRepository.get_recent_messages("s1")
        assert result == []

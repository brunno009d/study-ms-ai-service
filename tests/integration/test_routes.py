import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock, MagicMock

from app.main import app
from app.api.dependencies import require_auth
from app.services.notes_client import NotesServiceClient

FAKE_USER = "test-user-id"
AUTH = {"Authorization": "Bearer fake-token"}

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


@pytest.fixture(autouse=True)
def reset_notes_client():
    """Restaura el cliente HTTP singleton de NotesServiceClient entre tests."""
    original = NotesServiceClient._client
    yield
    NotesServiceClient._client = original


def make_sb_chain(data):
    """
    Construye la cadena supabase_client.from_(...).xxx.execute() → MagicMock(data=data).
    Todos los métodos encadenados retornan el mismo objeto para soportar
    cualquier combinación de: select, insert, update, delete, eq, is_, order,
    maybe_single, limit, in_.
    """
    result = MagicMock()
    result.data = data

    chain = MagicMock()
    chain.execute.return_value = result
    for method in ["insert", "select", "update", "delete",
                   "eq", "is_", "order", "maybe_single", "limit", "in_"]:
        getattr(chain, method).return_value = chain

    return chain


# ─── POST /parse-curriculum ───────────────────────────────────────────────────

class TestParseCurriculum:

    async def test_retorna_201_con_el_curriculo_extraido(self):
        # Arrange — httpx descarga el PDF, gemini_client lo procesa
        # La cadena real route → pdf_service → httpx y route → GeminiService → gemini_client
        # se ejerce completa; solo los clientes externos están mockeados.
        fake_curriculum = {
            "curriculum": {
                "name": "Plan 2024", "institution": "UNAB", "career": "Ingeniería",
                "total_credits": 240, "total_semester": 10,
            },
            "subjects": [{
                "name": "Cálculo", "code": "MAT101", "credits": 6,
                "semester_number": 1, "area_type": None, "prerequisites": [],
            }],
        }

        # Mock httpx (pdf_service usa `async with httpx.AsyncClient() as client`)
        mock_http_response = MagicMock()
        mock_http_response.headers = {"content-type": "application/pdf"}
        mock_http_response.content = b"fake-pdf-bytes"
        mock_http_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_http_response)

        mock_http_cls = MagicMock()
        mock_http_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock gemini_client (GeminiService lo importa de app.core.config)
        mock_uploaded_file = MagicMock()
        mock_uploaded_file.name = "files/fake-123"   # name debe setearse por separado
        mock_uploaded_file.uri = "https://generativelanguage.googleapis.com/fake"

        mock_parsed = MagicMock()
        mock_parsed.model_dump.return_value = fake_curriculum

        mock_gemini_response = MagicMock()
        mock_gemini_response.parsed = mock_parsed

        mock_gemini = MagicMock()
        mock_gemini.files.upload.return_value = mock_uploaded_file
        mock_gemini.models.generate_content.return_value = mock_gemini_response

        # Act — settings.SUPABASE_URL se parchea a "" para que la validación de URL
        # en pdf_service pase sin depender del valor real del .env
        with patch("app.services.pdf_service.httpx.AsyncClient", mock_http_cls), \
             patch("app.services.gemini_service.gemini_client", mock_gemini), \
             patch("app.services.pdf_service.settings") as mock_settings:
            mock_settings.SUPABASE_URL = ""
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post(
                    "/parse-curriculum",
                    json={"file_url": "https://fake.supabase.co/file.pdf"},
                    headers=AUTH,
                )

        # Assert
        assert res.status_code == 201
        body = res.json()
        assert body["curriculum"]["career"] == "Ingeniería"
        assert len(body["subjects"]) == 1
        # La cadena real GeminiService → gemini_client se ejerció
        mock_gemini.files.upload.assert_called_once()
        mock_gemini.models.generate_content.assert_called_once()

    async def test_url_sin_https_retorna_400_sin_llamar_a_gemini(self):
        # Arrange — URL sin HTTPS; pdf_service rechaza antes de cualquier llamada externa
        mock_gemini = MagicMock()

        # Act
        with patch("app.services.gemini_service.gemini_client", mock_gemini):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post(
                    "/parse-curriculum",
                    json={"file_url": "http://sin-https.com/file.pdf"},
                    headers=AUTH,
                )

        # Assert — validación en pdf_service, no llega a GeminiService
        assert res.status_code == 400
        mock_gemini.files.upload.assert_not_called()
        mock_gemini.models.generate_content.assert_not_called()

    async def test_propaga_500_cuando_gemini_no_puede_parsear_el_archivo(self):
        # Arrange — gemini devuelve response.parsed = None (archivo no reconocido)
        mock_http_response = MagicMock()
        mock_http_response.headers = {"content-type": "application/pdf"}
        mock_http_response.content = b"fake-pdf-bytes"
        mock_http_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_http_response)

        mock_http_cls = MagicMock()
        mock_http_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_uploaded_file = MagicMock()
        mock_uploaded_file.name = "files/fake-123"
        mock_uploaded_file.uri = "https://fake-uri"

        mock_gemini_response = MagicMock()
        mock_gemini_response.parsed = None   # Gemini no pudo extraer datos estructurados

        mock_gemini = MagicMock()
        mock_gemini.files.upload.return_value = mock_uploaded_file
        mock_gemini.models.generate_content.return_value = mock_gemini_response

        # Act
        with patch("app.services.pdf_service.httpx.AsyncClient", mock_http_cls), \
             patch("app.services.gemini_service.gemini_client", mock_gemini), \
             patch("app.services.pdf_service.settings") as mock_settings:
            mock_settings.SUPABASE_URL = ""
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post(
                    "/parse-curriculum",
                    json={"file_url": "https://fake.supabase.co/file.pdf"},
                    headers=AUTH,
                )

        # Assert — GeminiService detecta parsed=None y lanza HTTPException(500)
        assert res.status_code == 500
        mock_gemini.models.generate_content.assert_called_once()


# ─── POST /chat-notes ────────────────────────────────────────────────────────

class TestChatNotes:

    async def test_retorna_200_con_la_respuesta_del_chat(self):
        # Arrange — nueva sesión, notas disponibles, gemini responde
        # cadena real: route → ChatRepository → supabase_client
        #              route → NotesServiceClient → httpx
        #              route → GeminiService → gemini_client
        def sb_from_factory(table):
            if table == "chat_sessions":
                return make_sb_chain([FAKE_SESSION])   # create_session → data[0]
            return make_sb_chain([FAKE_MESSAGE])        # add_message (×2) → data[0]

        mock_sb = MagicMock()
        mock_sb.from_.side_effect = sb_from_factory

        # NotesServiceClient usa un singleton httpx; lo sustituimos directamente
        mock_notes_http = AsyncMock()
        mock_notes_http.is_closed = False
        mock_notes_response = MagicMock()
        mock_notes_response.json.return_value = [
            {"title": "Nota 1", "content_text": "Contenido de la nota"}
        ]
        mock_notes_response.raise_for_status = MagicMock()
        mock_notes_http.get = AsyncMock(return_value=mock_notes_response)
        NotesServiceClient._client = mock_notes_http

        mock_gemini_response = MagicMock()
        mock_gemini_response.text = "Este es el resumen de tus notas."
        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.return_value = mock_gemini_response

        # Act
        with patch("app.repository.chat_repository.supabase_client", mock_sb), \
             patch("app.services.gemini_service.gemini_client", mock_gemini):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post(
                    "/chat-notes",
                    json={"subject_id": 7, "message": "Resúmeme las notas"},
                    headers=AUTH,
                )

        # Assert
        assert res.status_code == 200
        body = res.json()
        assert body["answer"] == "Este es el resumen de tus notas."
        assert body["notes_used"] == 1
        # ChatRepository tocó Supabase real (no fue bypaseado)
        mock_sb.from_.assert_called()
        # GeminiService.chat_with_notes llamó a gemini_client real
        mock_gemini.models.generate_content.assert_called_once()

    async def test_retorna_404_cuando_el_ramo_no_tiene_notas(self):
        # Arrange — supabase crea la sesión, notes_client retorna lista vacía
        def sb_from_factory(table):
            if table == "chat_sessions":
                return make_sb_chain([FAKE_SESSION])
            return make_sb_chain([FAKE_MESSAGE])

        mock_sb = MagicMock()
        mock_sb.from_.side_effect = sb_from_factory

        mock_notes_http = AsyncMock()
        mock_notes_http.is_closed = False
        mock_notes_response = MagicMock()
        mock_notes_response.json.return_value = []   # sin notas
        mock_notes_response.raise_for_status = MagicMock()
        mock_notes_http.get = AsyncMock(return_value=mock_notes_response)
        NotesServiceClient._client = mock_notes_http

        mock_gemini = MagicMock()

        # Act
        with patch("app.repository.chat_repository.supabase_client", mock_sb), \
             patch("app.services.gemini_service.gemini_client", mock_gemini):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post(
                    "/chat-notes",
                    json={"subject_id": 7, "message": "Resúmeme las notas"},
                    headers=AUTH,
                )

        # Assert — el route detecta notas vacías y retorna 404 sin llamar a gemini
        assert res.status_code == 404
        mock_gemini.models.generate_content.assert_not_called()

    async def test_continua_sesion_existente_cuando_session_id_es_valido(self):
        # Arrange — sesión ya existe (route la busca y actualiza en lugar de crear)
        session_call_count = [0]

        def sb_from_factory(table):
            if table == "chat_sessions":
                session_call_count[0] += 1
                if session_call_count[0] == 1:
                    return make_sb_chain(FAKE_SESSION)   # get_session_by_id → dict
                return make_sb_chain([FAKE_SESSION])      # update_session → lista
            return make_sb_chain([FAKE_MESSAGE])

        mock_sb = MagicMock()
        mock_sb.from_.side_effect = sb_from_factory

        mock_notes_http = AsyncMock()
        mock_notes_http.is_closed = False
        mock_notes_response = MagicMock()
        mock_notes_response.json.return_value = [{"title": "N", "content_text": "X"}]
        mock_notes_response.raise_for_status = MagicMock()
        mock_notes_http.get = AsyncMock(return_value=mock_notes_response)
        NotesServiceClient._client = mock_notes_http

        mock_gemini_response = MagicMock()
        mock_gemini_response.text = "Respuesta continuada."
        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.return_value = mock_gemini_response

        # Act
        with patch("app.repository.chat_repository.supabase_client", mock_sb), \
             patch("app.services.gemini_service.gemini_client", mock_gemini):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post(
                    "/chat-notes",
                    json={"subject_id": 7, "message": "Hola", "session_id": "s1"},
                    headers=AUTH,
                )

        # Assert — la sesión existente fue usada (get_session_by_id llamado)
        assert res.status_code == 200
        assert session_call_count[0] >= 1


# ─── POST /advisor ────────────────────────────────────────────────────────────

class TestAdvisor:

    async def test_retorna_200_con_la_respuesta_del_consejero(self):
        # Arrange — nueva sesión, openrouter responde directamente sin tool_calls
        # cadena real: route → GeminiService.advisor_chat → ChatRepository → supabase_client
        #              route → GeminiService.advisor_chat → openrouter_client
        messages_call_count = [0]

        def sb_from_factory(table):
            if table == "chat_sessions":
                return make_sb_chain([FAKE_SESSION])   # create_session
            if table == "chat_messages":
                messages_call_count[0] += 1
                if messages_call_count[0] == 1:
                    return make_sb_chain([])             # get_recent_messages → historial vacío
                return make_sb_chain([FAKE_MESSAGE])     # add_message (user + model)
            return make_sb_chain([])

        mock_sb = MagicMock()
        mock_sb.from_.side_effect = sb_from_factory

        # OpenRouter responde con texto final (sin tool_calls)
        mock_or_message = MagicMock()
        mock_or_message.content = "Mi consejo académico es estudiar más Cálculo."
        mock_or_message.tool_calls = None

        mock_or_choice = MagicMock()
        mock_or_choice.message = mock_or_message

        mock_or_response = MagicMock()
        mock_or_response.choices = [mock_or_choice]

        mock_or = MagicMock()
        mock_or.chat.completions.create.return_value = mock_or_response

        # Act
        with patch("app.repository.chat_repository.supabase_client", mock_sb), \
             patch("app.services.gemini_service.openrouter_client", mock_or):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post(
                    "/advisor",
                    json={"message": "¿Cómo voy en la carrera?"},
                    headers=AUTH,
                )

        # Assert
        assert res.status_code == 200
        body = res.json()
        assert body["answer"] == "Mi consejo académico es estudiar más Cálculo."
        # ChatRepository usó Supabase real (no fue bypaseado)
        mock_sb.from_.assert_called()
        mock_or.chat.completions.create.assert_called_once()


# ─── GET /sessions ────────────────────────────────────────────────────────────

class TestListSessions:

    async def test_retorna_200_con_lista_de_sesiones(self):
        mock_sb = MagicMock()
        mock_sb.from_.return_value = make_sb_chain([FAKE_SESSION])

        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.get("/sessions", headers=AUTH)

        assert res.status_code == 200
        assert len(res.json()) == 1
        mock_sb.from_.assert_called_with("chat_sessions")


# ─── GET /sessions/{session_id} ──────────────────────────────────────────────

class TestGetSessionDetail:

    async def test_retorna_200_con_sesion_y_mensajes(self):
        def sb_from_factory(table):
            if table == "chat_sessions":
                return make_sb_chain(FAKE_SESSION)    # maybe_single → dict
            return make_sb_chain([FAKE_MESSAGE])       # select → lista

        mock_sb = MagicMock()
        mock_sb.from_.side_effect = sb_from_factory

        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.get("/sessions/s1", headers=AUTH)

        assert res.status_code == 200
        body = res.json()
        assert body["session"]["id"] == "s1"
        assert len(body["messages"]) == 1

    async def test_retorna_404_cuando_la_sesion_no_existe(self):
        mock_sb = MagicMock()
        mock_sb.from_.return_value = make_sb_chain(None)   # maybe_single → None

        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.get("/sessions/no-existe", headers=AUTH)

        assert res.status_code == 404

    async def test_retorna_404_cuando_la_sesion_pertenece_a_otro_usuario(self):
        other_session = {**FAKE_SESSION, "student_id": "otro-user"}
        mock_sb = MagicMock()
        mock_sb.from_.return_value = make_sb_chain(other_session)

        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.get("/sessions/s1", headers=AUTH)

        assert res.status_code == 404


# ─── PATCH /sessions/{session_id} ────────────────────────────────────────────

class TestUpdateSession:

    async def test_retorna_200_con_la_sesion_actualizada(self):
        updated = {**FAKE_SESSION, "title": "Nuevo título"}
        session_call_count = [0]

        def sb_from_factory(table):
            if table == "chat_sessions":
                session_call_count[0] += 1
                if session_call_count[0] == 1:
                    return make_sb_chain(FAKE_SESSION)   # get_session_by_id → dict
                return make_sb_chain([updated])           # update_session → lista

        mock_sb = MagicMock()
        mock_sb.from_.side_effect = sb_from_factory

        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.patch("/sessions/s1", json={"title": "Nuevo título"}, headers=AUTH)

        assert res.status_code == 200
        assert res.json()["title"] == "Nuevo título"

    async def test_retorna_404_cuando_la_sesion_no_le_pertenece(self):
        other_session = {**FAKE_SESSION, "student_id": "otro-user"}
        mock_sb = MagicMock()
        mock_sb.from_.return_value = make_sb_chain(other_session)

        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.patch("/sessions/s1", json={"title": "X"}, headers=AUTH)

        assert res.status_code == 404


# ─── DELETE /sessions/{session_id} ───────────────────────────────────────────

class TestDeleteSession:

    async def test_retorna_204_al_eliminar_correctamente(self):
        session_call_count = [0]

        def sb_from_factory(table):
            if table == "chat_sessions":
                session_call_count[0] += 1
                if session_call_count[0] == 1:
                    return make_sb_chain(FAKE_SESSION)   # get_session_by_id
                return make_sb_chain([])                  # delete

        mock_sb = MagicMock()
        mock_sb.from_.side_effect = sb_from_factory

        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.delete("/sessions/s1", headers=AUTH)

        assert res.status_code == 204

    async def test_retorna_404_cuando_la_sesion_no_le_pertenece(self):
        other_session = {**FAKE_SESSION, "student_id": "otro-user"}
        mock_sb = MagicMock()
        mock_sb.from_.return_value = make_sb_chain(other_session)

        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.delete("/sessions/s1", headers=AUTH)

        assert res.status_code == 404

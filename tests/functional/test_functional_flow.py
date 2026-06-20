import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4
from datetime import datetime

from app.main import app
from app.api.dependencies import require_auth
from app.services.notes_client import NotesServiceClient

FAKE_USER = "functional-test-user"
AUTH = {"Authorization": "Bearer fake-token"}

@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[require_auth] = lambda: FAKE_USER
    yield
    app.dependency_overrides.clear()

@pytest.fixture(autouse=True)
def reset_notes_client():
    original = NotesServiceClient._client
    yield
    NotesServiceClient._client = original

class StatefulSupabaseMock:
    def __init__(self):
        self.db = {
            "chat_sessions": [],
            "chat_messages": []
        }
        # Variables to store current query state
        self._table = None
        self._action = None
        self._data = None
        self._filters = {}
        self._order = []
        self._limit = None

    def _reset_query(self):
        self._action = None
        self._data = None
        self._filters = {}
        self._order = []
        self._limit = None

    def from_(self, table_name):
        self._table = table_name
        self._reset_query()
        return self

    def insert(self, data):
        self._action = "insert"
        self._data = data
        return self

    def select(self, cols="*"):
        self._action = "select"
        return self

    def update(self, data):
        self._action = "update"
        self._data = data
        return self

    def delete(self):
        self._action = "delete"
        return self

    def eq(self, column, value):
        self._filters[column] = {"op": "eq", "val": value}
        return self

    def is_(self, column, value):
        self._filters[column] = {"op": "is", "val": value}
        return self

    def in_(self, column, values):
        self._filters[column] = {"op": "in", "val": values}
        return self

    def order(self, column, desc=False):
        self._order.append({"column": column, "desc": desc})
        return self

    def limit(self, limit):
        self._limit = limit
        return self

    def maybe_single(self):
        self._limit = 1
        return self

    def execute(self):
        result = MagicMock()
        table_data = self.db.get(self._table, [])

        if self._action == "insert":
            if isinstance(self._data, dict):
                record = {**self._data}
                if "id" not in record:
                    record["id"] = str(uuid4())
                if "created_at" not in record:
                    record["created_at"] = datetime.now().isoformat()
                if "updated_at" not in record:
                    record["updated_at"] = datetime.now().isoformat()
                table_data.append(record)
                result.data = [record]
            elif isinstance(self._data, list):
                # Omit for simplicity, we mostly insert dicts
                pass

        elif self._action == "select":
            filtered = []
            for row in table_data:
                match = True
                for col, f in self._filters.items():
                    if f["op"] == "eq" and row.get(col) != f["val"]: match = False
                    elif f["op"] == "is":
                        if f["val"] == "null" and row.get(col) is not None: match = False
                        if f["val"] != "null" and str(row.get(col)).lower() != str(f["val"]).lower(): match = False
                    elif f["op"] == "in" and row.get(col) not in f["val"]: match = False
                if match:
                    filtered.append(row)
            
            # Ordenamiento simple por string
            for o in reversed(self._order):
                col = o["column"]
                filtered.sort(key=lambda x: x.get(col, ""), reverse=o["desc"])
            
            if self._limit is not None:
                filtered = filtered[:self._limit]
                
            if getattr(self, "_limit", None) == 1:
                result.data = filtered[0] if filtered else None
            else:
                result.data = filtered

        elif self._action == "update":
            updated = []
            for row in table_data:
                match = True
                for col, f in self._filters.items():
                    if f["op"] == "eq" and row.get(col) != f["val"]: match = False
                if match:
                    row.update(self._data)
                    updated.append(row)
            result.data = updated

        elif self._action == "delete":
            kept = []
            for row in table_data:
                match = True
                for col, f in self._filters.items():
                    if f["op"] == "eq" and row.get(col) != f["val"]: match = False
                if not match:
                    kept.append(row)
            self.db[self._table] = kept
            result.data = []

        return result

@pytest.mark.asyncio
async def test_flujo_chat_advisor_completo():
    db_mock = StatefulSupabaseMock()
    
    # Mock Gemini Service para devolver respuestas
    mock_or_message = MagicMock()
    mock_or_message.content = "Respuesta del Advisor Funcional"
    mock_or_message.tool_calls = None
    mock_or_choice = MagicMock()
    mock_or_choice.message = mock_or_message
    mock_or_response = MagicMock()
    mock_or_response.choices = [mock_or_choice]
    
    mock_or = MagicMock()
    mock_or.chat.completions.create.return_value = mock_or_response

    with patch("app.repository.chat_repository.supabase_client", db_mock), \
         patch("app.services.gemini_service.openrouter_client", mock_or):
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # 1. Crear sesión a través de enviar el primer mensaje
            res_chat = await ac.post("/advisor", json={"message": "Hola, necesito ayuda"}, headers=AUTH)
            assert res_chat.status_code == 200
            session_id = res_chat.json()["session_id"]
            assert session_id is not None
            assert res_chat.json()["answer"] == "Respuesta del Advisor Funcional"
            
            # Verificar DB state
            assert len(db_mock.db["chat_sessions"]) == 1
            assert len(db_mock.db["chat_messages"]) == 2 # 1 user, 1 model
            
            # 2. Consultar lista de sesiones
            res_list = await ac.get("/sessions", headers=AUTH)
            assert res_list.status_code == 200
            assert len(res_list.json()) == 1
            assert res_list.json()[0]["id"] == session_id
            
            # 3. Consultar la sesión en detalle
            res_detail = await ac.get(f"/sessions/{session_id}", headers=AUTH)
            assert res_detail.status_code == 200
            detail = res_detail.json()
            assert detail["session"]["id"] == session_id
            assert len(detail["messages"]) == 2
            
            # 4. Actualizar título de la sesión
            res_patch = await ac.patch(f"/sessions/{session_id}", json={"title": "Chat Funcional"}, headers=AUTH)
            assert res_patch.status_code == 200
            assert res_patch.json()["title"] == "Chat Funcional"
            
            # Verificar el cambio persistido
            assert db_mock.db["chat_sessions"][0]["title"] == "Chat Funcional"
            
            # 5. Enviar un segundo mensaje a la misma sesión
            res_chat2 = await ac.post("/advisor", json={"message": "Otra pregunta", "session_id": session_id}, headers=AUTH)
            assert res_chat2.status_code == 200
            assert res_chat2.json()["session_id"] == session_id
            
            # Verificar BD (deberían haber 4 mensajes ahora)
            assert len(db_mock.db["chat_messages"]) == 4
            
            # 6. Eliminar la sesión
            res_delete = await ac.delete(f"/sessions/{session_id}", headers=AUTH)
            assert res_delete.status_code == 204
            
            # Verificar BD (la sesión debe desaparecer)
            assert len(db_mock.db["chat_sessions"]) == 0

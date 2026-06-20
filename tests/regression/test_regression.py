import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock, AsyncMock

from app.main import app
from app.api.dependencies import require_auth

AUTH = {"Authorization": "Bearer fake"}

@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[require_auth] = lambda: "user123"
    yield
    app.dependency_overrides.clear()

class TestRegressionAI:
    """
    Pruebas de regresión para asegurar que bugs previamente corregidos no vuelvan a aparecer.
    """

    @pytest.mark.asyncio
    async def test_BUG_AI_001_parse_curriculum_valida_https_sin_crashear(self):
        # BUG-AI-001: El servicio intentaba descargar cualquier URL (incluyendo ftp:// o http://) 
        # y causaba un crash (HTTP 500) en el pdf_service al fallar la conexión.
        # Corrección: Se agregó validación para aceptar solo archivos del almacenamiento oficial de Supabase.
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post("/parse-curriculum", json={"file_url": "http://insecure.com/file.pdf"}, headers=AUTH)
            
        assert res.status_code == 400
        assert "almacenamiento oficial de Supabase" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_BUG_AI_002_advisor_chat_no_debe_crear_sesion_con_id_inexistente(self):
        # BUG-AI-002: Si se enviaba un session_id inventado, el sistema intentaba recuperar 
        # una sesión nula y arrojaba un TypeError (500).
        # Corrección: Se agregó verificación que devuelve 404 si el session_id no se encuentra.
        
        mock_sb = MagicMock()
        mock_sb.from_().select().eq().maybe_single().execute.return_value = MagicMock(data=None)
        
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post("/advisor", json={"message": "Hola", "session_id": "inventado-999"}, headers=AUTH)
                
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_BUG_AI_003_get_session_detail_retorna_404_en_lugar_de_500(self):
        # BUG-AI-003: Al consultar el detalle de una sesión inexistente, fallaba al intentar 
        # acceder a session["student_id"] sobre un NoneType.
        # Corrección: Manejo explícito de "if not session:" para retornar 404.
        
        mock_sb = MagicMock()
        mock_sb.from_().select().eq().maybe_single().execute.return_value = MagicMock(data=None)
        
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.get("/sessions/borrada-000", headers=AUTH)
                
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_BUG_AI_004_delete_session_valida_propietario(self):
        # BUG-AI-004: Un usuario podía eliminar sesiones de otros usuarios simplemente 
        # enviando su session_id.
        # Corrección: get_session_by_id recupera la sesión y se verifica session["student_id"] == user_id.
        
        mock_session_de_otro = {
            "id": "s1",
            "student_id": "otro-usuario",
            "title": "Hackeable"
        }
        
        mock_sb = MagicMock()
        mock_sb.from_().select().eq().maybe_single().execute.return_value = MagicMock(data=mock_session_de_otro)
        
        with patch("app.repository.chat_repository.supabase_client", mock_sb):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.delete("/sessions/s1", headers=AUTH)
                
        # Como override_auth define al usuario como "user123", esto debe arrojar 404 
        # (por seguridad se oculta la existencia de la sesión).
        assert res.status_code == 404

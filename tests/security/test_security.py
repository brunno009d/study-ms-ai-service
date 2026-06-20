import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock, AsyncMock

from app.main import app
from app.api.dependencies import require_auth

# Mock para bypasear la autenticación en los test que SÍ necesitan auth,
# pero en este archivo queremos probar fallos de auth también.
# Por tanto, no usamos un fixture global de auth override.

@pytest.mark.asyncio
async def test_seguridad_sin_token_retorna_403():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/advisor", json={"message": "Hola"})
    # HTTPBearer o la capa de seguridad retorna 401 o 403
    assert res.status_code in [401, 403]

@pytest.mark.asyncio
async def test_seguridad_token_invalido_retorna_401():
    mock_sb = MagicMock()
    # auth.get_user levanta una excepcion si el token no es válido
    mock_sb.auth.get_user.side_effect = Exception("Invalid token")
    
    with patch("app.api.dependencies.supabase_client", mock_sb):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post("/advisor", json={"message": "Hola"}, headers={"Authorization": "Bearer BAD_TOKEN"})
        
    assert res.status_code == 401

@pytest.mark.asyncio
async def test_seguridad_payload_masivo_no_causa_500():
    # Bypass auth para probar el payload
    app.dependency_overrides[require_auth] = lambda: "user123"
    
    massive_string = "A" * 1000000  # 1 MB de string
    
    # Mockear Gemini para que simplemente responda si es que llega
    mock_gemini = AsyncMock(return_value={"answer": "Too long", "session_id": "s1", "tools_used": []})
    
    with patch("app.api.routes.GeminiService.advisor_chat", mock_gemini):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post("/advisor", json={"message": massive_string}, headers={"Authorization": "Bearer fake"})
            
    # Dependiendo de si hay un límite en Pydantic o en FastAPI, 
    # retornará 200, 413, o 422, pero NO un 500 (Server Error)
    assert res.status_code != 500
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_seguridad_xss_injection_no_causa_error():
    app.dependency_overrides[require_auth] = lambda: "user123"
    
    xss_string = "<script>alert('xss')</script> SELECT * FROM users;"
    
    mock_gemini = AsyncMock(return_value={"answer": "OK", "session_id": "s1", "tools_used": []})
    
    with patch("app.api.routes.GeminiService.advisor_chat", mock_gemini):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post("/advisor", json={"message": xss_string}, headers={"Authorization": "Bearer fake"})
            
    # Debe ser capaz de manejar strings maliciosos sin chocar (escapará/sanitizará a nivel de DB o Prompt)
    assert res.status_code == 200
    
    app.dependency_overrides.clear()

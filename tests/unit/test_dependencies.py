import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from app.api.dependencies import require_auth

@pytest.fixture
def credentials():
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid_token")

@pytest.mark.asyncio
@patch("app.api.dependencies.supabase_client")
async def test_require_auth_success(mock_supabase, credentials):
    mock_response = MagicMock()
    mock_response.user.id = "user_123"
    mock_supabase.auth.get_user.return_value = mock_response

    user_id = await require_auth(credentials)
    assert user_id == "user_123"
    mock_supabase.auth.get_user.assert_called_once_with("valid_token")

@pytest.mark.asyncio
@patch("app.api.dependencies.supabase_client")
async def test_require_auth_invalid_token_no_response(mock_supabase, credentials):
    mock_supabase.auth.get_user.return_value = None

    with pytest.raises(HTTPException) as exc:
        await require_auth(credentials)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token inválido o expirado"

@pytest.mark.asyncio
@patch("app.api.dependencies.supabase_client")
async def test_require_auth_invalid_token_no_user(mock_supabase, credentials):
    mock_response = MagicMock()
    mock_response.user = None
    mock_supabase.auth.get_user.return_value = mock_response

    with pytest.raises(HTTPException) as exc:
        await require_auth(credentials)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token inválido o expirado"

@pytest.mark.asyncio
@patch("app.api.dependencies.supabase_client")
async def test_require_auth_exception(mock_supabase, credentials):
    mock_supabase.auth.get_user.side_effect = Exception("Supabase Error")

    with pytest.raises(HTTPException) as exc:
        await require_auth(credentials)
    assert exc.value.status_code == 401
    assert "No autorizado: Supabase Error" in exc.value.detail

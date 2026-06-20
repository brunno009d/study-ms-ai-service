import pytest
from unittest.mock import patch, MagicMock
import httpx
from app.services.microservices_client import MicroservicesClient
from app.core.config import settings

@pytest.fixture(autouse=True)
def reset_client():
    MicroservicesClient._client = None
    yield
    MicroservicesClient._client = None

@pytest.mark.asyncio
async def test_get_client():
    client1 = MicroservicesClient._get_client()
    assert isinstance(client1, httpx.AsyncClient)
    client2 = MicroservicesClient._get_client()
    assert client1 is client2

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_fetch_success(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": "test"}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    result = await MicroservicesClient._fetch("http://test.com", "token123")
    assert result == {"data": "test"}
    mock_get.assert_called_once()

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_fetch_timeout(mock_get):
    mock_get.side_effect = httpx.TimeoutException("Timeout")
    result = await MicroservicesClient._fetch("http://test.com", "token")
    assert result is None

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_fetch_connect_error(mock_get):
    mock_get.side_effect = httpx.ConnectError("Error")
    result = await MicroservicesClient._fetch("http://test.com", "token")
    assert result is None

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_fetch_http_status_error(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_get.side_effect = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)
    result = await MicroservicesClient._fetch("http://test.com", "token")
    assert result is None

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_fetch_unexpected_error(mock_get):
    mock_get.side_effect = Exception("Unexpected")
    result = await MicroservicesClient._fetch("http://test.com", "token")
    assert result is None

@pytest.mark.asyncio
@patch("app.services.microservices_client.MicroservicesClient._fetch")
async def test_endpoints(mock_fetch):
    mock_fetch.return_value = {"status": "ok"}
    token = "test_token"
    
    await MicroservicesClient.get_user_profile(token)
    mock_fetch.assert_called_with(f"{settings.USER_SERVICE_URL}/ai-context", token)

    await MicroservicesClient.get_curriculum(token)
    mock_fetch.assert_called_with(f"{settings.CURRICULUM_SERVICE_URL}/ai-context", token)

    await MicroservicesClient.get_grades(token)
    mock_fetch.assert_called_with(f"{settings.GRADES_SERVICE_URL}/ai-context", token)

    await MicroservicesClient.get_calendar(token)
    mock_fetch.assert_called_with(f"{settings.CALENDAR_SERVICE_URL}/ai-context", token)

    await MicroservicesClient.get_notes(token)
    mock_fetch.assert_called_with(f"{settings.NOTES_SERVICE_URL}/ai-context", token)

    await MicroservicesClient.get_current_subjects(token)
    mock_fetch.assert_called_with(f"{settings.CURRICULUM_SERVICE_URL}/ai-context/current", token)

    await MicroservicesClient.get_current_grades(token)
    mock_fetch.assert_called_with(f"{settings.GRADES_SERVICE_URL}/ai-context/current", token)

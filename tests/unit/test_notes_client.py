import pytest
from unittest.mock import patch, MagicMock
import httpx
from fastapi import HTTPException
from app.services.notes_client import NotesServiceClient
from app.core.config import settings

@pytest.fixture(autouse=True)
def reset_client():
    NotesServiceClient._client = None
    yield
    NotesServiceClient._client = None

@pytest.mark.asyncio
async def test_get_client():
    client1 = NotesServiceClient._get_client()
    assert isinstance(client1, httpx.AsyncClient)
    client2 = NotesServiceClient._get_client()
    assert client1 is client2

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_get_note_contents_success(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = [{"id": 1}]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    res = await NotesServiceClient.get_note_contents(1, "token")
    assert res == [{"id": 1}]

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_get_note_contents_timeout(mock_get):
    mock_get.side_effect = httpx.TimeoutException("Timeout")
    with pytest.raises(HTTPException) as exc:
        await NotesServiceClient.get_note_contents(1, "token")
    assert exc.value.status_code == 504

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_get_note_contents_403(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_get.side_effect = httpx.HTTPStatusError("403", request=MagicMock(), response=mock_response)
    with pytest.raises(HTTPException) as exc:
        await NotesServiceClient.get_note_contents(1, "token")
    assert exc.value.status_code == 403

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_get_note_contents_401(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_get.side_effect = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)
    with pytest.raises(HTTPException) as exc:
        await NotesServiceClient.get_note_contents(1, "token")
    assert exc.value.status_code == 401

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_get_note_contents_502(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_get.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)
    with pytest.raises(HTTPException) as exc:
        await NotesServiceClient.get_note_contents(1, "token")
    assert exc.value.status_code == 502

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_get_note_contents_connect_error(mock_get):
    mock_get.side_effect = httpx.ConnectError("Error")
    with pytest.raises(HTTPException) as exc:
        await NotesServiceClient.get_note_contents(1, "token")
    assert exc.value.status_code == 503

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_save_summary_as_note_success(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    res = await NotesServiceClient.save_summary_as_note(1, "summary", "token")
    assert res == {"success": True}

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_save_summary_as_note_http_error(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_post.side_effect = httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response)
    with pytest.raises(HTTPException) as exc:
        await NotesServiceClient.save_summary_as_note(1, "summary", "token")
    assert exc.value.status_code == 502

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_save_summary_as_note_unexpected_error(mock_post):
    mock_post.side_effect = Exception("Unexpected")
    with pytest.raises(HTTPException) as exc:
        await NotesServiceClient.save_summary_as_note(1, "summary", "token")
    assert exc.value.status_code == 502

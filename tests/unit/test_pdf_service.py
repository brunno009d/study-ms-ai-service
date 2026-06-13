import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import HTTPException

from app.services.pdf_service import download_file_from_url

# URL válida: debe ser HTTPS y contener el SUPABASE_URL del conftest
VALID_URL = "https://fakeproject.supabase.co/storage/v1/object/public/academic-resources/file.pdf"


def _mock_http_client(content=b"fake pdf content", content_type="application/pdf"):
    """Helper: construye un mock de httpx.AsyncClient con respuesta exitosa."""
    mock_response = MagicMock()
    mock_response.headers = {"content-type": content_type}
    mock_response.content = content
    mock_response.raise_for_status = MagicMock()

    mock_cls = MagicMock()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_cls


# ─── Casos exitosos ───────────────────────────────────────────────────────────

class TestDownloadFileSuccess:

    async def test_descarga_pdf_exitosa(self):
        # Arrange
        mock_cls = _mock_http_client(b"pdf bytes", "application/pdf")

        # Act
        with patch("app.services.pdf_service.httpx.AsyncClient", mock_cls):
            file_bytes, content_type = await download_file_from_url(VALID_URL)

        # Assert
        assert file_bytes == b"pdf bytes"
        assert content_type == "application/pdf"

    async def test_descarga_imagen_jpeg_exitosa(self):
        # Arrange
        mock_cls = _mock_http_client(b"jpg bytes", "image/jpeg")

        # Act
        with patch("app.services.pdf_service.httpx.AsyncClient", mock_cls):
            file_bytes, content_type = await download_file_from_url(VALID_URL)

        # Assert
        assert file_bytes == b"jpg bytes"
        assert content_type == "image/jpeg"

    async def test_octet_stream_infiere_pdf_por_defecto(self):
        # Arrange — URL sin extensión conocida, content-type genérico
        mock_cls = _mock_http_client(b"bytes", "application/octet-stream")

        # Act
        with patch("app.services.pdf_service.httpx.AsyncClient", mock_cls):
            _, content_type = await download_file_from_url(VALID_URL)

        # Assert
        assert content_type == "application/pdf"

    async def test_octet_stream_infiere_jpeg_por_extension_url(self):
        # Arrange — URL con extensión .jpg
        url = "https://fakeproject.supabase.co/storage/file.jpg"
        mock_cls = _mock_http_client(b"bytes", "application/octet-stream")

        # Act
        with patch("app.services.pdf_service.httpx.AsyncClient", mock_cls):
            _, content_type = await download_file_from_url(url)

        # Assert
        assert content_type == "image/jpeg"


# ─── Validación de URL ────────────────────────────────────────────────────────

class TestUrlValidation:

    async def test_url_sin_https_lanza_400(self):
        # Arrange
        insecure_url = "http://fakeproject.supabase.co/storage/file.pdf"

        # Act & Assert
        with pytest.raises(HTTPException) as exc:
            await download_file_from_url(insecure_url)
        assert exc.value.status_code == 400

    async def test_url_de_dominio_externo_lanza_400(self):
        # Arrange
        external_url = "https://malicious-site.com/fake.pdf"

        # Act & Assert
        with pytest.raises(HTTPException) as exc:
            await download_file_from_url(external_url)
        assert exc.value.status_code == 400


# ─── Errores de red ───────────────────────────────────────────────────────────

class TestNetworkErrors:

    async def test_timeout_lanza_408(self):
        # Arrange
        mock_cls = MagicMock()
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        # Act & Assert
        with patch("app.services.pdf_service.httpx.AsyncClient", mock_cls):
            with pytest.raises(HTTPException) as exc:
                await download_file_from_url(VALID_URL)
        assert exc.value.status_code == 408

    async def test_http_error_lanza_502(self):
        # Arrange
        mock_cls = MagicMock()
        mock_client = AsyncMock()
        error_response = MagicMock()
        error_response.status_code = 404
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=error_response
        )
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        # Act & Assert
        with patch("app.services.pdf_service.httpx.AsyncClient", mock_cls):
            with pytest.raises(HTTPException) as exc:
                await download_file_from_url(VALID_URL)
        assert exc.value.status_code == 502

    async def test_error_de_conexion_lanza_502(self):
        # Arrange
        mock_cls = MagicMock()
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.RequestError("Connection refused")
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        # Act & Assert
        with patch("app.services.pdf_service.httpx.AsyncClient", mock_cls):
            with pytest.raises(HTTPException) as exc:
                await download_file_from_url(VALID_URL)
        assert exc.value.status_code == 502


# ─── Validación de contenido ─────────────────────────────────────────────────

class TestContentValidation:

    async def test_content_type_invalido_lanza_400(self):
        # Arrange
        mock_cls = _mock_http_client(b"bytes", "text/html")

        # Act & Assert
        with patch("app.services.pdf_service.httpx.AsyncClient", mock_cls):
            with pytest.raises(HTTPException) as exc:
                await download_file_from_url(VALID_URL)
        assert exc.value.status_code == 400

    async def test_archivo_vacio_lanza_400(self):
        # Arrange
        mock_cls = _mock_http_client(b"", "application/pdf")

        # Act & Assert
        with patch("app.services.pdf_service.httpx.AsyncClient", mock_cls):
            with pytest.raises(HTTPException) as exc:
                await download_file_from_url(VALID_URL)
        assert exc.value.status_code == 400

    async def test_archivo_demasiado_grande_lanza_413(self):
        # Arrange — 11 MB supera el límite de 10 MB
        big_content = b"x" * (11 * 1024 * 1024)
        mock_cls = _mock_http_client(big_content, "application/pdf")

        # Act & Assert
        with patch("app.services.pdf_service.httpx.AsyncClient", mock_cls):
            with pytest.raises(HTTPException) as exc:
                await download_file_from_url(VALID_URL)
        assert exc.value.status_code == 413

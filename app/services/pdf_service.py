import httpx
from fastapi import HTTPException
from app.core.config import settings

# Tamaño máximo permitido para un PDF: 10 MB
MAX_PDF_SIZE_BYTES = 10 * 1024 * 1024


async def download_file_from_url(file_url: str) -> tuple[bytes, str]:
    """
    Descarga un archivo (PDF o imagen) desde una URL de Supabase Storage.
    """
    # Validación de seguridad: el archivo debe estar alojado en el Supabase del proyecto
    if not file_url.startswith("https://") or settings.SUPABASE_URL not in file_url:
        raise HTTPException(
            status_code=400,
            detail="Acceso denegado: El archivo debe provenir del almacenamiento oficial de Supabase de este proyecto."
        )

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(file_url)
            response.raise_for_status()

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=408,
            detail="Timeout al descargar el archivo. Verifica que la URL sea accesible."
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error al descargar el archivo: HTTP {e.response.status_code}"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error de conexión al descargar el archivo: {str(e)}"
        )

    # Validamos tipos de archivos permitidos
    content_type = response.headers.get("content-type", "").lower()
    allowed_types = ["application/pdf", "image/jpeg", "image/png", "image/webp", "application/octet-stream"]
    
    is_allowed = any(allowed in content_type for allowed in allowed_types)
    if not is_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"El archivo no es válido. Debe ser un PDF o imagen (JPG/PNG). Content-Type recibido: {content_type}"
        )

    # Validar tamaño
    file_bytes = response.content
    if len(file_bytes) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"El archivo excede el tamaño máximo permitido ({MAX_PDF_SIZE_BYTES // (1024*1024)} MB)."
        )

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=400,
            detail="El archivo descargado está vacío."
        )

    # Si viene con content-type genérico octet-stream, intentamos inferirlo
    if "octet-stream" in content_type:
        if file_url.lower().endswith(('.jpg', '.jpeg')):
            content_type = "image/jpeg"
        elif file_url.lower().endswith('.png'):
            content_type = "image/png"
        else:
            content_type = "application/pdf" # Default a PDF si no podemos inferir
            
    return file_bytes, content_type

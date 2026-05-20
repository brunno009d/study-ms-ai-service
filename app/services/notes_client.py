import httpx
from fastapi import HTTPException
from app.core.config import settings


class NotesServiceClient:
    """
    Cliente HTTP para comunicarse con el servicio de notas (ps-ms-notes-materials-service).
    Reenvía el JWT del usuario para mantener el contexto de autorización.
    """

    _client: httpx.AsyncClient = None

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(timeout=15.0)
        return cls._client

    @classmethod
    async def get_note_contents(cls, subject_id: int, token: str) -> list:
        """
        Obtiene el contenido completo de todas las notas asociadas a una asignatura.
        """
        url = f"{settings.NOTES_SERVICE_URL}/subject/{subject_id}/content"

        try:
            client = cls._get_client()
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            return response.json()

        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="Timeout al conectar con el servicio de notas."
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise HTTPException(
                    status_code=403,
                    detail="No tienes acceso a este ramo."
                )
            if e.response.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="Token inválido o expirado."
                )
            raise HTTPException(
                status_code=502,
                detail=f"Error del servicio de notas: HTTP {e.response.status_code}"
            )
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail="No se pudo conectar con el servicio de notas."
            )

    @classmethod
    async def save_summary_as_note(cls, subject_id: int, summary_text: str, token: str) -> dict:
        """
        Guarda la respuesta generada por la IA como una nota nueva en el ramo correspondiente.
        """
        url = f"{settings.NOTES_SERVICE_URL}/"

        try:
            client = cls._get_client()
            response = await client.post(
                url,
                json={
                    "subject_id": subject_id,
                    "title": "📝 Respuesta IA",
                    "content_text": summary_text
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Error al guardar la respuesta como nota: HTTP {e.response.status_code}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Error al guardar la respuesta: {str(e)}"
            )

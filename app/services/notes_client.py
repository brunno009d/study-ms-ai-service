import httpx
from fastapi import HTTPException
from app.core.config import settings


class NotesServiceClient:
    """
    Cliente HTTP para comunicarse con ps-ms-notes-materials-service.
    Usa llamadas service-to-service reenviando el JWT del usuario
    para mantener la autenticación y el ownership de las notas.
    """

    @staticmethod
    async def get_note_contents(subject_id: int, token: str) -> list:
        """
        Obtiene el contenido completo de TODAS las notas de un ramo.
        La IA se encarga de filtrar e interpretar qué notas son relevantes
        según el mensaje del usuario.
        
        Args:
            subject_id: ID del ramo/asignatura
            token: JWT del usuario autenticado (se reenvía al notes-service)
            
        Returns:
            Lista de notas con id, title, content_text, created_at, tags
        """
        url = f"{settings.NOTES_SERVICE_URL}/subject/{subject_id}/content"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"}
                )
                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="Timeout al conectar con el servicio de notas. Verifica que esté corriendo."
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
                detail="No se pudo conectar con el servicio de notas. Verifica que esté corriendo."
            )

    @staticmethod
    async def save_summary_as_note(subject_id: int, summary_text: str, token: str) -> dict:
        """
        Guarda la respuesta de la IA como una nueva nota dentro del ramo.
        
        Args:
            subject_id: ID del ramo donde guardar la nota
            summary_text: Contenido de la respuesta en Markdown
            token: JWT del usuario autenticado
            
        Returns:
            La nota creada con su ID
        """
        url = f"{settings.NOTES_SERVICE_URL}/"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
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

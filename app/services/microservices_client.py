import httpx
from app.core.config import settings


class MicroservicesClient:
    """
    Cliente HTTP para consultar los endpoints /ai-context de todos los microservicios.
    Reenvía el JWT del usuario para mantener la autenticación en cada servicio.
    Si un servicio falla o no está disponible, retorna None (la IA trabaja con lo que tenga).
    
    Sigue el mismo patrón que notes_client.py pero generalizado para todos los servicios.
    """

    _client: httpx.AsyncClient = None

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(timeout=10.0)
        return cls._client

    @classmethod
    async def _fetch(cls, url: str, token: str) -> dict | None:
        """Método genérico para hacer GET con JWT a un microservicio."""
        try:
            client = cls._get_client()
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            print(f"[AI-Context] Timeout al consultar {url}")
            return None
        except httpx.ConnectError:
            print(f"[AI-Context] No se pudo conectar a {url}")
            return None
        except httpx.HTTPStatusError as e:
            print(f"[AI-Context] Error HTTP {e.response.status_code} de {url}")
            return None
        except Exception as e:
            print(f"[AI-Context] Error inesperado al consultar {url}: {e}")
            return None

    # --- Endpoints completos (toda la información) ---

    @staticmethod
    async def get_user_profile(token: str) -> dict | None:
        # Perfil completo del estudiante.
        return await MicroservicesClient._fetch(
            f"{settings.USER_SERVICE_URL}/ai-context", token
        )

    @staticmethod
    async def get_curriculum(token: str) -> dict | None:
        # Malla curricular completa: todos los ramos, prerrequisitos, progreso.
        return await MicroservicesClient._fetch(
            f"{settings.CURRICULUM_SERVICE_URL}/ai-context", token
        )

    @staticmethod
    async def get_grades(token: str) -> dict | None:
        # Calificaciones de TODAS las materias con estructura completa.
        return await MicroservicesClient._fetch(
            f"{settings.GRADES_SERVICE_URL}/ai-context", token
        )

    @staticmethod
    async def get_calendar(token: str) -> dict | None:
        # Calendarios + eventos de los próximos 30 días.
        return await MicroservicesClient._fetch(
            f"{settings.CALENDAR_SERVICE_URL}/ai-context", token
        )

    @staticmethod
    async def get_notes(token: str) -> dict | None:
        # Metadatos de todas las notas (títulos, ramos, tags, fechas). 
        return await MicroservicesClient._fetch(
            f"{settings.NOTES_SERVICE_URL}/ai-context", token
        )

    # --- Endpoints filtrados por "cursando" (semestre actual) ---

    @staticmethod
    async def get_current_subjects(token: str) -> dict | None:
        # Solo materias que el estudiante está cursando actualmente.
        return await MicroservicesClient._fetch(
            f"{settings.CURRICULUM_SERVICE_URL}/ai-context/current", token
        )

    @staticmethod
    async def get_current_grades(token: str) -> dict | None:
        # Calificaciones SOLO de materias cursando actualmente.
        return await MicroservicesClient._fetch(
            f"{settings.GRADES_SERVICE_URL}/ai-context/current", token
        )

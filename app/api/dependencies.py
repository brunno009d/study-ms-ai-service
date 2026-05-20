from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import supabase_client

# Define el esquema de seguridad Bearer Token para FastAPI
security = HTTPBearer()

# Token del usuario (JWT) 
async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Dependencia de seguridad que valida el JWT de Supabase.
    Extrae el token del header Authorization, lo valida contra Supabase,
    y retorna el ID del usuario si es válido.
    Equivalente al requireAuth.js de Node.js.
    """
    token = credentials.credentials

    try:
        # Supabase Python SDK tiene un método para obtener el usuario basado en el JWT
        response = supabase_client.auth.get_user(token)
        
        if not response or not response.user:
            raise HTTPException(
                status_code=401,
                detail="Token inválido o expirado"
            )
            
        # Retornamos el userId por si algún controlador lo necesita
        return response.user.id
        
    except Exception as e:
        # Cualquier error al decodificar el token o hablar con Supabase
        raise HTTPException(
            status_code=401,
            detail=f"No autorizado: {str(e)}"
        )

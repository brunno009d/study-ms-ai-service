from app.core.config import supabase_client
from datetime import datetime


class ChatRepository:
    # Repositorio para gestionar sesiones de chat y mensajes en Supabase.

    # --- SESIONES ---
    @staticmethod
    async def create_session(student_id: str, title: str = None, subject_id: int = None) -> dict:
        # Crea una nueva sesión de chat (advisor si subject_id=None, RAG si subject_id=int)
        data = {"student_id": student_id, "title": title}
        if subject_id is not None:
            data["subject_id"] = subject_id
        result = supabase_client.from_("chat_sessions") \
            .insert(data) \
            .execute()
        return result.data[0] if result.data else None

    @staticmethod
    async def get_sessions_by_student(student_id: str) -> list:
        # Obtiene sesiones del consejero (subject_id IS NULL)
        result = supabase_client.from_("chat_sessions") \
            .select("*") \
            .eq("student_id", student_id) \
            .is_("subject_id", "null") \
            .order("updated_at", desc=True) \
            .execute()
        return result.data or []

    @staticmethod
    async def get_sessions_by_subject(student_id: str, subject_id: int) -> list:
        # Obtiene sesiones RAG de un ramo específico
        result = supabase_client.from_("chat_sessions") \
            .select("*") \
            .eq("student_id", student_id) \
            .eq("subject_id", subject_id) \
            .order("updated_at", desc=True) \
            .execute()
        return result.data or []

    @staticmethod
    async def get_session_by_id(session_id: str) -> dict | None:
        # Obtiene una sesión por su ID.
        result = supabase_client.from_("chat_sessions") \
            .select("*") \
            .eq("id", session_id) \
            .maybe_single() \
            .execute()
        return result.data

    @staticmethod
    async def update_session(session_id: str, updates: dict) -> dict | None:
        # Actualiza una sesión (título, updated_at).
        updates["updated_at"] = datetime.now().isoformat()
        result = supabase_client.from_("chat_sessions") \
            .update(updates) \
            .eq("id", session_id) \
            .execute()
        return result.data[0] if result.data else None

    @staticmethod
    async def delete_session(session_id: str) -> bool:
        # Elimina una sesión y todos sus mensajes (CASCADE)
        supabase_client.from_("chat_sessions") \
            .delete() \
            .eq("id", session_id) \
            .execute()
        return True

    # --- MENSAJES ---

    @staticmethod
    async def add_message(session_id: str, role: str, content: str) -> dict:
        # Agregar mensaje a la base de datos
        result = supabase_client.from_("chat_messages") \
            .insert({
                "session_id": session_id,
                "role": role,
                "content": content,
                "token_count": len(content.split())  # Estimación simple por palabras
            }) \
            .execute()
        return result.data[0] if result.data else None

    @staticmethod
    async def get_messages_by_session(session_id: str, limit: int = 50) -> list:
        # Obtener mensajes de una sesión
        result = supabase_client.from_("chat_messages") \
            .select("*") \
            .eq("session_id", session_id) \
            .order("created_at", desc=False) \
            .limit(limit) \
            .execute()
        return result.data or []

    @staticmethod
    async def get_recent_messages(session_id: str, limit: int = 20) -> list:
        # Recupera los mensajes recientes de rol 'user' y 'model' para el contexto
        result = supabase_client.from_("chat_messages") \
            .select("role, content, created_at") \
            .eq("session_id", session_id) \
            .in_("role", ["user", "model"]) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()

        # Invertimos para el orden cronológico
        messages = result.data or []
        messages.reverse()
        return messages

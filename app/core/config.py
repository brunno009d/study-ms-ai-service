import os
from google import genai
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

class Settings:
    # Google AI config
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    VISION_MODEL_NAME: str = os.getenv("VISION_MODEL_NAME", "gemini-2.5-flash")
    TEXT_MODEL_NAME: str = os.getenv("TEXT_MODEL_NAME", "gemini-2.5-flash-lite")
    PORT: int = int(os.getenv("PORT", "3006"))
    NOTES_SERVICE_URL: str = os.getenv("NOTES_SERVICE_URL", "http://localhost:3005")
    USER_SERVICE_URL: str = os.getenv("USER_SERVICE_URL", "http://localhost:3001")
    CURRICULUM_SERVICE_URL: str = os.getenv("CURRICULUM_SERVICE_URL", "http://localhost:3002")
    GRADES_SERVICE_URL: str = os.getenv("GRADES_SERVICE_URL", "http://localhost:3003")
    CALENDAR_SERVICE_URL: str = os.getenv("CALENDAR_SERVICE_URL", "http://localhost:3004")
    
    # Supabase config
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE: str = os.getenv("SUPABASE_SERVICE_ROLE", "")

settings = Settings()

# Inicializar el cliente del SDK nuevo (google-genai)
gemini_client = genai.Client(api_key=settings.GOOGLE_API_KEY)

# Inicializar cliente de Supabase
supabase_client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE)
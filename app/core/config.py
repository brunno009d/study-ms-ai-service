import os
from google import genai
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

class Settings:
    # Google AI config
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    MODEL_NAME: str = "gemini-2.5-flash"
    PORT: int = int(os.getenv("PORT", "3006"))
    
    # Supabase config
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE: str = os.getenv("SUPABASE_SERVICE_ROLE", "")

settings = Settings()

# Inicializar el cliente del SDK nuevo (google-genai)
gemini_client = genai.Client(api_key=settings.GOOGLE_API_KEY)

# Inicializar cliente de Supabase
supabase_client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE)
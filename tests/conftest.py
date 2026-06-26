import os

# Forzar valores de test sin importar lo que CI ponga en el entorno.
# setdefault() no sirve aquí porque CI pre-carga SUPABASE_URL con un valor
# distinto a "fakeproject.supabase.co", lo que hace que la validación de URL
# en pdf_service.py rechace todas las URLs de los tests.
os.environ["GOOGLE_API_KEY"] = "fake-key-for-tests"
os.environ["OPENROUTER_API_KEY"] = "fake-key-for-tests"
os.environ["SUPABASE_URL"] = "https://fakeproject.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE"] = "fake-service-role-for-tests"

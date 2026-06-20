import os

# Valores falsos para que config.py pueda importar sin un .env real.
# setdefault() no sobreescribe si ya existe la variable (ej: en CI con vars reales).
os.environ.setdefault("GOOGLE_API_KEY", "fake-key-for-tests")
os.environ.setdefault("OPENROUTER_API_KEY", "fake-key-for-tests")
os.environ.setdefault("SUPABASE_URL", "https://fakeproject.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE", "fake-service-role-for-tests")

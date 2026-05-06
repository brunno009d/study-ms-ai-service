from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router

# Inicializamos la app de FastAPI
app = FastAPI(
    title="PopStudy - AI Service",
    description="Microservicio de IA para extracción de mallas curriculares y resumen de apuntes con Gemini",
    version="1.0.0"
)

# Configuración básica de CORS (El Gateway será quien hable con este servicio)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción limitaremos esto a la IP del Gateway
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar las rutas de la API
app.include_router(router)


# Endpoint de prueba para verificar que el servicio está vivo
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "ai-service",
        "message": "El motor de IA está listo para procesar."
    }
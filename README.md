# 🧠 PopStudy - AI Service

Microservicio encargado de procesar documentos mediante Inteligencia Artificial (Google Gemini) para la extracción de datos académicos y generación de resúmenes.

---

## 🏗️ Estructura del Proyecto

El proyecto utiliza una arquitectura limpia dividida por responsabilidades:

### 📁 `app/api/` (Controladores)
*   **`routes.py`**: Define los "endpoints" (puntos de acceso). Su única responsabilidad es recibir la petición HTTP, llamar a los servicios necesarios y devolver la respuesta. No debe contener lógica compleja.

### 📁 `app/services/` (Lógica de Negocio)
*   **`gemini_service.py`**: Contiene la lógica para interactuar con Google Gemini. Aquí se definen los "prompts" (instrucciones) y se gestiona la subida de archivos a la IA.
*   **`pdf_service.py`**: Servicio utilitario para descargar PDFs desde URLs (como Supabase).
*   **`notes_client.py`**: Cliente HTTP para la comunicación inter-servicios con `ps-ms-notes-materials-service`.

### 📁 `app/models/` (Contratos de Datos)
*   **`schemas.py`**: Define los objetos **Pydantic**. Son esenciales en FastAPI porque:
    1.  Validan los datos de entrada (Request).
    2.  Definen el formato de salida (Response).
    3.  Generan la documentación automática en `/docs`.

### 📁 `app/core/` (Configuración)
*   **`config.py`**: Lee el archivo `.env` y centraliza la configuración. Aquí se inicializa el cliente de Gemini para que sea reutilizado en toda la app.

### 📄 `main.py`
*   Es el punto de entrada. Aquí se crea la instancia de FastAPI y se conectan todas las rutas de los diferentes archivos.

---

## 🚀 Conceptos de FastAPI para Principiantes

1.  **Validación Automática**: Si un esquema pide un `int` y envías un `string`, FastAPI rechazará la petición antes de que llegue a tu lógica.
2.  **Documentación Interactiva**: FastAPI crea una web para probar tu API automáticamente. Solo entra a `http://localhost:3006/docs`.
3.  **Dependencias**: Facilita inyectar configuraciones o seguridad en cada ruta.

---

## 🤖 Integración con IA (Gemini 2.5 Flash)

Este servicio utiliza capacidades avanzadas de Google Gemini para dos propósitos principales:

### 1. Extracción de Mallas Curriculares (Structured Outputs)
A diferencia de un chat normal donde la IA responde con texto libre, aquí le pasamos un esquema de datos para parsear documentos.
**Flujo:** URL de PDF/Imagen → Descarga → Subida a File API → Análisis → JSON Estructurado.

### 2. Chat Inteligente con Notas (RAG)
Implementa un sistema de **Generación Aumentada por Recuperación (RAG)**. El servicio recupera todas las notas de un ramo del usuario y las utiliza como contexto exclusivo para responder preguntas.
**Flujo:** ID de Ramo → Petición a Microservicio de Notas → Inyección de Contexto en Gemini → Respuesta en Markdown → Guardado opcional de respuesta.

---

## 🛠️ Instalación y Uso Local

1.  **Crear Entorno Virtual**:
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```
2.  **Instalar dependencias**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configurar `.env`**: Asegúrate de tener tu `GOOGLE_API_KEY`.
4.  **Ejecutar**:
    ```bash
    uvicorn app.main:app --port 3006 --reload
    ```

---

## 🐳 Docker
El archivo `Dockerfile` permite que este servicio corra igual en cualquier computadora.
*   Puerto interno: `3006`
*   Imagen base: `python:3.11-slim`

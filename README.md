# 🧠 PopStudy - AI Service

Microservicio desarrollado con **FastAPI** y **Python** que provee capacidades avanzadas de Inteligencia Artificial para el ecosistema PopStudy, integrado con **Google Gemini (SDK `google-genai`)** y **Supabase**.

---

## 🏗️ Arquitectura del Proyecto

El microservicio está estructurado siguiendo principios de diseño limpio, separación de responsabilidades y modularidad:

### 📁 `app/` (Directorio Principal)

*   **`main.py`**: Punto de entrada del microservicio. Inicializa FastAPI, habilita el middleware de CORS y monta las rutas definidas en la API.
*   **`api/`** (Controladores e Interfaces)
    *   **`routes.py`**: Contiene la definición de todos los endpoints de la API (HTTP POST, GET, PATCH, DELETE). Se encarga de procesar las peticiones, coordinar con los servicios y retornar las respuestas estructuradas.
    *   **`dependencies.py`**: Contiene middlewares y dependencias de FastAPI, como la autenticación obligatoria de tokens JWT de Supabase (`require_auth`).
*   **`core/`** (Configuraciones de Sistema)
    *   **`config.py`**: Centraliza la carga y tipado de variables de entorno usando Pydantic Settings. Inicializa de forma global los clientes para el SDK de Google Gemini y Supabase.
*   **`models/`** (Esquemas y Validación)
    *   **`schemas.py`**: Define las clases de Pydantic utilizadas para la validación automática de datos de entrada (Request) y el formateo de datos de salida (Response), alimentando la documentación interactiva OpenAPI.
*   **`repository/`** (Acceso a Datos / Persistencia)
    *   **`chat_repository.py`**: Repositorio encargado de interactuar directamente con Supabase Database para crear, listar, actualizar y eliminar sesiones de chat e historiales de mensajes del Consejero Académico.
*   **`services/`** (Capa de Servicios y Lógica de Negocio)
    *   **`gemini_service.py`**: Implementa la lógica principal de Inteligencia Artificial (prompts del sistema, llamadas a Gemini, estructuración de outputs y Function Calling).
    *   **`pdf_service.py`**: Servicio utilitario para descargar archivos PDF o imágenes desde URLs de almacenamiento externo (Supabase Storage) en flujos asíncronos.
    *   **`notes_client.py`**: Cliente HTTP de integración asíncrona dedicada con el microservicio de apuntes (`notes-service`).
    *   **`microservices_client.py`**: Cliente HTTP de integración asíncrona unificado con los otros microservicios (perfil, mallas, notas, calificaciones y calendario).

### 📁 `.github/` (Integración Continua)
*   **`workflows/deploy.yml`**: Pipeline automatizado de GitHub Actions para el despliegue automático del contenedor en producción.

---

## 🤖 Integraciones y Capacidades de IA

Este servicio exprime las ventajas del modelo **Gemini 2.5 Flash** mediante tres flujos principales:

### 1. Extracción Estructurada de Mallas Curriculares
Permite extraer el contenido completo de una malla curricular a partir de un PDF o una imagen (almacenada en Supabase Storage).
*   **Mecanismo**: Utiliza *Structured Outputs* (`response_schema`) del SDK de Gemini para asegurar que la respuesta sea un objeto JSON estrictamente válido que se mapea directamente a nuestro esquema de datos.
*   **Flujo**: Descarga de archivo temporal → Subida a Gemini File API → Análisis cognitivo → Conversión a JSON estructurado → Limpieza automática de archivos locales y temporales de Google Cloud.

### 2. Chat de Apuntes Inteligente (RAG)
Permite al estudiante chatear y realizar preguntas únicamente en base al contexto de sus apuntes subidos para una asignatura en particular.
*   **Mecanismo**: Implementa un patrón **RAG (Retrieval-Augmented Generation)** básico. Recupera en tiempo real las notas completas del ramo solicitado mediante el `notes_client` y las inyecta en el prompt del sistema como el único contexto de verdad para Gemini.
*   **Opción de Guardado**: Permite al estudiante salvar la respuesta de la IA (resúmenes, guías de estudio, explicaciones) directamente como una nueva nota dentro del ramo.

### 3. Consejero Académico con Function Calling y Memoria
Un chat inteligente persistente que actúa como tutor académico. Analiza de manera transversal el estado curricular, calificaciones y eventos del alumno.
*   **Mecanismo**: Utiliza **Function Calling (Herramientas)**. Gemini decide dinámicamente si necesita consultar datos del estudiante y llama autónomamente a funciones que obtienen información de otros microservicios en tiempo real.
*   **Memoria e Historial**: Las sesiones y mensajes se guardan en las tablas de Supabase (`chat_sessions` y `chat_messages`), permitiendo reanudar conversaciones previas y alimentar a la IA con hasta 20 mensajes anteriores como memoria histórica.

## 🚀 Instalación y Ejecución Local

### Requisitos Previos
*   Python 3.11 o superior.
*   Acceso a internet (para llamadas de API a Google Gemini y Supabase).

### Pasos
1.  **Clonar el repositorio y situarse en él**:
    ```bash
    git clone <url-del-repositorio>
    cd ps-ms-ai-service
    ```
2.  **Crear y activar el entorno virtual de Python**:
    *   **Windows**:
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```
    *   **macOS/Linux**:
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```
3.  **Instalar las dependencias necesarias**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Crear y configurar el archivo `.env`** basándose en el archivo `.env.example`.
5.  **Ejecutar el servidor de desarrollo**:
    ```bash
    uvicorn app.main:app --port 3006 --reload
    ```
6.  **Acceder a la documentación interactiva**:
    Abre tu navegador en `http://localhost:3006/docs` para visualizar y probar todos los endpoints a través de **Swagger UI**.

---

## 🐳 Despliegue con Docker

El microservicio está listo para ser compilado y ejecutado dentro de un contenedor Docker mediante la imagen ligera `python:3.11-slim`.

1.  **Construir la imagen de Docker**:
    ```bash
    docker build -t ps-ms-ai-service .
    ```
2.  **Correr el contenedor** (inyectando las variables de entorno desde un archivo `.env`):
    ```bash
    docker run -d -p 3006:3006 --env-file .env --name ai-service ps-ms-ai-service
    ```

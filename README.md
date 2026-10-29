AURA — Sistema Multiagente para Asistencia de Tareas de Enfermería

AURA (AURA-MultiAgentes-IA) es un sistema multiagente que asiste a la enfermera durante el turno: estructura los datos clínicos ingresados, redacta la evolución de enfermería, genera alertas de seguridad basadas en reglas versionadas y arma el pase de guardia. Asiste, no reemplaza el criterio clínico: ningún registro se guarda sin la aprobación explícita de la enfermera, y las alertas nunca son diagnósticos.

Proyecto académico — Modelización de Sistemas de IA. Usar únicamente con datos de prueba.

    Arquitectura
    Capa:	Tecnología
    Frontend:	Streamlit (interfaz visual, se comunica con la API solo por HTTP)
    Backend:	FastAPI
    Orquestación:	Grafo de estados con agentes especializados (Enfermería, Documentación, Seguridad)
    Persistencia:	PostgreSQL (Neon)
    Testing	pytest
    Gestor de paquetes:	uv

El repositorio está dividido en dos carpetas principales:

    backend/    API, agentes, grafo, modelos y persistencia
    frontend/   Interfaz Streamlit (no importa código del backend)
    tests/      Pruebas automáticas

    - Requisitos previos
    uv instalado (gestiona Python y las dependencias).
    Una base de datos PostgreSQL accesible (por ejemplo, un proyecto gratuito en Neon).
    Una clave de API de Google Gemini si querés que los agentes redacten con LLM (sin ella, el sistema usa textos deterministas de respaldo).
    Configuración

    - Cloná el repositorio e instalá las dependencias:
        bash
        uv sync
        Copiá el archivo de ejemplo y completalo con tus propios valores:
        bash
        cp .env.example .env
        Variable	Descripción
    DATABASE_URL	Cadena de conexión a PostgreSQL
    JWT_SECRET	Secreto para firmar los tokens de autenticación
    GOOGLE_API_KEY	Clave de Gemini (opcional)
    SEED_PASSWORD	Contraseña de los usuarios de prueba que crea el seed (opcional)
    LANGSMITH_API_KEY, LANGSMITH_TRACING, LANGSMITH_PROJECT	Trazabilidad con LangSmith (opcionales)

    - Aplicá las migraciones de la base de datos:
    bash
    uv run alembic upgrade head
    Cargá los pacientes y usuarios de prueba:
    bash
    uv run python -m backend.app.core.seed

⚠️ ¡Nunca subas el archivo .env al repositorio!

⚠️ Las pruebas automáticas incluyen tests de integración que usan la base configurada en DATABASE_URL y pueden modificar sus datos de prueba. Usá siempre una base de desarrollo, nunca la de producción.

Ejecución y Pruebas Locales
    - Este proyecto utiliza uv como gestor de paquetes. Asegúrate de configurar la base de datos en el archivo .env.

Para ejecutar las pruebas automáticas (Pytest):

    Windows: Haz doble clic en test.bat.
    Mac/Linux: Ejecuta ./test.sh en la terminal.

Para iniciar la API y la interfaz simultáneamente:

    Windows: Haz doble clic en iniciar.bat.
    Mac/Linux: Ejecuta ./iniciar.sh en la terminal.
    En VS Code/Codespaces: Presiona Ctrl + Shift + B para iniciar, o usa Run Task para los tests.

Una vez iniciado:

    API: http://localhost:8000 (documentación interactiva en http://localhost:8000/docs)
    Interfaz: http://localhost:8501

En local, la interfaz detecta automáticamente que debe apuntar a http://localhost:8000.

Despliegue en producción:

Backend (FastAPI): servicio web en Render, con las credenciales como variables de entorno del servicio.
Frontend (Streamlit): Streamlit Community Cloud, con la URL pública de la API configurada en sus Secrets (API_URL).
Base de datos: PostgreSQL gestionado en Neon.
Consideraciones de seguridad y privacidad: Las credenciales y claves de API se gestionan siempre por variables de entorno o secretos de la plataforma, nunca en el código.
Los datos de pacientes son sensibles: este repositorio solo debe usarse con datos ficticios.
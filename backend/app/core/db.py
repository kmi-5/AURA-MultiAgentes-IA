from app.core.config import settings
from langchain_postgres import PostgresSaver  # o psycopg directo

conn_string = settings.database_url
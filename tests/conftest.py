import os

# Antes de importar la app: los tests no dependen de tu .env ni de tu secreto real
os.environ.setdefault("JWT_SECRET", "secreto-solo-para-tests-" + "x" * 32)

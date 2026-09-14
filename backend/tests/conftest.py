"""
Configuración de la suite de tests backend.

Los tests deben ser herméticos: el .env del despliegue local (hosts de
Docker como `postgres`/`redis`, claves reales, AI_PROVIDER, etc.) no debe
colarse en la suite. Los tests configuran explícitamente las variables que
necesitan vía monkeypatch.
"""
import os
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Bloquear carga de .env antes de que se importe cualquier módulo del backend
# (config/app_config.py e infrastructure/db/session.py llaman a load_dotenv()).
os.environ.setdefault("DOTENV_PATH", "/dev/null")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DB_BACKEND"] = "sqlite"
os.environ["STORAGE_BACKEND"] = "filesystem"
os.environ["REDIS_URL"] = "memory://"
os.environ["AI_PROVIDER"] = "disabled"
os.environ.pop("AI_API_BASE_URL", None)
os.environ.pop("AI_API_KEY", None)

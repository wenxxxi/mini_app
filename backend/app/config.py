import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "app.db"))
WX_APPID = os.getenv("WX_APPID", "")
WX_SECRET = os.getenv("WX_SECRET", "")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
DEV_LOGIN = os.getenv("DEV_LOGIN", "0") == "1"
DEFAULT_TZ = os.getenv("TZ", "Asia/Shanghai")

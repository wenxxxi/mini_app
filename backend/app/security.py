from datetime import datetime, timedelta

import jwt

from .config import JWT_EXPIRE_DAYS, JWT_SECRET
from .timeutil import CST

ALGORITHM = "HS256"


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(CST) + timedelta(days=JWT_EXPIRE_DAYS),
        "iat": datetime.now(CST),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> int:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    return int(payload["sub"])

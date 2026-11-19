import logging
import os
import redis
from datetime import datetime, date, timezone
from typing import Literal

from fastapi import HTTPException

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
try:
    # Timeouts cortos: si Redis cae, se falla rapido en vez de colgar la request.
    _redis = redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
except Exception:
    _redis = None

DAILY_LIMIT = 50  # chat endpoints


def _window_key(window: Literal["minute", "hour", "day"]) -> str:
    now = datetime.now(timezone.utc)
    if window == "minute":
        return now.strftime("%Y-%m-%dT%H:%M")
    if window == "hour":
        return now.strftime("%Y-%m-%dT%H")
    return str(date.today())


def check_and_increment(
    uid: str,
    limit: int = DAILY_LIMIT,
    window: Literal["minute", "hour", "day"] = "day",
) -> bool:
    # Falla cerrado: sin Redis no se puede contar, y los endpoints protegidos
    # (chat con LLM de pago, subida de documentos, ejecucion de agentes) no
    # deben quedar sin limite.
    if not _redis:
        raise HTTPException(status_code=503, detail="Servicio de limites no disponible.")

    key = f"rate:{uid}:{_window_key(window)}"
    try:
        current = _redis.get(key)
        if current and int(current) >= limit:
            return False
            
        pipe = _redis.pipeline()
        pipe.incr(key)
        if window == "minute":
            pipe.expire(key, 60)
        elif window == "hour":
            pipe.expire(key, 3600)
        else:
            pipe.expire(key, 86400)
        pipe.execute()
        return True
    except Exception:
        logger.exception("Rate limiter: Redis no disponible, request rechazada (falla cerrado)")
        raise HTTPException(status_code=503, detail="Servicio de limites no disponible.")

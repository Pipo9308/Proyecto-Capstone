import os
import json
import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
try:
    _redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
except Exception:
    _redis = None

def get(key: str):
    if _redis:
        try:
            val = _redis.get(key)
            return json.loads(val) if val else None
        except Exception:
            pass
    return None

def set(key: str, val, ttl: int = 120):
    if _redis:
        try:
            _redis.setex(key, ttl, json.dumps(val))
        except Exception:
            pass

def invalidate(key: str):
    if _redis:
        try:
            _redis.delete(key)
        except Exception:
            pass

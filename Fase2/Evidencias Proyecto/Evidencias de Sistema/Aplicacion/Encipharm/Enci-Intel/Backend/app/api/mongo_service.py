from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import Counter
import time
from app.db import get_db

ZONA_CHILE = ZoneInfo("America/Santiago")

_summary_cache: dict | None = None
_summary_cache_ts: float = 0
CACHE_TTL = 120  # segundos

async def get_dashboard_summary() -> dict:
    global _summary_cache, _summary_cache_ts
    now = time.monotonic()
    if _summary_cache is not None and (now - _summary_cache_ts) < CACHE_TTL:
        return _summary_cache

    db = get_db()

    def get_urgency(a: dict) -> int:
        u = a.get("urgency")
        if isinstance(u, (int, float)):
            return int(u)
        return {"critical": 90, "high": 70, "medium": 50, "low": 20}.get(
            str(a.get("priority", "")).lower(), 0
        )

    def parse_ts(a: dict):
        ts = a.get("created_at") or a.get("timestamp")
        if isinstance(ts, datetime):
            return ts
        elif isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                pass
        return datetime.min

    alerts = await db.alerts.find(
        {}, 
        {"urgency": 1, "priority": 1, "type": 1, "leida": 1, "created_at": 1, "category": 1, "_id": 0}
    ).to_list(length=None)

    critical_count = sum(1 for a in alerts if get_urgency(a) >= 80)
    high_count     = sum(1 for a in alerts if 60 <= get_urgency(a) < 80)
    unread_count   = sum(1 for a in alerts if not a.get("leida", False))

    latest_alert    = max(alerts, key=parse_ts, default=None)
    last_alert_type = latest_alert.get("type", "") if latest_alert else ""

    opp_alerts = [a for a in alerts if a.get("type") in ("LAUNCH", "PRICE") and not a.get("leida", False)]
    opportunities_count = len(opp_alerts)
    cats = [a.get("category", "") for a in opp_alerts if a.get("category")]
    top_category = Counter(cats).most_common(1)[0][0] if cats else ""

    agents = await db.agents.find().to_list(length=None)
    estados_activos = {"running", "active"}

    agent_runs = await db.agent_runs.find().sort("started_at", -1).limit(1).to_list(length=1)

    last_run_ts = ""
    if agent_runs:
        ts = agent_runs[0].get("started_at") or agent_runs[0].get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                last_run_ts = ts
        if isinstance(ts, datetime):
            # Texto ya formateado para el panel: en hora de Chile (las fechas sin zona de Firestore son UTC).
            last_run_ts = (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)).astimezone(ZONA_CHILE).strftime("%Y-%m-%d %H:%M")

    result = {
        "success": True,
        "data": {
            "agents": {
                "total":    len(agents),
                "running":  sum(1 for a in agents if a.get("status") in estados_activos),
                "idle":     sum(1 for a in agents if a.get("status") == "idle"),
                "waiting":  sum(1 for a in agents if a.get("status") == "waiting"),
                "last_run": last_run_ts,
            },
            "alerts": {
                "unread_count":    unread_count,
                "critical_count":  critical_count,
                "high_count":      high_count,
                "last_alert_type": last_alert_type,
            },
            "market": {
                "encipharm_share_pct": 0,
                "trend":               "estable",
                "trend_delta":         None,
                "leading_competitor":  "",
            },
            "opportunities_count":        opportunities_count,
            "opportunities_top_category": top_category,
        }
    }

    _summary_cache = result
    _summary_cache_ts = now
    return result

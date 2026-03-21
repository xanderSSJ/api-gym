from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import too_many_requests
from app.core.rate_limit import rate_limit_hit
from app.db.models.enums import MembershipStatus
from app.db.models.membership import MembershipPlan, UserMembership
from app.db.models.user import User
from app.db.session import get_db_session

router = APIRouter(tags=["demo"])

DEMO_FREE_FEATURE_LIMIT = 2
DEMO_FREE_WINDOW_DAYS = 15
DEMO_FREE_WINDOW_SECONDS = DEMO_FREE_WINDOW_DAYS * 24 * 60 * 60
DEMO_LIMITED_FEATURES = {"rutina", "nutricion"}
DEMO_SQL_LIMIT_ROWS = 50


def _normalize_device_id(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    return cleaned[:120]


def _resolve_demo_device_id(request: Request, query_device_id: str | None) -> str:
    candidate = _normalize_device_id(query_device_id) or _normalize_device_id(request.headers.get("x-device-id"))
    if candidate:
        return candidate
    user_agent = request.headers.get("user-agent", "unknown-device")
    digest = hashlib.sha256(user_agent.encode("utf-8")).hexdigest()[:24]
    return f"ua-{digest}"


async def _enforce_demo_free_quota(feature: str, device_id: str) -> None:
    if feature not in DEMO_LIMITED_FEATURES:
        return
    allowed, _ = await rate_limit_hit(
        key=f"rate:demo:{feature}:device:{device_id}",
        limit=DEMO_FREE_FEATURE_LIMIT,
        window_seconds=DEMO_FREE_WINDOW_SECONDS,
    )
    if not allowed:
        raise too_many_requests(
            f"Demo free limit reached for '{feature}'. Allowed: {DEMO_FREE_FEATURE_LIMIT} requests every {DEMO_FREE_WINDOW_DAYS} days per device."
        )


def _demo_routine_payload() -> dict[str, Any]:
    monday = date.today() - timedelta(days=date.today().weekday())
    day_specs = [
        ("Lunes", "Pierna + Core"),
        ("Miercoles", "Empuje"),
        ("Viernes", "Tiron"),
        ("Sabado", "Full body"),
    ]
    offsets = {"Lunes": 0, "Miercoles": 2, "Viernes": 4, "Sabado": 5}
    days = [
        {
            "dia": day_name,
            "fecha": (monday + timedelta(days=offsets[day_name])).isoformat(),
            "enfoque": focus,
            "duracion_min": 60,
        }
        for day_name, focus in day_specs
    ]
    return {
        "feature": "rutina",
        "plan_nombre": "Demo Fuerza y Composicion (4 dias)",
        "objetivo": "Bajar grasa y mantener masa muscular",
        "nivel": "Principiante",
        "duracion_semanas": 4,
        "dias": days,
    }


def _demo_nutrition_payload() -> dict[str, Any]:
    start = date.today()
    day_names = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
    days = [
        {
            "dia": day_names[(start + timedelta(days=offset)).weekday()],
            "fecha": (start + timedelta(days=offset)).isoformat(),
            "calorias_objetivo": 2100,
        }
        for offset in range(7)
    ]
    return {
        "feature": "nutricion",
        "plan_nombre": "Demo Nutricion Balanceada (7 dias)",
        "objetivo": "Deficit moderado",
        "calorias_objetivo": 2100,
        "macros_diarios": {"proteina_g": 165, "carbohidratos_g": 220, "grasas_g": 65},
        "dias": days,
    }


def _demo_benefits_payload() -> dict[str, Any]:
    return {
        "feature": "beneficios",
        "free": {
            "rutinas": "Hasta 2 rutinas por ventana de uso",
            "nutricion": "Plan de 7 dias cada 15 dias",
            "seguimiento": "Basico",
        },
        "premium": {
            "rutinas": "Rutinas completas con regeneraciones inteligentes",
            "nutricion": "Plan de 30 dias con sustituciones",
            "seguimiento": "Historial completo y ajustes periodicos",
        },
    }


async def _membership_snapshot_for_user(session: AsyncSession, user_id: str) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(UserMembership, MembershipPlan)
            .join(MembershipPlan, MembershipPlan.id == UserMembership.plan_id)
            .where(UserMembership.user_id == user_id)
            .order_by(UserMembership.starts_at.desc(), UserMembership.created_at.desc())
        )
    ).all()
    if not rows:
        return {"plan_code": None, "plan_name": None, "status": "none", "is_premium": False}

    now = datetime.now(UTC)
    active_rows = [
        row
        for row in rows
        if row[0].status == MembershipStatus.ACTIVE and row[0].starts_at <= now <= row[0].ends_at
    ]
    membership, plan = active_rows[0] if active_rows else rows[0]
    is_active = membership.status == MembershipStatus.ACTIVE and membership.starts_at <= now <= membership.ends_at

    return {
        "plan_code": plan.code,
        "plan_name": plan.name,
        "status": membership.status.value,
        "starts_at": membership.starts_at.isoformat(),
        "ends_at": membership.ends_at.isoformat(),
        "is_premium": is_active and plan.code != "free",
    }


async def _demo_sql_payload(session: AsyncSession) -> dict[str, Any]:
    users = (await session.execute(select(User).order_by(User.created_at.desc()).limit(DEMO_SQL_LIMIT_ROWS))).scalars()
    rows: list[dict[str, Any]] = []
    verified_users = 0
    premium_users = 0

    for user in users:
        membership = await _membership_snapshot_for_user(session, user.id)
        verified = user.email_verified_at is not None
        if verified:
            verified_users += 1
        if membership["is_premium"]:
            premium_users += 1
        rows.append(
            {
                "user_id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "user_status": user.status.value,
                "email_verified": verified,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "membership": membership,
            }
        )

    return {
        "feature": "sql",
        "source": "postgresql",
        "max_rows": DEMO_SQL_LIMIT_ROWS,
        "totals": {"users": len(rows), "verified_users": verified_users, "premium_users": premium_users},
        "rows": rows,
    }


async def _build_demo_payload(feature: str, session: AsyncSession) -> dict[str, Any]:
    if feature == "rutina":
        payload = _demo_routine_payload()
    elif feature == "nutricion":
        payload = _demo_nutrition_payload()
    elif feature == "beneficios":
        payload = _demo_benefits_payload()
    elif feature == "sql":
        payload = await _demo_sql_payload(session)
    else:
        raise HTTPException(status_code=400, detail="feature must be one of: rutina, nutricion, beneficios, sql")

    payload["generated_at"] = datetime.now(UTC).isoformat()
    if feature in DEMO_LIMITED_FEATURES:
        payload["demo_policy"] = {
            "mode": "free_demo",
            "scope": "device",
            "quota": DEMO_FREE_FEATURE_LIMIT,
            "window_days": DEMO_FREE_WINDOW_DAYS,
        }
    return payload


def _build_demo_html() -> str:
    return """<!doctype html>
<html lang="es"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Gym API Demo</title><style>body{font-family:Arial,sans-serif;margin:20px}button{margin:4px;padding:8px 10px}pre{background:#f3f4f6;padding:10px;white-space:pre-wrap}</style></head>
<body><h1>Gym API Demo</h1><p><code>/v1/demo</code> | Device ID: <code id="device"></code></p>
<button data-feature="rutina">Rutina</button><button data-feature="nutricion">Nutricion</button><button data-feature="beneficios">Beneficios</button><button data-feature="sql">Datos SQL</button>
<h3>Vista bonita</h3><div id="pretty">Presiona un boton.</div><h3>JSON</h3><pre id="json">{}</pre>
<script>
const pretty=document.getElementById("pretty"), raw=document.getElementById("json"), deviceNode=document.getElementById("device"), endpoint=window.location.pathname, key="gym_demo_device_id";
let deviceId=localStorage.getItem(key); if(!deviceId){deviceId=(window.crypto&&crypto.randomUUID)?crypto.randomUUID():`demo-${Date.now()}-${Math.random().toString(16).slice(2)}`; localStorage.setItem(key,deviceId);}
deviceNode.textContent=deviceId;
function renderPretty(data){
  if(data.feature==="rutina"){pretty.textContent=`Plan: ${data.plan_nombre}\\nObjetivo: ${data.objetivo}\\nDias: ${(data.dias||[]).map(d=>d.dia).join(", ")}`;return;}
  if(data.feature==="nutricion"){pretty.textContent=`Plan: ${data.plan_nombre}\\nDias del plan: ${(data.dias||[]).length} (free 7 dias)`;return;}
  if(data.feature==="beneficios"){pretty.textContent=`Free: ${data.free?.rutinas} | ${data.free?.nutricion}\\nPremium: ${data.premium?.rutinas} | ${data.premium?.nutricion}`;return;}
  if(data.feature==="sql"){pretty.textContent=`Usuarios: ${data.totals?.users||0}\\nVerificados: ${data.totals?.verified_users||0}\\nPremium: ${data.totals?.premium_users||0}`;return;}
  pretty.textContent="Sin datos";
}
async function fetchFeature(feature){
  const url=`${endpoint}?response=json&feature=${encodeURIComponent(feature)}&device_id=${encodeURIComponent(deviceId)}`;
  const response=await fetch(url); const data=await response.json(); if(!response.ok){throw new Error(data.detail||`HTTP ${response.status}`);}
  renderPretty(data); raw.textContent=JSON.stringify(data,null,2);
}
document.querySelectorAll("button[data-feature]").forEach(btn=>btn.addEventListener("click",()=>fetchFeature(btn.dataset.feature).catch(e=>{pretty.textContent=e.message; raw.textContent=JSON.stringify({error:e.message},null,2);})));
fetchFeature("beneficios");
</script></body></html>"""


@router.get("/demo", response_class=HTMLResponse)
async def demo(
    request: Request,
    response: str = Query(default="html"),
    feature: str | None = Query(default=None),
    device_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
):
    if response.lower() == "json":
        if not feature:
            raise HTTPException(status_code=400, detail="feature query param is required when response=json")
        normalized_feature = feature.lower()
        resolved_device_id = _resolve_demo_device_id(request, device_id)
        await _enforce_demo_free_quota(normalized_feature, resolved_device_id)
        payload = await _build_demo_payload(normalized_feature, session)
        if normalized_feature in DEMO_LIMITED_FEATURES:
            payload["demo_device_id"] = resolved_device_id
        return JSONResponse(content=payload)
    return HTMLResponse(content=_build_demo_html())

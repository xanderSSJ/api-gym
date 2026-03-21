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
from app.db.models.nutrition import NutritionPlan
from app.db.models.training import TrainingPlan
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
    users = (
        await session.execute(select(User).order_by(User.created_at.desc()).limit(DEMO_SQL_LIMIT_ROWS))
    ).scalars()
    user_rows: list[dict[str, Any]] = []
    verified_users = 0
    premium_users = 0

    users_map: dict[str, User] = {}
    for user in users:
        users_map[user.id] = user
        membership = await _membership_snapshot_for_user(session, user.id)
        verified = user.email_verified_at is not None
        if verified:
            verified_users += 1
        if membership["is_premium"]:
            premium_users += 1
        user_rows.append(
            {
                "user_id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "phone": user.phone,
                "user_status": user.status.value,
                "email_verified": verified,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "membership": membership,
            }
        )

    routine_plans = (
        await session.execute(
            select(TrainingPlan).order_by(TrainingPlan.created_at.desc()).limit(DEMO_SQL_LIMIT_ROWS)
        )
    ).scalars()
    routine_rows: list[dict[str, Any]] = []
    for plan in routine_plans:
        user = users_map.get(plan.user_id)
        routine_rows.append(
            {
                "plan_id": plan.id,
                "user_id": plan.user_id,
                "user_email": user.email if user else None,
                "name": plan.name,
                "goal": plan.goal.value,
                "level": plan.level.value,
                "weeks": plan.weeks,
                "status": plan.status.value,
                "is_current": plan.is_current,
                "created_at": plan.created_at.isoformat() if plan.created_at else None,
            }
        )

    nutrition_plans = (
        await session.execute(
            select(NutritionPlan).order_by(NutritionPlan.created_at.desc()).limit(DEMO_SQL_LIMIT_ROWS)
        )
    ).scalars()
    nutrition_rows: list[dict[str, Any]] = []
    for plan in nutrition_plans:
        user = users_map.get(plan.user_id)
        nutrition_rows.append(
            {
                "plan_id": plan.id,
                "user_id": plan.user_id,
                "user_email": user.email if user else None,
                "name": plan.name,
                "goal": plan.goal.value,
                "days_count": plan.days_count,
                "target_calories": plan.target_calories,
                "status": plan.status.value,
                "is_current": plan.is_current,
                "created_at": plan.created_at.isoformat() if plan.created_at else None,
            }
        )

    return {
        "feature": "sql",
        "source": "postgresql",
        "max_rows": DEMO_SQL_LIMIT_ROWS,
        "totals": {
            "users": len(user_rows),
            "verified_users": verified_users,
            "premium_users": premium_users,
            "routines_saved": len(routine_rows),
            "nutrition_plans_saved": len(nutrition_rows),
        },
        "users": user_rows,
        "routines": routine_rows,
        "nutrition_plans": nutrition_rows,
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
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Gym API Demo</title>
    <style>
      :root { --bg:#0e1116; --card:#171c25; --line:#2a3445; --text:#e8edf7; --muted:#9fb0c6; --accent:#2e90fa; --ok:#16a34a; }
      * { box-sizing: border-box; }
      body { margin:0; font-family:Segoe UI, Arial, sans-serif; background:linear-gradient(135deg,#0e1116,#17213a); color:var(--text); }
      .wrap { max-width:1200px; margin:24px auto; padding:0 16px 20px; }
      .card { background:rgba(23,28,37,.95); border:1px solid var(--line); border-radius:16px; padding:16px; margin-bottom:12px; }
      h1,h2,h3 { margin:.2rem 0 .8rem; }
      .muted { color:var(--muted); font-size:14px; }
      .btns, .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
      button { border:0; border-radius:10px; padding:9px 14px; font-weight:700; cursor:pointer; background:var(--accent); color:white; }
      button.secondary { background:#334155; }
      .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
      .stat { border:1px solid var(--line); border-radius:12px; padding:12px; background:#111826; }
      .stat .v { font-size:22px; font-weight:800; }
      table { width:100%; border-collapse:collapse; margin-top:8px; font-size:14px; }
      th, td { border-bottom:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; }
      th { color:#bad3ff; }
      .hidden { display:none; }
      pre { margin:0; background:#0c1018; border:1px solid var(--line); border-radius:12px; padding:12px; white-space:pre-wrap; word-break:break-word; }
      .pill { background:#10253f; border:1px solid #1d3e68; color:#c7ddff; padding:4px 8px; border-radius:999px; font-size:12px; }
      @media (max-width:1000px){ .grid{grid-template-columns:1fr 1fr;} }
      @media (max-width:650px){ .grid{grid-template-columns:1fr;} }
    </style>
  </head>
  <body>
    <div class="wrap">
      <section class="card">
        <h1>Gym API Demo Dashboard</h1>
        <p class="muted">Demo publico con limite free por dispositivo. Device: <span id="device" class="pill"></span></p>
        <div class="btns">
          <button data-feature="rutina">Rutina</button>
          <button data-feature="nutricion">Nutricion</button>
          <button data-feature="beneficios">Beneficios</button>
          <button data-feature="sql">Datos SQL</button>
        </div>
        <div class="actions">
          <button id="toggle-json" class="secondary">Ver JSON</button>
          <button id="download-json" class="secondary">Descargar JSON</button>
          <span id="status" class="muted"></span>
        </div>
      </section>

      <section id="pretty" class="card"></section>
      <section id="json-panel" class="card hidden">
        <h3>JSON</h3>
        <pre id="json-view">{}</pre>
      </section>
    </div>

    <script>
      const endpoint = window.location.pathname;
      const key = "gym_demo_device_id";
      const pretty = document.getElementById("pretty");
      const jsonPanel = document.getElementById("json-panel");
      const jsonView = document.getElementById("json-view");
      const statusNode = document.getElementById("status");
      const deviceNode = document.getElementById("device");
      const toggleJsonBtn = document.getElementById("toggle-json");
      const downloadJsonBtn = document.getElementById("download-json");
      let currentData = null;

      function esc(value) {
        const s = String(value ?? "");
        return s.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
      }

      let deviceId = localStorage.getItem(key);
      if (!deviceId) {
        deviceId = (window.crypto && crypto.randomUUID)
          ? crypto.randomUUID()
          : `demo-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        localStorage.setItem(key, deviceId);
      }
      deviceNode.textContent = deviceId;

      function renderRoutine(data) {
        const rows = (data.dias || []).map((d) => `<tr><td>${esc(d.dia)}</td><td>${esc(d.fecha)}</td><td>${esc(d.enfoque)}</td><td>${esc(d.duracion_min)} min</td></tr>`).join("");
        return `
          <h2>${esc(data.plan_nombre)}</h2>
          <p class="muted">Objetivo: ${esc(data.objetivo)} | Nivel: ${esc(data.nivel)} | Semanas: ${esc(data.duracion_semanas)}</p>
          <table><thead><tr><th>Dia</th><th>Fecha</th><th>Enfoque</th><th>Duracion</th></tr></thead><tbody>${rows}</tbody></table>
        `;
      }

      function renderNutrition(data) {
        const rows = (data.dias || []).map((d) => `<tr><td>${esc(d.dia)}</td><td>${esc(d.fecha)}</td><td>${esc(d.calorias_objetivo)}</td></tr>`).join("");
        const m = data.macros_diarios || {};
        return `
          <h2>${esc(data.plan_nombre)}</h2>
          <p class="muted">Objetivo: ${esc(data.objetivo)} | Dias: ${(data.dias || []).length} (free 7 dias)</p>
          <p class="muted">Macros: P ${esc(m.proteina_g)}g | C ${esc(m.carbohidratos_g)}g | F ${esc(m.grasas_g)}g</p>
          <table><thead><tr><th>Dia</th><th>Fecha</th><th>Kcal</th></tr></thead><tbody>${rows}</tbody></table>
        `;
      }

      function renderBenefits(data) {
        return `
          <h2>Comparativo Free vs Premium</h2>
          <table>
            <thead><tr><th>Plan</th><th>Rutinas</th><th>Nutricion</th><th>Seguimiento</th></tr></thead>
            <tbody>
              <tr><td>Free</td><td>${esc(data.free?.rutinas)}</td><td>${esc(data.free?.nutricion)}</td><td>${esc(data.free?.seguimiento)}</td></tr>
              <tr><td>Premium</td><td>${esc(data.premium?.rutinas)}</td><td>${esc(data.premium?.nutricion)}</td><td>${esc(data.premium?.seguimiento)}</td></tr>
            </tbody>
          </table>
        `;
      }

      function renderSql(data) {
        const users = data.users || [];
        const routines = data.routines || [];
        const nutritions = data.nutrition_plans || [];

        const userRows = users.map((u) => `
          <tr>
            <td>${esc(u.full_name)}</td>
            <td>${esc(u.email)}</td>
            <td>${esc(u.phone ?? "N/A")}</td>
            <td>${esc(u.membership?.plan_code ?? "none")}</td>
            <td>${esc(u.membership?.status ?? "none")}</td>
          </tr>
        `).join("");

        const routineRows = routines.slice(0, 50).map((r) => `
          <tr><td>${esc(r.name)}</td><td>${esc(r.user_email ?? r.user_id)}</td><td>${esc(r.goal)}</td><td>${esc(r.level)}</td><td>${esc(r.status)}</td></tr>
        `).join("");

        const nutritionRows = nutritions.slice(0, 50).map((n) => `
          <tr><td>${esc(n.name)}</td><td>${esc(n.user_email ?? n.user_id)}</td><td>${esc(n.goal)}</td><td>${esc(n.days_count)}</td><td>${esc(n.status)}</td></tr>
        `).join("");

        return `
          <h2>Dashboard SQL</h2>
          <div class="grid">
            <div class="stat"><div class="muted">Usuarios</div><div class="v">${esc(data.totals?.users ?? 0)}</div></div>
            <div class="stat"><div class="muted">Verificados</div><div class="v">${esc(data.totals?.verified_users ?? 0)}</div></div>
            <div class="stat"><div class="muted">Premium</div><div class="v">${esc(data.totals?.premium_users ?? 0)}</div></div>
            <div class="stat"><div class="muted">Rutinas Guardadas</div><div class="v">${esc(data.totals?.routines_saved ?? 0)}</div></div>
          </div>
          <h3>Usuarios registrados</h3>
          <table><thead><tr><th>Nombre</th><th>Correo</th><th>Numero</th><th>Membresia</th><th>Estado</th></tr></thead><tbody>${userRows}</tbody></table>
          <h3>Rutinas guardadas</h3>
          <table><thead><tr><th>Plan</th><th>Usuario</th><th>Objetivo</th><th>Nivel</th><th>Estado</th></tr></thead><tbody>${routineRows}</tbody></table>
          <h3>Planes de nutricion guardados</h3>
          <table><thead><tr><th>Plan</th><th>Usuario</th><th>Objetivo</th><th>Dias</th><th>Estado</th></tr></thead><tbody>${nutritionRows}</tbody></table>
        `;
      }

      function renderPretty(data) {
        if (data.feature === "rutina") { pretty.innerHTML = renderRoutine(data); return; }
        if (data.feature === "nutricion") { pretty.innerHTML = renderNutrition(data); return; }
        if (data.feature === "beneficios") { pretty.innerHTML = renderBenefits(data); return; }
        if (data.feature === "sql") { pretty.innerHTML = renderSql(data); return; }
        pretty.innerHTML = "<p>Sin datos</p>";
      }

      async function loadFeature(feature) {
        const url = `${endpoint}?response=json&feature=${encodeURIComponent(feature)}&device_id=${encodeURIComponent(deviceId)}`;
        statusNode.textContent = `Consultando ${feature}...`;
        const response = await fetch(url);
        const data = await response.json();
        currentData = data;
        if (!response.ok) {
          currentData = {
            feature,
            error: data.detail || `HTTP ${response.status}`,
            status: response.status,
            response_json: data,
          };
          jsonView.textContent = JSON.stringify(currentData, null, 2);
          throw new Error(currentData.error);
        }
        renderPretty(data);
        jsonView.textContent = JSON.stringify(data, null, 2);
        statusNode.textContent = `Cargado: ${feature}`;
      }

      toggleJsonBtn.addEventListener("click", () => jsonPanel.classList.toggle("hidden"));

      downloadJsonBtn.addEventListener("click", () => {
        if (!currentData) return;
        const blob = new Blob([JSON.stringify(currentData, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        const filename = `demo-${currentData.feature || "data"}.json`;
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
        URL.revokeObjectURL(a.href);
      });

      document.querySelectorAll("button[data-feature]").forEach((btn) => {
        btn.addEventListener("click", () => {
          loadFeature(btn.dataset.feature).catch((error) => {
            if (!currentData || !currentData.feature) {
              currentData = { feature: btn.dataset.feature, error: error.message };
              jsonView.textContent = JSON.stringify(currentData, null, 2);
            }
            pretty.innerHTML = `<p style="color:#f87171;"><strong>Error:</strong> ${esc(error.message)}</p><p class="muted">Puedes descargar el JSON de este error con el boton "Descargar JSON".</p>`;
            statusNode.textContent = "Error";
          });
        });
      });

      loadFeature("beneficios").catch(() => {});
    </script>
  </body>
</html>"""


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

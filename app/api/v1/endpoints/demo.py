from __future__ import annotations

import hashlib
import random
import secrets
from collections import Counter
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

_DAY_NAMES = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
_DAY_OFFSETS = {"Lunes": 0, "Martes": 1, "Miercoles": 2, "Jueves": 3, "Viernes": 4, "Sabado": 5, "Domingo": 6}
_LAST_VARIANT_BY_DEVICE_FEATURE: dict[str, int] = {}

_ROUTINE_VARIANTS = [
    {
        "plan": "Demo Fuerza y Composicion",
        "objetivo": "Bajar grasa y mantener masa muscular",
        "goal_profile": "fat_loss",
        "nivel": "Principiante",
        "duracion_semanas": 4,
        "dias": [
            ("Lunes", "Pierna + Core", 60),
            ("Miercoles", "Empuje", 60),
            ("Viernes", "Tiron", 60),
            ("Sabado", "Full body", 55),
        ],
    },
    {
        "plan": "Demo Hipertrofia Controlada",
        "objetivo": "Subir masa muscular limpia",
        "goal_profile": "hypertrophy",
        "nivel": "Intermedio",
        "duracion_semanas": 5,
        "dias": [
            ("Lunes", "Torso", 70),
            ("Martes", "Pierna + Core", 70),
            ("Jueves", "Empuje", 65),
            ("Sabado", "Tiron", 65),
        ],
    },
    {
        "plan": "Demo Potencia y Rendimiento",
        "objetivo": "Fuerza general y rendimiento",
        "goal_profile": "strength",
        "nivel": "Intermedio",
        "duracion_semanas": 4,
        "dias": [
            ("Lunes", "Empuje", 65),
            ("Miercoles", "Pierna", 70),
            ("Viernes", "Tiron", 65),
            ("Sabado", "Core + Cardio", 50),
        ],
    },
    {
        "plan": "Demo Resistencia Activa",
        "objetivo": "Resistencia muscular y acondicionamiento",
        "goal_profile": "endurance",
        "nivel": "Principiante",
        "duracion_semanas": 4,
        "dias": [
            ("Lunes", "Full body", 50),
            ("Miercoles", "Core + Cardio", 45),
            ("Viernes", "Pierna + Core", 55),
            ("Sabado", "Empuje", 50),
        ],
    },
]

_FOCUS_EXERCISE_LIBRARY: dict[str, list[dict[str, str]]] = {
    "Empuje": [
        {"nombre": "Press de banca con barra", "tipo": "compound"},
        {"nombre": "Press inclinado con mancuernas", "tipo": "compound"},
        {"nombre": "Press militar con barra", "tipo": "compound"},
        {"nombre": "Fondos asistidos", "tipo": "accessory"},
        {"nombre": "Elevaciones laterales", "tipo": "accessory"},
        {"nombre": "Extension de triceps en polea", "tipo": "accessory"},
    ],
    "Tiron": [
        {"nombre": "Dominadas asistidas", "tipo": "compound"},
        {"nombre": "Jalon al pecho", "tipo": "compound"},
        {"nombre": "Remo con barra", "tipo": "compound"},
        {"nombre": "Remo sentado en polea", "tipo": "compound"},
        {"nombre": "Face pull", "tipo": "accessory"},
        {"nombre": "Curl de biceps con barra", "tipo": "accessory"},
    ],
    "Pierna + Core": [
        {"nombre": "Sentadilla goblet", "tipo": "compound"},
        {"nombre": "Prensa de piernas", "tipo": "compound"},
        {"nombre": "Peso muerto rumano", "tipo": "compound"},
        {"nombre": "Zancadas caminando", "tipo": "accessory"},
        {"nombre": "Plancha frontal", "tipo": "core"},
        {"nombre": "Dead bug", "tipo": "core"},
    ],
    "Full body": [
        {"nombre": "Sentadilla frontal", "tipo": "compound"},
        {"nombre": "Press banca con mancuernas", "tipo": "compound"},
        {"nombre": "Remo con mancuernas", "tipo": "compound"},
        {"nombre": "Kettlebell swing", "tipo": "cardio"},
        {"nombre": "Plancha lateral", "tipo": "core"},
        {"nombre": "Mountain climbers", "tipo": "cardio"},
    ],
    "Torso": [
        {"nombre": "Press inclinado con barra", "tipo": "compound"},
        {"nombre": "Remo pendlay", "tipo": "compound"},
        {"nombre": "Jalon neutro", "tipo": "compound"},
        {"nombre": "Press militar sentado", "tipo": "compound"},
        {"nombre": "Curl barra Z", "tipo": "accessory"},
        {"nombre": "Fondos en banco", "tipo": "accessory"},
    ],
    "Pierna": [
        {"nombre": "Sentadilla trasera", "tipo": "compound"},
        {"nombre": "Peso muerto sumo", "tipo": "compound"},
        {"nombre": "Bulgarian split squat", "tipo": "compound"},
        {"nombre": "Prensa inclinada", "tipo": "compound"},
        {"nombre": "Elevacion de talones", "tipo": "accessory"},
        {"nombre": "Ab wheel", "tipo": "core"},
    ],
    "Core + Cardio": [
        {"nombre": "Plancha frontal", "tipo": "core"},
        {"nombre": "Crunch cable", "tipo": "core"},
        {"nombre": "Elevaciones de piernas", "tipo": "core"},
        {"nombre": "Remo ergometro", "tipo": "cardio"},
        {"nombre": "Bicicleta estatica por intervalos", "tipo": "cardio"},
        {"nombre": "Saltar cuerda", "tipo": "cardio"},
    ],
}

_NUTRITION_VARIANTS = [
    {
        "plan": "Demo Nutricion Balanceada",
        "objetivo": "Deficit moderado",
        "goal_profile": "fat_loss",
        "calorias_objetivo": 2100,
        "macros_diarios": {"proteina_g": 165, "carbohidratos_g": 220, "grasas_g": 65},
    },
    {
        "plan": "Demo Recompostion Activa",
        "objetivo": "Recomposicion corporal",
        "goal_profile": "recomposition",
        "calorias_objetivo": 2300,
        "macros_diarios": {"proteina_g": 180, "carbohidratos_g": 240, "grasas_g": 75},
    },
    {
        "plan": "Demo Superavit Limpio",
        "objetivo": "Subir peso con control",
        "goal_profile": "muscle_gain",
        "calorias_objetivo": 2600,
        "macros_diarios": {"proteina_g": 185, "carbohidratos_g": 320, "grasas_g": 75},
    },
]

_MEAL_LIBRARY: dict[str, list[dict[str, Any]]] = {
    "Desayuno": [
        {
            "hora": "07:00",
            "alimentos": [
                {"nombre": "Avena", "porcion": "70 g", "calorias": 265},
                {"nombre": "Yogur griego natural", "porcion": "200 g", "calorias": 130},
                {"nombre": "Banano", "porcion": "1 pieza", "calorias": 105},
            ],
        },
        {
            "hora": "07:20",
            "alimentos": [
                {"nombre": "Huevos enteros", "porcion": "2 piezas", "calorias": 156},
                {"nombre": "Claras de huevo", "porcion": "150 g", "calorias": 75},
                {"nombre": "Pan integral", "porcion": "2 rebanadas", "calorias": 160},
            ],
        },
    ],
    "Colacion AM": [
        {
            "hora": "10:30",
            "alimentos": [
                {"nombre": "Yogur griego", "porcion": "170 g", "calorias": 115},
                {"nombre": "Fresas", "porcion": "120 g", "calorias": 40},
                {"nombre": "Granola", "porcion": "30 g", "calorias": 140},
            ],
        },
        {
            "hora": "10:45",
            "alimentos": [
                {"nombre": "Atun en agua", "porcion": "100 g", "calorias": 120},
                {"nombre": "Galletas de arroz", "porcion": "3 piezas", "calorias": 105},
                {"nombre": "Manzana", "porcion": "1 pieza", "calorias": 95},
            ],
        },
    ],
    "Comida": [
        {
            "hora": "14:00",
            "alimentos": [
                {"nombre": "Pechuga de pollo a la plancha", "porcion": "180 g", "calorias": 300},
                {"nombre": "Arroz cocido", "porcion": "180 g", "calorias": 235},
                {"nombre": "Ensalada verde", "porcion": "200 g", "calorias": 80},
                {"nombre": "Aceite de oliva", "porcion": "10 g", "calorias": 90},
            ],
        },
        {
            "hora": "14:20",
            "alimentos": [
                {"nombre": "Carne magra de res", "porcion": "170 g", "calorias": 295},
                {"nombre": "Papa cocida", "porcion": "260 g", "calorias": 225},
                {"nombre": "Verduras salteadas", "porcion": "180 g", "calorias": 95},
                {"nombre": "Aguacate", "porcion": "60 g", "calorias": 96},
            ],
        },
    ],
    "Colacion PM": [
        {
            "hora": "17:30",
            "alimentos": [
                {"nombre": "Queso cottage", "porcion": "180 g", "calorias": 150},
                {"nombre": "Pina", "porcion": "140 g", "calorias": 70},
                {"nombre": "Almendras", "porcion": "15 g", "calorias": 90},
            ],
        },
        {
            "hora": "17:45",
            "alimentos": [
                {"nombre": "Sandwich integral de pavo", "porcion": "1 pieza", "calorias": 290},
                {"nombre": "Pepino con limon", "porcion": "150 g", "calorias": 25},
            ],
        },
    ],
    "Cena": [
        {
            "hora": "21:00",
            "alimentos": [
                {"nombre": "Pechuga de pavo", "porcion": "160 g", "calorias": 220},
                {"nombre": "Camote horneado", "porcion": "220 g", "calorias": 190},
                {"nombre": "Ensalada mixta", "porcion": "200 g", "calorias": 85},
                {"nombre": "Aceite de oliva", "porcion": "8 g", "calorias": 72},
            ],
        },
        {
            "hora": "20:45",
            "alimentos": [
                {"nombre": "Tacos de atun en tortilla de maiz", "porcion": "3 piezas", "calorias": 345},
                {"nombre": "Guacamole", "porcion": "50 g", "calorias": 85},
                {"nombre": "Verduras al vapor", "porcion": "180 g", "calorias": 75},
            ],
        },
    ],
}

_EQUIVALENCES = [
    {"grupo": "Proteina", "ejemplos": ["Pollo", "Atun", "Pavo", "Claras", "Carne magra"]},
    {"grupo": "Carbohidrato", "ejemplos": ["Arroz", "Papa", "Camote", "Pasta integral", "Avena"]},
    {"grupo": "Grasa", "ejemplos": ["Aguacate", "Nueces", "Almendras", "Aceite de oliva"]},
]


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


def _pick_variant_index(feature: str, device_id: str, total_variants: int) -> int:
    key = f"{feature}:{device_id}"
    previous = _LAST_VARIANT_BY_DEVICE_FEATURE.get(key)
    if total_variants <= 1:
        selected = 0
    else:
        selected = secrets.randbelow(total_variants)
        if previous is not None and selected == previous:
            selected = (selected + 1 + secrets.randbelow(total_variants - 1)) % total_variants
    _LAST_VARIANT_BY_DEVICE_FEATURE[key] = selected
    return selected


def _build_rng(feature: str, device_id: str, variant_index: int) -> random.Random:
    seed = f"{feature}:{device_id}:{variant_index}:{secrets.token_hex(8)}"
    return random.Random(seed)


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


def _rep_and_rest(goal_profile: str, level: str, movement_type: str, rng: random.Random) -> dict[str, Any]:
    base_sets = {"Principiante": 3, "Intermedio": 4, "Avanzado": 5}.get(level, 3)
    if movement_type == "cardio":
        return {
            "series": 3,
            "repeticiones": rng.choice(["8-12 min", "12-15 min"]),
            "descanso_segundos": rng.choice([30, 45]),
        }
    if movement_type == "core":
        return {
            "series": max(3, base_sets - 1),
            "repeticiones": rng.choice(["12-15", "15-20", "30-40 seg"]),
            "descanso_segundos": rng.choice([30, 40, 45]),
        }

    if goal_profile == "strength":
        reps = ["4-6", "5-7"] if movement_type == "compound" else ["6-8", "8-10"]
        rests = [120, 135, 150] if movement_type == "compound" else [75, 90]
    elif goal_profile == "hypertrophy":
        reps = ["6-8", "8-10"] if movement_type == "compound" else ["10-12", "12-15"]
        rests = [90, 105, 120] if movement_type == "compound" else [60, 75]
    elif goal_profile == "endurance":
        reps = ["12-15", "15-18"] if movement_type == "compound" else ["15-20", "20-25"]
        rests = [45, 60] if movement_type == "compound" else [30, 45]
    else:
        reps = ["8-10", "10-12"] if movement_type == "compound" else ["12-15", "15-18"]
        rests = [75, 90] if movement_type == "compound" else [45, 60]
    sets = base_sets if movement_type == "compound" else max(2, base_sets - 1)
    return {"series": sets, "repeticiones": rng.choice(reps), "descanso_segundos": rng.choice(rests)}


def _exercise_count_for_day(minutes: int) -> int:
    if minutes <= 50:
        return 4
    if minutes <= 65:
        return 5
    return 6


def _build_routine_day(
    rng: random.Random,
    goal_profile: str,
    level: str,
    day_name: str,
    focus: str,
    duration_min: int,
    monday: date,
) -> dict[str, Any]:
    pool = _FOCUS_EXERCISE_LIBRARY.get(focus) or _FOCUS_EXERCISE_LIBRARY["Full body"]
    selected = rng.sample(pool, k=min(len(pool), _exercise_count_for_day(duration_min)))
    exercises: list[dict[str, Any]] = []
    for idx, exercise in enumerate(selected, start=1):
        values = _rep_and_rest(goal_profile, level, exercise["tipo"], rng)
        exercises.append(
            {
                "orden": idx,
                "nombre": exercise["nombre"],
                "series": values["series"],
                "repeticiones": values["repeticiones"],
                "descanso_segundos": values["descanso_segundos"],
            }
        )
    return {
        "dia": day_name,
        "fecha": (monday + timedelta(days=_DAY_OFFSETS[day_name])).isoformat(),
        "enfoque": focus,
        "duracion_min": duration_min,
        "ejercicios": exercises,
    }


def _demo_routine_payload(device_id: str) -> dict[str, Any]:
    variant_index = _pick_variant_index("rutina", device_id, len(_ROUTINE_VARIANTS))
    variant = _ROUTINE_VARIANTS[variant_index]
    rng = _build_rng("rutina", device_id, variant_index)
    monday = date.today() - timedelta(days=date.today().weekday())
    days = [
        _build_routine_day(rng, variant["goal_profile"], variant["nivel"], day_name, focus, duration_min, monday)
        for day_name, focus, duration_min in variant["dias"]
    ]
    return {
        "feature": "rutina",
        "variation_id": f"rutina-{variant_index}-{secrets.token_hex(4)}",
        "plan_nombre": f"{variant['plan']} ({len(days)} dias)",
        "objetivo": variant["objetivo"],
        "nivel": variant["nivel"],
        "duracion_semanas": variant["duracion_semanas"],
        "dias": days,
        "recomendaciones": [
            "Calentar 8-10 minutos antes de entrenar.",
            "Mantener tecnica y dejar 1-2 repeticiones en reserva.",
            "Registrar cargas para progresar cada semana.",
        ],
    }


def _pick_meal_template(slot: str, variant_index: int, day_offset: int, rng: random.Random) -> dict[str, Any]:
    options = _MEAL_LIBRARY[slot]
    idx = (variant_index + day_offset + rng.randrange(len(options))) % len(options)
    template = options[idx]
    return {"hora": template["hora"], "alimentos": [dict(item) for item in template["alimentos"]]}


def _build_shopping_summary(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str]] = Counter()
    for day in days:
        for meal in day["comidas"]:
            for item in meal["alimentos"]:
                counter[(item["nombre"], item["porcion"])] += 1
    return [
        {"alimento": key[0], "porcion_referencia": key[1], "cantidad_aprox": f"{qty} porciones"}
        for key, qty in counter.most_common(16)
    ]


def _demo_nutrition_payload(device_id: str) -> dict[str, Any]:
    variant_index = _pick_variant_index("nutricion", device_id, len(_NUTRITION_VARIANTS))
    variant = _NUTRITION_VARIANTS[variant_index]
    rng = _build_rng("nutricion", device_id, variant_index)
    start = date.today()
    meal_slots = ["Desayuno", "Colacion AM", "Comida", "Colacion PM", "Cena"]
    days: list[dict[str, Any]] = []

    for day_offset in range(7):
        current_date = start + timedelta(days=day_offset)
        meals: list[dict[str, Any]] = []
        total = 0
        for meal_number, slot in enumerate(meal_slots, start=1):
            template = _pick_meal_template(slot, variant_index, day_offset + meal_number, rng)
            kcal = sum(int(item["calorias"]) for item in template["alimentos"])
            total += kcal
            meals.append(
                {
                    "numero": meal_number,
                    "nombre": slot,
                    "hora": template["hora"],
                    "alimentos": template["alimentos"],
                    "calorias_estimadas": kcal,
                }
            )
        days.append(
            {
                "dia": _DAY_NAMES[current_date.weekday()],
                "fecha": current_date.isoformat(),
                "calorias_objetivo": variant["calorias_objetivo"],
                "total_calorias_estimadas": total,
                "comidas": meals,
            }
        )

    return {
        "feature": "nutricion",
        "variation_id": f"nutricion-{variant_index}-{secrets.token_hex(4)}",
        "plan_nombre": f"{variant['plan']} (7 dias)",
        "objetivo": variant["objetivo"],
        "calorias_objetivo": variant["calorias_objetivo"],
        "macros_diarios": variant["macros_diarios"],
        "dias": days,
        "equivalencias_rapidas": _EQUIVALENCES,
        "lista_compras_resumen": _build_shopping_summary(days),
        "recomendaciones": [
            "Distribuir proteina durante todo el dia mejora recuperacion.",
            "Mantener hidratacion de 30-40 ml por kg de peso.",
            "Usar equivalencias para sostener adherencia sin romper macros.",
        ],
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


async def _build_demo_payload(feature: str, session: AsyncSession, device_id: str) -> dict[str, Any]:
    if feature == "rutina":
        payload = _demo_routine_payload(device_id)
    elif feature == "nutricion":
        payload = _demo_nutrition_payload(device_id)
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
            "variation_strategy": "non_repeating_by_device",
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
      :root { --card:#171c25; --line:#2a3445; --text:#e8edf7; --muted:#9fb0c6; --accent:#2e90fa; }
      * { box-sizing: border-box; }
      body { margin:0; font-family:Segoe UI, Arial, sans-serif; background:linear-gradient(135deg,#0e1116,#17213a); color:var(--text); }
      .wrap { max-width:1300px; margin:24px auto; padding:0 16px 20px; }
      .card { background:rgba(23,28,37,.95); border:1px solid var(--line); border-radius:16px; padding:16px; margin-bottom:12px; }
      h1,h2,h3 { margin:.2rem 0 .8rem; }
      .muted { color:var(--muted); font-size:14px; }
      .btns, .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
      button { border:0; border-radius:10px; padding:9px 14px; font-weight:700; cursor:pointer; background:var(--accent); color:white; }
      button.secondary { background:#334155; }
      .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
      .row-grid { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:12px; }
      .block { border:1px solid var(--line); border-radius:12px; padding:12px; background:#111826; }
      .stat { border:1px solid var(--line); border-radius:12px; padding:12px; background:#111826; }
      .stat .v { font-size:22px; font-weight:800; }
      table { width:100%; border-collapse:collapse; margin-top:8px; font-size:14px; }
      th, td { border-bottom:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; }
      th { color:#bad3ff; }
      .hidden { display:none; }
      pre { margin:0; background:#0c1018; border:1px solid var(--line); border-radius:12px; padding:12px; white-space:pre-wrap; word-break:break-word; }
      .pill { background:#10253f; border:1px solid #1d3e68; color:#c7ddff; padding:4px 8px; border-radius:999px; font-size:12px; }
      @media (max-width:1000px){ .grid{grid-template-columns:1fr 1fr;} .row-grid{grid-template-columns:1fr;} }
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
        const days = (data.dias || []).map((d) => {
          const rows = (d.ejercicios || []).map((e) => `<tr><td>${esc(e.orden)}</td><td>${esc(e.nombre)}</td><td>${esc(e.series)}</td><td>${esc(e.repeticiones)}</td><td>${esc(e.descanso_segundos)} seg</td></tr>`).join("");
          return `<article class="block"><h3>${esc(d.dia)} - ${esc(d.enfoque)}</h3><p class="muted">Fecha: ${esc(d.fecha)} | Duracion: ${esc(d.duracion_min)} min</p><table><thead><tr><th>#</th><th>Ejercicio</th><th>Series</th><th>Reps</th><th>Descanso</th></tr></thead><tbody>${rows}</tbody></table></article>`;
        }).join("");
        const recs = (data.recomendaciones || []).map((r) => `<li>${esc(r)}</li>`).join("");
        return `<h2>${esc(data.plan_nombre)}</h2><p class="muted">Objetivo: ${esc(data.objetivo)} | Nivel: ${esc(data.nivel)} | Semanas: ${esc(data.duracion_semanas)} | Variacion: ${esc(data.variation_id)}</p><div class="row-grid">${days}</div><h3>Recomendaciones</h3><ul>${recs}</ul>`;
      }

      function renderNutrition(data) {
        const days = (data.dias || []).map((d) => {
          const rows = (d.comidas || []).map((meal) => {
            const foods = (meal.alimentos || []).map((food) => `${esc(food.nombre)} (${esc(food.porcion)}) - ${esc(food.calorias)} kcal`).join("<br/>");
            return `<tr><td>${esc(meal.numero)}. ${esc(meal.nombre)}</td><td>${esc(meal.hora)}</td><td>${foods}</td><td>${esc(meal.calorias_estimadas)}</td></tr>`;
          }).join("");
          return `<article class="block"><h3>${esc(d.dia)} (${esc(d.fecha)})</h3><p class="muted">Objetivo: ${esc(d.calorias_objetivo)} kcal | Estimado: ${esc(d.total_calorias_estimadas)} kcal</p><table><thead><tr><th>Comida</th><th>Hora</th><th>Alimentos</th><th>Kcal</th></tr></thead><tbody>${rows}</tbody></table></article>`;
        }).join("");
        const shopping = (data.lista_compras_resumen || []).map((i) => `<tr><td>${esc(i.alimento)}</td><td>${esc(i.porcion_referencia)}</td><td>${esc(i.cantidad_aprox)}</td></tr>`).join("");
        const m = data.macros_diarios || {};
        return `<h2>${esc(data.plan_nombre)}</h2><p class="muted">Objetivo: ${esc(data.objetivo)} | Dias: ${(data.dias || []).length} (free 7 dias) | Variacion: ${esc(data.variation_id)}</p><p class="muted">Macros: P ${esc(m.proteina_g)}g | C ${esc(m.carbohidratos_g)}g | F ${esc(m.grasas_g)}g</p><div class="row-grid">${days}</div><h3>Lista de compras sugerida</h3><table><thead><tr><th>Alimento</th><th>Porcion</th><th>Cantidad</th></tr></thead><tbody>${shopping}</tbody></table>`;
      }

      function renderBenefits(data) {
        return `<h2>Comparativo Free vs Premium</h2><table><thead><tr><th>Plan</th><th>Rutinas</th><th>Nutricion</th><th>Seguimiento</th></tr></thead><tbody><tr><td>Free</td><td>${esc(data.free?.rutinas)}</td><td>${esc(data.free?.nutricion)}</td><td>${esc(data.free?.seguimiento)}</td></tr><tr><td>Premium</td><td>${esc(data.premium?.rutinas)}</td><td>${esc(data.premium?.nutricion)}</td><td>${esc(data.premium?.seguimiento)}</td></tr></tbody></table>`;
      }

      function renderSql(data) {
        const users = data.users || [];
        const routines = data.routines || [];
        const nutritions = data.nutrition_plans || [];
        const userRows = users.map((u) => `<tr><td>${esc(u.full_name)}</td><td>${esc(u.email)}</td><td>${esc(u.phone ?? "N/A")}</td><td>${esc(u.membership?.plan_code ?? "none")}</td><td>${esc(u.membership?.status ?? "none")}</td></tr>`).join("");
        const routineRows = routines.slice(0, 50).map((r) => `<tr><td>${esc(r.name)}</td><td>${esc(r.user_email ?? r.user_id)}</td><td>${esc(r.goal)}</td><td>${esc(r.level)}</td><td>${esc(r.status)}</td></tr>`).join("");
        const nutritionRows = nutritions.slice(0, 50).map((n) => `<tr><td>${esc(n.name)}</td><td>${esc(n.user_email ?? n.user_id)}</td><td>${esc(n.goal)}</td><td>${esc(n.days_count)}</td><td>${esc(n.status)}</td></tr>`).join("");
        return `<h2>Dashboard SQL</h2><div class="grid"><div class="stat"><div class="muted">Usuarios</div><div class="v">${esc(data.totals?.users ?? 0)}</div></div><div class="stat"><div class="muted">Verificados</div><div class="v">${esc(data.totals?.verified_users ?? 0)}</div></div><div class="stat"><div class="muted">Premium</div><div class="v">${esc(data.totals?.premium_users ?? 0)}</div></div><div class="stat"><div class="muted">Rutinas Guardadas</div><div class="v">${esc(data.totals?.routines_saved ?? 0)}</div></div></div><h3>Usuarios registrados</h3><table><thead><tr><th>Nombre</th><th>Correo</th><th>Numero</th><th>Membresia</th><th>Estado</th></tr></thead><tbody>${userRows}</tbody></table><h3>Rutinas guardadas</h3><table><thead><tr><th>Plan</th><th>Usuario</th><th>Objetivo</th><th>Nivel</th><th>Estado</th></tr></thead><tbody>${routineRows}</tbody></table><h3>Planes de nutricion guardados</h3><table><thead><tr><th>Plan</th><th>Usuario</th><th>Objetivo</th><th>Dias</th><th>Estado</th></tr></thead><tbody>${nutritionRows}</tbody></table>`;
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
          currentData = { feature, error: data.detail || `HTTP ${response.status}`, status: response.status, response_json: data };
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
        a.href = URL.createObjectURL(blob);
        a.download = `demo-${currentData.feature || "data"}.json`;
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
        payload = await _build_demo_payload(normalized_feature, session, resolved_device_id)
        if normalized_feature in DEMO_LIMITED_FEATURES:
            payload["demo_device_id"] = resolved_device_id
        return JSONResponse(content=payload)
    return HTMLResponse(content=_build_demo_html())

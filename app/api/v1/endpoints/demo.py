from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(tags=["demo"])


def _demo_routine_payload() -> dict[str, Any]:
    monday = date.today() - timedelta(days=date.today().weekday())
    days = []
    day_specs = [
        ("Lunes", "Pierna + Core", [("Sentadilla goblet", "4x12"), ("Peso muerto rumano", "4x10"), ("Plancha", "4x40s")]),
        ("Miercoles", "Empuje", [("Press banca", "4x10"), ("Press militar", "3x10"), ("Fondos asistidos", "3x12")]),
        ("Viernes", "Tiron", [("Remo con barra", "4x10"), ("Jalon al pecho", "4x12"), ("Curl biceps", "3x12")]),
        ("Sabado", "Full body", [("Zancadas", "3x12"), ("Dominadas asistidas", "3x8"), ("Farmer carry", "4x30m")]),
    ]
    offsets = {"Lunes": 0, "Miercoles": 2, "Viernes": 4, "Sabado": 5}

    for day_name, focus, exercises in day_specs:
        day_date = monday + timedelta(days=offsets[day_name])
        days.append(
            {
                "dia": day_name,
                "fecha": day_date.isoformat(),
                "enfoque": focus,
                "duracion_min": 60,
                "ejercicios": [
                    {
                        "nombre": exercise_name,
                        "series_reps": series_reps,
                        "descanso_segundos": 75,
                    }
                    for exercise_name, series_reps in exercises
                ],
            }
        )

    return {
        "feature": "rutina",
        "plan_nombre": "Demo Fuerza y Composicion (4 dias)",
        "objetivo": "Bajar grasa y mantener masa muscular",
        "nivel": "Principiante",
        "duracion_semanas": 4,
        "dias": days,
        "recomendaciones": [
            "Calienta 8-10 minutos antes de cada sesion.",
            "Sube carga cuando completes todas las repeticiones con buena tecnica.",
            "Deja 1-2 repeticiones en reserva en ejercicios principales.",
        ],
    }


def _demo_nutrition_payload() -> dict[str, Any]:
    start = date.today()
    day_names = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
    meal_template = [
        ("Desayuno", "Avena + yogurt griego + fruta", 520),
        ("Comida", "Pollo, arroz y ensalada", 780),
        ("Cena", "Tortilla de huevo con verduras y pan integral", 620),
    ]

    days = []
    for offset in range(7):
        current = start + timedelta(days=offset)
        days.append(
            {
                "dia": day_names[current.weekday()],
                "fecha": current.isoformat(),
                "calorias_objetivo": 2100,
                "comidas": [
                    {"tipo": meal_name, "menu": menu, "kcal_aprox": kcal}
                    for meal_name, menu, kcal in meal_template
                ],
            }
        )

    return {
        "feature": "nutricion",
        "plan_nombre": "Demo Nutricion Balanceada (7 dias)",
        "objetivo": "Deficit moderado",
        "calorias_objetivo": 2100,
        "macros_diarios": {"proteina_g": 165, "carbohidratos_g": 220, "grasas_g": 65},
        "dias": days,
        "notas": [
            "Hidratacion sugerida: 30-35 ml de agua por kg de peso corporal.",
            "Cambia una comida por equivalentes segun disponibilidad.",
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
        "cta": "Crea tu cuenta y actualiza a premium para liberar todo el potencial.",
    }


def _build_demo_payload(feature: str) -> dict[str, Any]:
    if feature == "rutina":
        payload = _demo_routine_payload()
    elif feature == "nutricion":
        payload = _demo_nutrition_payload()
    elif feature == "beneficios":
        payload = _demo_benefits_payload()
    else:
        raise HTTPException(status_code=400, detail="feature must be one of: rutina, nutricion, beneficios")

    payload["generated_at"] = datetime.now(UTC).isoformat()
    return payload


def _build_demo_html() -> str:
    return """<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Gym API Demo</title>
    <style>
      :root {
        --bg: #0e1116;
        --card: #171c25;
        --muted: #91a0b6;
        --text: #e8edf7;
        --primary: #2e90fa;
        --ok: #2ea043;
        --border: #2a3445;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Segoe UI", Arial, sans-serif;
        background: radial-gradient(circle at top right, #1e293b 0%, var(--bg) 60%);
        color: var(--text);
      }
      .wrap {
        max-width: 1100px;
        margin: 28px auto;
        padding: 0 16px 24px;
      }
      .hero, .panel {
        background: rgba(23, 28, 37, 0.94);
        border: 1px solid var(--border);
        border-radius: 16px;
      }
      .hero {
        padding: 20px;
        margin-bottom: 16px;
      }
      .hero h1 {
        margin: 0 0 8px;
      }
      .hero p {
        margin: 0;
        color: var(--muted);
      }
      .buttons {
        margin-top: 14px;
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
      }
      button {
        border: 0;
        border-radius: 10px;
        padding: 10px 16px;
        background: var(--primary);
        color: #fff;
        font-size: 15px;
        font-weight: 600;
        cursor: pointer;
      }
      button:hover { opacity: 0.92; }
      .grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
      }
      .panel {
        padding: 16px;
      }
      .panel h2 {
        margin: 0 0 10px;
      }
      .muted {
        color: var(--muted);
        font-size: 14px;
      }
      pre {
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        background: #0c1018;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 12px;
        min-height: 240px;
      }
      .line {
        padding: 8px 0;
        border-bottom: 1px dashed var(--border);
      }
      .line:last-child { border-bottom: none; }
      .ok { color: #9de6aa; }
      @media (max-width: 920px) {
        .grid { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <div class="wrap">
      <section class="hero">
        <h1>Gym API Demo Publica</h1>
        <p>Un solo endpoint: esta pagina y la data JSON salen desde <code>/v1/demo</code>.</p>
        <div class="buttons">
          <button data-feature="rutina">Rutina</button>
          <button data-feature="nutricion">Nutricion</button>
          <button data-feature="beneficios">Beneficios</button>
        </div>
      </section>
      <section class="grid">
        <article class="panel">
          <h2>Vista bonita</h2>
          <div class="muted" id="meta-text">Presiona un boton para cargar datos de demo.</div>
          <div id="pretty-output"></div>
        </article>
        <article class="panel">
          <h2>JSON crudo</h2>
          <pre id="json-output">{}</pre>
        </article>
      </section>
    </div>
    <script>
      const pretty = document.getElementById("pretty-output");
      const raw = document.getElementById("json-output");
      const meta = document.getElementById("meta-text");
      const endpointPath = window.location.pathname;

      function dayLine(day) {
        const exercises = (day.ejercicios || [])
          .map((item) => `${item.nombre} (${item.series_reps})`)
          .join(", ");
        return `<div class="line"><strong>Dia:</strong> ${day.dia || "-"} | <strong>Fecha:</strong> ${day.fecha || "-"}<br/><strong>Trabajo:</strong> ${day.enfoque || "-"}<br/><strong>Ejercicios:</strong> ${exercises || "-"}</div>`;
      }

      function mealLine(day) {
        const meals = (day.comidas || [])
          .map((item) => `${item.tipo}: ${item.menu} (${item.kcal_aprox} kcal)`)
          .join(" | ");
        return `<div class="line"><strong>Dia:</strong> ${day.dia || "-"} | <strong>Fecha:</strong> ${day.fecha || "-"}<br/><strong>Comidas:</strong> ${meals || "-"}</div>`;
      }

      function renderPretty(data) {
        if (data.feature === "rutina") {
          const days = (data.dias || []).map(dayLine).join("");
          pretty.innerHTML = `
            <p><strong>Plan:</strong> ${data.plan_nombre || "-"}</p>
            <p><strong>Objetivo:</strong> ${data.objetivo || "-"}</p>
            <p><strong>Nivel:</strong> ${data.nivel || "-"}</p>
            <p class="ok"><strong>Salida bonita + salida JSON activas.</strong></p>
            ${days}
          `;
          return;
        }
        if (data.feature === "nutricion") {
          const days = (data.dias || []).map(mealLine).join("");
          const macros = data.macros_diarios || {};
          pretty.innerHTML = `
            <p><strong>Plan:</strong> ${data.plan_nombre || "-"}</p>
            <p><strong>Objetivo:</strong> ${data.objetivo || "-"}</p>
            <p><strong>Macros:</strong> Proteina ${macros.proteina_g || 0}g, Carbohidratos ${macros.carbohidratos_g || 0}g, Grasas ${macros.grasas_g || 0}g</p>
            <p class="ok"><strong>Salida bonita + salida JSON activas.</strong></p>
            ${days}
          `;
          return;
        }
        if (data.feature === "beneficios") {
          pretty.innerHTML = `
            <div class="line"><strong>Free:</strong> Rutinas: ${data.free?.rutinas || "-"} | Nutricion: ${data.free?.nutricion || "-"} | Seguimiento: ${data.free?.seguimiento || "-"}</div>
            <div class="line"><strong>Premium:</strong> Rutinas: ${data.premium?.rutinas || "-"} | Nutricion: ${data.premium?.nutricion || "-"} | Seguimiento: ${data.premium?.seguimiento || "-"}</div>
            <div class="line"><strong>CTA:</strong> ${data.cta || "-"}</div>
            <p class="ok"><strong>Salida bonita + salida JSON activas.</strong></p>
          `;
          return;
        }
        pretty.textContent = "No hay informacion para mostrar.";
      }

      async function fetchFeature(feature) {
        const url = `${endpointPath}?response=json&feature=${encodeURIComponent(feature)}`;
        meta.textContent = `Consultando: ${url}`;
        try {
          const response = await fetch(url);
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.detail || `HTTP ${response.status}`);
          }
          renderPretty(data);
          raw.textContent = JSON.stringify(data, null, 2);
        } catch (error) {
          pretty.innerHTML = `<p><strong>Error:</strong> ${error.message}</p>`;
          raw.textContent = JSON.stringify({ error: error.message }, null, 2);
        }
      }

      document.querySelectorAll("button[data-feature]").forEach((button) => {
        button.addEventListener("click", () => fetchFeature(button.dataset.feature));
      });

      fetchFeature("rutina");
    </script>
  </body>
</html>
"""


@router.get("/demo", response_class=HTMLResponse)
async def demo(
    response: str = Query(default="html"),
    feature: str | None = Query(default=None),
):
    """
    Single endpoint demo:
    - /v1/demo -> HTML with buttons
    - /v1/demo?response=json&feature=rutina|nutricion|beneficios -> JSON
    """
    if response.lower() == "json":
        if not feature:
            raise HTTPException(status_code=400, detail="feature query param is required when response=json")
        return JSONResponse(content=_build_demo_payload(feature.lower()))
    return HTMLResponse(content=_build_demo_html())

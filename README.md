# Gym API SaaS (FastAPI + PostgreSQL + Docker)

API profesional para gimnasio con sistema `free/premium`, generación de rutinas y planes alimenticios personalizados, seguimiento de progreso, membresías, límites de consumo y base preparada para pagos/webhooks.

## 1) Stack técnico

- `Python 3.11`
- `FastAPI`
- `SQLAlchemy 2.0 + Alembic`
- `PostgreSQL 16`
- `Redis 7` (rate limiting, límites y cola)
- `Celery` (workers)
- `Docker + docker-compose`

## 2) Arquitectura

```text
Frontend local (localhost)
  -> HTTPS / CORS
  -> FastAPI (/v1)
     -> PostgreSQL (transaccional + historial + auditoría)
     -> Redis (rate limit / consumo / broker)
     -> Celery worker (tareas pesadas)
     -> Object storage (fotos de progreso, vía URL firmada en producción)
     -> Pasarela de pagos (webhook listo)
```

## 3) Módulos incluidos

- `auth`: registro, login, refresh, logout, reset, verificación de correo.
- `users`: perfil completo físico, preferencias, seguridad y estado.
- `memberships`: plan actual, suscripción, cancelación.
- `routines`: generación con reglas, regeneración premium, historial, jobs.
- `nutrition`: cálculo de calorías/macros, plan de comidas, shopping list, ajustes premium.
- `progress`: peso, medidas, fuerza, check-ins, fotos, resumen.
- `usage`: consumo y contadores por feature.
- `billing`: webhook de pago y registro de transacciones.
- `jobs`: estado unificado de generación.

## 4) Reglas de negocio implementadas

- Free:
  - Generación de rutina y nutrición limitada por ventanas de tiempo (entitlements).
  - Cooldown configurable.
- Premium:
  - Regeneración/ajustes adicionales por cuota mensual.
  - Historial ampliado.
- Seguridad funcional:
  - JWT access token corto + refresh token rotatorio hasheado en DB.
  - Hash Argon2 para contraseña.
  - Rate limiting para login/registro.
  - Validación de membresía y entitlements en backend.
  - CORS para frontend local + producción.
- Riesgo de salud:
  - Si usuario requiere supervisión profesional, se bloquea generación automática.

## 5) Endpoints principales

### Auth
- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `POST /v1/auth/refresh`
- `POST /v1/auth/logout`
- `POST /v1/auth/forgot-password`
- `POST /v1/auth/reset-password`
- `POST /v1/auth/verify-email`

### Usuario
- `GET /v1/users/me`
- `PATCH /v1/users/me`
- `POST /v1/users/me/onboarding`
- `GET /v1/users/me/state`
- `GET /v1/users/me/limits`
- `GET /v1/users/me/history`

### Rutinas
- `POST /v1/routines/generations`
- `POST /v1/routines/{plan_id}/regenerate` (premium)
- `GET /v1/routines/current`
- `GET /v1/routines/history`
- `GET /v1/routines/jobs/{job_id}`

### Nutrición
- `POST /v1/nutrition/plans/generations`
- `POST /v1/nutrition/plans/{plan_id}/adjust` (premium)
- `GET /v1/nutrition/plans/current`
- `GET /v1/nutrition/plans/history`
- `GET /v1/nutrition/plans/{plan_id}/shopping-list` (premium)
- `GET /v1/nutrition/plans/jobs/{job_id}`

### Progreso
- `POST /v1/progress/weights`
- `POST /v1/progress/measurements`
- `POST /v1/progress/strength`
- `POST /v1/progress/checkins`
- `POST /v1/progress/photos/presign`
- `GET /v1/progress/summary`

### Membresías/uso/pagos
- `GET /v1/memberships/current`
- `POST /v1/memberships/subscribe`
- `POST /v1/memberships/cancel`
- `GET /v1/usage/me`
- `POST /v1/billing/webhooks/stripe`
- `GET /v1/jobs/{job_id}`
- `GET /v1/health`

## 6) Estructura del proyecto

```text
app/
  api/v1/endpoints/
  core/
  db/models/
  schemas/
  services/
    routine_engine/
    nutrition_engine/
  workers/
alembic/
tests/
Dockerfile
docker-compose.yml
```

## 7) Levantar local con Docker

1. Copiar variables de entorno si falta:
```bash
cp .env.example .env
```
La configuracion por defecto de `.env` ya viene preparada para Docker (`db` y `redis` como hosts internos de compose).

2. Construir y levantar:
```bash
docker compose up --build
```

3. Documentación OpenAPI:
- `http://localhost:8000/v1/docs`

## 8) Levantar local sin Docker (Windows nativo)

Si no quieres activar Hyper-V/WSL, puedes correr la API sin contenedores.

Requisitos minimos:
- Python 3.11+
- PostgreSQL (local instalado en Windows o remoto en la nube)
- Redis opcional en desarrollo (hay fallback en memoria para rate limiting)

Pasos:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Configura `.env`:
- `DATABASE_URL=postgresql+psycopg://usuario:password@localhost:5432/gym_api`
- `REDIS_URL=redis://localhost:6379/0` (opcional)
- `ALLOW_INMEMORY_RATE_LIMIT_FALLBACK=true`

Levanta la API:
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Documentacion:
- `http://localhost:8000/v1/docs`

## 9) Migraciones

El proyecto trae configuración Alembic. En desarrollo local también crea tablas al arrancar (`app_env=development`).

Comandos recomendados:
```bash
alembic revision --autogenerate -m "init"
alembic upgrade head
```

## 10) Producción (Render o Cloud Run)

- Desactivar `app_debug`.
- Ejecutar migraciones con Alembic en pipeline antes del deploy.
- Usar Postgres gestionado y Redis gestionado.
- Configurar dominio: `api.midominio.com`.
- Forzar HTTPS.
- Guardar secretos en secret manager del proveedor.
- Mover fotos a bucket externo (S3/Cloud Storage/R2).
- Añadir observabilidad (`Sentry`, logs JSON, métricas).

## 11) Advertencia de salud (disclaimer)

Esta API no sustituye médico, nutriólogo ni entrenador profesional. El sistema debe mostrar advertencias para lesiones, enfermedades y condiciones especiales antes de recomendaciones automáticas.
"# api-gym" 

# Gym API Yeka

Proyecto de unidad para la universidad. Esta API de gimnasio implementa sistema `free/premium`, generación de rutinas y planes alimenticios, seguimiento de progreso, membresías y límites de consumo.

> Nota académica: este repositorio es un trabajo universitario (no se presenta como producto comercial final).

## Novedades recientes

- Se agrego `GET /v1/admin/sql-import` para consultar formatos JSON listos para Postman.
- `POST /v1/admin/sql-import` y `PUT /v1/admin/sql-import` permiten crear/editar usuarios por email (upsert).
- `DELETE /v1/admin/sql-import` permite borrar usuario; en uso basico solo requiere `user_id`.
- Ajuste de membresia: al importar `plan_code: "free"` se reemplaza la membresia activa por una free activa.

## Evidencias visuales

### 1) Health
Endpoint: `GET /v1/health`

![Evidencia Health](docs/images/evidencia-health.svg)

### 2) Rutinas (demo)
Endpoint: `GET /v1/demo?response=json&feature=rutina&device_id=demo-a1`

![Evidencia Rutina](docs/images/evidencia-rutina.svg)

### 3) Plan alimenticio (demo)
Endpoint: `GET /v1/demo?response=json&feature=nutricion&device_id=demo-a1`

![Evidencia Nutricion](docs/images/evidencia-nutricion.svg)

### 4) Datos de base de datos (demo SQL)
Endpoint: `GET /v1/demo?response=json&feature=sql`

![Evidencia SQL DB](docs/images/evidencia-sql-db.svg)

### 5) Creación/edición por import (Postman)
Endpoint: `POST /v1/admin/sql-import` o `PUT /v1/admin/sql-import`

![Evidencia Import Postman](docs/images/evidencia-import-postman.svg)

### 6) Eliminación desde API (DELETE)
Endpoint: `DELETE /v1/admin/sql-import`

![Evidencia Delete](docs/images/evidencia-delete.svg)

### 7) Dashboard de demo
Endpoint: `GET /v1/demo`

![Evidencia Demo Dashboard](docs/images/evidencia-demo-dashboard.svg)

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
  - Si usuario requiere supervisión especializada, se bloquea generación automática.

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

### Admin import SQL (controlado)
- `GET /v1/admin/sql-import`
- `PUT /v1/admin/sql-import`
- `POST /v1/admin/sql-import`
- `DELETE /v1/admin/sql-import`
  - Si `ADMIN_IMPORT_REQUIRE_KEY=true`, requiere `ADMIN_IMPORT_KEY` por alguno de estos medios:
    - header `X-Admin-Import-Key` (recomendado)
    - body JSON `admin_import_key`
    - query param `?admin_import_key=...`
  - Si `ADMIN_IMPORT_REQUIRE_KEY=false`, no pide llave.
  - Acepta dos modos:
    - `sql`: solo permite `INSERT` y `UPDATE`
    - `users`: importa usuarios/membresias desde JSON y genera `id` automatico
  - `GET` devuelve formatos JSON listos para consumir en Postman.
  - `DELETE`: para borrado rapido solo necesitas `user_id` en el body.
  - En modo `users`, ambos metodos (`POST` y `PUT`) hacen upsert:
    - si el correo no existe -> crea usuario
    - si el correo existe -> actualiza nombre, telefono, estado y plan
  - Tablas permitidas:
    - `users`
    - `user_memberships`
    - `user_physical_profiles`
    - `user_training_preferences`
    - `user_nutrition_preferences`
    - `user_safety_profiles`

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
- `ENABLE_SQL_IMPORT_ENDPOINT=true` (solo para carga manual controlada)
- `ADMIN_IMPORT_REQUIRE_KEY=false` (solo demo; en produccion usar `true`)
- `ADMIN_IMPORT_KEY=tu_llave_super_segura`

Levanta la API:
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Documentacion:
- `http://localhost:8000/v1/docs`

### Ejemplo de uso del import SQL (Postman)

Formato JSON por `GET` (consulta directa tipo API publica en Postman):
- `GET /v1/admin/sql-import?view=template`
- `GET /v1/admin/sql-import?view=users`
- `GET /v1/admin/sql-import?view=delete`
- `GET /v1/admin/sql-import?view=sql`
- `GET /v1/admin/sql-import?view=db_schema`

URLs completas (produccion):
- `https://api.xanderssj.xyz/v1/admin/sql-import?view=template`
- `https://api.xanderssj.xyz/v1/admin/sql-import?view=users`
- `https://api.xanderssj.xyz/v1/admin/sql-import?view=delete`
- `https://api.xanderssj.xyz/v1/admin/sql-import?view=sql`
- `https://api.xanderssj.xyz/v1/admin/sql-import?view=db_schema`

Si quieres ver datos reales de BD en JSON:
- `GET /v1/demo?response=json&feature=sql`

Request:
- Metodo: `PUT` o `POST`
- URL: `http://localhost:8000/v1/admin/sql-import`
- Headers:
  - `Content-Type: application/json`
  - `X-Admin-Import-Key: tu_llave_super_segura` (opcional; no se necesita si `ADMIN_IMPORT_REQUIRE_KEY=false`)

Body JSON (modo SQL):
```json
{
  "dry_run": false,
  "sql": "INSERT INTO users (full_name, email, phone, password_hash, status, email_verified_at, created_at, updated_at) VALUES ('Alumno Demo', 'alumno_demo@gym.local', '5551234567', '$argon2id$v=19$m=65536,t=3,p=4$demo_hash', 'active', NOW(), NOW(), NOW());"
}
```

Nota:
- El endpoint no ejecuta `DROP/DELETE/ALTER`.
- Para `users`, puedes omitir `id` y Postgres lo genera automaticamente.

Body JSON (modo usuarios desde JSON):
```json
{
  "admin_import_key": "tu_llave_super_segura",
  "dry_run": false,
  "auto_verify_email": true,
  "default_password": "1234567890",
  "users": [
    {
      "full_name": "Phone Check",
      "email": "phonecheck_c2f7a93e@example.com",
      "phone": "5551234567",
      "membership": {
        "plan_code": "premium_monthly"
      }
    }
  ]
}
```

Notas del modo usuarios:
- No necesitas mandar `user_id`; se genera automaticamente.
- Con `auto_verify_email=true` quedan verificados y no se pide verificacion de correo.
- Si no mandas `membership.plan_code`, se asigna `free`.
- Si mandas `membership.plan_code: "free"`, el import reemplaza la membresia activa actual por una `free` activa.
- Para editar un usuario existente, envia el mismo `email` con nuevos valores en:
  - `full_name`
  - `phone`
  - `membership.plan_code` (por ejemplo `premium_monthly` o `free`)

Ejemplo de borrado (DELETE) minimo requerido:
```json
{
  "user_id": "b0a76620-0a52-4bb7-be2d-1d544031baf0"
}
```

Ejemplo opcional avanzado (soft delete):
```json
{
  "user_id": "b0a76620-0a52-4bb7-be2d-1d544031baf0",
  "hard_delete": false,
  "dry_run": false
}
```

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

### Deploy rapido en Render (desde este repo)

1. En Render, crea un **Blueprint** desde el repo GitHub y usa el archivo `render.yaml`.
2. El Blueprint crea:
- `gym-api-web` (API)
- `gym-api-worker` (Celery)
- `gym-api-db` (PostgreSQL)
- `gym-api-redis` (Key Value)
3. En Render, completa estas variables manuales en **web** y **worker**:
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `SECRET_KEY` (usar el mismo valor en web y worker)
- `PAYMENT_WEBHOOK_SECRET` (si aplica)
4. Ajusta CORS con tu dominio real:
- `CORS_ORIGINS=https://xanderssj.xyz,http://localhost:3000,http://localhost:5173`
5. Haz deploy y prueba:
- `https://<tu-servicio>.onrender.com/v1/health`

### Dominio personalizado para API

Para usar `api.xanderssj.xyz`:

1. En Render, abre el servicio `gym-api-web` -> `Settings` -> `Custom Domains`.
2. Agrega `api.xanderssj.xyz`.
3. Render te mostrará el destino CNAME (ejemplo: `something.onrender.com`).
4. En tu proveedor DNS, crea:
- `Type`: `CNAME`
- `Host/Name`: `api`
- `Target`: el valor `onrender.com` que te dio Render
5. Espera propagación DNS y verifica `https://api.xanderssj.xyz/v1/health`.

Nota DNS importante:
- Para un subdominio (`api.xanderssj.xyz`) normalmente se usa **CNAME**, no IP fija.
- No hay una IP estática recomendada para enlazar manualmente en este caso.

## 11) Advertencia de salud (disclaimer)

Esta API no sustituye médico, nutriólogo ni entrenador. El sistema debe mostrar advertencias para lesiones, enfermedades y condiciones especiales antes de recomendaciones automáticas.

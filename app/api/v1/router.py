from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import auth, billing, demo, health, jobs, memberships, nutrition, progress, routines, usage, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(demo.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(memberships.router)
api_router.include_router(routines.router)
api_router.include_router(nutrition.router)
api_router.include_router(progress.router)
api_router.include_router(usage.router)
api_router.include_router(billing.router)
api_router.include_router(jobs.router)

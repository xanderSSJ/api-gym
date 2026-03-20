from __future__ import annotations

from app.core.exceptions import bad_request
from app.schemas.routines import RoutineGenerationRequest


def validate_request(payload: RoutineGenerationRequest) -> None:
    if payload.frequency_per_week < 2:
        raise bad_request("La frecuencia minima es 2 dias por semana.")
    if payload.minutes_per_session < 20:
        raise bad_request("El tiempo minimo por sesion es 20 minutos.")
    if payload.weeks < 2:
        raise bad_request("La duracion minima del plan es 2 semanas.")

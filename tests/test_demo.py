import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def force_inmemory_rate_limit_fallback() -> None:
    original = settings.allow_inmemory_rate_limit_fallback
    settings.allow_inmemory_rate_limit_fallback = True
    try:
        yield
    finally:
        settings.allow_inmemory_rate_limit_fallback = original


def test_demo_html_page() -> None:
    client = TestClient(app)
    response = client.get("/v1/demo")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Gym API Demo" in response.text
    assert "Rutina" in response.text
    assert "Nutricion" in response.text
    assert "Beneficios" in response.text
    assert "Datos SQL" in response.text


def test_demo_json_routine() -> None:
    client = TestClient(app)
    device_id = f"device-{uuid.uuid4()}"
    response = client.get(
        f"/v1/demo?response=json&feature=rutina&device_id={device_id}",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["feature"] == "rutina"
    assert "dias" in body
    assert isinstance(body["dias"], list)
    assert len(body["dias"]) >= 1
    first_day = body["dias"][0]
    assert "ejercicios" in first_day
    assert isinstance(first_day["ejercicios"], list)
    assert len(first_day["ejercicios"]) >= 1
    first_ex = first_day["ejercicios"][0]
    assert "series" in first_ex
    assert "repeticiones" in first_ex
    assert "descanso_segundos" in first_ex
    assert body["demo_policy"]["quota"] == 2
    assert body["demo_policy"]["window_days"] == 15
    assert body["demo_policy"]["scope"] == "device"
    assert body["demo_policy"]["variation_strategy"] == "non_repeating_by_device"


def test_demo_json_nutrition_is_7_days() -> None:
    client = TestClient(app)
    device_id = f"device-{uuid.uuid4()}"
    response = client.get(
        f"/v1/demo?response=json&feature=nutricion&device_id={device_id}",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["feature"] == "nutricion"
    assert len(body["dias"]) == 7
    first_day = body["dias"][0]
    assert "comidas" in first_day
    assert isinstance(first_day["comidas"], list)
    assert len(first_day["comidas"]) >= 1
    first_meal = first_day["comidas"][0]
    assert "alimentos" in first_meal
    assert isinstance(first_meal["alimentos"], list)
    assert len(first_meal["alimentos"]) >= 1


def test_demo_variation_changes_between_two_calls_same_device() -> None:
    client = TestClient(app)
    device_id = f"device-{uuid.uuid4()}"

    first = client.get(f"/v1/demo?response=json&feature=rutina&device_id={device_id}")
    second = client.get(f"/v1/demo?response=json&feature=rutina&device_id={device_id}")

    assert first.status_code == 200
    assert second.status_code == 200
    body_a = first.json()
    body_b = second.json()
    assert body_a["variation_id"] != body_b["variation_id"]
    assert body_a["dias"][0]["ejercicios"] != body_b["dias"][0]["ejercicios"] or body_a["plan_nombre"] != body_b["plan_nombre"]


def test_demo_quota_limit_for_routine_per_device() -> None:
    client = TestClient(app)
    device_id = f"device-{uuid.uuid4()}"

    first = client.get(f"/v1/demo?response=json&feature=rutina&device_id={device_id}")
    second = client.get(f"/v1/demo?response=json&feature=rutina&device_id={device_id}")
    third = client.get(f"/v1/demo?response=json&feature=rutina&device_id={device_id}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert "Demo free limit reached" in third.json()["detail"]


def test_demo_quota_isolated_between_devices() -> None:
    client = TestClient(app)
    device_a = f"device-{uuid.uuid4()}"
    device_b = f"device-{uuid.uuid4()}"

    _ = client.get(f"/v1/demo?response=json&feature=rutina&device_id={device_a}")
    _ = client.get(f"/v1/demo?response=json&feature=rutina&device_id={device_a}")
    blocked = client.get(f"/v1/demo?response=json&feature=rutina&device_id={device_a}")
    fresh = client.get(f"/v1/demo?response=json&feature=rutina&device_id={device_b}")

    assert blocked.status_code == 429
    assert fresh.status_code == 200


def test_demo_json_requires_feature() -> None:
    client = TestClient(app)
    response = client.get("/v1/demo?response=json")
    assert response.status_code == 400
    assert "feature" in response.json()["detail"]

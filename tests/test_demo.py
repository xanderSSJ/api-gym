from fastapi.testclient import TestClient

from app.main import app


def test_demo_html_page() -> None:
    client = TestClient(app)
    response = client.get("/v1/demo")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Gym API Demo Publica" in response.text
    assert "Rutina" in response.text
    assert "Nutricion" in response.text
    assert "Beneficios" in response.text


def test_demo_json_routine() -> None:
    client = TestClient(app)
    response = client.get("/v1/demo?response=json&feature=rutina")
    assert response.status_code == 200
    body = response.json()
    assert body["feature"] == "rutina"
    assert "dias" in body
    assert isinstance(body["dias"], list)
    assert len(body["dias"]) >= 1


def test_demo_json_requires_feature() -> None:
    client = TestClient(app)
    response = client.get("/v1/demo?response=json")
    assert response.status_code == 400
    assert "feature" in response.json()["detail"]

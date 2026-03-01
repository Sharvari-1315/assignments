from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_create_todo():
    response = client.post("/todos/test")
    assert response.status_code == 200

def test_get_all():
    response = client.get("/todos")
    assert response.status_code == 200

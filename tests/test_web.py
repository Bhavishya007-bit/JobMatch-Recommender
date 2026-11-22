from fastapi.testclient import TestClient

from app import app


def test_homepage_served_outside_project_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert 'id="search-form"' in response.text
        assert client.get("/docs").status_code == 200

# PROMPT: Create unit tests for FastAPI exception handlers verifying database connection failures (OperationalError) yield a structured HTTP 503 Service Unavailable response instead of crash stacks.
# CHANGES MADE: Integrated pytest and TestClient, mocked OperationalError in route dependencies, and verified JSON content structure and HTTP status code.

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.main import app
from app.database import get_db

@pytest.fixture(name="client_with_broken_db")
def fixture_client_with_broken_db():
    def override_get_db_broken():
        # Mock database connection failure
        raise OperationalError("Mock Connection Timeout", params=None, orig=None)
    
    app.dependency_overrides[get_db] = override_get_db_broken
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_database_unavailable_returns_503(client_with_broken_db):
    """
    Test that a database OperationalError returns a structured HTTP 503 response.
    """
    response = client_with_broken_db.get("/stores/ST1076/metrics")
    
    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "Database Unavailable"
    assert "unreachable" in data["message"].lower()

def test_health_endpoint_on_db_failure(client_with_broken_db):
    """
    Test that health endpoint returns 503 or degrades gracefully when DB is down.
    """
    response = client_with_broken_db.get("/health")
    assert response.status_code == 503

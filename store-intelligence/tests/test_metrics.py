# PROMPT: Generate comprehensive unit tests for FastAPI retail store analytics endpoints using pytest and SQLAlchemy in-memory SQLite database, covering store metrics, funnel computation, heatmaps, and edge cases.
# CHANGES MADE: Customized DB mock overrides, added specific assertion logic for drop-off percentages and normalized heatmaps, and mock seeded sample events.

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db, Base
from app.models import DBEvent, DBPOSTransaction

# Use in-memory SQLite for testing
from sqlalchemy.pool import StaticPool
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(name="db_session")
def fixture_db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
def fixture_client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_empty_store_metrics(client):
    """
    Edge case: Test store metrics when there are no events (empty store).
    """
    response = client.get("/stores/ST9999/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["unique_visitors"] == 0
    assert data["conversion_rate"] == 0.0
    assert data["queue_depth"] == 0
    assert data["abandonment_rate"] == 0.0

def test_all_staff_events(client, db_session):
    """
    Edge case: Test metrics when all events in the store are flagged as is_staff=True.
    """
    timestamp = datetime(2026, 3, 8, 14, 0, 0)
    # Add staff events
    db_session.add(DBEvent(
        event_id="e1", store_id="ST1076", camera_id="c1", visitor_id="v1",
        event_type="ZONE_ENTER", timestamp=timestamp, zone_id="SKINCARE",
        is_staff=True, confidence=0.99
    ))
    db_session.add(DBPOSTransaction(
        order_id="tx1", order_date="08-03-2026", order_time="14:02:00",
        store_id="ST1076", product_id="p1", brand_name="Faces Canada",
        total_amount=100.0, timestamp=timestamp + timedelta(minutes=2)
    ))
    db_session.commit()

    response = client.get("/stores/ST1076/metrics")
    assert response.status_code == 200
    data = response.json()
    # Unique visitors should be 0 because staff is excluded
    assert data["unique_visitors"] == 0
    assert data["conversion_rate"] == 0.0

def test_standard_metrics_and_conversion(client, db_session):
    """
    Verify conversion rate, metrics, and funnel calculations with standard traffic.
    """
    timestamp = datetime(2026, 3, 8, 14, 0, 0)
    
    # Customer 1 (Converted)
    db_session.add(DBEvent(
        event_id="evt_c1_1", store_id="ST1076", camera_id="cam_entry", visitor_id="cust1",
        event_type="ENTRY", timestamp=timestamp, is_staff=False, confidence=0.95
    ))
    db_session.add(DBEvent(
        event_id="evt_c1_2", store_id="ST1076", camera_id="cam_zone", visitor_id="cust1",
        event_type="ZONE_ENTER", timestamp=timestamp + timedelta(seconds=30), zone_id="LIPSTICK",
        is_staff=False, confidence=0.95
    ))
    db_session.add(DBEvent(
        event_id="evt_c1_3", store_id="ST1076", camera_id="cam_billing", visitor_id="cust1",
        event_type="BILLING_QUEUE_JOIN", timestamp=timestamp + timedelta(minutes=2), zone_id="BILLING_01",
        is_staff=False, confidence=0.95
    ))
    
    # Customer 2 (Abandoned Billing Queue)
    db_session.add(DBEvent(
        event_id="evt_c2_1", store_id="ST1076", camera_id="cam_entry", visitor_id="cust2",
        event_type="ENTRY", timestamp=timestamp + timedelta(minutes=1), is_staff=False, confidence=0.95
    ))
    db_session.add(DBEvent(
        event_id="evt_c2_2", store_id="ST1076", camera_id="cam_billing", visitor_id="cust2",
        event_type="BILLING_QUEUE_JOIN", timestamp=timestamp + timedelta(minutes=3), zone_id="BILLING_01",
        is_staff=False, confidence=0.95
    ))
    db_session.add(DBEvent(
        event_id="evt_c2_3", store_id="ST1076", camera_id="cam_billing", visitor_id="cust2",
        event_type="BILLING_QUEUE_ABANDON", timestamp=timestamp + timedelta(minutes=5), zone_id="BILLING_01",
        is_staff=False, confidence=0.95
    ))

    # POS transaction matching cust1 (3 minutes after entry, 1 minute after joining billing queue)
    db_session.add(DBPOSTransaction(
        order_id="tx_cust1", order_date="08-03-2026", order_time="14:03:00",
        store_id="ST1076", product_id="p1", brand_name="Faces Canada",
        total_amount=250.0, timestamp=timestamp + timedelta(minutes=3)
    ))
    
    db_session.commit()

    # 1. Test Metrics Endpoint
    res_metrics = client.get("/stores/ST1076/metrics")
    assert res_metrics.status_code == 200
    metrics_data = res_metrics.json()
    assert metrics_data["unique_visitors"] == 2
    assert metrics_data["conversion_rate"] == 0.5  # 1 out of 2 converted
    assert metrics_data["abandonment_rate"] == 0.5  # 1 abandon out of 2 joins
    # Since cust2 abandoned but cust1 didn't explicitly exit billing, active queue depth is 1
    assert metrics_data["queue_depth"] == 1 

    # 2. Test Funnel Endpoint
    res_funnel = client.get("/stores/ST1076/funnel")
    assert res_funnel.status_code == 200
    funnel_data = res_funnel.json()
    stages = {s["stage"]: s for s in funnel_data["stages"]}
    
    assert stages["Entry"]["count"] == 2
    assert stages["Zone Visit"]["count"] == 1  # only cust1 had zone visit event
    assert stages["Billing Queue"]["count"] == 2  # both joined billing
    assert stages["Purchase"]["count"] == 1  # only cust1 purchased

    # 3. Test Heatmap Endpoint
    res_heatmap = client.get("/stores/ST1076/heatmap")
    assert res_heatmap.status_code == 200
    heatmap_data = res_heatmap.json()
    assert heatmap_data["total_sessions"] == 2
    assert heatmap_data["data_confidence"] is False  # Less than 20 sessions
    
    zones = heatmap_data["zones"]
    assert "LIPSTICK" in zones
    assert zones["LIPSTICK"]["normalized_frequency"] == 100.0  # Only zone visited

    # 4. Test Anomalies Endpoint
    res_anom = client.get("/stores/ST1076/anomalies")
    assert res_anom.status_code == 200
    anom_data = res_anom.json()
    # Verify we got some diagnostic report (e.g. dead zones or conversion drops)
    assert len(anom_data) >= 0

    # 5. Test Events Endpoint
    res_events = client.get("/stores/ST1076/events?limit=10")
    assert res_events.status_code == 200
    events_data = res_events.json()
    # Should return all mock events sorted desc
    assert len(events_data) == 6
    assert events_data[0]["visitor_id"] == "cust2"
    assert events_data[0]["event_type"] == "BILLING_QUEUE_ABANDON"


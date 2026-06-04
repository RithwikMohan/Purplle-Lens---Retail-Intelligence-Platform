import os
import time
import uuid
import logging
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, DBAPIError
from sqlalchemy import or_
from typing import List, Dict, Any

from .database import get_db, engine, Base
from .models import IngestPayloadSchema, EventSchema, DBEvent
from .ingestion import ingest_events_batch, import_pos_transactions_csv
from .metrics import get_store_metrics, get_store_heatmap, normalize_store_id
from .funnel import get_store_funnel
from .anomalies import detect_store_anomalies
from .health import get_system_health

# Initialize Logger
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("store_intelligence")

# Create FastAPI instance
app = FastAPI(
    title="Store Intelligence API",
    description="Real-time offline retail analytics API",
    version="1.0.0"
)

# Enable CORS for frontend dashboard connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure images directory exists and mount it
os.makedirs("images", exist_ok=True)
app.mount("/images", StaticFiles(directory="images"), name="images")

# Create tables and seed data on startup
@app.on_event("startup")
def startup_event():
    logger.info("Starting up Store Intelligence API...")
    # Initialize DB tables
    Base.metadata.create_all(bind=engine)
    
    # Import POS data
    db = next(get_db())
    try:
        import_pos_transactions_csv(db)
    except Exception as e:
        logger.error(f"Error seeding POS transactions: {e}")
    finally:
        db.close()

# ----------------- MIDDLEWARE: STRUCTURED LOGGING -----------------

@app.middleware("http")
async def structured_logging_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    start_time = time.time()
    
    # Extract store_id from path if available
    path_params = request.path_params
    store_id = path_params.get("id") or path_params.get("store_id") or "N/A"
    
    # Process request
    response = await call_next(request)
    
    # Calculate latency
    latency_ms = round((time.time() - start_time) * 1000.0, 2)
    
    # Log details
    log_data = {
        "trace_id": trace_id,
        "store_id": store_id,
        "endpoint": request.url.path,
        "method": request.method,
        "latency_ms": latency_ms,
        "status_code": response.status_code
    }
    
    logger.info(f"REQUEST_LOG: {log_data}")
    
    # Attach trace_id to response header
    response.headers["X-Trace-ID"] = trace_id
    return response

# ----------------- EXCEPTION HANDLERS (GRACEFUL DEGRADATION) -----------------

@app.exception_handler(OperationalError)
async def db_operational_error_handler(request: Request, exc: OperationalError):
    logger.error(f"Database OperationalError: {exc}")
    return JSONResponse(
        status_code=503,
        content={
            "error": "Database Unavailable",
            "message": "The store intelligence database is currently unreachable. Please try again later."
        }
    )

@app.exception_handler(DBAPIError)
async def db_api_error_handler(request: Request, exc: DBAPIError):
    logger.error(f"Database APIError: {exc}")
    return JSONResponse(
        status_code=503,
        content={
            "error": "Database Service Error",
            "message": "A database system error occurred. Please try again later."
        }
    )

# ----------------- API ENDPOINTS -----------------

@app.post("/events/ingest", status_code=200)
async def ingest_events(payload: IngestPayloadSchema, db: Session = Depends(get_db)):
    """
    Ingests batches of up to 500 events. Identifies duplicates, validates schema, 
    and handles partial ingestion success.
    """
    events = payload.events
    if len(events) > 500:
        raise HTTPException(status_code=400, detail="Batch size exceeds maximum limit of 500 events.")
    
    if not events:
        return {"processed": 0, "skipped": 0, "failed": 0, "errors": []}
    
    result = ingest_events_batch(db, events)
    return result


@app.get("/stores/{id}/metrics")
async def get_metrics(id: str, db: Session = Depends(get_db)):
    """
    Computes real-time store metrics for 'today': unique visitors, conversion rate,
    avg dwell times per zone, billing queue depth, and queue abandonment rate.
    """
    metrics = get_store_metrics(db, id)
    return metrics


@app.get("/stores/{id}/funnel")
async def get_funnel(id: str, db: Session = Depends(get_db)):
    """
    Computes conversion funnel analysis based on unique customer sessions:
    Entry -> Zone Visit -> Billing Queue -> Purchase.
    """
    funnel = get_store_funnel(db, id)
    return funnel


@app.get("/stores/{id}/heatmap")
async def get_heatmap(id: str, db: Session = Depends(get_db)):
    """
    Computes zone visit frequencies and dwell times, normalized 0-100.
    Returns low data confidence warning if fewer than 20 customer sessions are present.
    """
    heatmap = get_store_heatmap(db, id)
    return heatmap


@app.get("/stores/{id}/anomalies")
async def get_anomalies(id: str, db: Session = Depends(get_db)):
    """
    Returns active store anomalies such as queue spikes, dead zones, and conversion rate drops,
    with custom severities and suggested actions.
    """
    anomalies = detect_store_anomalies(db, id)
    return anomalies


@app.get("/stores/{id}/events")
async def get_recent_events(id: str, limit: int = 50, db: Session = Depends(get_db)):
    """
    Returns the most recently ingested events for a store, sorted chronologically descending.
    """
    normalized_sid = normalize_store_id(id)
    store_filter = or_(
        DBEvent.store_id == id,
        DBEvent.store_id.like(f"%{normalized_sid}%")
    )
    events = db.query(DBEvent).filter(store_filter).order_by(DBEvent.timestamp.desc(), DBEvent.id.desc()).limit(limit).all()
    return [
        {
            "event_id": e.event_id,
            "store_id": e.store_id,
            "camera_id": e.camera_id,
            "visitor_id": e.visitor_id,
            "event_type": e.event_type,
            "timestamp": e.timestamp.isoformat() + "Z" if e.timestamp else None,
            "zone_id": e.zone_id,
            "dwell_ms": e.dwell_ms,
            "is_staff": e.is_staff,
            "confidence": e.confidence,
            "metadata": {
                "queue_depth": e.queue_depth,
                "sku_zone": e.sku_zone,
                "session_seq": e.session_seq
            }
        }
        for e in events
    ]


@app.get("/health")
async def get_health(db: Session = Depends(get_db)):
    """
    Service liveness and readiness check. Checks event feed timeliness per store.
    """
    health = get_system_health(db)
    return health

# Purplle Store Intelligence System

Real-time retail analytics platform for physical Purplle stores — processing CCTV video and POS transactions into actionable insights via a live web dashboard.

---

## Quick Start

### 1. Install Python Dependencies

```powershell
cd d:\purple_hackathon\store-intelligence
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run the Pipeline (generates events from CCTV videos)

```powershell
# Store 2 (with simulation fallback if YOLO not available)
cd pipeline
python detect.py --store_id ST1076 --video_dir "d:\purple_hackathon\Store 2" --output events_store2.jsonl

# Store 1
python detect.py --store_id ST1008 --video_dir "d:\purple_hackathon\Store 1" --output events_store1.jsonl
```

### 3. Start the API Server

```powershell
cd d:\purple_hackathon\store-intelligence
.\venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The POS CSV is automatically imported on first startup.

### 4. Feed Pipeline Events into the API

```powershell
cd pipeline
python feed_to_api.py --jsonl events_store2.jsonl --api http://localhost:8000
```

### 5. Run the Real-Time Event Replayer (Live Dashboard Bonus)

To see the dashboard cards, charts, and event stream update live in real time, stream the events one-by-one with a time delay and speed multiplier (e.g., 5x speed):

```powershell
cd pipeline

# Option A: Align events to match POS transactions on 10-04-2026 (for conversion metrics)
python replay_realtime.py --jsonl events_store1.jsonl --api http://localhost:8000 --speed 5.0 --align-time 2026-04-10T12:10:00

# Option B: Run in LIVE mode (timestamps shift to start *now* in real time, showing 0-lag metrics)
python replay_realtime.py --jsonl events_store1.jsonl --api http://localhost:8000 --speed 5.0 --live
```

### 6. Open the Dashboard

Simply open `dashboard/index.html` in your browser:
```
d:\purple_hackathon\store-intelligence\dashboard\index.html
```

The dashboard auto-refreshes every **5 seconds** and connects to `http://localhost:8000`.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/events/ingest` | Batch ingest events (max 500 per call) |
| GET | `/stores/{id}/metrics` | Live store metrics |
| GET | `/stores/{id}/funnel` | Conversion funnel |
| GET | `/stores/{id}/heatmap` | Zone visit heatmap |
| GET | `/stores/{id}/anomalies` | Active anomalies |
| GET | `/health` | System health + feed freshness |

### Interactive Docs
Visit `http://localhost:8000/docs` for Swagger UI.

### Example: Ingest an Event

```bash
curl -X POST http://localhost:8000/events/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "event_id": "evt-001",
      "store_id": "ST1076",
      "camera_id": "CAM_ENTRY",
      "visitor_id": "VIS_abc123",
      "event_type": "ENTRY",
      "timestamp": "2026-03-08T18:12:00",
      "is_staff": false,
      "confidence": 0.97
    }]
  }'
```

---

## Store IDs

| Store | ID Used in API |
|-------|---------------|
| Store 1 | `ST1008` |
| Store 2 | `ST1076` |

The system normalizes store IDs, so `store_1076`, `STORE_BLR_1076`, etc. all match `ST1076`.

---

## Project Structure

```
store-intelligence/
├── app/                    # FastAPI backend
│   ├── __init__.py
│   ├── main.py             # API entrypoint + middleware
│   ├── models.py           # SQLAlchemy + Pydantic schemas
│   ├── database.py         # SQLite connection
│   ├── ingestion.py        # Batch event ingest + POS CSV import
│   ├── metrics.py          # Visitor/conversion/dwell/queue metrics
│   ├── funnel.py           # 4-stage conversion funnel
│   ├── anomalies.py        # Queue spike / dead zone / conversion drop
│   └── health.py           # System health endpoint
├── pipeline/               # CCTV processing pipeline
│   ├── detect.py           # YOLOv8 detection + zone logic
│   ├── tracker.py          # Cross-camera Re-ID tracker
│   ├── emit.py             # JSONL event emitter
│   ├── feed_to_api.py      # Push events to API
│   ├── run.sh              # Unix batch script
│   └── run.ps1             # Windows batch script
├── dashboard/              # Real-time web dashboard
│   ├── index.html          # Single-page dashboard
│   ├── style.css           # Premium dark theme CSS
│   └── app.js              # Polling + Chart.js visualization
├── tests/                  # Pytest test suite
│   ├── test_metrics.py
│   └── test_errors.py
├── docs/                   # Architecture documentation
│   ├── DESIGN.md           # System design + AI decisions
│   └── CHOICES.md          # Trade-off decisions
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Running Tests

```powershell
cd d:\purple_hackathon\store-intelligence
.\venv\Scripts\activate
pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## Docker Deployment

```powershell
docker compose up --build
```

This starts the API on port 8000. The dashboard can be opened as a static file.

---

## Dashboard Features

- **Store Toggle**: Switch between Store 1 and Store 2 live
- **KPI Cards**: Animated real-time metrics (visitors, conversion, queue, abandonment)
- **Live Chart**: Rolling 20-point time-series of visitors + queue depth
- **Conversion Funnel**: Entry → Zone Visit → Billing Queue → Purchase
- **Zone Heatmap**: Color-intensity grid of zone visit frequencies
- **Anomaly Panel**: Real-time alerts with severity levels and recommended actions
- **Event Stream**: Live scrolling feed of CCTV-derived events
- **Offline Mode**: Gracefully displays demo data when API is unreachable

---

## Architecture Summary

```
CCTV Videos → YOLOv8 Detection → Re-ID Tracker → JSONL Events
                                                        ↓
POS CSV ─────────────────────────────────────► FastAPI + SQLite
                                                        ↓
                                              Dashboard (HTML/JS)
                                         Real-time poll every 5s
```

See [`docs/DESIGN.md`](docs/DESIGN.md) for the full architecture and [`docs/CHOICES.md`](docs/CHOICES.md) for all design decisions.

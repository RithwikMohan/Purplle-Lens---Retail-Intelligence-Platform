# Design Document — Purplle Store Intelligence System

## Overview

This system ingests CCTV video streams and POS transactions from physical Purplle retail stores to produce a real-time analytics dashboard.  It answers: *Who entered? Where did they go? Did they buy?*

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  CCTV MP4 Clips   POS CSV Transactions   Sample Events   │
│        │                  │                    │          │
│        ▼                  ▼                    ▼          │
│  ┌───────────────────────────────────────────────────┐   │
│  │          PIPELINE  (pipeline/)                    │   │
│  │  detect.py (YOLOv8n CPU) → tracker.py (ReID)     │   │
│  │                → emit.py (JSONL events)           │   │
│  └───────────────────┬───────────────────────────────┘   │
│                      │ POST /events/ingest               │
│                      ▼                                   │
│  ┌───────────────────────────────────────────────────┐   │
│  │        FASTAPI APP  (app/)                        │   │
│  │  ingestion.py  ─►  SQLite DB                      │   │
│  │  metrics.py    ─►  /stores/{id}/metrics           │   │
│  │  funnel.py     ─►  /stores/{id}/funnel            │   │
│  │  metrics.py    ─►  /stores/{id}/heatmap           │   │
│  │  anomalies.py  ─►  /stores/{id}/anomalies         │   │
│  │  health.py     ─►  /health                        │   │
│  └───────────────────┬───────────────────────────────┘   │
│                      │ HTTP polling every 5s             │
│                      ▼                                   │
│  ┌───────────────────────────────────────────────────┐   │
│  │        DASHBOARD  (dashboard/)                    │   │
│  │  index.html + style.css + app.js                  │   │
│  │  Chart.js · KPI Cards · Zone Heatmap              │   │
│  │  Conversion Funnel · Anomaly Alerts               │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

---

## Pipeline Design

### Object Detection
- **Model**: YOLOv8 Nano (`yolov8n.pt`) — smallest model for CPU inference  
- **Frame Skip**: Every 15th frame (≈1 FPS from 15fps video) — reduces processing by 93%  
- **Class Filter**: COCO class 0 (`person`) only  

### Staff Detection
- Black top and black bottom HSV range detection on upper and lower body crops  
- HSV range: V <= 55 (low brightness representing black)  

### Cross-Camera Re-ID
- HSV color histogram (16-bin) extracted from each detected person  
- Cosine similarity matching across cameras  
- Threshold: 0.85 similarity for global visitor ID assignment  
- New visitor IDs: `VIS_<uuid4>`  

### Event Types Emitted
| Event | Trigger |
|-------|---------|
| `ENTRY` | Person crosses door threshold inbound |
| `EXIT` | Person crosses door threshold outbound |
| `REENTRY` | Entry after a prior exit |
| `ZONE_ENTER` | Person enters a product zone bounding box |
| `ZONE_EXIT` | Person leaves a zone; includes computed `dwell_ms` |
| `ZONE_DWELL` | Person remains in zone ≥ 30 seconds |
| `BILLING_QUEUE_JOIN` | Person detected in billing zone |
| `BILLING_QUEUE_ABANDON` | Person leaves billing zone without completing purchase |

---

## API Design

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/events/ingest` | Batch ingest ≤500 events with deduplication |
| GET | `/stores/{id}/metrics` | Visitors, conversion, dwell, queue depth |
| GET | `/stores/{id}/funnel` | 4-stage conversion funnel |
| GET | `/stores/{id}/heatmap` | Zone visit frequencies (normalized 0–100) |
| GET | `/stores/{id}/anomalies` | Active operational anomalies |
| GET | `/health` | Feed freshness per store |

### Graceful Degradation
- DB `OperationalError` → HTTP 503 (never 500 crash)  
- YOLO not installed → simulation fallback mode  
- All endpoints return structured JSON even when no data  

### Store ID Normalization
- `ST1008`, `store_1008`, `STORE_BLR_1008` → all match via digit extraction  
- Allows flexibility in how pipelines report store IDs  

---

## Database Schema

```sql
-- Events table (CCTV-derived)
CREATE TABLE events (
  id          INTEGER PRIMARY KEY,
  event_id    TEXT UNIQUE,      -- UUID for deduplication
  store_id    TEXT,
  camera_id   TEXT,
  visitor_id  TEXT,
  event_type  TEXT,
  timestamp   DATETIME,
  zone_id     TEXT,
  dwell_ms    INTEGER,
  is_staff    BOOLEAN,
  confidence  REAL,
  queue_depth INTEGER,
  sku_zone    TEXT,
  session_seq INTEGER
);

-- POS Transactions table  
CREATE TABLE pos_transactions (
  id           INTEGER PRIMARY KEY,
  order_id     TEXT,
  order_date   TEXT,
  order_time   TEXT,
  store_id     TEXT,
  product_id   TEXT,
  brand_name   TEXT,
  total_amount REAL,
  timestamp    DATETIME
);
```

---

## Metrics Computation

### Conversion Rate
Visitors who appear in the billing zone within ±5 minutes of a POS transaction, divided by total unique visitors.

### Average Dwell per Zone
ZONE_ENTER/ZONE_EXIT pairs are matched per visitor per zone. Duration = exit_time − enter_time. `ZONE_DWELL` events supplement with direct `dwell_ms`.

### Queue Depth
`BILLING_QUEUE_JOIN` visitors minus those who subsequently `EXIT` or `BILLING_QUEUE_ABANDON`.

### Abandonment Rate
`BILLING_QUEUE_ABANDON` events / total `BILLING_QUEUE_JOIN` events.

---

## Anomaly Detection Rules

| Anomaly | Condition | Severity |
|---------|-----------|----------|
| `BILLING_QUEUE_SPIKE` | Queue depth > 10 | CRITICAL |
| `BILLING_QUEUE_SPIKE` | Queue depth > 5 | WARN |
| `CONVERSION_DROP` | Today's rate < 50% of 7-day avg | CRITICAL |
| `CONVERSION_DROP` | Today's rate < 70% of 7-day avg | WARN |
| `DEAD_ZONE` | Zone has no new visits in 30+ mins | WARN |
| `DEAD_ZONE` | Zone has zero visits today | INFO |

---

## Dashboard

- **Tech**: Vanilla HTML/CSS/JS + Chart.js (no framework required)
- **Polling**: Every 5 seconds via `fetch()`
- **Stores**: Toggle between Store 1 (ST1008) and Store 2 (ST1076)
- **Offline Mode**: Gracefully renders demo data when API is unreachable

### Widgets
1. **KPI Cards**: Visitors · Conversion · Queue Depth · Abandonment (animated bump on update)
2. **Live Metrics Chart**: Time-series line chart of visitors + queue depth (last 20 data points)
3. **Conversion Funnel**: Entry → Zone Visit → Billing Queue → Purchase with drop-off %
4. **Zone Heatmap**: Color-coded zones by visit frequency; hover for dwell time
5. **Anomaly Panel**: Severity-colored alerts with suggested actions
6. **Event Stream**: Scrolling live feed of CCTV events

---

## AI-Assisted Design Decisions

The following decisions were made collaboratively with the AI coding assistant:

1. **YOLOv8 Nano + Frame Skip**: Chosen for CPU-only environments (no GPU required)
2. **HSV Color Histogram for Re-ID**: Lightweight alternative to deep learning embeddings; no CUDA required
3. **SQLite over PostgreSQL**: Zero-infrastructure setup; file-based; perfect for single-node hackathon deployment
4. **Cosine Similarity for Track Matching**: Standard for histogram comparison; tunable threshold
5. **5-Minute POS Correlation Window**: Pragmatic heuristic linking billing events to POS sales
6. **7-Day Historical Baseline**: Anomaly detection uses rolling 7-day average for conversion comparison

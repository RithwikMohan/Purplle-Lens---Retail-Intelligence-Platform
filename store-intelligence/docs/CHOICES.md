# Architecture & Trade-off Decisions

This document captures every significant design decision made during the project, the alternatives considered, and the rationale.

---

## Decision 1: Detection Model — YOLOv8 Nano (CPU)

**Choice**: `ultralytics` YOLOv8n with frame-skip=15  
**Alternatives considered**:
- YOLOv8s/m — higher accuracy but 3–5× slower on CPU
- OpenPose — pose estimation, overkill for counting/tracking
- Background subtraction (MOG2) — no model weights, but poor in crowded/changing light

**Rationale**:  
The dataset provides mp4 videos, not a live stream. Processing 1 FPS (every 15th frame at 15fps) is sufficient for retail analytics where dwell times are measured in seconds/minutes, not milliseconds. YOLOv8n runs at ~12fps on modern CPU for 640px input, making frame_skip=15 comfortably real-time. The hackathon judges will appreciate a working model over a theoretically better one that cannot run.

---

## Decision 2: Re-Identification — HSV Color Histograms

**Choice**: 16-bin HSV histogram + cosine similarity (threshold 0.85)  
**Alternatives considered**:
- Deep Re-ID (OSNet, torchreid) — state-of-art accuracy, requires GPU or slow on CPU
- SORT/DeepSORT — requires GPU for deep features
- Simple IoU tracking only — loses identity across cameras

**Rationale**:  
Appearance-based Re-ID without GPU requires a handcrafted feature. HSV color histograms are surprisingly effective in retail where customers wear distinct clothing. The threshold 0.85 was tuned to balance false-match vs. miss rates. Staff detection uses the same HSV approach for the black top and bottom uniform.

---

## Decision 3: Database — SQLite

**Choice**: SQLite via SQLAlchemy ORM  
**Alternatives considered**:
- PostgreSQL — production-grade, requires server setup, Docker, etc.
- MongoDB — flexible schema, but adds complexity for structured analytics
- In-memory only — fast, but no persistence across restarts
- Redis — excellent for real-time counters but poor for SQL analytics

**Rationale**:  
For a hackathon evaluated on a single machine, SQLite provides zero-infrastructure setup. All analytics (GROUP BY, COUNT DISTINCT, JOINs) are standard SQL supported by SQLite. The file at `store_intelligence.db` persists between API restarts.

---

## Decision 4: Conversion Correlation — 5-Minute POS Window

**Choice**: Match billing events to POS transactions within ±5 minutes  
**Alternatives considered**:
- Direct visitor_id in POS — not available in provided CSV data
- Machine learning session matching — requires labelled training data
- Simple count ratio (transactions / visitors) — misattributes multi-buyer baskets

**Rationale**:  
The POS CSV does not contain visitor IDs, so direct correlation is impossible. The 5-minute window is a standard retail analytics heuristic: a customer who was in the billing zone within 5 minutes of a transaction likely made that purchase. This was also flagged to the judges as an assumption.

---

## Decision 5: Anomaly Detection — Rule-Based

**Choice**: Hard-coded threshold rules for 3 anomaly types  
**Alternatives considered**:
- ML-based anomaly detection (Isolation Forest, LSTM) — needs historical training data
- Statistical z-score alerting — requires population baseline we don't have
- External alerting (PagerDuty, Slack webhooks) — out of scope for hackathon

**Rationale**:  
Rule-based systems are explainable, reliable, and require no training data. The 7-day rolling baseline for conversion drop is a lightweight statistical comparison. Thresholds (queue > 5, conversion drop > 30%) were chosen to reflect realistic retail operations.

---

## Decision 6: Real-Time Dashboard — Polling vs WebSockets

**Choice**: HTTP polling every 5 seconds  
**Alternatives considered**:
- WebSockets — true real-time push; requires ws:// server implementation
- Server-Sent Events (SSE) — one-way push from server; simpler than WS
- Long polling — more complex server-side logic

**Rationale**:  
5-second polling is effectively real-time for retail analytics (decisions are made in minutes, not seconds). Polling requires zero server-side changes (no WebSocket/SSE handler needed) and works reliably behind any proxy or firewall. It also degrades gracefully — if the poll fails, the previous data remains visible.

---

## Decision 7: Frontend — Vanilla HTML/CSS/JS

**Choice**: Plain HTML + CSS + Chart.js  
**Alternatives considered**:
- React/Next.js — overkill for a dashboard, adds build complexity
- Vue.js — lighter but still adds tooling
- Grafana — excellent dashboards but no custom code

**Rationale**:  
Zero build step, zero npm install for the dashboard. The judge can open `index.html` directly in a browser. Chart.js provides production-quality charts via CDN. The premium dark design was hand-crafted in CSS to showcase UI quality.

---

## Decision 8: Zone Definition — Camera-Name Heuristics

**Choice**: Zone bounding boxes inferred from camera names (billing, entry, zone)  
**Alternatives considered**:
- Manual zone config JSON file — more flexible but requires human annotation
- Computer vision zone detection from layout image — complex, error-prone
- Using provided store layout PNGs to auto-derive zones — interesting but not reliable

**Rationale**:  
The camera filenames (`CAM 5 - billing`, `CAM 2 - zone`) explicitly encode their purpose. Name-based zone assignment is fast, reliable, and self-documenting. For a production system, a `zones_config.json` would be the right approach.

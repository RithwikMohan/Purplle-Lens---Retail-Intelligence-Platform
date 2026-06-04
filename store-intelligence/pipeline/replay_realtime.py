"""
replay_realtime.py — Streams events to the Store Intelligence API in real time.
Preserves relative delays between events and supports custom speed multipliers.

Options:
  --jsonl            Path to events JSONL file (default: events_store1.jsonl)
  --api              API base URL (default: http://localhost:8000)
  --speed            Speed multiplier (default: 5.0). E.g. 5.0 replays 5x faster.
  --align-time       Shift timestamps to start at a specific time (e.g. "2026-04-10T12:10:00")
  --live             Shift timestamps so that the replay starts *now* in real time.
"""

import json
import time
import argparse
import sys
import os
from datetime import datetime, timedelta

# Import normalizer if available (same directory)
sys.path.insert(0, os.path.dirname(__file__))
try:
    from normalizer import convert_event
    NORMALIZER_AVAILABLE = True
except ImportError:
    NORMALIZER_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    import urllib.request
    import urllib.error

def post_event(api_base: str, event: dict):
    payload = json.dumps({"events": [event]}).encode("utf-8")
    url = f"{api_base}/events/ingest"

    if REQUESTS_AVAILABLE:
        resp = requests.post(url, data=payload, headers={"Content-Type": "application/json"}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    else:
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

def parse_iso_timestamp(ts_str: str) -> datetime:
    # Try parsing different ISO formats
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts_str.replace("Z", ""), fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(ts_str)

def main():
    parser = argparse.ArgumentParser(description="Stream events to API in simulated real time")
    parser.add_argument("--jsonl", default="events_store1.jsonl", help="Path to events JSONL file")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--speed", type=float, default=5.0, help="Speed multiplier (e.g. 10.0 for 10x speed)")
    parser.add_argument("--align-time", default=None, help="Align start to ISO datetime (e.g. '2026-04-10T12:10:00')")
    parser.add_argument("--live", action="store_true", help="Shift event timestamps to start *now*")
    parser.add_argument("--store-id", default=None, help="Override store_id for all events")
    args = parser.parse_args()

    # Locate the file
    jsonl_path = args.jsonl
    if not os.path.exists(jsonl_path):
        # Check in parent or pipeline folder
        possible_paths = [
            os.path.join(os.path.dirname(__file__), jsonl_path),
            os.path.join(os.path.dirname(__file__), "..", jsonl_path),
            os.path.abspath(jsonl_path)
        ]
        for p in possible_paths:
            if os.path.exists(p):
                jsonl_path = p
                break

    if not os.path.exists(jsonl_path):
        print(f"ERROR: Event file not found: {args.jsonl}")
        sys.exit(1)

    print(f"Loading events from {jsonl_path}...")
    raw_events = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                raw_events.append(json.loads(line))

    # Convert events and sort chronologically
    events = []
    for item in raw_events:
        # Use normalizer if the event looks like a raw sample event (not already in our schema)
        needs_conversion = (
            "event_timestamp" in item
            or "event_time" in item
            or "queue_join_ts" in item
            or "timestamp" not in item
        )
        if NORMALIZER_AVAILABLE and needs_conversion:
            evt = convert_event(item)
        else:
            evt = item.copy()
        
        # Override store_id if requested
        if args.store_id:
            evt["store_id"] = args.store_id

        # Parse timestamp — fall back to event_timestamp if needed
        ts_raw = evt.get("timestamp") or item.get("event_timestamp") or item.get("event_time")
        if not ts_raw:
            continue
        evt["timestamp"] = ts_raw
        evt["_dt"] = parse_iso_timestamp(ts_raw)

        events.append(evt)

    # Sort chronologically by original timestamp
    events.sort(key=lambda x: x["_dt"])

    if not events:
        print("No events found in file.")
        return

    # Calculate shift offset
    first_dt = events[0]["_dt"]
    shift_delta = timedelta(0)

    if args.live:
        shift_delta = datetime.now() - first_dt
        print(f"Aligning events to start LIVE now ({datetime.now().strftime('%H:%M:%S')})")
    elif args.align_time:
        try:
            target_start = parse_iso_timestamp(args.align_time)
            shift_delta = target_start - first_dt
            print(f"Aligning events to start at specified datetime: {args.align_time}")
        except Exception as e:
            print(f"WARNING: Could not parse target start time: {e}. Replaying with original timestamps.")

    # Apply shifts to timestamps
    for e in events:
        shifted_dt = e["_dt"] + shift_delta
        e["timestamp"] = shifted_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        e["_shifted_dt"] = shifted_dt

    print(f"Successfully prepared {len(events)} events for streaming.")
    print(f"Replay Speed: {args.speed}x")
    print(f"Press Ctrl+C to terminate.\n")

    start_perf_time = time.perf_counter()
    first_shifted_dt = events[0]["_shifted_dt"]

    for idx, event in enumerate(events):
        # Calculate target time in performance counter space
        event_offset = (event["_shifted_dt"] - first_shifted_dt).total_seconds()
        target_perf_time = start_perf_time + (event_offset / args.speed)

        # Sleep until the target time
        current_perf_time = time.perf_counter()
        sleep_duration = target_perf_time - current_perf_time
        if sleep_duration > 0:
            time.sleep(sleep_duration)

        # Clean metadata fields for JSON submission
        submit_event = event.copy()
        submit_event.pop("_dt", None)
        submit_event.pop("_shifted_dt", None)

        # Post event
        try:
            ts_short = parse_iso_timestamp(submit_event["timestamp"]).strftime("%H:%M:%S")
            print(f"[{idx+1}/{len(events)}] Sending: {submit_event['event_type']} | Visitor: {submit_event['visitor_id'][:8]} | Zone: {submit_event.get('zone_id') or 'N/A'} | Time: {ts_short} ... ", end="")
            res = post_event(args.api, submit_event)
            print("OK")
        except Exception as err:
            print(f"FAILED ({err})")

if __name__ == "__main__":
    main()

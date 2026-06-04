"""
feed_to_api.py — Reads a JSONL events file and POSTs to the API ingestion endpoint.
Automatically normalizes Purplle sample_events format into API EventSchema format.
Usage:
    python feed_to_api.py --jsonl events_output.jsonl --api http://localhost:8000
"""
import json
import time
import argparse
import sys
import os

# Import normalizer if available (same directory)
sys.path.insert(0, os.path.dirname(__file__))
try:
    from normalizer import convert_jsonl_file
    NORMALIZER_AVAILABLE = True
except ImportError:
    NORMALIZER_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    try:
        import urllib.request
        import urllib.error
    except ImportError:
        pass

BATCH_SIZE = 100
DELAY_BETWEEN_BATCHES = 0.2  # seconds


def post_batch(api_base: str, events: list) -> dict:
    payload = json.dumps({"events": events}).encode("utf-8")
    url = f"{api_base}/events/ingest"

    if REQUESTS_AVAILABLE:
        resp = requests.post(url, data=payload, headers={"Content-Type": "application/json"}, timeout=30)
        resp.raise_for_status()
        return resp.json()
    else:
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


def feed_jsonl_to_api(jsonl_path: str, api_base: str, store_id: str = None):
    print(f"Reading events from: {jsonl_path}")
    print(f"Posting to API: {api_base}/events/ingest")

    # Use normalizer to convert raw Purplle format -> API EventSchema
    if NORMALIZER_AVAILABLE:
        print("  Using schema normalizer for Purplle event format...")
        events = convert_jsonl_file(jsonl_path)
        if store_id:
            for e in events:
                e["store_id"] = store_id
        total_lines = len(events)
    else:
        # Fallback: load raw JSON lines (assumes already in API format)
        events = []
        total_lines = 0
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        if store_id:
                            event["store_id"] = store_id
                        events.append(event)
                        total_lines += 1
                    except json.JSONDecodeError as e:
                        print(f"  WARNING: Skipping malformed line: {e}")
        except FileNotFoundError:
            print(f"ERROR: File not found: {jsonl_path}")
            sys.exit(1)

    print(f"Loaded {total_lines} events. Sending in batches of {BATCH_SIZE}...")

    total_processed = 0
    total_skipped = 0
    total_failed = 0

    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i:i + BATCH_SIZE]
        try:
            result = post_batch(api_base, batch)
            total_processed += result.get("processed", 0)
            total_skipped += result.get("skipped", 0)
            total_failed += result.get("failed", 0)
            print(f"  Batch {i // BATCH_SIZE + 1}: processed={result.get('processed',0)} "
                  f"skipped={result.get('skipped',0)} failed={result.get('failed',0)}")
            time.sleep(DELAY_BETWEEN_BATCHES)
        except Exception as e:
            print(f"  ERROR on batch {i // BATCH_SIZE + 1}: {e}")
            total_failed += len(batch)

    print(f"\nDone! Total: processed={total_processed}, skipped={total_skipped}, failed={total_failed}")


def feed_sample_events(api_base: str):
    """
    Feed the provided sample_eventsbe42122.jsonl from the hackathon dataset.
    """
    sample_path = r"d:\purple_hackathon\sample_eventsbe42122.jsonl"
    feed_jsonl_to_api(sample_path, api_base)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Feed JSONL events to Store Intelligence API")
    parser.add_argument("--jsonl", default=r"d:\purple_hackathon\sample_eventsbe42122.jsonl",
                        help="Path to JSONL events file")
    parser.add_argument("--api", default="http://localhost:8000",
                        help="API base URL")
    parser.add_argument("--store_id", default=None,
                        help="Override store_id for all events")
    args = parser.parse_args()

    feed_jsonl_to_api(args.jsonl, args.api, args.store_id)

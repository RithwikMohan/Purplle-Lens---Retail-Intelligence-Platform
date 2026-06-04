import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

class EventEmitter:
    """
    Formats, validates, and serializes visitor behavioral events 
    into a structured JSONL file following the required schema.
    """
    def __init__(self, output_path: str = "events_output.jsonl"):
        self.output_path = output_path

    def emit(self, 
             store_id: str, 
             camera_id: str, 
             visitor_id: str, 
             event_type: str, 
             timestamp: datetime, 
             zone_id: Optional[str] = None, 
             dwell_ms: int = 0, 
             is_staff: bool = False, 
             confidence: float = 0.90,
             queue_depth: Optional[int] = None,
             sku_zone: Optional[str] = None,
             session_seq: int = 1) -> Dict[str, Any]:
        """
        Builds a schema-compliant event and appends it to the JSONL output file.
        """
        event = {
            "event_id": str(uuid.uuid4()),
            "store_id": store_id,
            "camera_id": camera_id,
            "visitor_id": visitor_id,
            "event_type": event_type,
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),  # Standard ISO-8601 UTC
            "zone_id": zone_id,
            "dwell_ms": int(dwell_ms),
            "is_staff": bool(is_staff),
            "confidence": round(float(confidence), 2),
            "metadata": {
                "queue_depth": int(queue_depth) if queue_depth is not None else None,
                "sku_zone": sku_zone if sku_zone is not None else None,
                "session_seq": int(session_seq)
            }
        }

        # Append to JSONL file
        with open(self.output_path, mode='a', encoding='utf-8') as f:
            f.write(json.dumps(event) + "\n")

        return event

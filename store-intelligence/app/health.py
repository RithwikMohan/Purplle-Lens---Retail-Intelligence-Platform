from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from .models import DBEvent
from typing import Dict, Any

def get_system_health(db: Session) -> Dict[str, Any]:
    """
    Returns the service health status, last received event timestamp per store,
    and flags a STALE_FEED warning if any feed lag exceeds 10 minutes (600 seconds).
    """
    status = "OK"
    warnings = []
    store_statuses = {}
    
    # 1. Fetch unique stores in database
    stores_query = db.query(DBEvent.store_id).distinct().all()
    stores = [s[0] for s in stores_query]
    
    current_time = datetime.utcnow()
    
    for store_id in stores:
        # Find the latest event for this store
        latest_event = db.query(DBEvent.timestamp).filter(
            DBEvent.store_id == store_id
        ).order_by(DBEvent.timestamp.desc()).first()
        
        if latest_event:
            last_ts = latest_event[0]
            # Calculate lag relative to UTC now
            lag_seconds = (current_time - last_ts).total_seconds()
            
            # 10 minutes = 600 seconds
            is_stale = lag_seconds > 600
            
            store_statuses[store_id] = {
                "status": "STALE_FEED" if is_stale else "OK",
                "last_event_timestamp": last_ts.isoformat() + "Z",
                "lag_seconds": round(lag_seconds, 1)
            }
            
            if is_stale:
                status = "WARNING"
                warnings.append(f"STALE_FEED for store '{store_id}': Last event was {round(lag_seconds / 60, 1)} minutes ago.")
        else:
            store_statuses[store_id] = {
                "status": "NO_DATA",
                "last_event_timestamp": None,
                "lag_seconds": None
            }

    return {
        "status": status,
        "timestamp": current_time.isoformat() + "Z",
        "stores": store_statuses,
        "warnings": warnings
    }

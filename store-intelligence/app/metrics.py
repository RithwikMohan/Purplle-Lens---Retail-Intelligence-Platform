from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta
from .models import DBEvent, DBPOSTransaction
from typing import Dict, Any, List

def get_latest_date_for_store(db: Session, store_id: str) -> datetime:
    """
    Finds the date of the latest event in the database for the given store.
    """
    # Try exact match, prefix, or normalized match
    normalized_sid = normalize_store_id(store_id)
    latest_event = db.query(DBEvent).filter(
        or_(
            DBEvent.store_id == store_id,
            DBEvent.store_id.like(f"%{normalized_sid}%")
        )
    ).order_by(DBEvent.timestamp.desc()).first()
    
    if latest_event:
        return latest_event.timestamp
    return datetime.now()

def normalize_store_id(store_id: str) -> str:
    """
    Normalizes store IDs (e.g. 'STORE_BLR_002' -> '002', 'ST1008' -> '1008', 'store_1076' -> '1076')
    by extracting numerical suffix or alphanumeric core.
    """
    if not store_id:
        return ""
    # Extract only digits to find a common matching key
    digits = "".join([c for c in store_id if c.isdigit()])
    if digits:
        return digits
    return store_id.lower().replace("store_", "").replace("st", "")

def get_store_metrics(db: Session, store_id: str) -> Dict[str, Any]:
    """
    Computes today's metrics: unique visitors, conversion rate, 
    average dwell per zone, queue depth, and abandonment rate.
    """
    # 1. Determine "Today" (latest event timestamp date boundary)
    latest_ts = get_latest_date_for_store(db, store_id)
    start_of_day = datetime(latest_ts.year, latest_ts.month, latest_ts.day, 0, 0, 0)
    end_of_day = datetime(latest_ts.year, latest_ts.month, latest_ts.day, 23, 59, 59)
    
    normalized_sid = normalize_store_id(store_id)

    # Base filters
    store_filter = or_(
        DBEvent.store_id == store_id,
        DBEvent.store_id.like(f"%{normalized_sid}%")
    )
    time_filter = DBEvent.timestamp.between(start_of_day, end_of_day)
    customer_filter = DBEvent.is_staff == False

    # A. Unique Visitors (excluding staff)
    unique_visitors_query = db.query(DBEvent.visitor_id).filter(
        and_(store_filter, time_filter, customer_filter)
    ).distinct().all()
    
    unique_visitors = [v[0] for v in unique_visitors_query]
    total_unique_visitors = len(unique_visitors)

    if total_unique_visitors == 0:
        return {
            "store_id": store_id,
            "date": start_of_day.strftime("%Y-%m-%d"),
            "unique_visitors": 0,
            "conversion_rate": 0.0,
            "avg_dwell_seconds_per_zone": {},
            "queue_depth": 0,
            "abandonment_rate": 0.0
        }

    # B. Converted Visitors (time window + store correlation)
    # Get all transactions for this store on this day
    tx_store_filter = or_(
        DBPOSTransaction.store_id == store_id,
        DBPOSTransaction.store_id.like(f"%{normalized_sid}%")
    )
    tx_time_filter = DBPOSTransaction.timestamp.between(start_of_day, end_of_day)
    
    transactions = db.query(DBPOSTransaction).filter(
        and_(tx_store_filter, tx_time_filter)
    ).all()

    converted_visitors = set()
    for tx in transactions:
        # 5-minute window before the transaction timestamp
        win_start = tx.timestamp - timedelta(minutes=5)
        win_end = tx.timestamp
        
        # Find unique customer visitors in the billing zone during this window
        billing_events = db.query(DBEvent.visitor_id).filter(
            and_(
                store_filter,
                DBEvent.timestamp.between(win_start, win_end),
                customer_filter,
                or_(
                    DBEvent.event_type.in_(["BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON"]),
                    DBEvent.zone_id.like("%BILLING%"),
                    DBEvent.zone_id.like("%QUEUE%")
                )
            )
        ).distinct().all()
        
        for v in billing_events:
            converted_visitors.add(v[0])

    # Fetch all queue abandons today to exclude from converted visitors
    abandons_query = db.query(DBEvent.visitor_id).filter(
        and_(
            store_filter,
            time_filter,
            customer_filter,
            DBEvent.event_type == "BILLING_QUEUE_ABANDON"
        )
    ).distinct().all()
    abandoned_visitors = {v[0] for v in abandons_query}

    # Intersect converted visitors with visitors of today to prevent leakage,
    # and exclude those who abandoned the queue.
    converted_visitors_today = converted_visitors.intersection(set(unique_visitors)) - abandoned_visitors
    conversion_rate = len(converted_visitors_today) / total_unique_visitors

    # C. Average Dwell per Zone
    # Fetch all enter and exit events for today to pair them
    zone_events = db.query(
        DBEvent.visitor_id, DBEvent.zone_id, DBEvent.event_type, DBEvent.timestamp, DBEvent.dwell_ms
    ).filter(
        and_(
            store_filter,
            time_filter,
            DBEvent.zone_id != None,
            DBEvent.event_type.in_(["ZONE_ENTER", "ZONE_EXIT", "ZONE_DWELL"])
        )
    ).order_by(DBEvent.visitor_id, DBEvent.zone_id, DBEvent.timestamp).all()

    # Pair ZONE_ENTER and ZONE_EXIT to compute dwell
    # Also fallback to ZONE_DWELL's dwell_ms
    zone_dwells = {} # zone_id -> list of seconds
    
    # Store enter events by (visitor_id, zone_id)
    active_enters = {}
    for ev in zone_events:
        key = (ev.visitor_id, ev.zone_id)
        if ev.event_type == "ZONE_ENTER":
            active_enters[key] = ev.timestamp
        elif ev.event_type == "ZONE_EXIT":
            if key in active_enters:
                duration = (ev.timestamp - active_enters[key]).total_seconds()
                zone_dwells.setdefault(ev.zone_id, []).append(duration)
                del active_enters[key]
        elif ev.event_type == "ZONE_DWELL" and ev.dwell_ms:
            # Fallback or supplementary dwell check
            zone_dwells.setdefault(ev.zone_id, []).append(ev.dwell_ms / 1000.0)

    avg_dwells = {}
    for zone_id, durations in zone_dwells.items():
        if durations:
            avg_dwells[zone_id] = round(sum(durations) / len(durations), 1)

    # D. Queue Depth
    # Number of joins minus completed/abandoned
    queue_joins = db.query(DBEvent.visitor_id).filter(
        and_(
            store_filter,
            time_filter,
            customer_filter,
            DBEvent.event_type == "BILLING_QUEUE_JOIN"
        )
    ).distinct().all()
    
    joins_set = {v[0] for v in queue_joins}

    # Find exits/abandons for those joins
    queue_exits = db.query(DBEvent.visitor_id).filter(
        and_(
            store_filter,
            time_filter,
            customer_filter,
            DBEvent.event_type.in_(["BILLING_QUEUE_ABANDON", "EXIT"])
        )
    ).distinct().all()
    
    exits_set = {v[0] for v in queue_exits}

    # Current queue depth is joins without exits/abandons
    active_queue = joins_set - exits_set
    queue_depth = len(active_queue)

    # E. Abandonment Rate
    # (Queue abandons) / (Total queue joins)
    total_joins = len(joins_set)
    total_abandons = len(abandoned_visitors)

    abandonment_rate = 0.0
    if total_joins > 0:
        abandonment_rate = total_abandons / total_joins

    return {
        "store_id": store_id,
        "date": start_of_day.strftime("%Y-%m-%d"),
        "unique_visitors": total_unique_visitors,
        "conversion_rate": round(conversion_rate, 4),
        "avg_dwell_seconds_per_zone": avg_dwells,
        "queue_depth": queue_depth,
        "abandonment_rate": round(abandonment_rate, 4)
    }

def get_store_heatmap(db: Session, store_id: str) -> Dict[str, Any]:
    """
    Computes zone visit frequency and average dwell.
    Normalizes both metrics to a 0-100 scale across zones.
    Includes data_confidence flag based on total sessions (>= 20).
    """
    # 1. Determine "Today" boundary
    latest_ts = get_latest_date_for_store(db, store_id)
    start_of_day = datetime(latest_ts.year, latest_ts.month, latest_ts.day, 0, 0, 0)
    end_of_day = datetime(latest_ts.year, latest_ts.month, latest_ts.day, 23, 59, 59)
    
    normalized_sid = normalize_store_id(store_id)
    store_filter = or_(
        DBEvent.store_id == store_id,
        DBEvent.store_id.like(f"%{normalized_sid}%")
    )
    time_filter = DBEvent.timestamp.between(start_of_day, end_of_day)
    customer_filter = DBEvent.is_staff == False

    # Get total unique sessions today
    total_sessions = db.query(DBEvent.visitor_id).filter(
        and_(store_filter, time_filter, customer_filter)
    ).distinct().count()
    
    data_confidence = total_sessions >= 20

    # Get visit count per zone (unique visits count - unique visitors per zone)
    zone_visits = db.query(
        DBEvent.zone_id,
        func.count(func.distinct(DBEvent.visitor_id))
    ).filter(
        and_(
            store_filter,
            time_filter,
            customer_filter,
            DBEvent.zone_id != None,
            ~DBEvent.zone_id.like("%ENTRY%"),
            ~DBEvent.zone_id.like("%EXIT%"),
            ~DBEvent.zone_id.like("%BILLING%"),
            ~DBEvent.zone_id.like("%QUEUE%")
        )
    ).group_by(DBEvent.zone_id).all()

    # Get average dwell per zone using get_store_metrics average dwell output
    metrics = get_store_metrics(db, store_id)
    avg_dwells = metrics["avg_dwell_seconds_per_zone"]

    # Gather data by zone
    zones_data = {}
    for zone_id, count in zone_visits:
        dwell = avg_dwells.get(zone_id, 0.0)
        zones_data[zone_id] = {
            "frequency": count,
            "avg_dwell": dwell
        }

    # Normalize frequency and dwell to 0-100
    max_freq = max([z["frequency"] for z in zones_data.values()]) if zones_data else 0
    max_dwell = max([z["avg_dwell"] for z in zones_data.values()]) if zones_data else 0.0

    normalized_zones = {}
    for zone_id, data in zones_data.items():
        norm_freq = round((data["frequency"] / max_freq * 100.0), 1) if max_freq > 0 else 0.0
        norm_dwell = round((data["avg_dwell"] / max_dwell * 100.0), 1) if max_dwell > 0.0 else 0.0
        normalized_zones[zone_id] = {
            "visit_frequency": data["frequency"],
            "avg_dwell_seconds": data["avg_dwell"],
            "normalized_frequency": norm_freq,
            "normalized_dwell": norm_dwell
        }

    return {
        "store_id": store_id,
        "date": start_of_day.strftime("%Y-%m-%d"),
        "data_confidence": data_confidence,
        "total_sessions": total_sessions,
        "zones": normalized_zones
    }


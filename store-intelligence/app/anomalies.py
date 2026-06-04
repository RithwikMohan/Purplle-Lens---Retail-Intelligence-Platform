from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta
from .models import DBEvent, DBPOSTransaction
from .metrics import get_latest_date_for_store, normalize_store_id, get_store_metrics
from typing import Dict, Any, List

def detect_store_anomalies(db: Session, store_id: str) -> List[Dict[str, Any]]:
    """
    Analyzes events and transactions to detect active operational anomalies:
    1. Queue Spike
    2. Conversion Drop vs. historical average
    3. Dead Zone (no visits in past 30 minutes)
    """
    anomalies = []
    
    # 1. Determine simulated "Current Time" (latest event timestamp in DB)
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

    # Get current today's metrics
    today_metrics = get_store_metrics(db, store_id)

    # -------- ANOMALY 1: Queue Spike --------
    q_depth = today_metrics["queue_depth"]
    if q_depth > 10:
        anomalies.append({
            "type": "BILLING_QUEUE_SPIKE",
            "severity": "CRITICAL",
            "message": f"Billing queue depth is severely high ({q_depth} people in line).",
            "suggested_action": "Deploy floor staff immediately to assist and open all available billing registers."
        })
    elif q_depth > 5:
        anomalies.append({
            "type": "BILLING_QUEUE_SPIKE",
            "severity": "WARN",
            "message": f"Billing queue is building up ({q_depth} people in line).",
            "suggested_action": "Open another billing counter to disperse the queue."
        })

    # -------- ANOMALY 2: Conversion Drop vs. 7-Day Average --------
    # Compute conversion rates of previous 7 days
    hist_conversion_rates = []
    
    # Query distinct dates before today that have events
    distinct_dates_query = db.query(
        func.date(DBEvent.timestamp)
    ).filter(
        and_(
            store_filter,
            func.date(DBEvent.timestamp) < latest_ts.date()
        )
    ).distinct().order_by(func.date(DBEvent.timestamp).desc()).limit(7).all()
    
    for dt_tuple in distinct_dates_query:
        dt_str = dt_tuple[0]
        dt = datetime.strptime(dt_str, "%Y-%m-%d")
        d_start = datetime(dt.year, dt.month, dt.day, 0, 0, 0)
        d_end = datetime(dt.year, dt.month, dt.day, 23, 59, 59)
        
        # Calculate unique visitors for that day
        v_count = db.query(DBEvent.visitor_id).filter(
            and_(
                store_filter,
                DBEvent.timestamp.between(d_start, d_end),
                customer_filter
            )
        ).distinct().count()
        
        if v_count > 0:
            # Calculate conversion for that day
            tx_store_filter = or_(
                DBPOSTransaction.store_id == store_id,
                DBPOSTransaction.store_id.like(f"%{normalized_sid}%")
            )
            tx_count = db.query(DBPOSTransaction.order_id).filter(
                and_(
                    tx_store_filter,
                    DBPOSTransaction.timestamp.between(d_start, d_end)
                )
            ).distinct().count()
            
            # Simple fallback conversion rate if we don't do complex correlation per day
            # (or we could run full correlation, but direct ratio is a good historical baseline)
            hist_conversion_rates.append(tx_count / v_count)

    # Use a default baseline of 15% if no historical data is found
    avg_hist_conv = sum(hist_conversion_rates) / len(hist_conversion_rates) if hist_conversion_rates else 0.15
    today_conv = today_metrics["conversion_rate"]

    if today_conv < avg_hist_conv * 0.5:  # >50% drop
        anomalies.append({
            "type": "CONVERSION_DROP",
            "severity": "CRITICAL",
            "message": f"Conversion rate has dropped by more than 50% vs. historical average (Today: {today_conv * 100:.1f}%, Avg: {avg_hist_conv * 100:.1f}%).",
            "suggested_action": "Investigate checkout counter POS failures, payment gateway issues, or severe pricing discrepancies."
        })
    elif today_conv < avg_hist_conv * 0.7:  # >30% drop
        anomalies.append({
            "type": "CONVERSION_DROP",
            "severity": "WARN",
            "message": f"Conversion rate is down by more than 30% vs. historical average (Today: {today_conv * 100:.1f}%, Avg: {avg_hist_conv * 100:.1f}%).",
            "suggested_action": "Check for billing queue bottlenecks or check if floor staff are available to assist customers."
        })

    # -------- ANOMALY 3: Dead Zone (No visits in 30 minutes) --------
    # Find all zones that have events in this store
    zones = db.query(DBEvent.zone_id).filter(
        and_(
            store_filter,
            DBEvent.zone_id != None,
            ~DBEvent.zone_id.like("%ENTRY%"),
            ~DBEvent.zone_id.like("%EXIT%")
        )
    ).distinct().all()
    
    zone_ids = [z[0] for z in zones]

    # For each zone, find the timestamp of the latest ZONE_ENTER event today
    for zone_id in zone_ids:
        latest_visit = db.query(DBEvent.timestamp).filter(
            and_(
                store_filter,
                time_filter,
                DBEvent.zone_id == zone_id,
                DBEvent.event_type == "ZONE_ENTER"
            )
        ).order_by(DBEvent.timestamp.desc()).first()

        if latest_visit:
            time_since_visit = latest_ts - latest_visit[0]
            if time_since_visit > timedelta(minutes=30):
                anomalies.append({
                    "type": "DEAD_ZONE",
                    "severity": "WARN",
                    "message": f"Zone '{zone_id}' has not had any new visits in the past {int(time_since_visit.total_seconds() / 60)} minutes.",
                    "suggested_action": "Verify if the display is obstructed, check product stocking levels, or inspect the zone lighting."
                })
        else:
            # Never visited today
            anomalies.append({
                "type": "DEAD_ZONE",
                "severity": "INFO",
                "message": f"Zone '{zone_id}' has had zero visits today.",
                "suggested_action": "Ensure items in this zone are properly stocked, promoted, and visible to traffic."
            })

    return anomalies

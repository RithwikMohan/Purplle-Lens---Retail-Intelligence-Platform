from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta
from .models import DBEvent, DBPOSTransaction
from .metrics import get_latest_date_for_store, normalize_store_id
from typing import Dict, Any, List

def get_store_funnel(db: Session, store_id: str) -> Dict[str, Any]:
    """
    Computes conversion funnel stages for unique visitor sessions:
    Entry -> Zone Visit -> Billing Queue -> Purchase
    Includes counts and drop-off percentages.
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

    # Stage 0: Entry (All unique customer sessions)
    all_visitors_query = db.query(DBEvent.visitor_id).filter(
        and_(store_filter, time_filter, customer_filter)
    ).distinct().all()
    
    entry_visitors = {v[0] for v in all_visitors_query}
    entry_count = len(entry_visitors)

    if entry_count == 0:
        return {
            "store_id": store_id,
            "date": start_of_day.strftime("%Y-%m-%d"),
            "stages": [
                {"stage": "Entry", "count": 0, "drop_off_pct": 0.0},
                {"stage": "Zone Visit", "count": 0, "drop_off_pct": 0.0},
                {"stage": "Billing Queue", "count": 0, "drop_off_pct": 0.0},
                {"stage": "Purchase", "count": 0, "drop_off_pct": 0.0}
            ]
        }

    # Stage 1: Zone Visit (Merchandise zone enter/dwell, excluding billing/entry/exit zones)
    zone_visitors_query = db.query(DBEvent.visitor_id).filter(
        and_(
            store_filter,
            time_filter,
            customer_filter,
            DBEvent.event_type.in_(["ZONE_ENTER", "ZONE_DWELL"]),
            DBEvent.zone_id != None,
            ~DBEvent.zone_id.like("%BILLING%"),
            ~DBEvent.zone_id.like("%QUEUE%"),
            ~DBEvent.zone_id.like("%ENTRY%"),
            ~DBEvent.zone_id.like("%EXIT%")
        )
    ).distinct().all()
    
    zone_visitors = {v[0] for v in zone_visitors_query}.intersection(entry_visitors)
    zone_count = len(zone_visitors)

    # Stage 2: Billing Queue (Joined billing queue)
    billing_visitors_query = db.query(DBEvent.visitor_id).filter(
        and_(
            store_filter,
            time_filter,
            customer_filter,
            or_(
                DBEvent.event_type == "BILLING_QUEUE_JOIN",
                and_(
                    DBEvent.event_type == "ZONE_ENTER",
                    or_(
                        DBEvent.zone_id.like("%BILLING%"),
                        DBEvent.zone_id.like("%QUEUE%")
                    )
                )
            )
        )
    ).distinct().all()
    
    billing_visitors = {v[0] for v in billing_visitors_query}.intersection(entry_visitors)
    billing_count = len(billing_visitors)

    # Stage 3: Purchase (Correlated with POS transactions)
    tx_store_filter = or_(
        DBPOSTransaction.store_id == store_id,
        DBPOSTransaction.store_id.like(f"%{normalized_sid}%")
    )
    tx_time_filter = DBPOSTransaction.timestamp.between(start_of_day, end_of_day)
    
    transactions = db.query(DBPOSTransaction).filter(
        and_(tx_store_filter, tx_time_filter)
    ).all()

    purchase_visitors = set()
    for tx in transactions:
        win_start = tx.timestamp - timedelta(minutes=5)
        win_end = tx.timestamp
        
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
            purchase_visitors.add(v[0])

    # Fetch all queue abandons today to exclude from purchase visitors
    abandons_query = db.query(DBEvent.visitor_id).filter(
        and_(
            store_filter,
            time_filter,
            customer_filter,
            DBEvent.event_type == "BILLING_QUEUE_ABANDON"
        )
    ).distinct().all()
    abandoned_visitors = {v[0] for v in abandons_query}

    purchase_visitors_today = purchase_visitors.intersection(entry_visitors) - abandoned_visitors
    purchase_count = len(purchase_visitors_today)

    # Calculate Drop-offs
    drop_off_1 = round((entry_count - zone_count) / entry_count * 100.0, 2) if entry_count > 0 else 0.0
    drop_off_2 = round((zone_count - billing_count) / zone_count * 100.0, 2) if zone_count > 0 else 0.0
    drop_off_3 = round((billing_count - purchase_count) / billing_count * 100.0, 2) if billing_count > 0 else 0.0

    return {
        "store_id": store_id,
        "date": start_of_day.strftime("%Y-%m-%d"),
        "stages": [
            {"stage": "Entry", "count": entry_count, "drop_off_pct": 0.0},
            {"stage": "Zone Visit", "count": zone_count, "drop_off_pct": drop_off_1},
            {"stage": "Billing Queue", "count": billing_count, "drop_off_pct": drop_off_2},
            {"stage": "Purchase", "count": purchase_count, "drop_off_pct": drop_off_3}
        ]
    }

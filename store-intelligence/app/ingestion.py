import os
import csv
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .models import DBEvent, DBPOSTransaction, EventSchema
from .database import engine, Base

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

def ingest_events_batch(db: Session, events_data: list) -> dict:
    """
    Ingests a batch of events. Deduplicates by event_id (idempotency)
    and reports validation errors for malformed events.
    """
    success_count = 0
    skipped_count = 0
    errors = []

    for index, event_dict in enumerate(events_data):
        try:
            # 1. Validation using Pydantic (if dict is passed raw)
            if isinstance(event_dict, dict):
                event = EventSchema(**event_dict)
            else:
                event = event_dict

            # 2. Check for duplication (Idempotency)
            existing_event = db.query(DBEvent).filter(DBEvent.event_id == event.event_id).first()
            if existing_event:
                skipped_count += 1
                continue

            # 3. Insert new event
            queue_depth = event.metadata.queue_depth if event.metadata else None
            sku_zone = event.metadata.sku_zone if event.metadata else None
            session_seq = event.metadata.session_seq if event.metadata else None

            db_event = DBEvent(
                event_id=event.event_id,
                store_id=event.store_id,
                camera_id=event.camera_id,
                visitor_id=event.visitor_id,
                event_type=event.event_type,
                timestamp=event.timestamp,
                zone_id=event.zone_id,
                dwell_ms=event.dwell_ms,
                is_staff=event.is_staff,
                confidence=event.confidence,
                queue_depth=queue_depth,
                sku_zone=sku_zone,
                session_seq=session_seq
            )
            db.add(db_event)
            success_count += 1

        except Exception as e:
            errors.append({
                "index": index,
                "error": str(e)
            })

    # Commit successful inserts
    if success_count > 0:
        db.commit()

    return {
        "processed": success_count,
        "skipped": skipped_count,
        "failed": len(errors),
        "errors": errors
    }


def import_pos_transactions_csv(db: Session, csv_path: str = None) -> int:
    """
    Loads POS transactions from CSV into the database if the table is empty.
    """
    if csv_path is None:
        csv_path = os.environ.get("POS_CSV_PATH", "pos_transactions.csv")
        
    # Check if we already have transactions
    if db.query(DBPOSTransaction).first() is not None:
        return 0

    if not os.path.exists(csv_path):
        print(f"POS CSV file not found at {csv_path}")
        return 0

    count = 0
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Combine order_date and order_time into a datetime object
                # CSV date format: DD-MM-YYYY (e.g. 10-04-2026)
                # CSV time format: HH:MM:SS (e.g. 12:15:05)
                dt_str = f"{row['order_date']} {row['order_time']}"
                timestamp = datetime.strptime(dt_str, "%d-%m-%Y %H:%M:%S")

                tx = DBPOSTransaction(
                    order_id=row['order_id'],
                    order_date=row['order_date'],
                    order_time=row['order_time'],
                    store_id=row['store_id'],
                    product_id=row['product_id'],
                    brand_name=row['brand_name'],
                    total_amount=float(row['total_amount']),
                    timestamp=timestamp
                )
                db.add(tx)
                count += 1
            except Exception as e:
                print(f"Error parsing POS row {row}: {e}")

    if count > 0:
        db.commit()
        print(f"Successfully imported {count} POS transactions from CSV.")

    return count

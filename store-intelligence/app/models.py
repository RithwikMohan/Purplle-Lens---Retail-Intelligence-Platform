from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, JSON
from .database import Base
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# ----------------- SQLALCHEMY MODELS (DATABASE) -----------------

class DBEvent(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, index=True, nullable=False)
    store_id = Column(String, index=True, nullable=False)
    camera_id = Column(String, nullable=False)
    visitor_id = Column(String, index=True, nullable=False)
    event_type = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime, index=True, nullable=False)
    zone_id = Column(String, nullable=True)
    dwell_ms = Column(Integer, default=0)
    is_staff = Column(Boolean, default=False)
    confidence = Column(Float, nullable=False)
    
    # Flattened metadata fields for easier SQL queries
    queue_depth = Column(Integer, nullable=True)
    sku_zone = Column(String, nullable=True)
    session_seq = Column(Integer, nullable=True)


class DBPOSTransaction(Base):
    __tablename__ = "pos_transactions"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, nullable=False)
    order_date = Column(String, nullable=False)
    order_time = Column(String, nullable=False)
    store_id = Column(String, index=True, nullable=False)
    product_id = Column(String, nullable=False)
    brand_name = Column(String, index=True, nullable=False)
    total_amount = Column(Float, nullable=False)
    timestamp = Column(DateTime, index=True, nullable=False)  # Computed datetime for correlation


# ----------------- PYDANTIC SCHEMAS (API & VALIDATION) -----------------

class EventMetadataSchema(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: Optional[int] = None

class EventSchema(BaseModel):
    event_id: str
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: str  # ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL, BILLING_QUEUE_JOIN, BILLING_QUEUE_ABANDON, REENTRY
    timestamp: datetime
    zone_id: Optional[str] = None
    dwell_ms: Optional[int] = 0
    is_staff: bool = False
    confidence: float
    metadata: Optional[EventMetadataSchema] = None

    class Config:
        from_attributes = True


class IngestPayloadSchema(BaseModel):
    events: List[EventSchema]

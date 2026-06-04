from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# SQLite database file path
DATABASE_URL = "sqlite:///d:/purple_hackathon/store-intelligence/store_intelligence.db"

# Create database engine
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False}  # Needed for SQLite in FastAPI
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base class for models
Base = declarative_base()

# Dependency to get db session in FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

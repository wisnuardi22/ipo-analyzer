from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:////tmp/ipo_analyzer.db')

# Railway PostgreSQL pakai "postgres://" tapi SQLAlchemy butuh "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# connect_args hanya untuk SQLite
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Analysis(Base):
    __tablename__ = 'analyses'

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, index=True)
    file_name = Column(String)
    raw_text = Column(Text)
    summary = Column(Text, nullable=True)
    risks = Column(Text, nullable=True)
    benefits = Column(Text, nullable=True)
    financial_data = Column(Text, nullable=True)
    ipo_details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    Base.metadata.create_all(bind=engine)
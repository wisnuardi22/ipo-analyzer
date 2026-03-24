import os
import sys
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── LOGGING CONFIG ──────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 1. ATUR PATH SISTEM
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# 2. IMPORT MODUL INTERNAL
from database.db import create_tables
from routes.upload import router as upload_router
from routes.analyze import router as analyze_router

# 3. INISIALISASI APLIKASI
app = FastAPI(title="IPO Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "/tmp/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.on_event('startup')
def startup_event():
    create_tables()
    logger.info("IPO Analyzer API started - logging active")

app.include_router(upload_router)
app.include_router(analyze_router)

@app.get('/')
def root():
    return {'message': 'IPO Analyzer API is running!'}
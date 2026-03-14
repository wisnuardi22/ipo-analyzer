import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


# 1. ATUR PATH SISTEM (Pastikan modul internal terbaca di server Linux)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# 2. IMPORT MODUL INTERNAL
from database.db import create_tables
from routes.upload import router as upload_router
from routes.analyze import router as analyze_router

# 3. INISIALISASI APLIKASI
app = FastAPI(title="IPO Analyzer API", version="1.0.0")

# Pengaturan CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DI VERCEL: Folder /tmp adalah satu-satunya tempat yang bisa ditulis
UPLOAD_DIR = "/tmp/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.on_event('startup')
def startup_event():
    create_tables()

app.include_router(upload_router)
app.include_router(analyze_router)

@app.get('/')
def root():
    return {'message': 'IPO Analyzer API is running! 🚀'}

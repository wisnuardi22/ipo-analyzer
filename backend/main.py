from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.db import create_tables
from routes.upload import router as upload_router
from routes.analyze import router as analyze_router
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="IPO Analyzer API", version="1.0.0")

# --- BAGIAN YANG DIPERBAIKI ---
app.add_middleware(
    CORSMiddleware, # <--- Tambahkan ini sebagai argumen pertama
    allow_origins=[
        "http://localhost:5173",
        "https://*.vercel.app", 
    ],
    allow_credentials=True, # Biasanya dibutuhkan untuk request dari frontend
    allow_methods=["*"],    # Mengizinkan semua method (GET, POST, PUT, DELETE, dll)
    allow_headers=["*"],    # Mengizinkan semua header
)
# ------------------------------

os.makedirs('uploads', exist_ok=True)

@app.on_event('startup')
def startup_event():
    create_tables()

app.include_router(upload_router)
app.include_router(analyze_router)

@app.get('/')
def root():
    return {'message': 'IPO Analyzer API is running! 🚀'}
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.db import create_tables
from routes.upload import router as upload_router
from routes.analyze import router as analyze_router
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="IPO Analyzer API", version="1.0.0")

app.add_middleware(
    allow_origins=[
    "http://localhost:5173",
    "https://*.vercel.app",
],
)

os.makedirs('uploads', exist_ok=True)

@app.on_event('startup')
def startup_event():
    create_tables()

app.include_router(upload_router)
app.include_router(analyze_router)

@app.get('/')
def root():
    return {'message': 'IPO Analyzer API is running! 🚀'}
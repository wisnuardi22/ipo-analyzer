import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

# Import internal - gunakan titik (.) untuk menandakan folder yang sama
from database.db import create_tables
from routes.upload import router as upload_router
from routes.analyze import router as analyze_router

app = FastAPI(title="IPO Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup folder upload (Vercel /tmp)
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

# SANGAT PENTING: Gunakan Mangum tanpa argumen tambahan yang rumit
handler = Mangum(app, lifespan="off")
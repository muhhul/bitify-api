from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.stego import router as stego_router
import os

app = FastAPI(title="Bitify API", version="0.1.0")

ALLOWED = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ok"}

app.include_router(stego_router, prefix="/api")

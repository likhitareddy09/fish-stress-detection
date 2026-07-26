from fastapi import APIRouter
from datetime import datetime

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check():
    """
    Simple health check.
    Visit http://localhost:8000/api/v1/health to confirm server is running.
    """
    return {
        "status": "ok",
        "service": "fish-stress-detection-backend",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "message": "Backend is running successfully",
    }


@router.get("/ping", tags=["Health"])
async def ping():
    """Minimal ping — just confirms server is alive."""
    return {"ping": "pong"}
from fastapi import FastAPI
from pydantic import BaseModel

from app.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")


class HealthResponse(BaseModel):
    status: str


@app.get("/health", tags=["system"])
def health() -> HealthResponse:
    """死活監視用。デプロイ先のヘルスチェックでも使う。"""
    return HealthResponse(status="ok")

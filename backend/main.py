"""FastAPI app: earnings feed endpoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import CORS_ORIGINS
from backend.routers import feed

app = FastAPI(
    title="Tracy API",
    description="Options (yfinance), Earnings & Quotes (Finnhub).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(feed.router, prefix="/feed", tags=["feed"])

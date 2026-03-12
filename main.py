from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Psychometric Analysis API",
    description="API for psychometric analysis, reliability, and factor analysis.",
    version="1.0.0"
)

# Configure CORS to be as permissive as possible for testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import JSONResponse
from fastapi import Request

# Global exception handler to ensure CORS headers are always sent
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Error interno del servidor: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )

@app.get("/")
def read_root():
    return {"message": "Welcome to the Psychometric Analysis API"}

# Register routes here later
from api import upload, reliability, efa, interpretation, report

app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(reliability.router, prefix="/api/reliability", tags=["Reliability"])
app.include_router(efa.router, prefix="/api/efa", tags=["EFA"])
app.include_router(interpretation.router, prefix="/api/interpretation", tags=["IA Interpretation"])
app.include_router(report.router, prefix="/api/report", tags=["Report Export"])

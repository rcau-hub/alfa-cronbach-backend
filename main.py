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

# Configure CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://www.utbinvestigacion.com",
        "https://utbinvestigacion.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

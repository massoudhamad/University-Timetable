from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.staticfiles import StaticFiles
import os

from app.database import Base, engine
from app.routers import router

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="University Timetable Generator",
    description="""
    An automatic timetable generation system for universities.
    
    Features:
    * Automatic timetable generation with conflict detection
    * Support for instructor preferences and availability
    * Room allocation based on course requirements
    * Customizable constraints and optimization strategies
    * Detailed statistics and analysis
    """,
    version="1.0.0",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)

# Serve static files if they exist
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8800, reload=True)
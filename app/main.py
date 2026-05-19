"""FastAPI application entry point for the GreenPack EPR service."""

from fastapi import FastAPI

from app.api.routes import router
from app.db.database import initialize_database


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    initialize_database()

    app = FastAPI(
        title="GreenPack EPR Service",
        description="Backend API for EPR compliance workflows.",
        version="0.1.0",
    )
    app.include_router(router)
    return app


app = create_app()

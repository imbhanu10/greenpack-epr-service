"""Tests for production-style application startup imports."""

from fastapi import FastAPI


def test_app_imports_without_rag_mock() -> None:
    """Import the real FastAPI app without replacing RAG dependencies."""
    from app.main import app

    assert isinstance(app, FastAPI)
    assert app.title == "GreenPack EPR Service"

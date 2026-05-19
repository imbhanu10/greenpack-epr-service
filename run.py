"""Development server runner for the GreenPack EPR service."""

import uvicorn


def main() -> None:
    """Run the FastAPI application with Uvicorn."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()

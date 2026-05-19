"""Tests for RAG API fallback behavior."""

from fastapi.testclient import TestClient


def test_rag_unknown_answer_fallback(
    client: TestClient,
    monkeypatch,
) -> None:
    """Return the anti-hallucination fallback for unknown answers."""
    from app.api import routes

    monkeypatch.setattr(
        routes,
        "answer_question",
        lambda _question: {
            "answer": "I do not know based on the provided documents",
            "citations": [],
        },
    )

    response = client.post(
        "/ask",
        json={"question": "What is the capital of Mars?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "I do not know based on the provided documents",
        "citations": [],
    }

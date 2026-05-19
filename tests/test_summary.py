"""Tests for deterministic reconciliation and LLM summary integration."""

from fastapi.testclient import TestClient

from tests.test_submit import VALID_DECLARATION


def test_reconciliation_flags_mismatches(
    client: TestClient,
    monkeypatch,
) -> None:
    """Return structured reconciliation with mismatches above 5% flagged."""
    from app.api import routes

    monkeypatch.setattr(
        routes,
        "generate_reconciliation_summary",
        lambda _reconciliation_json: "Mock Gemini compliance summary.",
    )

    submit_response = client.post("/submit", json=VALID_DECLARATION)
    assert submit_response.status_code == 201

    response = client.get("/summary/GREENPACK-001/2026-04")

    assert response.status_code == 200
    body = response.json()
    results = {
        item["material_type"]: item
        for item in body["reconciliation_results"]
    }

    assert body["producer_id"] == "GREENPACK-001"
    assert body["month"] == "2026-04"
    assert body["llm_summary"] == "Mock Gemini compliance summary."
    assert results["flexible_plastic"]["is_mismatch"] is True
    assert results["flexible_plastic"]["variance_percent"] == 6.25
    assert results["rigid_plastic"]["is_mismatch"] is False
    assert results["multilayer_plastic"]["is_mismatch"] is False


def test_summary_uses_gemini_summary_layer(
    client: TestClient,
    monkeypatch,
) -> None:
    """Call the Gemini summary integration after deterministic reconciliation."""
    from app.api import routes

    calls: list[dict] = []

    def fake_summary(reconciliation_json: dict) -> str:
        calls.append(reconciliation_json)
        return "Flexible plastic needs review before filing."

    monkeypatch.setattr(
        routes,
        "generate_reconciliation_summary",
        fake_summary,
    )

    client.post("/submit", json=VALID_DECLARATION)
    response = client.get("/summary/GREENPACK-001/2026-04")

    assert response.status_code == 200
    assert response.json()["llm_summary"] == (
        "Flexible plastic needs review before filing."
    )
    assert calls
    assert calls[0]["items"]

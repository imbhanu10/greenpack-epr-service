"""Tests for declaration submission validation and persistence."""

from fastapi.testclient import TestClient


VALID_DECLARATION = {
    "producer_id": "GREENPACK-001",
    "month": "2026-04",
    "declared_quantities_kg": {
        "rigid_plastic": 12000,
        "flexible_plastic": 8500,
        "multilayer_plastic": 3200,
    },
}


def test_invalid_declaration_payload_is_rejected(client: TestClient) -> None:
    """Reject payloads that do not match the declaration schema."""
    response = client.post(
        "/submit",
        json={
            "producer_id": "GREENPACK-001",
            "month": "04-2026",
            "declared_quantities_kg": {"rigid_plastic": 12000},
            "unexpected": "field",
        },
    )

    assert response.status_code == 422


def test_negative_quantity_is_rejected(client: TestClient) -> None:
    """Reject declarations with negative material quantities."""
    payload = {
        **VALID_DECLARATION,
        "declared_quantities_kg": {
            "rigid_plastic": -1,
        },
    }

    response = client.post("/submit", json=payload)

    assert response.status_code == 422


def test_successful_declaration_submission(client: TestClient) -> None:
    """Persist a valid declaration and return the stored record."""
    response = client.post("/submit", json=VALID_DECLARATION)

    assert response.status_code == 201
    body = response.json()
    assert body["record_id"]
    assert body["producer_id"] == "GREENPACK-001"
    assert body["month"] == "2026-04"
    assert body["created_at"]
    assert body["declared_quantities_kg"]["rigid_plastic"] == "12000"

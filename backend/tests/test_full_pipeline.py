from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.getenv("GROQ_API_KEY"),
    reason="Requires GROQ_API_KEY and live LLM integration.",
)
def test_full_pipeline_buyer_primary_flow() -> None:
    """
    Simulate a realistic first-time buyer conversation and verify full pipeline behavior.
    """
    client = TestClient(app)
    session_id = str(uuid.uuid4())

    messages = [
        "Hi, I'm looking to buy my first home",
        "I'm relocating to Austin, Texas for a new job",
        "My budget is around 350-400K. I'm pre-approved for an FHA loan",
        "A single-family home with at least 3 bedrooms",
        "I need to move within 2-3 months",
        "Yes, you can save my info. My email is test@example.com",
    ]

    final = None
    for message in messages:
        response = client.post(
            "/api/chat/message",
            json={"session_id": session_id, "message": message},
        )
        assert response.status_code == 200, response.text
        final = response.json()

    assert final is not None

    # Pipeline completion and routing
    assert final["pipeline_complete"] is True
    assert final["bucket"] in {"hot", "warm", "cold"}
    assert isinstance(final["score"], int)

    # Expected lead profile direction
    lead_profile = final["lead_profile"]
    assert lead_profile["intent"] == "buyer_primary"
    assert lead_profile["financing_type"] == "fha"
    assert lead_profile["consent_given"] is True
    assert lead_profile["email"] == "test@example.com"

    # Intent confidence > 0.8 from stored agent output if available.
    # Since /api/chat/message does not return intent confidence directly, we assert
    # strong downstream score expectation from the orchestrator output.
    assert final["score"] >= 75
    assert final["bucket"] == "hot"

    # Compliance and policy behavior
    reason = (final.get("reason") or "").lower()
    assert "fair housing" not in reason
    assert "appreciation" not in reason
    assert "returns" not in reason
    # TCPA tracking should not hard-fail this flow.
    assert "tcpa_missing_phone_consent" not in reason

    # Routing should either hit Sheets or a configured mock destination.
    assert final.get("destination") in {"google_sheets", "stored", "mock", "blocked"}
    if final.get("destination") == "blocked":
        pytest.fail(f"Expected routable compliant flow, but got blocked: {final.get('reason')}")

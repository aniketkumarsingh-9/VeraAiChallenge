from __future__ import annotations

from datetime import datetime, timezone


def test_health_and_metadata(client) -> None:
    root = client.get("/")
    health = client.get("/v1/healthz")
    metadata = client.get("/v1/metadata")

    assert root.status_code == 200
    assert root.json()["status"] == "ok"
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert set(health.json()["contexts_loaded"].keys()) == {"merchant", "customer", "category", "trigger"}
    assert metadata.status_code == 200
    assert metadata.json()["team_name"] == "Test Team"
    assert metadata.json()["contact_email"] == "team@example.com"



def test_context_tick_and_reply_flow(client) -> None:
    context_response = client.post(
        "/v1/context",
        json={
            "scope": "merchant",
            "context_id": "m1",
            "version": 1,
            "payload": {
                "id": "m1",
                "identity": {"name": "Dr Meera"},
                "performance": {"ctr": 0.021, "sales": "down 12%"},
                "offers": [{"title": "Dental Cleaning", "price": 299, "currency": "₹"}],
                "category_id": "dentists",
            },
            "delivered_at": "2026-04-29T10:00:00Z",
        },
    )
    category_response = client.post(
        "/v1/context",
        json={"scope": "category", "context_id": "dentists", "version": 1, "payload": {"name": "Dentists", "voice": "clinical"}},
    )
    trigger_response = client.post(
        "/v1/context",
        json={"scope": "trigger", "context_id": "t1", "version": 1, "payload": {"id": "t1", "kind": "sales_dropped", "reason": "CTR slipped below peer median"}},
    )

    assert context_response.status_code == 200
    assert category_response.status_code == 200
    assert trigger_response.status_code == 200

    conflict = client.post(
        "/v1/context",
        json={
            "scope": "merchant",
            "context_id": "m1",
            "version": 0,
            "payload": {
                "id": "m1",
                "identity": {"name": "Dr Meera"},
                "performance": {"ctr": 0.021, "sales": "down 12%"},
                "offers": [{"title": "Dental Cleaning", "price": 299, "currency": "₹"}],
                "category_id": "dentists",
            },
        },
    )
    tick = client.post("/v1/tick", json={"now": "2026-04-29T10:30:00Z", "available_triggers": ["t1"]})
    assert tick.status_code == 200
    payload = tick.json()
    assert payload["actions"]
    assert payload["actions"][0]["merchant_id"] == "m1"
    assert payload["actions"][0]["conversation_id"]
    assert payload["actions"][0]["send_as"] == "vera"
    assert payload["actions"][0]["template_name"].startswith("vera_")
    assert payload["actions"][0]["suppression_key"]
    assert conflict.status_code == 409
    assert conflict.json()["reason"] == "stale_version"

    reply = client.post(
        "/v1/reply",
        json={"conversation_id": "conv1", "merchant_id": "m1", "from_role": "merchant", "message": "Yes, send it", "turn_number": 1},
    )
    assert reply.status_code == 200
    assert reply.json()["action"] == "send"


def test_auto_reply_and_opt_out_flows(client) -> None:
    auto_reply = client.post(
        "/v1/reply",
        json={"conversation_id": "conv_auto", "merchant_id": "m1", "from_role": "merchant", "message": "Thank you for contacting us! Our team will respond shortly.", "turn_number": 1},
    )
    assert auto_reply.status_code == 200
    assert auto_reply.json()["action"] == "end"

    opt_out = client.post(
        "/v1/reply",
        json={"conversation_id": "conv_optout", "merchant_id": "m1", "from_role": "merchant", "message": "Stop messaging me. This is useless spam.", "turn_number": 1},
    )
    assert opt_out.status_code == 200
    assert opt_out.json()["action"] == "end"

    intent = client.post(
        "/v1/reply",
        json={"conversation_id": "conv_intent", "merchant_id": "m1", "from_role": "merchant", "message": "Ok lets do it. Whats next?", "turn_number": 1},
    )
    assert intent.status_code == 200
    assert intent.json()["action"] == "send"
    assert "drafting" in intent.json()["body"].lower() or "proceeding" in intent.json()["body"].lower()


def test_bot_compose_module() -> None:
    from bot import compose, respond
    res = compose(
        {"slug": "dentists", "name": "Dentists"},
        {"id": "m1", "identity": {"name": "Dr Meera's Dental Clinic"}},
        {"id": "t1", "kind": "sales_dropped", "payload": {}},
    )
    assert "body" in res
    assert "cta" in res
    assert "send_as" in res
    assert "suppression_key" in res
    assert "rationale" in res
    assert "Dr Meera" in res["body"]

    resp = respond({}, "Thank you for contacting us! Our team will respond shortly.")
    assert resp["action"] == "end"


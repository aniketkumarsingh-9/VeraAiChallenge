from __future__ import annotations

from datetime import datetime, timezone

from app.domain.composer import compose
from app.domain.conversation import ConversationEngine
from app.domain.engine import DecisionEngine
from app.domain.rules import build_suppression_key
from app.domain.types import ContextScope, ContextSnapshot, ConversationState


def test_compose_matches_challenge_contract() -> None:
    action = compose(
        category={"name": "Dentists", "voice": "clinical"},
        merchant={
            "id": "m1",
            "identity": {"name": "Dr Meera"},
            "performance": {"ctr": 0.021, "sales": "down 12%"},
            "offers": [{"title": "Dental Cleaning", "price": 299, "currency": "₹"}],
        },
        trigger={"id": "t1", "kind": "sales_dropped", "reason": "CTR slipped below peer median"},
        customer={"identity": {"name": "Priya"}, "consent": "opted in"},
        score=92,
        suppression_key=build_suppression_key({"id": "m1"}, {"kind": "sales_dropped"}, datetime(2026, 4, 29, 10, 30, tzinfo=timezone.utc)),
        rationale="High-signal context supports a send.",
    )

    assert action.body
    assert action.cta == "multi_choice_slot"
    assert action.send_as == "merchant_on_behalf"
    assert action.conversation_id == "conv_customer_t1"
    assert action.template_name == "merchant_sales_dropped_v1"
    assert action.template_params[0] == "Priya"
    assert action.suppression_key
    assert "High-signal context" in action.rationale


def test_merchant_compose_uses_vera_send_as() -> None:
    action = compose(
        category={"name": "Dentists", "voice": "clinical"},
        merchant={
            "id": "m1",
            "identity": {"name": "Dr Meera"},
            "performance": {"ctr": 0.021, "sales": "down 12%"},
            "offers": [{"title": "Dental Cleaning", "price": 299, "currency": "₹"}],
        },
        trigger={"id": "t1", "kind": "sales_dropped", "reason": "CTR slipped below peer median"},
        score=92,
        suppression_key=build_suppression_key({"id": "m1"}, {"kind": "sales_dropped"}, datetime(2026, 4, 29, 10, 30, tzinfo=timezone.utc)),
        rationale="High-signal context supports a send.",
    )

    assert action.send_as == "vera"
    assert action.cta == "open_ended"
    assert action.conversation_id == "conv_m1_t1"
    assert action.template_name == "vera_sales_dropped_v1"


def test_decision_engine_is_deterministic() -> None:
    merchant = ContextSnapshot(
        scope=ContextScope.MERCHANT,
        context_id="m1",
        version=1,
        payload={
            "id": "m1",
            "identity": {"name": "Dr Meera"},
            "performance": {"ctr": 0.021, "sales": "down 12%"},
            "offers": [{"title": "Dental Cleaning", "price": 299, "currency": "₹"}],
            "category_id": "dentists",
        },
    )
    category = ContextSnapshot(scope=ContextScope.CATEGORY, context_id="dentists", version=1, payload={"name": "Dentists", "voice": "clinical"})
    trigger = ContextSnapshot(scope=ContextScope.TRIGGER, context_id="t1", version=1, payload={"id": "t1", "kind": "sales_dropped", "reason": "CTR slipped below peer median"})
    now = datetime(2026, 4, 29, 10, 30, tzinfo=timezone.utc)
    engine = DecisionEngine()

    actions_a = engine.evaluate_tick([merchant], [category], [trigger], [], ["t1"], now, lambda *_: False, 20)
    actions_b = engine.evaluate_tick([merchant], [category], [trigger], [], ["t1"], now, lambda *_: False, 20)

    assert actions_a == actions_b
    assert actions_a[0].suppression_key == build_suppression_key(merchant.payload, trigger.payload, now)
    assert "Dr Meera" in actions_a[0].body
    assert actions_a[0].cta == "open_ended"



def test_conversation_engine_transitions() -> None:
    engine = ConversationEngine()
    accepted = engine.decide("Yes, send it", 1, ConversationState.OPEN)
    rejected = engine.decide("No, stop", 1, ConversationState.OPEN)
    clarified = engine.decide("What offer should I use?", 1, ConversationState.OPEN)

    assert accepted.action.value == "send"
    assert rejected.action.value == "end"
    assert clarified.action.value == "wait"

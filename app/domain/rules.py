from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.domain.types import DecisionTrace

TRIGGER_PRIORITY: dict[str, int] = {
    "offer_expiring": 95,
    "sales_dropped": 92,
    "festival": 88,
    "local_event": 84,
    "high_customer_demand": 78,
    "research_digest": 74,
    "competitor_trend": 70,
    "offer_launched": 60,
    "inactive_merchant": 55,
    "reengagement": 50,
    "generic": 35,
}

NEGATIVE_REPLY_TOKENS = {
    "no",
    "not now",
    "stop",
    "unsubscribe",
    "opt out",
    "don't",
    "do not",
    "reject",
    "spam",
    "useless",
    "quit",
    "leave me alone",
    "cancel",
    "never",
}

ACCEPT_REPLY_TOKENS = {
    "yes",
    "send",
    "go ahead",
    "approve",
    "draft it",
    "proceed",
    "ok",
    "okay",
    "whats next",
    "what's next",
    "let's do it",
    "lets do it",
    "i want to join",
    "join",
    "sure",
    "do it",
}

CLARIFY_REPLY_TOKENS = {
    "what",
    "how",
    "which",
    "clarify",
    "explain",
    "details",
    "more info",
}

AUTO_REPLY_PATTERNS = [
    "thank you for contacting",
    "respond shortly",
    "automated assistant",
    "auto-reply",
    "automated reply",
    "will get back to you",
    "out of office",
    "thanks for reaching out",
    "system generated",
]



@dataclass(frozen=True, slots=True)
class RuleOutcome:
    score: int
    traces: tuple[DecisionTrace, ...]
    should_send: bool
    suppression_key: str | None
    reason: str



def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)



def nested_get(payload: Mapping[str, Any] | None, path: str, default: Any = None) -> Any:
    current: Any = payload or {}
    for segment in path.split("."):
        if isinstance(current, Mapping) and segment in current:
            current = current[segment]
        else:
            return default
    return current



def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()



def normalize_token(value: Any) -> str:
    return as_text(value).lower()



def merchant_name(payload: Mapping[str, Any] | None) -> str:
    for key in ("identity.name", "name", "merchant_name", "business_name", "display_name"):
        value = nested_get(payload, key)
        if value:
            return as_text(value)
    return "Merchant"



def merchant_id(payload: Mapping[str, Any] | None, fallback: str = "merchant") -> str:
    for key in ("id", "merchant_id", "context_id", "identity.id"):
        value = nested_get(payload, key)
        if value:
            return as_text(value)
    return fallback



def category_name(payload: Mapping[str, Any] | None) -> str:
    for key in ("display_name", "name", "category", "category_slug", "vertical", "segment"):
        value = nested_get(payload, key)
        if value:
            return as_text(value)
    return "general"



def trigger_kind(payload: Mapping[str, Any] | None) -> str:
    for key in ("kind", "type", "name", "trigger_type", "reason"):
        value = nested_get(payload, key)
        if value:
            return normalize_token(value).replace(" ", "_")
    return "generic"



def trigger_id(payload: Mapping[str, Any] | None, fallback: str = "trigger") -> str:
    for key in ("id", "trigger_id", "context_id"):
        value = nested_get(payload, key)
        if value:
            return as_text(value)
    return fallback



def customer_id(payload: Mapping[str, Any] | None, fallback: str = "customer") -> str:
    for key in ("id", "customer_id", "context_id"):
        value = nested_get(payload, key)
        if value:
            return as_text(value)
    return fallback



def percent_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return as_text(value)
    if 0 <= numeric <= 1:
        numeric *= 100
    if numeric.is_integer():
        return f"{int(numeric)}%"
    return f"{numeric:.1f}%"



def money_text(value: Any, currency: Any = "₹") -> str:
    if value is None:
        return ""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return f"{currency}{as_text(value)}"
    if numeric.is_integer():
        return f"{currency}{int(numeric)}"
    return f"{currency}{numeric:.2f}"



def first_truthy(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}, ()):
            return value
    return None



def offer_summary(merchant_payload: Mapping[str, Any] | None) -> str:
    offers = nested_get(merchant_payload, "offers", [])
    if not isinstance(offers, list) or not offers:
        return ""
    first_offer = offers[0]
    if not isinstance(first_offer, Mapping):
        return as_text(first_offer)
    title = as_text(first_truthy(nested_get(first_offer, "title"), nested_get(first_offer, "name"), nested_get(first_offer, "headline")))
    price = first_truthy(nested_get(first_offer, "price"), nested_get(first_offer, "amount"), nested_get(first_offer, "discount_price"))
    currency = first_truthy(nested_get(first_offer, "currency"), nested_get(first_offer, "currency_symbol"), "₹")
    if title and price is not None:
        return f"{title} at {money_text(price, currency)}"
    if title:
        return title
    return as_text(first_offer)



def performance_hint(merchant_payload: Mapping[str, Any] | None) -> str:
    metrics = nested_get(merchant_payload, "performance", {})
    if not isinstance(metrics, Mapping):
        return ""
    ctr = first_truthy(metrics.get("ctr"), metrics.get("click_through_rate"))
    sales = first_truthy(metrics.get("sales"), metrics.get("sales_change"), metrics.get("revenue_change"))
    pieces: list[str] = []
    if ctr is not None:
        pieces.append(f"CTR {percent_text(ctr)}")
    if sales is not None:
        pieces.append(f"sales {as_text(sales)}")
    return ", ".join(piece for piece in pieces if piece)



def customer_hint(customer_payload: Mapping[str, Any] | None) -> str:
    if not customer_payload:
        return ""
    consent = as_text(first_truthy(nested_get(customer_payload, "consent"), nested_get(customer_payload, "relationship")))
    preference = as_text(first_truthy(nested_get(customer_payload, "preference"), nested_get(customer_payload, "channel_preference")))
    parts = [part for part in (consent, preference) if part]
    return ", ".join(parts)



def trigger_hint(trigger_payload: Mapping[str, Any] | None) -> str:
    """Return a human-readable hint string from the trigger payload.

    Intentionally omits the numeric ``urgency`` / ``priority`` fields because
    those are internal scoring inputs, not display-ready text, and their
    str() representation ("1", "2" …) was leaking into composed message bodies.
    """
    if not trigger_payload:
        return ""
    reason = as_text(first_truthy(
        nested_get(trigger_payload, "reason"),
        nested_get(trigger_payload, "summary"),
        nested_get(trigger_payload, "description"),
    ))
    return reason



def score_trigger(merchant_payload: Mapping[str, Any] | None, category_payload: Mapping[str, Any] | None, trigger_payload: Mapping[str, Any] | None, customer_payload: Mapping[str, Any] | None, now: datetime, suppression_hit: bool) -> RuleOutcome:
    trigger = trigger_payload or {}
    merchant = merchant_payload or {}
    category = category_payload or {}
    customer = customer_payload or {}

    traces: list[DecisionTrace] = []
    score = 0

    kind = trigger_kind(trigger)
    priority = TRIGGER_PRIORITY.get(kind, TRIGGER_PRIORITY["generic"])
    score += priority
    traces.append(DecisionTrace(rule="trigger_priority", score_delta=priority, rationale=f"Trigger kind {kind!r} maps to base priority {priority}."))

    category_voice = as_text(first_truthy(nested_get(category, "voice"), nested_get(category, "tone"), nested_get(category, "style")))
    if category_voice:
        score += 4
        traces.append(DecisionTrace(rule="category_voice", score_delta=4, rationale=f"Category voice is {category_voice!r}, enabling grounded tone choice."))

    hint = performance_hint(merchant)
    if hint:
        score += 6
        traces.append(DecisionTrace(rule="merchant_performance", score_delta=6, rationale=f"Merchant performance facts are available: {hint}."))

    offer = offer_summary(merchant)
    if offer:
        score += 8
        traces.append(DecisionTrace(rule="offer_available", score_delta=8, rationale=f"An explicit offer is present: {offer}."))

    customer_context = customer_hint(customer)
    if customer_context:
        score += 3
        traces.append(DecisionTrace(rule="customer_context", score_delta=3, rationale=f"Customer context is present: {customer_context}."))

    trigger_context = trigger_hint(trigger)
    if trigger_context:
        score += 5
        traces.append(DecisionTrace(rule="trigger_context", score_delta=5, rationale=f"Trigger context provides decision support: {trigger_context}."))

    if suppression_hit:
        score -= 100
        traces.append(DecisionTrace(rule="suppression", score_delta=-100, rationale="Matching suppression key is active, so this send must be blocked."))

    if nested_get(customer, "opted_out") is True:
        score -= 100
        traces.append(DecisionTrace(rule="customer_opt_out", score_delta=-100, rationale="Customer opted out, so no message should be sent."))

    if nested_get(merchant, "conversation.completed") is True:
        score -= 100
        traces.append(DecisionTrace(rule="conversation_complete", score_delta=-100, rationale="Conversation is already completed."))

    if kind in {"offer_expiring", "sales_dropped", "festival"}:
        score += 10
        traces.append(DecisionTrace(rule="high_value_trigger", score_delta=10, rationale=f"Trigger {kind!r} is a high-value send moment."))

    should_send = score >= 60
    suppression_key = None if not should_send else build_suppression_key(merchant, trigger, now)
    reason = "High-signal context supports a send." if should_send else "Context signal is too weak or blocked by suppression."
    return RuleOutcome(score=score, traces=tuple(traces), should_send=should_send, suppression_key=suppression_key, reason=reason)



def build_suppression_key(merchant_payload: Mapping[str, Any] | None, trigger_payload: Mapping[str, Any] | None, now: datetime) -> str:
    merchant_part = merchant_id(merchant_payload)
    trigger_part = trigger_kind(trigger_payload)
    week = now.isocalendar()
    return f"{merchant_part}:{trigger_part}:{week.year}-W{week.week:02d}"



def has_negative_reply(text: str) -> bool:
    normalized = normalize_token(text)
    return any(token in normalized for token in NEGATIVE_REPLY_TOKENS)



def has_accept_reply(text: str) -> bool:
    normalized = normalize_token(text)
    return any(token in normalized for token in ACCEPT_REPLY_TOKENS)



def needs_clarification(text: str) -> bool:
    normalized = normalize_token(text)
    return "?" in normalized or any(token in normalized for token in CLARIFY_REPLY_TOKENS)


def looks_like_auto_reply(text: str) -> bool:
    normalized = normalize_token(text)
    return any(pattern in normalized for pattern in AUTO_REPLY_PATTERNS)


"""
magicpin AI Challenge — Vera AI Bot Entrypoint
===============================================
Exposes top-level `compose` function as required by Section 7.1 of `challenge-brief.md`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.domain.composer import compose as domain_compose
from app.domain.rules import build_suppression_key


def compose(
    category: dict[str, Any] | None,
    merchant: dict[str, Any] | None,
    trigger: dict[str, Any] | None,
    customer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Composes a deterministic WhatsApp message given 4-layer context.

    Args:
        category: CategoryContext dict
        merchant: MerchantContext dict
        trigger: TriggerContext dict
        customer: Optional CustomerContext dict

    Returns:
        dict containing keys: body, cta, send_as, suppression_key, rationale
    """
    category_payload = category or {}
    merchant_payload = merchant or {}
    trigger_payload = trigger or {}
    customer_payload = customer

    now = datetime.now(tz=timezone.utc)
    supp_key = build_suppression_key(merchant_payload, trigger_payload, now)

    action = domain_compose(
        category=category_payload,
        merchant=merchant_payload,
        trigger=trigger_payload,
        customer=customer_payload,
        score=85,
        suppression_key=supp_key,
        rationale="Grounded context composition via deterministic decision engine.",
    )

    return {
        "body": action.body,
        "cta": action.cta,
        "send_as": action.send_as,
        "suppression_key": action.suppression_key,
        "rationale": action.rationale,
    }


from conversation_handlers import respond


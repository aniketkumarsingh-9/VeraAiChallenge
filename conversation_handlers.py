"""
magicpin AI Challenge — Conversation Handlers Module
=====================================================
Multi-turn interaction handler for merchant and customer replies.
Exposes `respond(state, merchant_message) -> dict` as defined in Section 7.4 of `challenge-brief.md`.
"""

from __future__ import annotations

from typing import Any
from app.domain.rules import has_accept_reply, has_negative_reply, looks_like_auto_reply, needs_clarification


def respond(state: dict[str, Any] | str, merchant_message: str) -> dict[str, Any]:
    """
    Given the conversation state and the merchant's latest message, produce the next action.

    Args:
        state: Conversation state object or string identifier
        merchant_message: Incoming message string from merchant

    Returns:
        dict containing keys: action, body, cta, wait_seconds, rationale
    """
    normalized = merchant_message.strip().lower()

    if looks_like_auto_reply(normalized):
        return {
            "action": "end",
            "body": None,
            "cta": None,
            "wait_seconds": None,
            "rationale": "Auto-reply pattern detected; ending conversation to avoid message pollution.",
        }
    elif has_negative_reply(normalized):
        return {
            "action": "end",
            "body": None,
            "cta": None,
            "wait_seconds": None,
            "rationale": "Merchant requested to stop / opted out; gracefully ending conversation.",
        }
    elif has_accept_reply(normalized) or any(phrase in normalized for phrase in ("what's next", "whats next", "what next", "let's do it", "lets do it", "i want to join", "join magicpin")):
        return {
            "action": "send",
            "body": "Great, proceeding now! Here is the next step: I am drafting the campaign with your exact context details. Confirm to publish or let me know if you want any adjustments.",
            "cta": "binary_confirm_cancel",
            "wait_seconds": None,
            "rationale": "Merchant committed; switching immediately from qualification mode to action execution mode.",
        }
    elif needs_clarification(normalized):
        return {
            "action": "wait",
            "body": "I need one more detail to avoid inventing facts. Which offer, audience, or time slot should I use?",
            "cta": None,
            "wait_seconds": 1800,
            "rationale": "Merchant asked for clarification; backing off briefly.",
        }

    return {
        "action": "send",
        "body": "Understood. Please confirm if you would like to proceed with the proposed listing updates or campaign.",
        "cta": "open_ended",
        "wait_seconds": None,
        "rationale": "Continuing active thread with open-ended offer.",
    }

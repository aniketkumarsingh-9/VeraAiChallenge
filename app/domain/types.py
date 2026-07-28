from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class ContextScope(str, Enum):
    MERCHANT = "merchant"
    CUSTOMER = "customer"
    CATEGORY = "category"
    TRIGGER = "trigger"


class ConversationState(str, Enum):
    OPEN = "open"
    AWAITING_REPLY = "awaiting_reply"
    COMPLETED = "completed"
    SUPPRESSED = "suppressed"


class ReplyAction(str, Enum):
    SEND = "send"
    WAIT = "wait"
    END = "end"


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    scope: ContextScope
    context_id: str
    version: int
    payload: Mapping[str, Any]
    delivered_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DecisionInput:
    merchant: Mapping[str, Any]
    category: Mapping[str, Any]
    trigger: Mapping[str, Any]
    customer: Mapping[str, Any] | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    rule: str
    score_delta: int
    rationale: str


@dataclass(frozen=True, slots=True)
class DecisionAction:
    conversation_id: str
    merchant_id: str
    customer_id: str | None
    trigger_id: str
    send_as: str
    template_name: str
    template_params: tuple[str, ...]
    body: str
    cta: str
    suppression_key: str
    rationale: str
    score: int
    traces: tuple[DecisionTrace, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ReplyDecision:
    action: ReplyAction
    rationale: str
    conversation_state: ConversationState
    body: str | None = None
    cta: str | None = None
    wait_seconds: int | None = None

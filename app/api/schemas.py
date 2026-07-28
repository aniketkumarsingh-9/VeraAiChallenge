from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.types import ConversationState, ReplyAction


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextRequest(StrictBaseModel):
    scope: Literal["merchant", "customer", "category", "trigger"]
    context_id: str = Field(min_length=1)
    version: int = Field(ge=0)
    payload: dict[str, Any]
    delivered_at: datetime | None = None


class ContextAckResponse(StrictBaseModel):
    accepted: bool
    ack_id: str
    stored_at: datetime


class TickRequest(StrictBaseModel):
    now: datetime | None = None
    available_triggers: list[str] = Field(default_factory=list)


class TickAction(StrictBaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: str | None = None
    send_as: Literal["vera", "merchant_on_behalf"]
    trigger_id: str
    template_name: str
    template_params: list[str] = Field(default_factory=list)
    body: str
    cta: str
    suppression_key: str
    rationale: str
    score: int


class TickResponse(StrictBaseModel):
    actions: list[TickAction] = Field(default_factory=list)


class ReplyRequest(StrictBaseModel):
    conversation_id: str = Field(min_length=1)
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: Literal["merchant", "customer"]
    message: str = Field(min_length=1)
    received_at: datetime | None = None
    turn_number: int = Field(ge=0)


class ReplyResponse(StrictBaseModel):
    action: ReplyAction
    body: str | None = None
    cta: str | None = None
    wait_seconds: int | None = None
    rationale: str
    conversation_state: ConversationState


class HealthResponse(StrictBaseModel):
    status: str
    uptime_seconds: int
    contexts_loaded: dict[str, int]


class MetadataResponse(StrictBaseModel):
    team_name: str
    team_members: list[str]
    model: str
    approach: str
    contact_email: str
    submitted_at: datetime
    version: str

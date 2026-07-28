from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class VersionedContextMixin(TimestampMixin):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    context_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MerchantContextRow(VersionedContextMixin, Base):
    __tablename__ = "merchants"


class CustomerContextRow(VersionedContextMixin, Base):
    __tablename__ = "customers"


class CategoryContextRow(VersionedContextMixin, Base):
    __tablename__ = "categories"


class TriggerContextRow(VersionedContextMixin, Base):
    __tablename__ = "triggers"


class OfferContextRow(VersionedContextMixin, Base):
    __tablename__ = "offers"


class CampaignContextRow(VersionedContextMixin, Base):
    __tablename__ = "campaigns"


class ContextHistoryRow(TimestampMixin, Base):
    __tablename__ = "context_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    context_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SuppressionKeyRow(TimestampMixin, Base):
    __tablename__ = "suppression_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    suppression_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (UniqueConstraint("merchant_id", "suppression_key", name="uq_suppression_merchant_key"),)


class ConversationRow(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    merchant_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    history: Mapped[list["ConversationHistoryRow"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class ConversationHistoryRow(TimestampMixin, Base):
    __tablename__ = "conversation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    from_role: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    response_body: Mapped[str] = mapped_column(Text, nullable=False)
    state_after: Mapped[str] = mapped_column(String(32), nullable=False)

    conversation: Mapped[ConversationRow] = relationship(back_populates="history")


class MessageRow(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    trigger_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str] = mapped_column(String(255), nullable=False)
    send_as: Mapped[str] = mapped_column(String(255), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    suppression_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DecisionLogRow(TimestampMixin, Base):
    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    trigger_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    traces_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class RuleExecutionHistoryRow(TimestampMixin, Base):
    __tablename__ = "rule_execution_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_log_id: Mapped[int] = mapped_column(ForeignKey("decision_logs.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    score_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.domain.rules import merchant_id
from app.domain.types import ContextScope, ContextSnapshot, ConversationState, ReplyAction
from app.persistence.models import (
    Base,
    CampaignContextRow,
    CategoryContextRow,
    ContextHistoryRow,
    ConversationHistoryRow,
    ConversationRow,
    CustomerContextRow,
    DecisionLogRow,
    MerchantContextRow,
    MessageRow,
    OfferContextRow,
    RuleExecutionHistoryRow,
    SuppressionKeyRow,
    TriggerContextRow,
)

CONTEXT_TABLES = {
    ContextScope.MERCHANT: MerchantContextRow,
    ContextScope.CUSTOMER: CustomerContextRow,
    ContextScope.CATEGORY: CategoryContextRow,
    ContextScope.TRIGGER: TriggerContextRow,
}


class ChallengeRepository:
    def __init__(self, session_factory: Callable[[], Session], suppression_days: int) -> None:
        self.session_factory = session_factory
        self.suppression_days = suppression_days

    def upsert_context(self, snapshot: ContextSnapshot) -> bool:
        table = CONTEXT_TABLES[snapshot.scope]
        with self.session_factory() as session:
            existing = session.scalar(select(table).where(table.context_id == snapshot.context_id))
            if existing and snapshot.version < existing.version:
                raise StaleVersionError(snapshot.context_id, existing.version)
            if existing and snapshot.version == existing.version:
                return True
            if existing is None:
                row = table(
                    context_id=snapshot.context_id,
                    version=snapshot.version,
                    payload_json=dict(snapshot.payload),
                    delivered_at=snapshot.delivered_at,
                )
                session.add(row)
            else:
                existing.version = snapshot.version
                existing.payload_json = dict(snapshot.payload)
                existing.delivered_at = snapshot.delivered_at
            session.add(
                ContextHistoryRow(
                    scope=snapshot.scope.value,
                    context_id=snapshot.context_id,
                    version=snapshot.version,
                    payload_json=dict(snapshot.payload),
                    delivered_at=snapshot.delivered_at,
                )
            )
            session.commit()
            return True

    def list_contexts(self, scope: ContextScope) -> list[ContextSnapshot]:
        table = CONTEXT_TABLES[scope]
        with self.session_factory() as session:
            rows = session.scalars(select(table).order_by(table.context_id.asc())).all()
            return [
                ContextSnapshot(scope=scope, context_id=row.context_id, version=row.version, payload=row.payload_json, delivered_at=row.delivered_at)
                for row in rows
            ]

    def context_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self.session_factory() as session:
            for scope, table in CONTEXT_TABLES.items():
                counts[scope.value] = session.scalar(select(func.count()).select_from(table)) or 0
        return counts

    def get_context_version(self, scope: ContextScope, context_id: str) -> int | None:
        table = CONTEXT_TABLES[scope]
        with self.session_factory() as session:
            row = session.scalar(select(table).where(table.context_id == context_id))
            return row.version if row is not None else None

    def get_conversation(self, conversation_id: str) -> ConversationRow | None:
        with self.session_factory() as session:
            return session.scalar(select(ConversationRow).where(ConversationRow.conversation_id == conversation_id))

    def get_or_create_conversation(self, conversation_id: str, merchant_id_value: str | None = None, customer_id_value: str | None = None) -> ConversationRow:
        with self.session_factory() as session:
            conversation = session.scalar(select(ConversationRow).where(ConversationRow.conversation_id == conversation_id))
            if conversation is None:
                conversation = ConversationRow(
                    conversation_id=conversation_id,
                    merchant_id=merchant_id_value,
                    customer_id=customer_id_value,
                    state=ConversationState.OPEN.value,
                    turn_number=0,
                )
                session.add(conversation)
                session.commit()
                session.refresh(conversation)
            return conversation

    def update_conversation(self, conversation_id: str, state: ConversationState, turn_number: int) -> None:
        with self.session_factory() as session:
            conversation = session.scalar(select(ConversationRow).where(ConversationRow.conversation_id == conversation_id))
            if conversation is None:
                conversation = ConversationRow(
                    conversation_id=conversation_id,
                    state=state.value,
                    turn_number=turn_number,
                )
                session.add(conversation)
            else:
                conversation.state = state.value
                conversation.turn_number = turn_number
                if state == ConversationState.COMPLETED:
                    conversation.completed_at = datetime.now(tz=timezone.utc)
            session.commit()

    def record_conversation_history(
        self,
        conversation_id: str,
        turn_number: int,
        from_role: str,
        message: str,
        action: ReplyAction,
        response_body: str,
        state_after: ConversationState,
    ) -> None:
        with self.session_factory() as session:
            conversation = session.scalar(select(ConversationRow).where(ConversationRow.conversation_id == conversation_id))
            if conversation is None:
                conversation = ConversationRow(conversation_id=conversation_id, state=state_after.value, turn_number=turn_number)
                session.add(conversation)
                session.flush()
            session.add(
                ConversationHistoryRow(
                    conversation_id=conversation.id,
                    turn_number=turn_number,
                    from_role=from_role,
                    message=message,
                    action=action.value,
                    response_body=response_body,
                    state_after=state_after.value,
                )
            )
            conversation.state = state_after.value
            conversation.turn_number = turn_number
            if state_after == ConversationState.COMPLETED:
                conversation.completed_at = datetime.now(tz=timezone.utc)
            session.commit()

    def conversation_history(self, conversation_id: str) -> list[ConversationHistoryRow]:
        with self.session_factory() as session:
            conversation = session.scalar(select(ConversationRow).where(ConversationRow.conversation_id == conversation_id))
            if conversation is None:
                return []
            rows = session.scalars(
                select(ConversationHistoryRow)
                .where(ConversationHistoryRow.conversation_id == conversation.id)
                .order_by(ConversationHistoryRow.turn_number.asc(), ConversationHistoryRow.id.asc())
            ).all()
            return list(rows)

    def store_suppression(self, merchant_id_value: str, suppression_key: str, reason: str, now: datetime) -> None:
        expires_at = now + timedelta(days=self.suppression_days)
        with self.session_factory() as session:
            existing = session.scalar(
                select(SuppressionKeyRow).where(
                    SuppressionKeyRow.merchant_id == merchant_id_value,
                    SuppressionKeyRow.suppression_key == suppression_key,
                )
            )
            if existing is None:
                session.add(
                    SuppressionKeyRow(
                        merchant_id=merchant_id_value,
                        suppression_key=suppression_key,
                        reason=reason,
                        expires_at=expires_at,
                    )
                )
            else:
                existing.reason = reason
                existing.expires_at = expires_at
            session.commit()

    def is_suppressed(self, merchant_id_value: str, suppression_key: str, now: datetime) -> bool:
        with self.session_factory() as session:
            row = session.scalar(
                select(SuppressionKeyRow).where(
                    SuppressionKeyRow.merchant_id == merchant_id_value,
                    SuppressionKeyRow.suppression_key == suppression_key,
                    SuppressionKeyRow.expires_at > now,
                )
            )
            return row is not None

    def record_decision(
        self,
        merchant_id_value: str,
        trigger_id_value: str,
        decision: str,
        score: int,
        rationale: str,
        traces: Iterable[Mapping[str, Any]],
    ) -> int:
        with self.session_factory() as session:
            row = DecisionLogRow(
                merchant_id=merchant_id_value,
                trigger_id=trigger_id_value,
                decision=decision,
                score=score,
                rationale=rationale,
                traces_json={"traces": [dict(trace) for trace in traces]},
            )
            session.add(row)
            session.flush()
            for trace in traces:
                session.add(
                    RuleExecutionHistoryRow(
                        decision_log_id=row.id,
                        rule_name=str(trace.get("rule", "rule")),
                        score_delta=int(trace.get("score_delta", 0)),
                        rationale=str(trace.get("rationale", "")),
                    )
                )
            session.commit()
            return row.id

    def record_message(
        self,
        merchant_id_value: str,
        trigger_id_value: str,
        conversation_id: str | None,
        body: str,
        cta: str,
        send_as: str,
        rationale: str,
        suppression_key: str,
        score: int,
    ) -> None:
        with self.session_factory() as session:
            session.add(
                MessageRow(
                    merchant_id=merchant_id_value,
                    trigger_id=trigger_id_value,
                    conversation_id=conversation_id,
                    body=body,
                    cta=cta,
                    send_as=send_as,
                    rationale=rationale,
                    suppression_key=suppression_key,
                    score=score,
                )
            )
            session.commit()

    def load_all_contexts(self) -> dict[ContextScope, list[ContextSnapshot]]:
        return {scope: self.list_contexts(scope) for scope in CONTEXT_TABLES}


class StaleVersionError(ValueError):
    def __init__(self, context_id: str, current_version: int) -> None:
        super().__init__(f"context {context_id!r} has current version {current_version}")
        self.context_id = context_id
        self.current_version = current_version

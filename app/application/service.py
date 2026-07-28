from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.api import schemas
from app.domain.conversation import ConversationEngine
from app.domain.engine import DecisionEngine
from app.domain.rules import has_accept_reply, has_negative_reply, needs_clarification
from app.domain.types import ContextScope, ContextSnapshot, ConversationState, ReplyAction, ReplyDecision
from app.persistence.repositories import ChallengeRepository, StaleVersionError


class ChallengeService:
    def __init__(self, repository: ChallengeRepository, decision_engine: DecisionEngine, conversation_engine: ConversationEngine, settings: Any, started_at: datetime) -> None:
        self.repository = repository
        self.decision_engine = decision_engine
        self.conversation_engine = conversation_engine
        self.settings = settings
        self.started_at = started_at

    def ingest_context(self, request: schemas.ContextRequest) -> schemas.ContextAckResponse:
        snapshot = ContextSnapshot(
            scope=ContextScope(request.scope),
            context_id=request.context_id,
            version=request.version,
            payload=request.payload,
            delivered_at=request.delivered_at,
        )
        accepted = self.repository.upsert_context(snapshot)
        stored_at = datetime.now(tz=timezone.utc)
        return schemas.ContextAckResponse(accepted=accepted, ack_id=f"ack_{snapshot.context_id}_v{snapshot.version}", stored_at=stored_at)

    def health(self) -> schemas.HealthResponse:
        counts = self.repository.context_counts()
        uptime_seconds = max(0, int((datetime.now(tz=timezone.utc) - self.started_at).total_seconds()))
        return schemas.HealthResponse(status="ok", uptime_seconds=uptime_seconds, contexts_loaded=counts)

    def metadata(self) -> schemas.MetadataResponse:
        team_members = [member.strip() for member in self.settings.team_members.split(",") if member.strip()]
        return schemas.MetadataResponse(
            team_name=self.settings.team_name,
            team_members=team_members,
            model=self.settings.team_model,
            approach="single-prompt compose(category, merchant, trigger, customer?) engine with retrieval over digest items",
            contact_email=self.settings.contact_email,
            submitted_at=self.settings.submitted_at,
            version="1.2.0",
        )

    def tick(self, request: schemas.TickRequest) -> schemas.TickResponse:
        now = request.now or datetime.now(tz=timezone.utc)
        contexts = self.repository.load_all_contexts()
        actions = self.decision_engine.evaluate_tick(
            merchants=contexts[ContextScope.MERCHANT],
            categories=contexts[ContextScope.CATEGORY],
            triggers=contexts[ContextScope.TRIGGER],
            customers=contexts[ContextScope.CUSTOMER],
            available_trigger_ids=request.available_triggers,
            now=now,
            is_suppressed=self.repository.is_suppressed,
            max_actions=self.settings.max_actions_per_tick,
        )
        emitted_actions: list[schemas.TickAction] = []
        for action in actions:
            if self.repository.is_suppressed(action.merchant_id, action.suppression_key, now):
                continue
            self.repository.store_suppression(action.merchant_id, action.suppression_key, action.rationale, now)
            self.repository.record_message(
                merchant_id_value=action.merchant_id,
                trigger_id_value=action.trigger_id,
                conversation_id=action.conversation_id,
                body=action.body,
                cta=action.cta,
                send_as=action.send_as,
                rationale=action.rationale,
                suppression_key=action.suppression_key,
                score=action.score,
            )
            self.repository.record_decision(
                merchant_id_value=action.merchant_id,
                trigger_id_value=action.trigger_id,
                decision="send",
                score=action.score,
                rationale=action.rationale,
                traces=[asdict_trace(trace) for trace in action.traces],
            )
            emitted_actions.append(
                schemas.TickAction(
                    conversation_id=action.conversation_id,
                    merchant_id=action.merchant_id,
                    customer_id=action.customer_id,
                    send_as=action.send_as,
                    trigger_id=action.trigger_id,
                    template_name=action.template_name,
                    template_params=list(action.template_params),
                    body=action.body,
                    cta=action.cta,
                    suppression_key=action.suppression_key,
                    rationale=action.rationale,
                    score=action.score,
                )
            )
        return schemas.TickResponse(actions=emitted_actions)

    def reply(self, request: schemas.ReplyRequest) -> schemas.ReplyResponse:
        conversation = self.repository.get_or_create_conversation(request.conversation_id, request.merchant_id, request.customer_id)
        current_state = ConversationState(conversation.state)
        normalized_message = request.message.strip().lower()

        if looks_like_auto_reply(normalized_message):
            decision = ReplyDecision(
                action=ReplyAction.END,
                body=None,
                cta=None,
                wait_seconds=None,
                rationale="Detected merchant auto-reply pattern; ending conversation to prevent message pollution.",
                conversation_state=ConversationState.COMPLETED,
            )
        elif has_negative_reply(normalized_message):
            decision = ReplyDecision(
                action=ReplyAction.END,
                body=None,
                cta=None,
                wait_seconds=None,
                rationale="Merchant explicitly opted out / expressed hostility. Closing the conversation.",
                conversation_state=ConversationState.COMPLETED,
            )
        elif has_accept_reply(normalized_message) or any(phrase in normalized_message for phrase in ("what's next", "what next", "whats next", "let's do it", "lets do it", "i want to join", "join magicpin")):
            decision = ReplyDecision(
                action=ReplyAction.SEND,
                body="Great, proceeding now! Here is the next step: I am drafting the campaign with your exact context details. Confirm to publish or let me know if you want any adjustments.",
                cta="binary_confirm_cancel",
                wait_seconds=None,
                rationale="Merchant committed; switching immediately from qualification to action execution mode.",
                conversation_state=ConversationState.AWAITING_REPLY,
            )
        elif needs_clarification(normalized_message):
            decision = ReplyDecision(
                action=ReplyAction.WAIT,
                body="I need one more detail to avoid inventing facts. Which offer, audience, or time slot should I use?",
                cta=None,
                wait_seconds=1800,
                rationale="Merchant asked for more context; backing off briefly.",
                conversation_state=ConversationState.AWAITING_REPLY,
            )
        elif looks_off_topic(normalized_message):
            decision = ReplyDecision(
                action=ReplyAction.SEND,
                body="I’ll leave that to your CA. Coming back to the original thread, should I send the draft or the abstract first?",
                cta="open_ended",
                wait_seconds=None,
                rationale="Out-of-scope ask detected; politely redirected to the active thread.",
                conversation_state=ConversationState.AWAITING_REPLY,
            )
        else:
            decision = self.conversation_engine.decide(request.message, request.turn_number, current_state)

        self.repository.update_conversation(request.conversation_id, decision.conversation_state, request.turn_number)
        self.repository.record_conversation_history(
            conversation_id=request.conversation_id,
            turn_number=request.turn_number,
            from_role=request.from_role,
            message=request.message,
            action=decision.action,
            response_body=decision.body or "",
            state_after=decision.conversation_state,
        )
        return schemas.ReplyResponse(
            action=decision.action,
            body=decision.body,
            cta=decision.cta,
            wait_seconds=decision.wait_seconds,
            rationale=decision.rationale,
            conversation_state=decision.conversation_state,
        )



def asdict_trace(trace: Any) -> dict[str, Any]:
    return {"rule": trace.rule, "score_delta": trace.score_delta, "rationale": trace.rationale}



def looks_like_auto_reply(message: str) -> bool:
    return "thank you for contacting" in message and "respond shortly" in message



def looks_off_topic(message: str) -> bool:
    return any(token in message for token in ("gst", "tax", "invoice", "filing", "return", "accounting"))

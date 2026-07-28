from __future__ import annotations

from dataclasses import dataclass

from app.domain.rules import has_accept_reply, has_negative_reply, needs_clarification
from app.domain.types import ConversationState, ReplyAction, ReplyDecision


@dataclass(frozen=True, slots=True)
class ConversationTransition:
    action: ReplyAction
    next_state: ConversationState
    body: str
    rationale: str


class ConversationEngine:
    def decide(self, message: str, turn_number: int, current_state: ConversationState) -> ReplyDecision:
        normalized = message.strip().lower()

        if current_state == ConversationState.COMPLETED:
            return ReplyDecision(
                action=ReplyAction.END,
                rationale="Conversation state is completed.",
                conversation_state=ConversationState.COMPLETED,
                body="This conversation is already complete, so no further action will be taken.",
            )

        if has_negative_reply(normalized):
            return ReplyDecision(
                action=ReplyAction.END,
                rationale="Merchant replied with a negative or opt-out signal.",
                conversation_state=ConversationState.COMPLETED,
                body="Understood. I will suppress further follow-ups for this conversation.",
            )

        if has_accept_reply(normalized):
            return ReplyDecision(
                action=ReplyAction.SEND,
                rationale="Merchant accepted the draft or requested sending.",
                conversation_state=ConversationState.AWAITING_REPLY,
                body="Acknowledged. I will proceed with the grounded draft and keep the facts unchanged.",
                cta="binary_confirm_cancel",
            )

        if needs_clarification(normalized):
            return ReplyDecision(
                action=ReplyAction.WAIT,
                rationale="Merchant asked for clarification or more context.",
                conversation_state=ConversationState.AWAITING_REPLY,
                body="I need one more detail to avoid inventing facts. Which offer, CTA, or audience should I use?",
                cta="open_ended",
                wait_seconds=1800,
            )

        if turn_number >= 5:
            return ReplyDecision(
                action=ReplyAction.END,
                rationale="Conversation has reached the deterministic timeout threshold.",
                conversation_state=ConversationState.COMPLETED,
                body="I will stop the thread here to avoid repeating the same request.",
            )

        return ReplyDecision(
            action=ReplyAction.WAIT,
            rationale="Reply is ambiguous and does not justify a send.",
            conversation_state=ConversationState.OPEN,
            body="I can continue, but I need a clearer instruction before sending.",
            cta="open_ended",
            wait_seconds=1800,
        )

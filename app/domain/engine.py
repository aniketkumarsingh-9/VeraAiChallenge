from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.composer import compose
from app.domain.rules import build_suppression_key, category_name, merchant_id, merchant_name, score_trigger, trigger_id, trigger_kind
from app.domain.types import ContextSnapshot, DecisionAction, DecisionInput, DecisionTrace


@dataclass(frozen=True, slots=True)
class EvaluatedCandidate:
    merchant: ContextSnapshot
    trigger: ContextSnapshot
    category: ContextSnapshot | None
    customer: ContextSnapshot | None
    score: int
    traces: tuple[DecisionTrace, ...]
    should_send: bool
    suppression_key: str | None
    rationale: str


class DecisionEngine:
    def evaluate_tick(
        self,
        merchants: Iterable[ContextSnapshot],
        categories: Iterable[ContextSnapshot],
        triggers: Iterable[ContextSnapshot],
        customers: Iterable[ContextSnapshot],
        available_trigger_ids: Iterable[str] | None,
        now: datetime,
        is_suppressed: callable,
        max_actions: int,
    ) -> list[DecisionAction]:
        merchant_list = sorted(merchants, key=lambda item: item.context_id)
        category_list = sorted(categories, key=lambda item: item.context_id)
        trigger_list = sorted(triggers, key=lambda item: item.context_id)
        customer_list = sorted(customers, key=lambda item: item.context_id)
        available_ids = {str(trigger_id_value) for trigger_id_value in available_trigger_ids or []}

        evaluated: list[EvaluatedCandidate] = []
        for merchant in merchant_list:
            merchant_payload = merchant.payload
            merchant_category_id = related_context_id(merchant_payload, ("category_id", "category.context_id", "category_id_ref"))
            merchant_customer_id = related_context_id(merchant_payload, ("customer_id", "customer.context_id", "customer_id_ref"))
            category_context = select_context(category_list, merchant_category_id) if merchant_category_id else first_or_none(category_list)
            customer_context = select_context(customer_list, merchant_customer_id) if merchant_customer_id else first_or_none(customer_list)

            trigger_candidates = [trigger for trigger in trigger_list if not available_ids or trigger.context_id in available_ids]
            for trigger in trigger_candidates:
                if not trigger_applies_to_merchant(merchant.payload, trigger.payload):
                    continue

                trigger_category_id = related_context_id(trigger.payload, ("category_id", "category.context_id"))
                if category_context is None and trigger_category_id:
                    category_context = select_context(category_list, trigger_category_id)

                trigger_customer_id = related_context_id(trigger.payload, ("customer_id", "customer.context_id"))
                if customer_context is None and trigger_customer_id:
                    customer_context = select_context(customer_list, trigger_customer_id)

                decision_input = DecisionInput(
                    merchant=merchant.payload,
                    category=category_context.payload if category_context else {},
                    trigger=trigger.payload,
                    customer=customer_context.payload if customer_context else None,
                    now=now,
                )
                suppression_key = build_suppression_key(decision_input.merchant, decision_input.trigger, now)
                suppressed = is_suppressed(merchant_id(decision_input.merchant), suppression_key, now)
                outcome = score_trigger(
                    decision_input.merchant,
                    decision_input.category,
                    decision_input.trigger,
                    decision_input.customer,
                    now,
                    suppressed,
                )
                if not outcome.should_send:
                    continue
                if outcome.suppression_key is None:
                    continue
                evaluated.append(
                    EvaluatedCandidate(
                        merchant=merchant,
                        trigger=trigger,
                        category=category_context,
                        customer=customer_context,
                        score=outcome.score,
                        traces=outcome.traces,
                        should_send=outcome.should_send,
                        suppression_key=outcome.suppression_key,
                        rationale=outcome.reason,
                    )
                )

        chosen = sorted(
            evaluated,
            key=lambda item: (-item.score, merchant_id(item.merchant.payload), trigger_id(item.trigger.payload)),
        )[:max_actions]
        actions: list[DecisionAction] = []
        for candidate in chosen:
            decision_input = DecisionInput(
                merchant=candidate.merchant.payload,
                category=candidate.category.payload if candidate.category else {},
                trigger=candidate.trigger.payload,
                customer=candidate.customer.payload if candidate.customer else None,
                now=now,
            )
            action = compose(
                category=candidate.category.payload if candidate.category else {},
                merchant=candidate.merchant.payload,
                trigger=candidate.trigger.payload,
                customer=candidate.customer.payload if candidate.customer else None,
                score=candidate.score,
                suppression_key=candidate.suppression_key or build_suppression_key(candidate.merchant.payload, candidate.trigger.payload, now),
                rationale=candidate.rationale,
            )
            actions.append(
                DecisionAction(
                    conversation_id=action.conversation_id,
                    merchant_id=action.merchant_id,
                    customer_id=action.customer_id,
                    trigger_id=action.trigger_id,
                    send_as=action.send_as,
                    template_name=action.template_name,
                    template_params=action.template_params,
                    body=action.body,
                    cta=action.cta,
                    suppression_key=action.suppression_key,
                    rationale=action.rationale,
                    score=action.score,
                    traces=candidate.traces,
                )
            )
        return actions



def related_context_id(payload: Mapping[str, Any] | None, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = nested_lookup(payload, key)
        if value:
            return str(value)
    return None



def nested_lookup(payload: Mapping[str, Any] | None, path: str) -> Any:
    current: Any = payload or {}
    for segment in path.split("."):
        if isinstance(current, Mapping) and segment in current:
            current = current[segment]
        else:
            return None
    return current



def select_context(contexts: list[ContextSnapshot], context_id: str | None) -> ContextSnapshot | None:
    if context_id is None:
        return first_or_none(contexts)
    for context in contexts:
        if context.context_id == context_id:
            return context
    return first_or_none(contexts)



def first_or_none(contexts: list[ContextSnapshot]) -> ContextSnapshot | None:
    return contexts[0] if contexts else None



def trigger_applies_to_merchant(merchant_payload: Mapping[str, Any] | None, trigger_payload: Mapping[str, Any] | None) -> bool:
    trigger_merchant_id = related_context_id(trigger_payload, ("merchant_id", "merchant.context_id"))
    if trigger_merchant_id:
        merchant_context_id = related_context_id(merchant_payload, ("context_id", "merchant_id", "id"))
        return merchant_context_id == trigger_merchant_id
    trigger_category_id = related_context_id(trigger_payload, ("category_id", "category.context_id"))
    if trigger_category_id:
        merchant_category_id = related_context_id(merchant_payload, ("category_id", "category.context_id"))
        return merchant_category_id is None or merchant_category_id == trigger_category_id
    return True

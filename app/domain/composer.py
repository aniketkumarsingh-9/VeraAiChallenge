from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.rules import (
    as_text,
    category_name,
    customer_id,
    customer_hint,
    merchant_id,
    merchant_name,
    money_text,
    offer_summary,
    performance_hint,
    trigger_hint,
    trigger_kind,
)
from app.domain.types import DecisionAction, DecisionInput



def compose(
    category: Mapping[str, Any] | None,
    merchant: Mapping[str, Any] | None,
    trigger: Mapping[str, Any] | None,
    customer: Mapping[str, Any] | None = None,
    *,
    score: int = 0,
    suppression_key: str = "",
    rationale: str = "",
) -> DecisionAction:
    decision_input = DecisionInput(
        merchant=merchant or {},
        category=category or {},
        trigger=trigger or {},
        customer=customer,
    )
    return compose_action(
        decision_input=decision_input,
        score=score,
        suppression_key=suppression_key,
        rationale=rationale,
    )



def compose_action(decision_input: DecisionInput, score: int, suppression_key: str, rationale: str) -> DecisionAction:
    merchant = decision_input.merchant
    trigger = decision_input.trigger
    category = decision_input.category
    customer = decision_input.customer or {}

    body = compose_body(merchant, category, trigger, customer)
    cta = compose_cta(trigger, customer)
    send_as = compose_send_as(customer)
    conversation_id = compose_conversation_id(merchant, trigger, customer)
    template_name = compose_template_name(trigger, customer)
    template_params = compose_template_params(category, merchant, trigger, customer)
    decision_rationale = compose_rationale(merchant, category, trigger, customer, rationale)
    return DecisionAction(
        conversation_id=conversation_id,
        merchant_id=merchant_id(merchant),
        customer_id=customer_id(customer) if customer else None,
        trigger_id=trigger.get("id") or trigger.get("trigger_id") or "trigger",
        send_as=send_as,
        template_name=template_name,
        template_params=template_params,
        body=body,
        cta=cta,
        suppression_key=suppression_key,
        rationale=decision_rationale,
        score=score,
    )



def compose_send_as(customer: Mapping[str, Any] | None) -> str:
    return "merchant_on_behalf" if customer else "vera"



def compose_conversation_id(
    merchant: Mapping[str, Any] | None,
    trigger: Mapping[str, Any] | None,
    customer: Mapping[str, Any] | None,
) -> str:
    trigger_part = trigger.get("id") or trigger.get("trigger_id") or trigger_kind(trigger)
    if customer:
        return f"conv_{customer_id(customer)}_{trigger_part}"
    return f"conv_{merchant_id(merchant)}_{trigger_part}"



def compose_template_name(trigger: Mapping[str, Any] | None, customer: Mapping[str, Any] | None) -> str:
    prefix = "merchant" if customer else "vera"
    return f"{prefix}_{trigger_kind(trigger)}_v1"



def compose_template_params(
    category: Mapping[str, Any] | None,
    merchant: Mapping[str, Any] | None,
    trigger: Mapping[str, Any] | None,
    customer: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    name = merchant_name(merchant)
    kind = trigger_kind(trigger)
    offer = offer_summary(merchant)
    perf = performance_hint(merchant)
    trigger_detail = trigger_hint(trigger)
    identity = (customer or {}).get("identity", {}) if isinstance(customer, Mapping) else {}
    preferences = (customer or {}).get("preferences", {}) if isinstance(customer, Mapping) else {}
    customer_name = as_text(identity.get("name")) if isinstance(identity, Mapping) else ""
    preferred_slots = as_text(preferences.get("preferred_slots")) if isinstance(preferences, Mapping) else ""

    if customer:
        return tuple(
            piece
            for piece in (
                customer_name or "Customer",
                name,
                first_sentence(trigger_detail or f"{kind.replace('_', ' ')} trigger"),
                preferred_slots,
                offer,
            )
            if piece
        )

    return tuple(
        piece
        for piece in (
            name,
            first_sentence(trigger_detail or perf or offer or kind.replace("_", " ")),
            perf,
            offer,
            category_name(category),
        )
        if piece
    )



def compose_cta(trigger: Mapping[str, Any] | None, customer: Mapping[str, Any] | None) -> str:
    kind = trigger_kind(trigger)
    if customer:
        return "multi_choice_slot"
    if kind in {"offer_expiring", "offer_launched", "inactive_merchant"}:
        return "binary_yes_no"
    return "open_ended"



def compose_body(
    merchant: Mapping[str, Any] | None,
    category: Mapping[str, Any] | None,
    trigger: Mapping[str, Any] | None,
    customer: Mapping[str, Any] | None,
) -> str:
    name = merchant_name(merchant)
    cat = category_name(category)
    kind = trigger_kind(trigger)
    offer = offer_summary(merchant)
    perf = performance_hint(merchant)
    customer_context = customer_hint(customer)
    trigger_detail = trigger_hint(trigger)
    t_payload = (trigger or {}).get("payload", {}) if isinstance(trigger, Mapping) else {}

    if customer:
        identity = (customer or {}).get("identity", {}) if isinstance(customer, Mapping) else {}
        preferences = (customer or {}).get("preferences", {}) if isinstance(customer, Mapping) else {}
        customer_name = as_text(identity.get("name")) if isinstance(identity, Mapping) else "Customer"
        preferred_slots = as_text(preferences.get("preferred_slots")) if isinstance(preferences, Mapping) else ""
        
        # Check trigger payload for specific available slots
        avail_slots = t_payload.get("available_slots", [])
        if avail_slots and isinstance(avail_slots, list):
            slot_labels = [s.get("label", "") for s in avail_slots if isinstance(s, dict) and "label" in s]
            slots_str = " or ".join(slot_labels) if slot_labels else preferred_slots
        else:
            slots_str = preferred_slots

        service_due = t_payload.get("service_due", "cleaning").replace("_", " ")
        lead = f"Hi {customer_name}, {name}'s clinic here 🦷" if cat.lower() == "dentists" else f"Hi {customer_name}, {name} here"
        slots_part = f" Available slots: {slots_str}." if slots_str else ""
        offer_part = f" {offer}." if offer else ""
        return f"{lead}. It has been a while since your last visit — your {service_due} recall is due.{slots_part}{offer_part} Reply 1 or 2 for a slot, or tell us what time works!".strip()

    # Research Digest or Regulation Change
    if kind in {"research_digest", "regulation_change"}:
        top_item_id = t_payload.get("top_item_id")
        digest_item = find_digest_item(category, top_item_id) if top_item_id else None
        if digest_item:
            title = digest_item.get("title", "")
            source = digest_item.get("source", "")
            trial_n = digest_item.get("trial_n", "")
            n_str = f" ({trial_n}-patient trial)" if trial_n else ""
            cite_str = f" — {source}" if source else ""
            return f"{name}, {source or 'industry update'} landed. '{title}'{n_str}. Relevant to your clinic's patient cohort. Want me to pull the abstract and draft a customer update?{cite_str}".strip()
        
        citation = nested_trigger_source(trigger)
        citation_part = f" — {citation}" if citation else ""
        return f"{name}, new research signal available. {trigger_detail or perf}. Want me to draft a concise merchant update for your {cat} context?{citation_part}".strip()

    # Performance Dip
    if kind in {"perf_dip", "seasonal_perf_dip"}:
        metric = t_payload.get("metric", "views")
        delta_pct = t_payload.get("delta_pct")
        window = t_payload.get("window", "7d")
        vs_base = t_payload.get("vs_baseline")
        pct_str = f" {abs(float(delta_pct))*100:.0f}%" if delta_pct is not None else ""
        base_str = f" (vs baseline of {vs_base})" if vs_base else ""
        offer_part = f" Want me to activate {offer} to recover traffic?" if offer else f" Want me to draft a recovery campaign for {cat}?"
        return f"{name}, performance alert: {metric} dropped{pct_str} over the last {window}{base_str}.{offer_part}".strip()

    # Renewal Due
    if kind == "renewal_due":
        days_rem = t_payload.get("days_remaining", 14)
        plan = t_payload.get("plan", "Pro")
        amount = t_payload.get("renewal_amount")
        amt_str = f" at ₹{amount}" if amount else ""
        return f"{name}, your {plan} plan has {days_rem} days remaining before renewal{amt_str}. Want me to ensure uninterrupted Google listing optimization?".strip()

    # Festival Upcoming
    if kind in {"festival", "festival_upcoming"}:
        festival = t_payload.get("festival", "upcoming festival")
        date = t_payload.get("date", "")
        days_until = t_payload.get("days_until")
        days_str = f" in {days_until} days ({date})" if days_until and date else ""
        offer_part = f" using {offer}" if offer else ""
        return f"{name}, {festival} is coming up{days_str}. Want me to prepare a festival campaign for {cat}{offer_part}?".strip()

    # IPL Match Today
    if kind == "ipl_match_today":
        match = t_payload.get("match", "Match today")
        city = t_payload.get("city", "")
        time_iso = t_payload.get("match_time_iso", "")
        return f"{name}, match day alert! {match} in {city}. Delivery orders peak 1 hour before kickoff. Want me to push a match-special offer for {cat}?".strip()

    # Review Theme Emerged
    if kind == "review_theme_emerged":
        theme = t_payload.get("theme", "service").replace("_", " ")
        count = t_payload.get("occurrences_30d", 3)
        return f"{name}, customer feedback signal: {count} reviews in the last 30 days mentioned '{theme}'. Want me to draft a response template for your team?".strip()

    # Milestone Reached
    if kind == "milestone_reached":
        val_now = t_payload.get("value_now")
        m_val = t_payload.get("milestone_value")
        metric = t_payload.get("metric", "reviews").replace("_", " ")
        if val_now and m_val and val_now < m_val:
            gap = m_val - val_now
            return f"{name}, milestone alert! You are at {val_now} {metric}, just {gap} away from {m_val}! Want me to send a review request campaign to your recent customers?".strip()
        elif val_now:
            return f"{name}, milestone alert! You have reached {val_now} {metric}! Want me to send a review request campaign to your recent customers?".strip()
        else:
            return f"{name}, you have hit a {metric} milestone! Want me to send a review request campaign to your recent customers?".strip()

    # Curious Ask Due
    if kind == "curious_ask_due":
        return f"{name}, quick check: what is your most requested {cat} service this week? Reply with the service name and I will build a featured Google Post for it right away!".strip()

    # Active Planning Intent
    if kind == "active_planning_intent":
        intent_topic = t_payload.get("intent_topic", "campaign").replace("_", " ")
        return f"{name}, following up on your {intent_topic} planning. Want me to finalize and draft the promotional message for it now?".strip()

    # Category Seasonal / Demand Shift
    if kind in {"category_seasonal", "seasonal_demand_shift", "summer_demand_shift"}:
        season_note = (t_payload.get("season_note") or t_payload.get("note") or t_payload.get("query") or "seasonal demand shift").replace("_", " ")
        return f"{name}, seasonal trend alert: {season_note}. Want me to align your active offer for {cat} to capture this demand?".strip()

    # Appointment Tomorrow / Followup (Customer Scope)
    if kind in {"appointment_tomorrow", "wedding_package_followup", "bridal_followup"}:
        identity = (customer or {}).get("identity", {}) if isinstance(customer, Mapping) else {}
        customer_name = as_text(identity.get("name")) if isinstance(identity, Mapping) else "Customer"
        if kind == "appointment_tomorrow":
            time_str = t_payload.get("time") or t_payload.get("appointment_time") or ""
            at_part = f" at {time_str}" if time_str else ""
            return f"Hi {customer_name}, {name} here! Quick reminder for your appointment scheduled for tomorrow{at_part}. Reply 1 to confirm or 2 to reschedule.".strip()
        else:
            days_w = t_payload.get("days_to_wedding")
            w_part = f" ({days_w} days to your date)" if days_w else ""
            return f"Hi {customer_name}, {name} here 🌸 Following up on your bridal trial{w_part}. We have your pre-wedding package ready. Reply YES to confirm your next prep slot!".strip()

    # CDE / Webinar Opportunity
    if kind == "cde_opportunity":
        digest_item_id = t_payload.get("digest_item_id", "")
        credits = t_payload.get("credits", "")
        fee = t_payload.get("fee", "")
        credits_part = f" ({credits} CPD credits)" if credits else ""
        fee_part = f" — {fee.replace('_', ' ')}" if fee else ""
        topic = digest_item_id.replace("_", " ").split(" ", 2)[-1] if digest_item_id else "continuing education"
        return f"{name}, there's a {cat} webinar opportunity for you{credits_part}{fee_part}. Want me to draft a reminder and registration prompt for your team?".strip()

    # Competitor Opened Nearby
    if kind == "competitor_opened":
        competitor = t_payload.get("competitor_name", "a new competitor")
        dist = t_payload.get("distance_km")
        their_offer = t_payload.get("their_offer", "")
        dist_part = f" just {dist}km from you" if dist else " nearby"
        their_part = f" They are advertising: {their_offer}." if their_offer else ""
        offer_part = f" Want me to sharpen your {offer} offer to stay competitive?" if offer else f" Want me to draft a competitive response campaign for {cat}?"
        return f"{name}, heads-up: {competitor} just opened{dist_part}.{their_part}{offer_part}".strip()

    # Dormant with Vera
    if kind == "dormant_with_vera":
        days = t_payload.get("days_since_last_merchant_message", 30)
        last_topic = t_payload.get("last_topic", "").replace("_", " ")
        topic_part = f" (last topic: {last_topic})" if last_topic else ""
        offer_part = f" I have {offer} ready to activate." if offer else ""
        return f"{name}, it has been {days} days since we last connected{topic_part}.{offer_part} Want me to draft a fresh re-engagement message to your {cat} customers?".strip()

    # GBP Unverified
    if kind == "gbp_unverified":
        uplift = t_payload.get("estimated_uplift_pct")
        uplift_part = f" Verification can boost your search visibility by up to {int(float(uplift)*100)}%." if uplift else ""
        path = t_payload.get("verification_path", "").replace("_", " ")
        path_part = f" ({path})" if path else ""
        return f"{name}, your Google Business Profile is unverified.{uplift_part} Want me to walk you through the verification steps{path_part}?".strip()

    # Performance Spike
    if kind == "perf_spike":
        metric = t_payload.get("metric", "traffic")
        delta_pct = t_payload.get("delta_pct")
        window = t_payload.get("window", "7d")
        driver = t_payload.get("likely_driver", "").replace("_", " ")
        pct_str = f" {abs(float(delta_pct))*100:.0f}%" if delta_pct is not None else ""
        driver_part = f" likely driven by your {driver} content" if driver else ""
        offer_part = f" Want me to push {offer} to convert this momentum?" if offer else f" Want me to draft a conversion campaign to capture this audience?"
        return f"{name}, great news: {metric} is up{pct_str} over {window}{driver_part}.{offer_part}".strip()

    if kind == "winback_eligible":
        days = t_payload.get("days_since_expiry", 30)
        lapsed = t_payload.get("lapsed_customers_added_since_expiry", 20)
        return f"{name}, re-activation opportunity: {lapsed} lapsed customers are ready to re-engage since subscription expiry {days} days ago. Want to reactivate your listing today?".strip()

    if kind == "sales_dropped":
        lead = f"{name}, sales need attention" if name else "Sales need attention"
        secondary = f"{perf}." if perf else ""
        offer_part = f" You already have {offer}." if offer else ""
        return f"{lead}. {secondary}{offer_part} Want me to draft a recovery message for your {cat} audience?".strip()

    if kind == "offer_expiring":
        lead = f"{name}, your offer is close to expiring" if name else "Your offer is close to expiring"
        offer_part = f" {offer}." if offer else ""
        return f"{lead}.{offer_part} Want me to send a short reminder now?".strip()

    if kind == "offer_launched":
        lead = f"{name}, your new offer can go live" if name else "Your new offer can go live"
        offer_part = f" {offer}." if offer else ""
        return f"{lead}.{offer_part} Want me to prepare the launch note?".strip()

    if kind == "inactive_merchant":
        lead = f"{name}, activity is low right now" if name else "Activity is low right now"
        return f"{lead}. Want me to suggest a simple reactivation message for {cat}?".strip()

    if customer_context:
        return f"{name}, there is a usable customer signal here: {customer_context}. Want me to draft the next message?".strip()

    fallback_detail = first_sentence(trigger_detail or perf or offer)
    if fallback_detail:
        return f"{name}, {fallback_detail}. Want me to draft a grounded follow-up?".strip()
    return f"{name}, should I draft the next grounded message for this {cat} context?".strip()


def find_digest_item(category: Mapping[str, Any] | None, top_item_id: Any) -> Mapping[str, Any] | None:
    if not category or not top_item_id:
        return None
    digest = category.get("digest")
    if isinstance(digest, list):
        for item in digest:
            if isinstance(item, Mapping) and item.get("id") == str(top_item_id):
                return item
    return None


def compose_rationale(
    merchant: Mapping[str, Any] | None,
    category: Mapping[str, Any] | None,
    trigger: Mapping[str, Any] | None,
    customer: Mapping[str, Any] | None,
    base_rationale: str,
) -> str:
    pieces = [base_rationale]
    perf = performance_hint(merchant)
    offer = offer_summary(merchant)
    customer_context = customer_hint(customer)
    trigger_detail = trigger_hint(trigger)
    if perf:
        pieces.append(f"Performance facts: {perf}")
    if offer:
        pieces.append(f"Offer fact: {offer}")
    if customer_context:
        pieces.append(f"Customer fact: {customer_context}")
    if trigger_detail:
        pieces.append(f"Trigger fact: {trigger_detail}")
    return " | ".join(piece for piece in pieces if piece)


def first_sentence(text: str) -> str:
    stripped = as_text(text)
    if not stripped:
        return ""
    for separator in (".", "!", "?"):
        if separator in stripped:
            return stripped.split(separator, 1)[0].strip()
    return stripped


def nested_trigger_source(trigger: Mapping[str, Any] | None) -> str:
    if not trigger:
        return ""
    source = trigger.get("source")
    if source:
        return as_text(source)
    payload = trigger.get("payload")
    if isinstance(payload, Mapping):
        return as_text(payload.get("source"))
    return ""


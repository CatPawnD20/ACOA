"""Deterministic drafting from approved profile facts and sourced opportunities."""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from acoa.domain.composition import (
    ComposedDraft,
    DraftKind,
    FormQuestion,
    ProfileFactBinding,
    UnresolvedFormQuestion,
    composition_binding_sha256,
    validate_composition_fact_kind,
)
from acoa.domain.profile import (
    ProfileFact,
    ProfileVariant,
    VerificationStatus,
    fact_content_sha256,
    variant_content_sha256,
    variant_is_usable,
)
from acoa.domain.research import (
    FieldConfidence,
    Opportunity,
    OpportunityField,
    evidence_is_current,
)
from acoa.domain.reviews import content_digest
from acoa.domain.values import DomainError, require_identifier, require_timestamp

MEDIA_TYPE = "text/plain; charset=utf-8"


def compose_resume(
    application_id: UUID,
    variant: ProfileVariant,
    opportunity: Opportunity,
    selected_fact_ids: tuple[UUID, ...],
    now: datetime,
) -> ComposedDraft:
    facts = _composition_inputs(application_id, variant, opportunity, selected_fact_ids, now)
    employer = _required_opportunity_field(opportunity, "employer", now)
    role = _required_opportunity_field(opportunity, "role_title", now)
    lines = [f"Resume for {role} at {employer}", ""]
    lines.extend(f"{_fact_label(fact.kind)}: {fact.value}" for fact in facts)
    return _build_draft(
        DraftKind.RESUME,
        application_id,
        variant,
        opportunity,
        facts,
        None,
        None,
        "\n".join(lines),
        now,
    )


def compose_cover_letter(
    application_id: UUID,
    variant: ProfileVariant,
    opportunity: Opportunity,
    selected_fact_ids: tuple[UUID, ...],
    now: datetime,
) -> ComposedDraft:
    facts = _composition_inputs(application_id, variant, opportunity, selected_fact_ids, now)
    employer = _required_opportunity_field(opportunity, "employer", now)
    role = _required_opportunity_field(opportunity, "role_title", now)
    lines = [
        f"Application for {role} at {employer}",
        "",
        f"I am applying for the {role} opportunity at {employer}.",
        "Relevant verified profile information:",
    ]
    lines.extend(f"- {fact.value}" for fact in facts)
    return _build_draft(
        DraftKind.COVER_LETTER,
        application_id,
        variant,
        opportunity,
        facts,
        None,
        None,
        "\n".join(lines),
        now,
    )


def compose_form_answer(
    application_id: UUID,
    variant: ProfileVariant,
    opportunity: Opportunity,
    question: FormQuestion,
    now: datetime,
) -> ComposedDraft:
    _validate_context(application_id, variant, opportunity, now)
    if not isinstance(question, FormQuestion):
        raise DomainError("Form composition requires a validated question mapping.")
    candidates = tuple(fact for fact in variant.facts if fact.kind == question.required_fact_kind)
    if len(candidates) != 1:
        raise UnresolvedFormQuestion(
            "A form question requires exactly one verified fact in the active profile."
        )
    return _build_draft(
        DraftKind.FORM_ANSWER,
        application_id,
        variant,
        opportunity,
        candidates,
        question.question_id,
        question.prompt_sha256,
        candidates[0].value,
        now,
    )


def draft_matches_inputs(
    draft: ComposedDraft,
    variant: ProfileVariant,
    opportunity: Opportunity,
    now: datetime,
) -> bool:
    require_timestamp(now)
    if not isinstance(draft, ComposedDraft):
        raise DomainError("Draft validation requires a composed draft.")
    if not isinstance(variant, ProfileVariant) or not isinstance(opportunity, Opportunity):
        raise DomainError("Draft validation requires exact profile and opportunity inputs.")
    return (
        variant_is_usable(variant, now)
        and evidence_is_current(opportunity.publication_evidence, now)
        and draft.profile_variant_id == variant.variant_id
        and draft.profile_variant_version == variant.version
        and draft.profile_variant_sha256 == variant_content_sha256(variant)
        and draft.opportunity_id == opportunity.opportunity_id
        and draft.opportunity_version == opportunity.version
        and draft.opportunity_sha256 == opportunity.content_sha256
        and _opportunity_fields_are_current(draft.kind, opportunity, now)
        and all(_binding_is_current(binding, variant) for binding in draft.fact_bindings)
    )


def _composition_inputs(
    application_id: UUID,
    variant: ProfileVariant,
    opportunity: Opportunity,
    selected_fact_ids: tuple[UUID, ...],
    now: datetime,
) -> tuple[ProfileFact, ...]:
    _validate_context(application_id, variant, opportunity, now)
    if not isinstance(selected_fact_ids, tuple) or not selected_fact_ids:
        raise DomainError("Composition requires an immutable nonempty fact selection.")
    for fact_id in selected_fact_ids:
        require_identifier(fact_id)
    if len(set(selected_fact_ids)) != len(selected_fact_ids):
        raise DomainError("Composition cannot select the same fact twice.")
    facts = {fact.fact_id: fact for fact in variant.facts}
    if any(fact_id not in facts for fact_id in selected_fact_ids):
        raise DomainError("Composition selected a fact outside the active profile.")
    selected = tuple(facts[fact_id] for fact_id in selected_fact_ids)
    for fact in selected:
        validate_composition_fact_kind(fact.kind)
    return selected


def _validate_context(
    application_id: UUID,
    variant: ProfileVariant,
    opportunity: Opportunity,
    now: datetime,
) -> None:
    require_identifier(application_id)
    require_timestamp(now)
    if not isinstance(variant, ProfileVariant) or not variant_is_usable(variant, now):
        raise DomainError("Composition requires a current active approved profile.")
    if not isinstance(opportunity, Opportunity) or not evidence_is_current(
        opportunity.publication_evidence, now
    ):
        raise DomainError("Composition requires a current sourced opportunity.")
    if any(fact.status is not VerificationStatus.VERIFIED for fact in variant.facts):
        raise DomainError("Composition may use only verified profile facts.")


def _required_opportunity_field(opportunity: Opportunity, name: str, now: datetime) -> str:
    field = next((item for item in opportunity.fields if item.name == name), None)
    if (
        not isinstance(field, OpportunityField)
        or field.confidence is not FieldConfidence.SOURCE_SUPPORTED
    ):
        raise DomainError("Draft personalization requires sourced employer and role fields.")
    if (
        field.value is None
        or field.evidence is None
        or not evidence_is_current(field.evidence, now)
    ):
        raise DomainError("Draft personalization requires current employer and role evidence.")
    return field.value


def _build_draft(
    kind: DraftKind,
    application_id: UUID,
    variant: ProfileVariant,
    opportunity: Opportunity,
    facts: tuple[ProfileFact, ...],
    question_id: UUID | None,
    prompt_sha256: str | None,
    content: str,
    now: datetime,
) -> ComposedDraft:
    bindings = tuple(
        ProfileFactBinding(fact.fact_id, fact.version, fact_content_sha256(fact)) for fact in facts
    )
    profile_sha256 = variant_content_sha256(variant)
    content_sha256 = sha256(content.encode("utf-8")).hexdigest()
    draft_id = uuid5(
        NAMESPACE_URL,
        "acoa:draft:"
        + content_digest(
            {
                "kind": kind.value,
                "application_id": str(application_id),
                "profile_sha256": profile_sha256,
                "opportunity_sha256": opportunity.content_sha256,
                "fact_bindings": [
                    [str(item.fact_id), item.version, item.content_sha256] for item in bindings
                ],
                "question_id": str(question_id) if question_id is not None else None,
                "prompt_sha256": prompt_sha256,
                "content_sha256": content_sha256,
                "composed_at": now.astimezone(UTC).isoformat(),
            }
        ),
    )
    binding_sha256 = composition_binding_sha256(
        draft_id,
        kind,
        application_id,
        variant.variant_id,
        variant.version,
        profile_sha256,
        opportunity.opportunity_id,
        opportunity.version,
        opportunity.content_sha256,
        bindings,
        question_id,
        prompt_sha256,
        MEDIA_TYPE,
        content_sha256,
        now,
    )
    return ComposedDraft(
        draft_id,
        kind,
        application_id,
        variant.variant_id,
        variant.version,
        profile_sha256,
        opportunity.opportunity_id,
        opportunity.version,
        opportunity.content_sha256,
        bindings,
        question_id,
        prompt_sha256,
        MEDIA_TYPE,
        content,
        content_sha256,
        binding_sha256,
        now,
    )


def _binding_is_current(binding: ProfileFactBinding, variant: ProfileVariant) -> bool:
    return any(
        fact.fact_id == binding.fact_id
        and fact.version == binding.version
        and fact.status is VerificationStatus.VERIFIED
        and fact_content_sha256(fact) == binding.content_sha256
        for fact in variant.facts
    )


def _opportunity_fields_are_current(
    kind: DraftKind, opportunity: Opportunity, now: datetime
) -> bool:
    if kind is DraftKind.FORM_ANSWER:
        return True
    fields = {item.name: item for item in opportunity.fields}
    required = tuple(fields.get(name) for name in ("employer", "role_title"))
    return all(
        isinstance(item, OpportunityField)
        and item.value is not None
        and item.confidence is FieldConfidence.SOURCE_SUPPORTED
        and item.evidence is not None
        and evidence_is_current(item.evidence, now)
        for item in required
    )


def _fact_label(kind: str) -> str:
    return kind.replace("_", " ").strip().title()

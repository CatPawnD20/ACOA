"""EP-01.03 deterministic Policy Gate; P-01–P-18; E-07; ADR-006/007."""

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from acoa.application.policy_inputs import (
    CommunicationPurpose,
    EvidenceStatus,
    PolicyContext,
    PolicyRequest,
    Requirement,
    evidence_status,
)
from acoa.config import external_action_readiness
from acoa.domain.action_requests import request_binding_sha256 as request_binding_sha256
from acoa.domain.authorization import (
    SENSITIVE_CATEGORIES,
    ActionKind,
    PermissionMode,
    grant_is_active,
    sensitive_consent_covers,
)

POLICY_VERSION = "acoa-policy/1"
EXTERNAL_ACTIONS = frozenset(
    (
        ActionKind.SUBMIT_INITIAL_APPLICATION,
        ActionKind.SEND_INITIAL_OUTREACH,
        ActionKind.CREATE_CAREER_ACCOUNT,
        ActionKind.UPLOAD_CV,
        ActionKind.SHARE_SENSITIVE_DOCUMENT,
        ActionKind.SEND_REPLY,
        ActionKind.SEND_FOLLOWUP,
    )
)
PERMISSION_MODES = MappingProxyType(
    {
        ActionKind.READ_PUBLIC_SOURCE: PermissionMode.AUTO_ALLOWED,
        ActionKind.SUBMIT_INITIAL_APPLICATION: PermissionMode.AUTO_ALLOWED,
        ActionKind.SEND_INITIAL_OUTREACH: PermissionMode.AUTO_ALLOWED,
        ActionKind.CREATE_CAREER_ACCOUNT: PermissionMode.AUTO_ALLOWED,
        ActionKind.UPLOAD_CV: PermissionMode.AUTO_ALLOWED,
        ActionKind.DRAFT_REPLY: PermissionMode.AUTO_ALLOWED,
        ActionKind.DRAFT_FOLLOWUP: PermissionMode.AUTO_ALLOWED,
        ActionKind.SEND_REPLY: PermissionMode.USER_SENDS,
        ActionKind.SEND_FOLLOWUP: PermissionMode.USER_SENDS,
        ActionKind.ACCEPT_OFFER: PermissionMode.USER_ONLY,
        ActionKind.SIGN_CONTRACT: PermissionMode.USER_ONLY,
        ActionKind.SHARE_SENSITIVE_DOCUMENT: PermissionMode.APPROVAL_REQUIRED,
        ActionKind.APPROVE_PROFILE_CLAIM: PermissionMode.APPROVAL_REQUIRED,
        ActionKind.RUN_GENERATED_TOOL: PermissionMode.SANDBOX_ONLY,
        ActionKind.MODIFY_PRODUCTION_CODE: PermissionMode.DENY,
    }
)


class GateDecision(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    NEED_USER = "NEED_USER"
    RECHECK = "RECHECK"


class ReasonCode(StrEnum):
    GLOBAL_SAFE_MODE = "global_safe_mode"
    USER_PAUSED = "user_paused"
    FUTURE_SNAPSHOT = "future_snapshot"
    SNAPSHOT_NOT_BOUND = "snapshot_not_bound"
    USER_SENDS = "user_sends"
    USER_ONLY = "user_only"
    ACTION_DENIED = "action_denied"
    USER_REVIEW_REQUIRED = "user_review_required"
    SANDBOX_UNVERIFIED = "sandbox_unverified"
    DRAFT_ONLY = "draft_only"
    PUBLIC_SOURCE_UNAUTHORIZED = "public_source_unauthorized"
    HARD_CONSTRAINT_FAILED = "hard_constraint_failed"
    TRUST_UNVERIFIED = "trust_unverified"
    ACCOUNT_UNVERIFIED = "account_unverified"
    RECIPIENT_NOT_CORPORATE = "recipient_not_corporate"
    GRANT_MISSING = "grant_missing"
    GRANT_INACTIVE = "grant_inactive"
    GRANT_NOT_CURRENT = "grant_not_current"
    POLICY_VERSION_MISMATCH = "policy_version_mismatch"
    GRANT_SCOPE_MISMATCH = "grant_scope_mismatch"
    CONFIGURATION_INCOMPLETE = "configuration_incomplete"
    DATA_NOT_AUTHORIZED = "data_not_authorized"
    SENSITIVE_CONSENT_REQUIRED = "sensitive_consent_required"
    OPT_OUT_OR_UNKNOWN = "opt_out_or_unknown"
    DUPLICATE_OR_UNKNOWN = "duplicate_or_unknown"
    AMBIGUOUS_SUBMISSION = "ambiguous_submission"
    QUOTA_UNKNOWN = "quota_unknown"
    QUOTA_EXHAUSTED = "quota_exhausted"
    BUDGET_UNKNOWN = "budget_unknown"
    BUDGET_EXCEEDED = "budget_exceeded"
    ARTIFACT_UNVERIFIED = "artifact_unverified"
    PROFILE_NOT_CURRENT = "profile_not_current"
    PERSONAL_ANSWER_REQUIRED = "personal_answer_required"
    ACCESS_CHALLENGE = "access_challenge"
    BINDING_TERMS = "binding_terms"
    PURPOSE_MISMATCH = "purpose_mismatch"
    PRECONDITIONS_SATISFIED = "preconditions_satisfied"


@dataclass(frozen=True, slots=True)
class GateResult:
    """Pure preflight result; no reservation, execution token or external sending occurs."""

    decision: GateDecision
    mode: PermissionMode
    reason_codes: tuple[ReasonCode, ...]
    policy_version: str = POLICY_VERSION


def permission_mode(request: PolicyRequest, context: PolicyContext) -> PermissionMode:
    """A reply/follow-up cannot be relabeled as initial contact or document upload."""
    mode = PERMISSION_MODES[request.action]
    if mode is PermissionMode.USER_ONLY:
        return mode
    if request.action in EXTERNAL_ACTIONS and context.purpose in (
        CommunicationPurpose.EMPLOYER_REPLY,
        CommunicationPurpose.FOLLOWUP,
    ):
        return PermissionMode.USER_SENDS
    return mode


def check_global_state(request: PolicyRequest, context: PolicyContext) -> ReasonCode | None:
    """Pause all work and suppress external side effects under safe defaults."""
    if context.snapshot_at > context.now:
        return ReasonCode.FUTURE_SNAPSHOT
    if context.paused:
        return ReasonCode.USER_PAUSED
    if request.action in EXTERNAL_ACTIONS and (
        context.settings.dry_run or not context.settings.external_actions_enabled
    ):
        return ReasonCode.GLOBAL_SAFE_MODE
    return None


def check_fixed_mode(mode: PermissionMode, action: ActionKind) -> ReasonCode | None:
    """Apply binding restrictions regardless of grant declarations or evidence scores."""
    if mode is PermissionMode.USER_SENDS:
        return ReasonCode.USER_SENDS
    if mode is PermissionMode.USER_ONLY:
        return ReasonCode.USER_ONLY
    if mode is PermissionMode.DENY:
        return ReasonCode.ACTION_DENIED
    if action is ActionKind.APPROVE_PROFILE_CLAIM:
        return ReasonCode.USER_REVIEW_REQUIRED
    return None


def check_evidence(
    context: PolicyContext, requirement: Requirement, reason: ReasonCode
) -> ReasonCode | None:
    """Only explicit satisfied evidence can advance a gate."""
    return None if evidence_status(context, requirement) is EvidenceStatus.SATISFIED else reason


def check_grant(request: PolicyRequest, context: PolicyContext) -> ReasonCode | None:
    """Use the current resolved grant, never the configuration's UUID alone."""
    grant = context.grant
    if grant is None:
        return ReasonCode.GRANT_MISSING
    if not grant_is_active(grant, context.now):
        return ReasonCode.GRANT_INACTIVE
    if grant.policy_version != POLICY_VERSION:
        return ReasonCode.POLICY_VERSION_MISMATCH
    if evidence_status(context, Requirement.AUTHORIZATION_CURRENT) is not EvidenceStatus.SATISFIED:
        return ReasonCode.GRANT_NOT_CURRENT
    if (
        context.settings.authorization.grant_id != grant.grant_id
        or request.action not in grant.actions
        or request.channel not in grant.channels
        or request.recipient_id not in grant.recipient_ids
        or request.account_id not in grant.account_ids
    ):
        return ReasonCode.GRANT_SCOPE_MISMATCH
    return None


def check_purpose(request: PolicyRequest, context: PolicyContext) -> ReasonCode | None:
    """Require the authoritative workflow purpose rather than trusting the action label."""
    expected = {
        ActionKind.SUBMIT_INITIAL_APPLICATION: (CommunicationPurpose.INITIAL_APPLICATION,),
        ActionKind.SEND_INITIAL_OUTREACH: (CommunicationPurpose.INITIAL_OUTREACH,),
        ActionKind.CREATE_CAREER_ACCOUNT: (CommunicationPurpose.CAREER_ACCOUNT,),
        ActionKind.UPLOAD_CV: (CommunicationPurpose.INITIAL_APPLICATION,),
        ActionKind.SHARE_SENSITIVE_DOCUMENT: (
            CommunicationPurpose.INITIAL_APPLICATION,
            CommunicationPurpose.INITIAL_OUTREACH,
            CommunicationPurpose.CAREER_ACCOUNT,
        ),
    }
    return (
        None if context.purpose in expected.get(request.action, ()) else ReasonCode.PURPOSE_MISMATCH
    )


def check_data_scope(request: PolicyRequest, context: PolicyContext) -> ReasonCode | None:
    """Check necessary declared categories and separate exact sensitive consent."""
    grant = context.grant
    if grant is None or not set(request.data_categories) <= set(grant.data_categories):
        return ReasonCode.DATA_NOT_AUTHORIZED
    if not {category.value for category in request.data_categories} <= set(
        context.settings.privacy.allowed_data_categories
    ):
        return ReasonCode.DATA_NOT_AUTHORIZED
    sensitive = tuple(
        category for category in request.data_categories if category in SENSITIVE_CATEGORIES
    )
    if request.action is ActionKind.SHARE_SENSITIVE_DOCUMENT and not sensitive:
        return ReasonCode.DATA_NOT_AUTHORIZED
    if sensitive and not any(
        sensitive_consent_covers(consent, grant, sensitive, context.now)
        for consent in context.sensitive_consents
    ):
        return ReasonCode.SENSITIVE_CONSENT_REQUIRED
    return None


def check_quota(context: PolicyContext) -> ReasonCode | None:
    """Compare authoritative initial-action usage with all declared hard caps."""
    grant = context.grant
    if grant is None or context.quota.limit_policy_id != grant.limit_policy_id:
        return ReasonCode.QUOTA_UNKNOWN
    if context.purpose is CommunicationPurpose.CAREER_ACCOUNT:
        return None
    for used, cap in (
        (context.quota.applications_today, context.settings.applications.max_per_day),
        (context.quota.applications_this_week, context.settings.applications.max_per_week),
        (context.quota.company_outreach, context.settings.outreach.per_company_limit),
        (context.quota.contact_outreach, context.settings.outreach.per_contact_limit),
    ):
        if used is None or cap is None:
            return ReasonCode.QUOTA_UNKNOWN
        if used >= cap:
            return ReasonCode.QUOTA_EXHAUSTED
    return None


def check_budget(context: PolicyContext) -> ReasonCode | None:
    """Refuse unknown/incompatible costs and projected money/token/time cap violations."""
    usage = context.budget
    caps = context.settings.budget
    if usage.currency is None or usage.currency != caps.currency or usage.estimated_cost is None:
        return ReasonCode.BUDGET_UNKNOWN
    for spent, money_cap in (
        (usage.spent_today, caps.max_currency_per_day),
        (usage.spent_this_month, caps.max_currency_per_month),
    ):
        if spent is None or money_cap is None:
            return ReasonCode.BUDGET_UNKNOWN
        if spent + usage.estimated_cost > money_cap:
            return ReasonCode.BUDGET_EXCEEDED
    for estimate, cap in (
        (usage.estimated_tokens, caps.max_tokens_per_task),
        (usage.estimated_seconds, caps.max_time_per_task),
    ):
        if estimate is None or cap is None:
            return ReasonCode.BUDGET_UNKNOWN
        if estimate > cap:
            return ReasonCode.BUDGET_EXCEEDED
    return None


def check_matching_and_trust(request: PolicyRequest, context: PolicyContext) -> ReasonCode | None:
    """Require hard-rule, company/channel/account and relevant recipient evidence."""
    for requirement, reason in (
        (Requirement.HARD_CONSTRAINTS, ReasonCode.HARD_CONSTRAINT_FAILED),
        (Requirement.COMPANY_CHANNEL_TRUST, ReasonCode.TRUST_UNVERIFIED),
        (Requirement.ACCOUNT_OWNERSHIP, ReasonCode.ACCOUNT_UNVERIFIED),
    ):
        result = check_evidence(context, requirement, reason)
        if result is not None:
            return result
    if request.action is ActionKind.SEND_INITIAL_OUTREACH:
        result = check_evidence(
            context, Requirement.CORPORATE_RECIPIENT, ReasonCode.RECIPIENT_NOT_CORPORATE
        )
        if result is not None:
            return result
    if context.account_email not in context.settings.accounts.authorized_emails:
        return ReasonCode.ACCOUNT_UNVERIFIED
    return None


def check_delivery_history(context: PolicyContext) -> ReasonCode | None:
    """Reject opt-out, duplicate or ambiguous previous delivery before reserving capacity."""
    for requirement, reason in (
        (Requirement.OPT_OUT_CLEAR, ReasonCode.OPT_OUT_OR_UNKNOWN),
        (Requirement.DUPLICATE_CLEAR, ReasonCode.DUPLICATE_OR_UNKNOWN),
        (Requirement.SUBMISSION_STATE_CLEAR, ReasonCode.AMBIGUOUS_SUBMISSION),
    ):
        result = check_evidence(context, requirement, reason)
        if result is not None:
            return result
    return None


def check_capacity(context: PolicyContext) -> ReasonCode | None:
    """Require complete configuration and authoritative quota/budget headroom."""
    if not external_action_readiness(context.settings).ready:
        return ReasonCode.CONFIGURATION_INCOMPLETE
    quota_reason = check_quota(context)
    if quota_reason is not None:
        return quota_reason
    budget_reason = check_budget(context)
    if budget_reason is not None:
        return budget_reason
    return None


def check_artifacts_and_access(request: PolicyRequest, context: PolicyContext) -> ReasonCode | None:
    """Bind classifications/integrity to the exact material and reject unsafe account steps."""
    if context.artifact_content_sha256 != request.content_sha256 or set(
        context.artifact_categories
    ) != set(request.data_categories):
        return ReasonCode.ARTIFACT_UNVERIFIED
    for requirement, reason in (
        (Requirement.ARTIFACT_INTEGRITY, ReasonCode.ARTIFACT_UNVERIFIED),
        (Requirement.PROFILE_VERSION_CURRENT, ReasonCode.PROFILE_NOT_CURRENT),
        (Requirement.PERSONAL_ANSWERS_COMPLETE, ReasonCode.PERSONAL_ANSWER_REQUIRED),
        (Requirement.ACCESS_CHALLENGES_CLEAR, ReasonCode.ACCESS_CHALLENGE),
        (Requirement.NONBINDING_TERMS, ReasonCode.BINDING_TERMS),
    ):
        result = check_evidence(context, requirement, reason)
        if result is not None:
            return result
    return None


def check_external_preconditions(
    request: PolicyRequest, context: PolicyContext
) -> ReasonCode | None:
    """Orchestrate the ordered external gates without doing I/O or reserving capacity."""
    for checker in (check_grant, check_purpose, check_matching_and_trust, check_data_scope):
        reason = checker(request, context)
        if reason is not None:
            return reason
    history_reason = check_delivery_history(context)
    if history_reason is not None:
        return history_reason
    capacity_reason = check_capacity(context)
    if capacity_reason is not None:
        return capacity_reason
    return check_artifacts_and_access(request, context)


def failure_decision(reason: ReasonCode) -> GateDecision:
    """Distinguish missing user decisions from authority/evidence that must be rechecked."""
    if reason in (
        ReasonCode.SENSITIVE_CONSENT_REQUIRED,
        ReasonCode.USER_REVIEW_REQUIRED,
        ReasonCode.PERSONAL_ANSWER_REQUIRED,
        ReasonCode.ACCESS_CHALLENGE,
        ReasonCode.BINDING_TERMS,
    ):
        return GateDecision.NEED_USER
    if reason in (
        ReasonCode.FUTURE_SNAPSHOT,
        ReasonCode.SNAPSHOT_NOT_BOUND,
        ReasonCode.GRANT_NOT_CURRENT,
        ReasonCode.QUOTA_UNKNOWN,
        ReasonCode.BUDGET_UNKNOWN,
        ReasonCode.POLICY_VERSION_MISMATCH,
    ):
        return GateDecision.RECHECK
    return GateDecision.BLOCK


def check_public_source(context: PolicyContext) -> ReasonCode | None:
    """Require permitted access without challenges and known free or affordable retrieval."""
    for requirement, reason in (
        (Requirement.SOURCE_ACCESS_ALLOWED, ReasonCode.PUBLIC_SOURCE_UNAUTHORIZED),
        (Requirement.ACCESS_CHALLENGES_CLEAR, ReasonCode.ACCESS_CHALLENGE),
    ):
        result = check_evidence(context, requirement, reason)
        if result is not None:
            return result
    if context.budget.estimated_cost is None:
        return ReasonCode.BUDGET_UNKNOWN
    return check_budget(context) if context.budget.estimated_cost > 0 else None


def evaluate_policy(request: PolicyRequest, context: PolicyContext) -> GateResult:
    """Pure ordered preflight; an ALLOW never reserves quota or calls a provider."""
    mode = permission_mode(request, context)
    reason = check_global_state(request, context)
    if reason is None:
        reason = check_fixed_mode(mode, request.action)
    if reason is not None:
        return GateResult(failure_decision(reason), mode, (reason,))
    if request.action in (ActionKind.DRAFT_REPLY, ActionKind.DRAFT_FOLLOWUP):
        return GateResult(GateDecision.ALLOW, mode, (ReasonCode.DRAFT_ONLY,))
    if context.request_binding_sha256 != request_binding_sha256(request):
        return GateResult(GateDecision.RECHECK, mode, (ReasonCode.SNAPSHOT_NOT_BOUND,))
    if request.action is ActionKind.READ_PUBLIC_SOURCE:
        reason = check_public_source(context)
    elif request.action is ActionKind.RUN_GENERATED_TOOL:
        reason = check_evidence(
            context, Requirement.SANDBOX_VERIFIED, ReasonCode.SANDBOX_UNVERIFIED
        )
    else:
        reason = check_external_preconditions(request, context)
    if reason is not None:
        return GateResult(failure_decision(reason), mode, (reason,))
    return GateResult(GateDecision.ALLOW, mode, (ReasonCode.PRECONDITIONS_SATISFIED,))

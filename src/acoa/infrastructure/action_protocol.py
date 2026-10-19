"""EP-02.03 PostgreSQL prepare/reserve/one-attempt dispatch; ADR-006/007/013."""

import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from acoa.application.decision_records import decision_record_json, evaluate_and_record
from acoa.application.executor import ActionCheck
from acoa.application.policy import GateDecision, request_binding_sha256
from acoa.application.policy_inputs import (
    EvidenceStatus,
    PolicyContext,
    PolicyEvidence,
    Requirement,
)
from acoa.domain.actions import (
    ActionState,
    DispatchLimits,
    PreparedAction,
    affects_application_submission,
    prepared_binding_sha256,
    validate_prepared_application,
)
from acoa.domain.applications import (
    ApplicationState,
    SubmissionState,
)
from acoa.domain.authorization import (
    SENSITIVE_CATEGORIES,
    ActionKind,
    RecipientClass,
    sensitive_consent_covers,
)
from acoa.domain.submission_evidence import IncidentKind
from acoa.domain.values import require_identifier
from acoa.infrastructure.action_usage import budget_usage, quota_usage
from acoa.infrastructure.application_ledger import APPLICATION_SELECT, application_from_row
from acoa.infrastructure.incidents import IncidentStore
from acoa.infrastructure.policy_authority import AuthorityStore, PolicyAuthority
from acoa.infrastructure.policy_codec import (
    decode_evidence_context,
    decode_request,
    encode_record,
    identifier,
    object_fields,
)
from acoa.infrastructure.postgres import (
    DatabaseBoundaryError,
    require_transaction,
    validate_application_connection,
)
from acoa.infrastructure.resource_budget import register_resource_attempt


def decode_prepared(value: object) -> PreparedAction:
    row = object_fields(value)
    return PreparedAction(
        identifier(row["attempt_id"]),
        identifier(row["application_id"]),
        cast(str, row["semantic_key"]),
        decode_request(row["request"]),
        identifier(row["plan_id"]),
        identifier(row["artifact_id"]),
        cast(int, row["artifact_version"]),
        identifier(row["provider_id"]),
    )


def current_evidence_facts(
    connection: Connection,
    context: PolicyContext,
    authority: PolicyAuthority,
    prepared: PreparedAction,
    evidence: RowMapping,
    application: RowMapping,
) -> tuple[PolicyEvidence, ...]:
    """Override stale authority/delivery assertions with current database facts."""
    facts = {item.requirement: item.status for item in context.evidence}
    facts[Requirement.AUTHORIZATION_CURRENT] = (
        EvidenceStatus.SATISFIED if authority.grant is not None else EvidenceStatus.UNKNOWN
    )
    facts[Requirement.RECIPIENT_CLASS_ENROLLED] = recipient_enrollment_status(
        connection, context, authority, prepared, application
    )
    if evidence["expires_at"] <= context.now or evidence[
        "request_sha256"
    ] != request_binding_sha256(prepared.request):
        facts[Requirement.ARTIFACT_INTEGRITY] = EvidenceStatus.VIOLATED
    if object_fields(evidence["payload"]).get("prepared_sha256") != prepared_binding_sha256(
        prepared
    ):
        facts[Requirement.ARTIFACT_INTEGRITY] = EvidenceStatus.VIOLATED
    if application["state"] != ApplicationState.OPEN.value:
        facts[Requirement.DUPLICATE_CLEAR] = EvidenceStatus.VIOLATED
    if application["submission_state"] != SubmissionState.NOT_STARTED.value:
        facts[Requirement.SUBMISSION_STATE_CLEAR] = EvidenceStatus.VIOLATED
    return tuple(PolicyEvidence(requirement, status) for requirement, status in facts.items())


def recipient_enrollment_status(
    connection: Connection,
    context: PolicyContext,
    authority: PolicyAuthority,
    prepared: PreparedAction,
    application: RowMapping,
) -> EvidenceStatus:
    """Recompute the exact target enrollment and current opt-out state at each gate."""
    grant = authority.grant
    recipient_class = {
        ActionKind.SUBMIT_INITIAL_APPLICATION: RecipientClass.VERIFIED_OFFICIAL_APPLICATION_EMAIL,
        ActionKind.SEND_INITIAL_OUTREACH: (
            RecipientClass.VERIFIED_PUBLIC_CORPORATE_RECRUITING_CONTACT
        ),
    }.get(prepared.request.action)
    if (
        grant is None
        or recipient_class is None
        or recipient_class not in grant.recipient_classes
        or prepared.request.recipient_id is None
    ):
        return EvidenceStatus.UNKNOWN
    enrolled: bool = connection.execute(
        text("""SELECT EXISTS (
            SELECT 1
            FROM acoa.production_recipient_enrollments e
            JOIN acoa.opportunity_versions o
              ON o.opportunity_id=e.target_id AND o.version=e.target_version
            JOIN acoa.contact_channel_versions c
              ON c.channel_id=e.channel_id AND c.version=e.channel_version
            JOIN acoa.employer_verification_versions v
              ON v.verification_id=e.employer_verification_id
             AND v.version=e.employer_verification_version
            WHERE e.recipient_id=:recipient
              AND e.recipient_class=:recipient_class
              AND e.grant_id=:grant AND e.grant_version=:grant_version
              AND e.organization_id=:organization AND e.target_id=:target
              AND e.enrolled_at <= :now AND :now < e.valid_until
              AND e.valid_until <= :grant_expires_at
              AND o.organization_id=e.organization_id AND o.status='active'
              AND o.content_sha256=e.target_content_sha256
              AND (o.opportunity->'publication_evidence'->>'observed_at')::timestamptz <= :now
              AND :now <
                (o.opportunity->'publication_evidence'->>'valid_until')::timestamptz
              AND NOT EXISTS (SELECT 1 FROM acoa.opportunity_versions newer
                WHERE newer.opportunity_id=o.opportunity_id AND newer.version>o.version)
              AND c.organization_id=e.organization_id
              AND c.endpoint_sha256=e.endpoint_sha256
              AND c.content_sha256=e.channel_content_sha256
              AND c.eligible_for_initial_contact
              AND c.channel->>'visibility'='public_corporate'
              AND (
                (:recipient_class='verified_official_application_email'
                  AND o.kind='published_job'
                  AND c.kind='general_application_email'
                  AND c.channel->>'purpose'='general_application')
                OR
                (:recipient_class='verified_public_corporate_recruiting_contact'
                  AND o.kind='unadvertised_prospect'
                  AND c.kind='public_corporate_email'
                  AND c.channel->>'purpose' IN
                    ('recruiting','human_resources','relevant_department'))
              )
              AND (c.channel->'evidence'->>'observed_at')::timestamptz <= :now
              AND :now < (c.channel->'evidence'->>'valid_until')::timestamptz
              AND NOT EXISTS (SELECT 1 FROM acoa.contact_channel_versions newer
                WHERE newer.channel_id=c.channel_id AND newer.version>c.version)
              AND v.organization_id=e.organization_id AND v.status='verified'
              AND v.content_sha256=e.employer_verification_sha256
              AND v.assessed_at <= :now AND :now < v.valid_until
              AND NOT EXISTS (SELECT 1 FROM acoa.employer_verification_versions newer
                WHERE newer.verification_id=v.verification_id AND newer.version>v.version)
              AND NOT EXISTS (
                SELECT 1 FROM (
                    SELECT DISTINCT ON (actor) actor, action
                    FROM acoa.company_contact_control_events controls
                    WHERE controls.organization_id=e.organization_id
                      AND controls.effective_at <= :now
                    ORDER BY actor, sequence DESC
                ) latest WHERE action='block'
              )
        )"""),
        {
            "recipient": prepared.request.recipient_id,
            "recipient_class": recipient_class.value,
            "grant": grant.grant_id,
            "grant_version": grant.version,
            "grant_expires_at": grant.expires_at,
            "organization": application["company_id"],
            "target": application["target_id"],
            "now": context.now,
        },
    ).scalar_one()
    return EvidenceStatus.SATISFIED if enrolled else EvidenceStatus.UNKNOWN


class ActionProtocol:
    """Caller owns transaction boundaries; this adapter never calls a provider."""

    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def _application_row(self, application_id: UUID) -> RowMapping:
        row = (
            self.connection.execute(
                text(APPLICATION_SELECT + " WHERE a.application_id = :id FOR UPDATE OF s, a"),
                {"id": application_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DatabaseBoundaryError("The canonical application is missing.")
        return row

    def read_prepared(self, attempt_id: UUID) -> PreparedAction:
        require_identifier(attempt_id)
        require_transaction(self.connection)
        payload: object = self.connection.execute(
            text("SELECT prepared FROM acoa.external_action_attempts WHERE attempt_id = :id"),
            {"id": attempt_id},
        ).scalar_one_or_none()
        if payload is None:
            raise DatabaseBoundaryError("The prepared action is missing.")
        return decode_prepared(payload)

    def record_prepared(self, prepared: PreparedAction) -> ActionState:
        """Persist side-effect-free material references and fence one semantic operation."""
        if not isinstance(prepared, PreparedAction):
            raise DatabaseBoundaryError("A validated prepared action is required.")
        AuthorityStore(self.connection).lock_current()
        application = application_from_row(self._application_row(prepared.application_id))
        prior = self._existing_preparation(prepared)
        if prior is not None:
            return prior
        validate_prepared_application(prepared, application)
        return self._insert_preparation(prepared)

    def _existing_preparation(self, prepared: PreparedAction) -> ActionState | None:
        prior = self.connection.execute(
            text("""SELECT prepared, state
            FROM acoa.external_action_attempts WHERE attempt_id = :id FOR UPDATE"""),
            {"id": prepared.attempt_id},
        ).one_or_none()
        if prior is not None:
            if decode_prepared(prior.prepared) != prepared:
                raise DatabaseBoundaryError("An attempt ID must retain its exact prepared content.")
            return ActionState(prior.state)
        return None

    def _insert_preparation(self, prepared: PreparedAction) -> ActionState:
        request = prepared.request
        evidence_binding = self.connection.execute(
            text("""SELECT payload->>'prepared_sha256'
                FROM acoa.action_evidence WHERE request_id = :id"""),
            {"id": request.request_id},
        ).scalar_one_or_none()
        if evidence_binding != prepared_binding_sha256(prepared):
            raise DatabaseBoundaryError(
                "Prepared requests require exact persisted validation evidence."
            )
        existing: bool = self.connection.execute(
            text("""SELECT EXISTS (
            SELECT 1 FROM acoa.external_action_attempts WHERE semantic_key = :key
                AND (state <> 'cancelled' OR execution_started_at IS NOT NULL))"""),
            {"key": prepared.semantic_key},
        ).scalar_one()
        if existing:
            raise DatabaseBoundaryError("This semantic operation already has an automatic attempt.")
        self.connection.execute(
            text("""INSERT INTO acoa.external_action_attempts
            (attempt_id, application_id, semantic_key, prepared, request_id, state)
            VALUES (:id, :application, :key, CAST(:prepared AS jsonb), :request, 'prepared')"""),
            {
                "id": prepared.attempt_id,
                "application": prepared.application_id,
                "key": prepared.semantic_key,
                "prepared": encode_record(asdict(prepared)),
                "request": request.request_id,
            },
        )
        return ActionState.PREPARED

    def lock_attempt(
        self, attempt_id: UUID
    ) -> tuple[int, PolicyAuthority, PreparedAction, RowMapping, RowMapping]:
        require_identifier(attempt_id)
        revision, authority = AuthorityStore(self.connection).lock_current()
        row = (
            self.connection.execute(
                text("SELECT * FROM acoa.external_action_attempts WHERE attempt_id = :id"),
                {"id": attempt_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DatabaseBoundaryError("The prepared action is missing.")
        prepared = decode_prepared(row["prepared"])
        application = self._application_row(prepared.application_id)
        row = (
            self.connection.execute(
                text(
                    "SELECT * FROM acoa.external_action_attempts WHERE attempt_id = :id FOR UPDATE"
                ),
                {"id": attempt_id},
            )
            .mappings()
            .one()
        )
        return revision, authority, prepared, row, application

    def _context(
        self,
        authority: PolicyAuthority,
        prepared: PreparedAction,
        application: RowMapping,
    ) -> PolicyContext:
        now = cast(datetime, self.connection.execute(text("SELECT clock_timestamp()")).scalar_one())
        evidence = (
            self.connection.execute(
                text("SELECT * FROM acoa.action_evidence WHERE request_id = :id FOR UPDATE"),
                {"id": prepared.request.request_id},
            )
            .mappings()
            .one()
        )
        context = decode_evidence_context(evidence["payload"], now)
        return replace(
            context,
            settings=authority.settings,
            grant=authority.grant,
            sensitive_consents=authority.consents,
            paused=authority.paused,
            quota=quota_usage(
                self.connection,
                authority,
                cast(UUID, application["owner_id"]),
                cast(UUID, application["company_id"]),
                prepared.request,
                prepared.attempt_id,
                now,
            ),
            budget=budget_usage(
                self.connection, authority, prepared.attempt_id, dict(evidence), now
            ),
            evidence=current_evidence_facts(
                self.connection, context, authority, prepared, evidence, application
            ),
        )

    def _evaluate(
        self,
        revision: int,
        authority: PolicyAuthority,
        prepared: PreparedAction,
        application: RowMapping,
        stage: str,
    ) -> tuple[ActionCheck, PolicyContext]:
        context = self._context(authority, prepared, application)
        record = evaluate_and_record(uuid4(), prepared.request, context)
        limits = (
            self._dispatch_limits(prepared, context)
            if stage == "execute" and record.decision is GateDecision.ALLOW
            else None
        )
        trace = json.loads(decision_record_json(record))
        trace["prepared_sha256"] = prepared_binding_sha256(prepared)
        trace["dispatch_limits"] = asdict(limits) if limits is not None else None
        self.connection.execute(
            text("""INSERT INTO acoa.policy_decisions
            (decision_id, attempt_id, authority_revision, stage, result)
            VALUES (:id, :attempt, :revision, :stage, CAST(:result AS jsonb))"""),
            {
                "id": record.decision_id,
                "attempt": prepared.attempt_id,
                "revision": revision,
                "stage": stage,
                "result": encode_record(trace),
            },
        )
        return ActionCheck(
            ActionState.PREPARED, record.decision_id, record.decision, limits=limits
        ), context

    def reserve(self, attempt_id: UUID) -> ActionCheck:
        revision, authority, prepared, row, application = self.lock_attempt(attempt_id)
        state = ActionState(row["state"])
        if state is not ActionState.PREPARED:
            return ActionCheck(state)
        result, context = self._evaluate(revision, authority, prepared, application, "reserve")
        if result.decision is not GateDecision.ALLOW:
            return result
        self._store_reservation(prepared, context)
        return replace(result, state=ActionState.RESERVED)

    def _hold_budget(self, attempt_id: UUID, context: PolicyContext) -> None:
        """Create or refresh this attempt's exact quoted hold under the global authority lock."""
        register_resource_attempt(self.connection, attempt_id, "external")
        self.connection.execute(
            text("""INSERT INTO acoa.budget_ledger
            (attempt_id, currency, estimated, reserved) VALUES (:id, :currency, :cost, :cost)
            ON CONFLICT (attempt_id) DO UPDATE SET currency = EXCLUDED.currency,
                estimated = EXCLUDED.estimated, reserved = EXCLUDED.reserved"""),
            {
                "id": attempt_id,
                "currency": context.budget.currency,
                "cost": context.budget.estimated_cost,
            },
        )

    def _store_reservation(self, prepared: PreparedAction, context: PolicyContext) -> None:
        self._hold_budget(prepared.attempt_id, context)
        self.connection.execute(
            text("""UPDATE acoa.external_action_attempts
            SET state = 'reserved', reserved_at = clock_timestamp(), updated_at = clock_timestamp()
            WHERE attempt_id = :id"""),
            {"id": prepared.attempt_id},
        )

    def _cancel_reserved(self, attempt_id: UUID) -> None:
        self.connection.execute(
            text("""UPDATE acoa.budget_ledger
            SET released = estimated, reserved = 0 WHERE attempt_id = :id"""),
            {"id": attempt_id},
        )
        self.connection.execute(
            text("""UPDATE acoa.external_action_attempts SET state = 'cancelled',
            updated_at = clock_timestamp() WHERE attempt_id = :id"""),
            {"id": attempt_id},
        )

    def cancel_before_execution(self, attempt_id: UUID, evidence_id: UUID) -> ActionCheck:
        """Cancel only while provider I/O is impossible; retain an immutable audit fact."""
        require_identifier(evidence_id)
        _, _, _, row, _ = self.lock_attempt(attempt_id)
        state = ActionState(row["state"])
        if state is ActionState.CANCELLED:
            return ActionCheck(state)
        if state not in (ActionState.PREPARED, ActionState.RESERVED):
            return ActionCheck(state)
        if state is ActionState.RESERVED:
            self._cancel_reserved(attempt_id)
        else:
            self.connection.execute(
                text("""UPDATE acoa.external_action_attempts SET state = 'cancelled',
                    updated_at = clock_timestamp() WHERE attempt_id = :id"""),
                {"id": attempt_id},
            )
        self.connection.execute(
            text("""INSERT INTO acoa.external_action_cancellations
                (cancellation_id,attempt_id,prior_state,evidence_id)
                VALUES (:id,:attempt,:prior,:evidence)"""),
            {
                "id": uuid4(),
                "attempt": attempt_id,
                "prior": state.value,
                "evidence": evidence_id,
            },
        )
        return ActionCheck(ActionState.CANCELLED)

    def begin_execution(self, attempt_id: UUID) -> ActionCheck:
        """Commit this linearization point before any provider call; never return a second token."""
        revision, authority, prepared, row, application = self.lock_attempt(attempt_id)
        state = ActionState(row["state"])
        if state is not ActionState.RESERVED:
            return ActionCheck(state)
        result, context = self._evaluate(revision, authority, prepared, application, "execute")
        if result.decision is not GateDecision.ALLOW:
            self._cancel_reserved(attempt_id)
            return replace(result, state=ActionState.CANCELLED)
        if result.limits is None:
            raise DatabaseBoundaryError("Allowed dispatch is missing bounded provider limits.")
        token = self._mark_executing(prepared, context)
        return replace(result, state=ActionState.EXECUTING, execution_token=token)

    def _dispatch_limits(self, prepared: PreparedAction, context: PolicyContext) -> DispatchLimits:
        """Bound dispatch to grant, evidence, task and usable sensitive-consent deadlines."""
        timeout = cast(int, context.settings.budget.max_time_per_task)
        deadlines = [context.now + timedelta(seconds=timeout)]
        expiry: datetime = self.connection.execute(
            text("SELECT expires_at FROM acoa.action_evidence WHERE request_id = :id"),
            {"id": prepared.request.request_id},
        ).scalar_one()
        deadlines.append(expiry)
        if context.grant is not None:
            deadlines.append(context.grant.expires_at)
            sensitive = tuple(
                x for x in prepared.request.data_categories if x in SENSITIVE_CATEGORIES
            )
            if sensitive:
                deadlines.append(
                    max(
                        consent.expires_at
                        for consent in context.sensitive_consents
                        if sensitive_consent_covers(consent, context.grant, sensitive, context.now)
                    )
                )
        return DispatchLimits(
            min(deadlines),
            timeout,
            cast(Decimal, context.budget.estimated_cost),
            cast(str, context.budget.currency),
        )

    def _mark_executing(self, prepared: PreparedAction, context: PolicyContext) -> UUID:
        """Update the hold and fence the operation/application before any provider I/O."""
        self._hold_budget(prepared.attempt_id, context)
        token = uuid4()
        self.connection.execute(
            text("""UPDATE acoa.external_action_attempts SET state = 'executing',
            execution_started_at = clock_timestamp(), execution_token = :token,
            updated_at = clock_timestamp() WHERE attempt_id = :id"""),
            {"id": prepared.attempt_id, "token": token},
        )
        if affects_application_submission(prepared):
            self.connection.execute(
                text("""UPDATE acoa.applications
                SET submission_state = 'submission_unconfirmed' WHERE application_id = :id"""),
                {"id": prepared.application_id},
            )
        return token

    def record_response(
        self, attempt_id: UUID, token: UUID, receipt_ref: UUID | None
    ) -> ActionState:
        """Acknowledgement is not verified acceptance; missing response remains unconfirmed."""
        require_identifier(token)
        if receipt_ref is not None:
            require_identifier(receipt_ref)
        _, _, prepared, row, _ = self.lock_attempt(attempt_id)
        if row["execution_token"] != token:
            raise DatabaseBoundaryError("The response does not match the dispatched attempt.")
        state = ActionState(row["state"])
        if state is not ActionState.EXECUTING:
            return state
        target = ActionState.RECONCILING if receipt_ref is not None else ActionState.UNCONFIRMED
        self.connection.execute(
            text("""UPDATE acoa.external_action_attempts
            SET state = :state, provider_receipt_ref = :receipt, updated_at = clock_timestamp()
            WHERE attempt_id = :id"""),
            {"id": attempt_id, "state": target.value, "receipt": receipt_ref},
        )
        if affects_application_submission(prepared):
            self.connection.execute(
                text("""UPDATE acoa.applications
                SET submission_state = 'submission_unconfirmed' WHERE application_id = :id"""),
                {"id": row["application_id"]},
            )
        if target is ActionState.UNCONFIRMED and affects_application_submission(prepared):
            IncidentStore(self.connection).open(attempt_id, IncidentKind.UNKNOWN_SUBMISSION)
        return target

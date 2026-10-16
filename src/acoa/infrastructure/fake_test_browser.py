"""Playwright-backed synthetic career site for offline timeout and recheck exercises."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from importlib import import_module
from types import ModuleType
from typing import Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from acoa.application.browser_submission import (
    BrowserSubmissionObservation,
    BrowserSubmissionOutcome,
    require_web_submission,
)
from acoa.domain.actions import DispatchLimits, PreparedAction, prepared_binding_sha256
from acoa.domain.reviews import content_digest
from acoa.domain.values import DomainError, require_identifier, require_sha256, require_text

SYNTHETIC_ORIGIN = "https://career.test.invalid"


class SyntheticBrowserOutcome(StrEnum):
    ACCEPT = "accept"
    TIMEOUT_AFTER_ACCEPT = "timeout_after_accept"
    TIMEOUT_BEFORE_ACCEPT = "timeout_before_accept"


@dataclass(frozen=True, slots=True)
class SyntheticApplicationMaterial:
    full_name: str = field(repr=False)
    email: str = field(repr=False)
    resume_name: str
    resume_sha256: str = field(repr=False)
    resume_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        require_text(self.full_name)
        require_text(self.email)
        require_text(self.resume_name)
        require_sha256(self.resume_sha256)
        if not self.email.endswith("@example.invalid"):
            raise DomainError("Synthetic browser material requires a reserved invalid email.")
        if not self.resume_name.endswith(".pdf") or not self.resume_bytes.startswith(b"%PDF-"):
            raise DomainError("Synthetic browser material requires a fake PDF resume.")
        if sha256(self.resume_bytes).hexdigest() != self.resume_sha256:
            raise DomainError("Synthetic resume bytes must match their declared digest.")


def synthetic_application_sha256(material: SyntheticApplicationMaterial) -> str:
    """Bind every submitted synthetic form value without exposing the resume bytes."""
    if not isinstance(material, SyntheticApplicationMaterial):
        raise DomainError("Synthetic application content requires validated material.")
    return content_digest(
        {
            "schema": "acoa-synthetic-browser-application/1",
            "full_name": material.full_name,
            "email": material.email,
            "resume_name": material.resume_name,
            "resume_sha256": material.resume_sha256,
        }
    )


class _Request(Protocol):
    @property
    def method(self) -> str: ...


class _Route(Protocol):
    @property
    def request(self) -> _Request: ...

    def fulfill(self, *, status: int, content_type: str, body: str) -> None: ...

    def abort(self, error_code: str = "failed") -> None: ...


class _Page(Protocol):
    def route(self, url: str, handler: Callable[[_Route], None]) -> None: ...

    def goto(self, url: str, *, wait_until: str, timeout: float) -> object: ...

    def fill(self, selector: str, value: str) -> None: ...

    def set_input_files(self, selector: str, files: object) -> None: ...

    def click(self, selector: str, *, timeout: float) -> None: ...


class _Browser(Protocol):
    def new_page(self) -> _Page: ...

    def close(self) -> None: ...


class _Chromium(Protocol):
    def launch(self, *, headless: bool) -> _Browser: ...


class _Playwright(Protocol):
    @property
    def chromium(self) -> _Chromium: ...


class _PlaywrightManager(Protocol):
    def __enter__(self) -> _Playwright: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...


class _PlaywrightModule(Protocol):
    def sync_playwright(self) -> _PlaywrightManager: ...


def _load_playwright() -> _PlaywrightModule:
    module: ModuleType = import_module("playwright.sync_api")
    return cast(_PlaywrightModule, module)


class PlaywrightSyntheticCareerSite:
    """A no-egress test double: every browser request is intercepted in process."""

    def __init__(
        self,
        provider_id: UUID,
        materials: dict[UUID, SyntheticApplicationMaterial],
        outcomes: dict[UUID, SyntheticBrowserOutcome],
    ) -> None:
        require_identifier(provider_id)
        if set(materials) != set(outcomes):
            raise DomainError("Synthetic browser attempts require one explicit outcome each.")
        if any(not isinstance(value, SyntheticBrowserOutcome) for value in outcomes.values()):
            raise DomainError("Synthetic browser outcomes must be explicit.")
        self.provider_id = provider_id
        self.materials = dict(materials)
        self.outcomes = dict(outcomes)
        self.invocations: dict[UUID, int] = {}
        self.accepted: dict[UUID, UUID] = {}

    def submit_once(self, prepared: PreparedAction, limits: DispatchLimits) -> UUID:
        material = self._validate_attempt(prepared)
        self.invocations[prepared.attempt_id] = self.invocations.get(prepared.attempt_id, 0) + 1
        if self.invocations[prepared.attempt_id] != 1:
            raise DomainError("A synthetic browser attempt cannot be submitted twice.")
        outcome = self.outcomes[prepared.attempt_id]
        receipt = uuid5(NAMESPACE_URL, f"acoa:synthetic-browser:{prepared.attempt_id}")
        timeout_ms = float(limits.timeout_seconds * 1000)

        def handle(route: _Route) -> None:
            if route.request.method == "GET":
                route.fulfill(status=200, content_type="text/html", body=_FORM_HTML)
                return
            if route.request.method != "POST":
                route.abort("blockedbyclient")
                return
            if outcome is SyntheticBrowserOutcome.TIMEOUT_BEFORE_ACCEPT:
                time.sleep(limits.timeout_seconds + 0.25)
                route.abort("timedout")
                return
            self.accepted[prepared.attempt_id] = receipt
            if outcome is SyntheticBrowserOutcome.TIMEOUT_AFTER_ACCEPT:
                time.sleep(limits.timeout_seconds + 0.25)
                route.abort("timedout")
                return
            route.fulfill(
                status=200, content_type="text/html", body="<h1>Application received</h1>"
            )

        try:
            playwright_module = _load_playwright()
            with playwright_module.sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.route("**/*", handle)
                    page.goto(
                        f"{SYNTHETIC_ORIGIN}/apply",
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    page.fill("#full-name", material.full_name)
                    page.fill("#email", material.email)
                    page.set_input_files(
                        "#resume",
                        {
                            "name": material.resume_name,
                            "mimeType": "application/pdf",
                            "buffer": material.resume_bytes,
                        },
                    )
                    page.click("button[type=submit]", timeout=timeout_ms)
                finally:
                    browser.close()
        except Exception as error:
            if outcome in (
                SyntheticBrowserOutcome.TIMEOUT_AFTER_ACCEPT,
                SyntheticBrowserOutcome.TIMEOUT_BEFORE_ACCEPT,
            ):
                raise TimeoutError("Synthetic browser submit timed out.") from error
            raise
        return receipt

    def read_status(
        self, prepared: PreparedAction, observed_at: datetime
    ) -> BrowserSubmissionObservation:
        """Inspect only the synthetic site's receipt ledger; this never opens a page."""
        self._validate_attempt(prepared)
        invoked = self.invocations.get(prepared.attempt_id, 0)
        receipt = self.accepted.get(prepared.attempt_id)
        if receipt is not None:
            outcome = BrowserSubmissionOutcome.PROVIDER_ACCEPTED
            source_ref = receipt
        elif invoked == 1:
            outcome = BrowserSubmissionOutcome.NOT_PERFORMED
            source_ref = uuid5(NAMESPACE_URL, f"acoa:synthetic-browser-empty:{prepared.attempt_id}")
        else:
            outcome = BrowserSubmissionOutcome.UNKNOWN
            source_ref = uuid5(
                NAMESPACE_URL, f"acoa:synthetic-browser-unknown:{prepared.attempt_id}"
            )
        snapshot = content_digest(
            {
                "schema": "acoa-synthetic-browser-status/1",
                "attempt_id": str(prepared.attempt_id),
                "outcome": outcome.value,
                "source_ref": str(source_ref),
            }
        )
        return BrowserSubmissionObservation(
            prepared.attempt_id,
            prepared.provider_id,
            prepared_binding_sha256(prepared),
            source_ref,
            snapshot,
            observed_at,
            outcome,
        )

    def _validate_attempt(self, prepared: PreparedAction) -> SyntheticApplicationMaterial:
        require_web_submission(prepared)
        material = self.materials.get(prepared.attempt_id)
        if (
            material is None
            or prepared.provider_id != self.provider_id
            or prepared.request.content_sha256 != synthetic_application_sha256(material)
        ):
            raise DomainError("Synthetic browser site requires an exact configured attempt.")
        return material


_FORM_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Synthetic career site</title></head>
<body><form method="post" action="https://career.test.invalid/submit">
<label>Full name <input id="full-name" name="full_name" required></label>
<label>Email <input id="email" name="email" type="email" required></label>
<label>Resume
<input id="resume" name="resume" type="file" accept="application/pdf" required>
</label>
<button type="submit">Submit application</button>
</form></body></html>"""

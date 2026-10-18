"""Authenticated Gmail REST transport with explicit token storage and redacted failures."""

import json
import os
from collections.abc import Mapping
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from acoa.domain.values import DomainError
from acoa.infrastructure.gmail import GMAIL_REQUIRED_SCOPES, GmailTransportError

GMAIL_API_ORIGIN = "https://gmail.googleapis.com"


def _credentials_class() -> Any:
    try:
        return import_module("google.oauth2.credentials").Credentials
    except (ImportError, AttributeError) as error:
        raise DomainError(
            "The isolated Gmail integration dependencies are not installed."
        ) from error


def _authorized_session_class() -> Any:
    try:
        return import_module("google.auth.transport.requests").AuthorizedSession
    except (ImportError, AttributeError) as error:
        raise DomainError(
            "The isolated Gmail integration dependencies are not installed."
        ) from error


def _write_token_atomically(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(payload)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class GoogleAuthorizedGmailTransport:
    """Use only an explicit OAuth token path; never discover ambient credentials."""

    def __init__(self, token_path: Path) -> None:
        if not isinstance(token_path, Path) or not token_path.is_file():
            raise DomainError("Gmail requires an explicit existing OAuth token file.")
        credentials = _credentials_class().from_authorized_user_file(
            str(token_path), sorted(GMAIL_REQUIRED_SCOPES)
        )
        if set(credentials.scopes or ()) != GMAIL_REQUIRED_SCOPES:
            raise DomainError("The OAuth token does not contain the exact Gmail pilot scopes.")
        self._token_path = token_path
        self._credentials = credentials
        self._session = _authorized_session_class()(credentials)

    def request(
        self,
        method: str,
        path: str,
        query: Mapping[str, str],
        body: Mapping[str, object] | None,
        *,
        timeout_seconds: int,
    ) -> Mapping[str, object]:
        if method not in {"GET", "POST"} or not path.startswith("/gmail/v1/users/me/"):
            raise DomainError("The Gmail transport request is outside its fixed API boundary.")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds < 1
        ):
            raise DomainError("The Gmail transport requires a positive timeout.")
        response = self._session.request(
            method,
            GMAIL_API_ORIGIN + path,
            params=dict(query),
            json=dict(body) if body is not None else None,
            timeout=timeout_seconds,
        )
        if not 200 <= response.status_code < 300:
            raise GmailTransportError(response.status_code)
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as error:
            raise DomainError("Gmail returned an invalid JSON response.") from error
        if not isinstance(payload, Mapping):
            raise DomainError("Gmail returned an invalid response object.")
        if getattr(self._credentials, "token", None):
            _write_token_atomically(self._token_path, self._credentials.to_json())
        return cast(Mapping[str, object], payload)

"""FastAPI, server-rendered HTML and protected controls for EP-07.01/02."""

from collections.abc import Awaitable, Callable
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi import Path as PathParameter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict
from starlette.responses import Response

from acoa.application.dashboard import DashboardQuery, DashboardSnapshot
from acoa.application.dashboard_controls import (
    DashboardControlCommand,
    DashboardControlResult,
    DashboardLimitValues,
)
from acoa.interfaces.dashboard_security import DashboardSecurity

DashboardLoader = Callable[[DashboardQuery], DashboardSnapshot]


class DashboardController(Protocol):
    def enter_safe_mode(self, command: DashboardControlCommand) -> DashboardControlResult: ...

    def resume_system(self, command: DashboardControlCommand) -> DashboardControlResult: ...

    def replace_limits(
        self, command: DashboardControlCommand, values: DashboardLimitValues
    ) -> DashboardControlResult: ...

    def pause_task(
        self, command: DashboardControlCommand, task_id: UUID
    ) -> DashboardControlResult: ...

    def resume_task(
        self, command: DashboardControlCommand, task_id: UUID
    ) -> DashboardControlResult: ...

    def cancel_task(
        self, command: DashboardControlCommand, task_id: UUID
    ) -> DashboardControlResult: ...


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID


class LimitRequest(ControlRequest):
    applications_per_day: int | None
    applications_per_week: int | None
    outreach_per_company: int | None
    outreach_per_contact: int | None
    currency: str | None
    currency_per_day: Decimal | None
    currency_per_month: Decimal | None
    tokens_per_task: int | None
    seconds_per_task: int | None

    def values(self) -> DashboardLimitValues:
        return DashboardLimitValues(
            self.applications_per_day,
            self.applications_per_week,
            self.outreach_per_company,
            self.outreach_per_contact,
            self.currency,
            self.currency_per_day,
            self.currency_per_month,
            self.tokens_per_task,
            self.seconds_per_task,
        )


def _dashboard_query(search: str | None, limit: int) -> DashboardQuery:
    normalized = search.strip() if search is not None else None
    return DashboardQuery(search=normalized or None, limit=limit)


def create_dashboard_app(
    loader: DashboardLoader,
    *,
    security: DashboardSecurity | None = None,
    controller: DashboardController | None = None,
) -> FastAPI:
    """Create a read view, adding authenticated controls only when explicitly injected."""
    if not callable(loader):
        raise TypeError("Dashboard application requires a snapshot loader.")
    if controller is not None and security is None:
        raise ValueError("Dashboard controls require server-side security.")
    asset_root = Path(__file__).parent
    templates = Jinja2Templates(directory=asset_root / "templates")
    basic = HTTPBasic(auto_error=False)
    app = FastAPI(title="ACOA Dashboard", version="0.2.0", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=asset_root / "static"), name="static")

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response_value = await call_next(request)
        response_value.headers["Cache-Control"] = "no-store"
        response_value.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response_value.headers["Referrer-Policy"] = "no-referrer"
        response_value.headers["X-Content-Type-Options"] = "nosniff"
        response_value.headers["X-Frame-Options"] = "DENY"
        return response_value

    def current_actor(
        credentials: Annotated[HTTPBasicCredentials | None, Depends(basic)],
    ) -> str:
        if security is None:
            return ""
        actor = (
            security.authenticator.authenticate(credentials.username, credentials.password)
            if credentials is not None
            else None
        )
        if actor is None:
            raise HTTPException(
                status_code=401,
                detail="Dashboard authentication required.",
                headers={"WWW-Authenticate": 'Basic realm="ACOA"'},
            )
        return actor

    def csrf_actor(
        actor: Annotated[str, Depends(current_actor)],
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> str:
        if security is None or csrf_token is None or not security.csrf.verify(csrf_token, actor):
            raise HTTPException(status_code=403, detail="Valid CSRF token required.")
        return actor

    def command(request_id: UUID, actor: str) -> DashboardControlCommand:
        return DashboardControlCommand(request_id, actor)

    def response(result: DashboardControlResult) -> JSONResponse:
        return JSONResponse(jsonable_encoder(asdict(result)))

    def reject_control() -> HTTPException:
        return HTTPException(status_code=409, detail="Control rejected for the current state.")

    @app.get("/", response_class=HTMLResponse)
    def dashboard(
        request: Request,
        actor: Annotated[str, Depends(current_actor)],
        q: Annotated[str | None, Query(max_length=100)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> HTMLResponse:
        query = _dashboard_query(q, limit)
        csrf_token = security.csrf.issue(actor) if security is not None else None
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "snapshot": loader(query),
                "query": query,
                "controls_enabled": controller is not None,
                "csrf_token": csrf_token,
            },
        )

    @app.get("/api/dashboard", response_class=JSONResponse)
    def dashboard_api(
        _actor: Annotated[str, Depends(current_actor)],
        q: Annotated[str | None, Query(max_length=100)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> JSONResponse:
        snapshot = loader(_dashboard_query(q, limit))
        return JSONResponse(jsonable_encoder(asdict(snapshot)))

    if controller is not None:

        @app.post("/api/controls/safe-mode", response_class=JSONResponse)
        def safe_mode(
            body: ControlRequest,
            actor: Annotated[str, Depends(csrf_actor)],
        ) -> JSONResponse:
            try:
                return response(controller.enter_safe_mode(command(body.request_id, actor)))
            except ValueError:
                raise reject_control() from None

        @app.post("/api/controls/resume", response_class=JSONResponse)
        def resume(
            body: ControlRequest,
            actor: Annotated[str, Depends(csrf_actor)],
        ) -> JSONResponse:
            try:
                return response(controller.resume_system(command(body.request_id, actor)))
            except ValueError:
                raise reject_control() from None

        @app.post("/api/controls/limits", response_class=JSONResponse)
        def limits(
            body: LimitRequest,
            actor: Annotated[str, Depends(csrf_actor)],
        ) -> JSONResponse:
            try:
                return response(
                    controller.replace_limits(command(body.request_id, actor), body.values())
                )
            except ValueError:
                raise reject_control() from None

        def task_action(
            body: ControlRequest,
            actor: str,
            task_id: UUID,
            action: Callable[[DashboardControlCommand, UUID], DashboardControlResult],
        ) -> JSONResponse:
            try:
                return response(action(command(body.request_id, actor), task_id))
            except ValueError:
                raise reject_control() from None

        @app.post("/api/tasks/{task_id}/pause", response_class=JSONResponse)
        def pause_task(
            body: ControlRequest,
            actor: Annotated[str, Depends(csrf_actor)],
            task_id: Annotated[UUID, PathParameter()],
        ) -> JSONResponse:
            return task_action(body, actor, task_id, controller.pause_task)

        @app.post("/api/tasks/{task_id}/resume", response_class=JSONResponse)
        def resume_task(
            body: ControlRequest,
            actor: Annotated[str, Depends(csrf_actor)],
            task_id: Annotated[UUID, PathParameter()],
        ) -> JSONResponse:
            return task_action(body, actor, task_id, controller.resume_task)

        @app.post("/api/tasks/{task_id}/cancel", response_class=JSONResponse)
        def cancel_task(
            body: ControlRequest,
            actor: Annotated[str, Depends(csrf_actor)],
            task_id: Annotated[UUID, PathParameter()],
        ) -> JSONResponse:
            return task_action(body, actor, task_id, controller.cancel_task)

    return app

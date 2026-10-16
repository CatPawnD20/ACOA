"""FastAPI and server-rendered HTML boundary for EP-07.01."""

from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from acoa.application.dashboard import DashboardQuery, DashboardSnapshot

DashboardLoader = Callable[[DashboardQuery], DashboardSnapshot]


def _dashboard_query(search: str | None, limit: int) -> DashboardQuery:
    normalized = search.strip() if search is not None else None
    return DashboardQuery(search=normalized or None, limit=limit)


def create_dashboard_app(loader: DashboardLoader) -> FastAPI:
    """Create a read-only app; database/configuration ownership remains with the caller."""
    if not callable(loader):
        raise TypeError("Dashboard application requires a snapshot loader.")
    asset_root = Path(__file__).parent
    templates = Jinja2Templates(directory=asset_root / "templates")
    app = FastAPI(title="ACOA Dashboard", version="0.1.0", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=asset_root / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    def dashboard(
        request: Request,
        q: Annotated[str | None, Query(max_length=100)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> HTMLResponse:
        query = _dashboard_query(q, limit)
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"snapshot": loader(query), "query": query},
        )

    @app.get("/api/dashboard", response_class=JSONResponse)
    def dashboard_api(
        q: Annotated[str | None, Query(max_length=100)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> JSONResponse:
        snapshot = loader(_dashboard_query(q, limit))
        return JSONResponse(jsonable_encoder(asdict(snapshot)))

    return app

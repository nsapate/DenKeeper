"""FastAPI entrypoint for the Denkeeper expense worker."""

from __future__ import annotations

from contextlib import asynccontextmanager
import secrets
from typing import Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .config import load_settings
from .database import connect, ensure_database
from .models import (
    ExpenseCommandRequest,
    ExpenseCommandResponse,
    ReceiptIngestRequest,
    StructuredExpenseCommandRequest,
)
from .repository import ExpenseRepository
from .service import ExpenseService


settings = load_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize the SQLite schema before serving traffic."""

    ensure_database(settings.db_path)
    yield


app = FastAPI(title="Denkeeper Expense Worker", lifespan=lifespan)


def require_token(x_denkeeper_token: str | None = Header(default=None)) -> None:
    """Authorize requests when a token is configured."""

    if settings.api_token is None:
        if settings.require_api_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Denkeeper API token is not configured",
            )
        return
    if not secrets.compare_digest(x_denkeeper_token or "", settings.api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Denkeeper API token",
        )


def get_repository() -> Iterator[ExpenseRepository]:
    """Provide a request-scoped repository."""

    connection = connect(settings.db_path)
    try:
        yield ExpenseRepository(connection)
    finally:
        connection.close()


def get_service(repository: ExpenseRepository = Depends(get_repository)) -> ExpenseService:
    """Provide the request-scoped service layer."""

    return ExpenseService(repository, settings.timezone, settings.allowed_scopes)


@app.get("/health")
def health() -> dict[str, object]:
    """Liveness endpoint."""

    return {"ok": True}


@app.post("/v1/expenses/handle", response_model=ExpenseCommandResponse)
def handle_expense_command(
    request: ExpenseCommandRequest,
    _: None = Depends(require_token),
    service: ExpenseService = Depends(get_service),
) -> ExpenseCommandResponse:
    """Handle a freeform expense request."""

    return service.handle(request)


@app.post("/v1/expenses/handle-structured", response_model=ExpenseCommandResponse)
def handle_structured_expense_command(
    request: StructuredExpenseCommandRequest,
    _: None = Depends(require_token),
    service: ExpenseService = Depends(get_service),
) -> ExpenseCommandResponse:
    """Handle a structured expense request from the OpenClaw tool schema."""

    return service.handle_structured(request)


@app.post("/v1/expenses/receipt", response_model=ExpenseCommandResponse)
def ingest_receipt(
    request: ReceiptIngestRequest,
    _: None = Depends(require_token),
    service: ExpenseService = Depends(get_service),
) -> ExpenseCommandResponse:
    """Persist a structured itemized receipt into the expense ledger."""

    return service.ingest_receipt(request)

import asyncio
import logging
from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.security import encrypt_secret
from app.db.models import IntegrationType, Printer, User
from app.db.session import get_db
from app.integrations.moonraker.client import PendingAction
from app.integrations.moonraker.print_guard import (
    CancelRefused,
    ResumeRefused,
    cancel_safely,
    pause_safely,
    resume_safely,
)
from app.schemas.printer import PrinterCreate, PrinterRead, PrinterUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/printers", tags=["printers"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[PrinterRead])
async def list_printers(db: AsyncSession = Depends(get_db)) -> list[Printer]:
    result = await db.execute(select(Printer).order_by(Printer.id))
    return list(result.scalars().all())


@router.post("", response_model=PrinterRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def create_printer(payload: PrinterCreate, request: Request, db: AsyncSession = Depends(get_db)) -> Printer:
    printer = Printer(
        name=payload.name,
        model=payload.model,
        octoprint_url=payload.octoprint_url,
        octoprint_api_key_encrypted=encrypt_secret(payload.octoprint_api_key or ""),
        integration_type=payload.integration_type,
    )
    db.add(printer)
    await db.commit()
    await db.refresh(printer)
    await request.app.state.printer_manager.start(printer.id)
    return printer


@router.get("/{printer_id}", response_model=PrinterRead)
async def get_printer(printer_id: int, db: AsyncSession = Depends(get_db)) -> Printer:
    printer = await db.get(Printer, printer_id)
    if printer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer not found")
    return printer


@router.patch("/{printer_id}", response_model=PrinterRead, dependencies=[Depends(require_admin)])
async def update_printer(printer_id: int, payload: PrinterUpdate, db: AsyncSession = Depends(get_db)) -> Printer:
    printer = await db.get(Printer, printer_id)
    if printer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer not found")

    updates = payload.model_dump(exclude_unset=True)
    if "octoprint_api_key" in updates:
        printer.octoprint_api_key_encrypted = encrypt_secret(updates.pop("octoprint_api_key"))
    for field, value in updates.items():
        setattr(printer, field, value)

    await db.commit()
    await db.refresh(printer)
    return printer


@router.delete("/{printer_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def delete_printer(printer_id: int, db: AsyncSession = Depends(get_db)) -> None:
    printer = await db.get(Printer, printer_id)
    if printer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer not found")
    await db.delete(printer)
    await db.commit()


async def _get_moonraker_printer_or_404(printer_id: int, db: AsyncSession) -> Printer:
    printer = await db.get(Printer, printer_id)
    if printer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer not found")
    if printer.integration_type != IntegrationType.moonraker:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This action is only supported for Moonraker printers"
        )
    return printer


# How long an endpoint waits for the printer before answering "accepted". A refusal comes back within a second or
# two (unreachable printer, Moonraker saying no), so it still reaches the user as an error; what takes long is the
# printer carrying out the order (a resume answers 45 to 65 s later) and that is not an error: the web follows the
# printer's own state change instead (see frontend/src/hooks/usePrintAction.ts).
ACCEPT_WAIT_SECONDS = 3.0


class ActionAccepted(BaseModel):
    """The order is on its way; `pending` says the printer had not answered yet."""

    action: str
    accepted: bool = True
    pending: bool
    sent_at: datetime


def _failure_detail(exc: httpx.HTTPError, action: str) -> str:
    # Some httpx exceptions (timeouts especially) carry an empty str(exc) - seen for real on this project's printer,
    # where a manual retry outside the app was the only way to tell what had actually happened. type(exc).__name__
    # keeps "which kind of failure" in the response even when the exception itself has nothing else to say.
    if str(exc):
        return f"Could not {action} via Moonraker ({type(exc).__name__}): {exc}"
    return f"Could not {action} via Moonraker: {type(exc).__name__} (no further detail - check backend logs)"


async def _accepted(pending: PendingAction, action: str) -> ActionAccepted:
    """Waits a few seconds for a quick refusal, then reports the order as accepted. The order itself goes on in the
    background and is noted in the event log as sent, not as failed because it took long."""
    done, _ = await asyncio.wait({pending.task}, timeout=ACCEPT_WAIT_SECONDS)
    if done:
        error = pending.task.result()
        if error is not None:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_failure_detail(error, action)) from error
    return ActionAccepted(action=action, pending=not done, sent_at=pending.command.sent_at)


@router.post("/{printer_id}/pause", status_code=status.HTTP_202_ACCEPTED, response_model=ActionAccepted)
async def pause_printer(
    printer_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)
) -> ActionAccepted:
    """Manual pause, for testing/demoing independently of the spaghetti auto-pause flow
    (app/services/auto_pause.py) - same Moonraker action, triggered directly instead of after a
    detected streak. Proxied through the backend rather than called from the browser directly:
    Moonraker has no auth of its own, so this keeps our own auth/audit log in front of an action
    that stops a physical machine. First reads the printer's state (to know it answers: unreachable, 502 at once and
    noted in the event log), then answers "accepted" without waiting for the printer to finish parking the head."""
    printer = await _get_moonraker_printer_or_404(printer_id, db)
    logger.warning("Manual pause requested for printer %s (%s)", printer.id, printer.octoprint_url)
    try:
        pending = await pause_safely(printer.octoprint_url, f"{user.username} (web)")
    except httpx.HTTPError as exc:
        # The printer did not answer the state read: nothing was sent.
        logger.warning("Pause not sent for printer %s, its state could not be read: %s", printer.id, type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_failure_detail(exc, "pause")) from exc
    return await _accepted(pending, "pause")


@router.post("/{printer_id}/resume", status_code=status.HTTP_202_ACCEPTED, response_model=ActionAccepted)
async def resume_printer(
    printer_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)
) -> ActionAccepted:
    """Manual resume - independent of whether the pause was triggered automatically (spaghetti
    auto-pause) or by hand on the printer itself. Proxied through the backend rather than called
    directly from the browser: Moonraker has no auth of its own, so this keeps our own
    auth/audit log in front of an action that stops/starts a physical machine. The printer takes 45 to 65 s to carry
    it out: the answer is "accepted" and the printer's own state change is the confirmation."""
    printer = await _get_moonraker_printer_or_404(printer_id, db)
    logger.warning("Manual resume requested for printer %s (%s)", printer.id, printer.octoprint_url)
    # See integrations/moonraker/print_guard.py: one at a time, not twice in a row, and only if the
    # printer itself says it is paused.
    try:
        pending = await resume_safely(printer.octoprint_url, f"{user.username} (web)")
    except ResumeRefused as refusal:
        logger.warning("Resume refused for printer %s: %s", printer.id, refusal)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(refusal)) from refusal
    except httpx.HTTPError as exc:
        # The state could not be read: nothing was sent.
        logger.warning("Resume not sent for printer %s, its state could not be read: %s", printer.id, type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_failure_detail(exc, "resume")) from exc
    return await _accepted(pending, "resume")


class CancelRequest(BaseModel):
    # Cancelling cannot be undone: besides the two confirmations in the web, the server only accepts the order
    # with this exact word, so a stray request cannot cancel a print.
    confirmation: Literal["CANCELAR"]


@router.post("/{printer_id}/cancel", status_code=status.HTTP_202_ACCEPTED, response_model=ActionAccepted)
async def cancel_printer(
    printer_id: int, payload: CancelRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)
) -> ActionAccepted:
    """Cancel the print in progress. Administrators only, with the typed confirmation, and only if the printer itself
    (a read-only GET of print_stats.state) says it is printing or paused: see
    integrations/moonraker/print_guard.py. One order at a time, 20 s between orders."""
    printer = await _get_moonraker_printer_or_404(printer_id, db)
    logger.warning("Cancel requested by %s for printer %s (%s)", user.username, printer.id, printer.octoprint_url)
    try:
        pending = await cancel_safely(printer.octoprint_url, f"{user.username} (web)")
    except CancelRefused as refusal:
        logger.warning("Cancel refused for printer %s: %s", printer.id, refusal)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(refusal)) from refusal
    except httpx.HTTPError as exc:
        # The state could not be read: nothing was sent.
        logger.warning("Cancel not sent for printer %s, its state could not be read: %s", printer.id, type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_failure_detail(exc, "cancel")) from exc
    return await _accepted(pending, "cancel")

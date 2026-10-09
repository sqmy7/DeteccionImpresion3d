import logging
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
from app.integrations.moonraker.client import send_print_action
from app.integrations.moonraker.print_guard import CancelRefused, ResumeRefused, cancel_safely, resume_safely
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


async def _send_print_action_or_502(printer: Printer, action: str, user: User) -> None:
    try:
        await send_print_action(printer.octoprint_url, action, requested_by=f"{user.username} (web)")
    except httpx.HTTPError as exc:
        # Some httpx exceptions (timeouts especially) carry an empty str(exc) - seen for real
        # on this project's printer, where a manual retry outside the app was the only way to
        # tell what had actually happened. type(exc).__name__ keeps "which kind of failure" in
        # the response even when the exception itself has nothing else to say.
        logger.exception("Moonraker '%s' action failed for printer %s (%s)", action, printer.id, printer.octoprint_url)
        detail = f"Could not {action} via Moonraker ({type(exc).__name__}): {exc}" if str(exc) else (
            f"Could not {action} via Moonraker: {type(exc).__name__} (no further detail - check backend logs)"
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc


@router.post("/{printer_id}/pause", status_code=status.HTTP_204_NO_CONTENT)
async def pause_printer(printer_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)) -> None:
    """Manual pause, for testing/demoing independently of the spaghetti auto-pause flow
    (app/services/auto_pause.py) - same Moonraker action, triggered directly instead of after a
    detected streak. Proxied through the backend rather than called from the browser directly:
    Moonraker has no auth of its own, so this keeps our own auth/audit log in front of an action
    that stops a physical machine."""
    printer = await _get_moonraker_printer_or_404(printer_id, db)
    logger.warning("Manual pause requested for printer %s (%s)", printer.id, printer.octoprint_url)
    await _send_print_action_or_502(printer, "pause", user)


@router.post("/{printer_id}/resume", status_code=status.HTTP_204_NO_CONTENT)
async def resume_printer(printer_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)) -> None:
    """Manual resume - independent of whether the pause was triggered automatically (spaghetti
    auto-pause) or by hand on the printer itself. Proxied through the backend rather than called
    directly from the browser: Moonraker has no auth of its own, so this keeps our own
    auth/audit log in front of an action that stops/starts a physical machine."""
    printer = await _get_moonraker_printer_or_404(printer_id, db)
    logger.warning("Manual resume requested for printer %s (%s)", printer.id, printer.octoprint_url)
    # See integrations/moonraker/print_guard.py: one at a time, not twice in a row, and only if the
    # printer itself says it is paused.
    try:
        await resume_safely(printer.octoprint_url, f"{user.username} (web)")
    except ResumeRefused as refusal:
        logger.warning("Resume refused for printer %s: %s", printer.id, refusal)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(refusal)) from refusal
    except httpx.HTTPError as exc:
        # Either the state could not be read (nothing was sent) or the order itself failed.
        logger.exception("Moonraker resume failed for printer %s (%s)", printer.id, printer.octoprint_url)
        detail = f"Could not resume via Moonraker ({type(exc).__name__}): {exc}" if str(exc) else (
            f"Could not resume via Moonraker: {type(exc).__name__} (no further detail - check backend logs)"
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc


class CancelRequest(BaseModel):
    # Cancelling cannot be undone: besides the two confirmations in the web, the server only accepts the order
    # with this exact word, so a stray request cannot cancel a print.
    confirmation: Literal["CANCELAR"]


@router.post("/{printer_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_printer(
    printer_id: int, payload: CancelRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)
) -> None:
    """Cancel the print in progress. Administrators only, with the typed confirmation, and only if the printer itself
    (a read-only GET of print_stats.state) says it is printing or paused: see
    integrations/moonraker/print_guard.py. One order at a time, 20 s between orders."""
    printer = await _get_moonraker_printer_or_404(printer_id, db)
    logger.warning("Cancel requested by %s for printer %s (%s)", user.username, printer.id, printer.octoprint_url)
    try:
        await cancel_safely(printer.octoprint_url, f"{user.username} (web)")
    except CancelRefused as refusal:
        logger.warning("Cancel refused for printer %s: %s", printer.id, refusal)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(refusal)) from refusal
    except httpx.HTTPError as exc:
        # Either the state could not be read (nothing was sent) or the order itself failed.
        logger.exception("Moonraker cancel failed for printer %s (%s)", printer.id, printer.octoprint_url)
        detail = f"Could not cancel via Moonraker ({type(exc).__name__}): {exc}" if str(exc) else (
            f"Could not cancel via Moonraker: {type(exc).__name__} (no further detail - check backend logs)"
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc

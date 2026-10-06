import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.security import encrypt_secret
from app.db.models import IntegrationType, Printer
from app.db.session import get_db
from app.integrations.moonraker.client import send_print_action
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


async def _send_print_action_or_502(printer: Printer, action: str) -> None:
    try:
        await send_print_action(printer.octoprint_url, action)
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


@router.post("/{printer_id}/pause", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def pause_printer(printer_id: int, db: AsyncSession = Depends(get_db)) -> None:
    """Manual pause, for testing/demoing independently of the spaghetti auto-pause flow
    (app/services/auto_pause.py) - same Moonraker action, triggered directly instead of after a
    detected streak. Proxied through the backend rather than called from the browser directly:
    Moonraker has no auth of its own, so this keeps our own auth/audit log in front of an action
    that stops a physical machine."""
    printer = await _get_moonraker_printer_or_404(printer_id, db)
    logger.warning("Manual pause requested for printer %s (%s)", printer.id, printer.octoprint_url)
    await _send_print_action_or_502(printer, "pause")


@router.post("/{printer_id}/resume", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def resume_printer(printer_id: int, db: AsyncSession = Depends(get_db)) -> None:
    """Manual resume - independent of whether the pause was triggered automatically (spaghetti
    auto-pause) or by hand on the printer itself. Proxied through the backend rather than called
    directly from the browser: Moonraker has no auth of its own, so this keeps our own
    auth/audit log in front of an action that stops/starts a physical machine."""
    printer = await _get_moonraker_printer_or_404(printer_id, db)
    logger.warning("Manual resume requested for printer %s (%s)", printer.id, printer.octoprint_url)
    await _send_print_action_or_502(printer, "resume")

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import text

from app.db.models import IntegrationType, Printer
from app.services.printer_events import EventOrigin, event_hash, event_payload, record_event, verify_chain


def _event(**overrides):
    values = {
        "printer_id": 35,
        "print_job_id": 7,
        "ts": datetime(2026, 9, 26, 0, 20, 7, 90000, tzinfo=timezone.utc),
        "klipper_eventtime": 12633.719,
        "event_type": "state_changed",
        "field": "print_stats.state",
        "value_before": "printing",
        "value_after": "error",
        "origin": "printer",
        "detail": {"error": {"code": "key243", "values": [292.424, 249.61, 28.401]}},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_hash_depends_on_content_and_previous_hash():
    base = event_hash("a" * 64, event_payload(_event()))

    assert event_hash("a" * 64, event_payload(_event())) == base
    assert event_hash("b" * 64, event_payload(_event())) != base
    assert event_hash("a" * 64, event_payload(_event(value_after="paused"))) != base


def test_hash_survives_how_postgres_returns_json_numbers():
    # JSONB may hand back 1e20 as an integer and 240.0 as 240.0; both must hash the same.
    stored = event_payload(_event(detail={"big": 1e20, "target": 240.0}))
    returned = event_payload(_event(detail={"big": 100000000000000000000, "target": 240.0}))
    assert event_hash(None, stored) == event_hash(None, returned)


def test_hash_ignores_the_timezone_the_timestamp_comes_back_in():
    utc = _event()
    bogota = _event(ts=utc.ts.astimezone(datetime.now().astimezone().tzinfo))
    assert event_hash(None, event_payload(utc)) == event_hash(None, event_payload(bogota))


async def _make_printer(session_factory) -> int:
    async with session_factory() as db:
        printer = Printer(
            name="Impresora de prueba",
            octoprint_url="http://mock",
            octoprint_api_key_encrypted="",
            integration_type=IntegrationType.moonraker,
        )
        db.add(printer)
        await db.commit()
        return printer.id


def test_chain_detects_an_edited_and_a_deleted_event(with_db):
    async def scenario(session_factory):
        printer_id = await _make_printer(session_factory)
        for index in range(5):
            await record_event(
                session_factory,
                printer_id,
                "state_changed",
                EventOrigin.EXTERNAL,
                before="printing",
                after="paused",
                detail={"index": index, "target": 240.0, "big": 1e20},
                klipper_eventtime=12345.678 + index,
            )

        async with session_factory() as db:
            intact = await verify_chain(db, printer_id)
            await db.execute(text("UPDATE printer_events SET value_after = '\"printing\"' WHERE id = 3"))
            await db.commit()
            edited = await verify_chain(db, printer_id)
            await db.execute(text("DELETE FROM printer_events WHERE id = 3"))
            await db.commit()
            deleted = await verify_chain(db, printer_id)
        return intact, edited, deleted

    intact, edited, deleted = with_db(scenario)

    assert intact["ok"] is True and intact["events_checked"] == 5
    assert (edited["ok"], edited["first_broken_id"], edited["reason"]) == (False, 3, "content_changed")
    assert (deleted["ok"], deleted["first_broken_id"], deleted["reason"]) == (False, 4, "prev_hash_mismatch")


def test_concurrent_writers_keep_a_single_chain(with_db):
    async def scenario(session_factory):
        printer_id = await _make_printer(session_factory)
        await asyncio.gather(
            *(
                record_event(session_factory, printer_id, "printwatch_command", EventOrigin.PRINTWATCH, detail={"n": n})
                for n in range(20)
            )
        )
        async with session_factory() as db:
            return await verify_chain(db, printer_id)

    result = with_db(scenario)
    assert result["ok"] is True and result["events_checked"] == 20

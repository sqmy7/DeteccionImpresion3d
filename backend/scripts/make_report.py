"""Builds the PDF report of a job straight from the database in DATABASE_URL (only SELECTs), without the
web or the API: for checking a report with real data, or saving one without logging in.

usage (repo root):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\make_report.py 43 reporte_trabajo_43.pdf
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models import PrintJob  # noqa: E402
from app.services import report  # noqa: E402


async def main(job_id: int, out: Path) -> None:
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            job = await db.get(PrintJob, job_id)
            if job is None:
                raise SystemExit(f"No existe el trabajo {job_id}")
            started = time.perf_counter()
            content = await report.build_report(db, job)
            out.write_bytes(content)
            print(f"trabajo {job_id}: {len(content) / 1024:.0f} KB en {(time.perf_counter() - started) * 1000:.0f} ms -> {out}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    asyncio.run(main(int(sys.argv[1]), Path(sys.argv[2])))

import sys
from pathlib import Path

# capture/ is a sibling of backend/ in this repo. Reuse backend's SQLAlchemy models
# (app.db.models) directly instead of a second copy, so the schema has one source of
# truth and can't drift between the two processes. This runs before any other capture
# submodule, since Python executes __init__.py first when the package is imported.
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

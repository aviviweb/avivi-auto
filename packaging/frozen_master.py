"""PyInstaller entry point: Avivi Master (FastAPI + uvicorn)."""
from __future__ import annotations

import os
import sys


def _chdir_to_bundle() -> None:
    if getattr(sys, "frozen", False):
        os.chdir(os.path.dirname(sys.executable))


def main() -> None:
    _chdir_to_bundle()
    import uvicorn

    from avivi_master.config import settings
    from avivi_master.main import app

    uvicorn.run(app, host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()

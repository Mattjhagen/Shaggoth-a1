"""Console-script bootstrap.

``python -m shaggoth`` keeps the repository-root behaviour (data and config
live next to the checkout). When installed as a package the console entry
point runs through this module instead, which points the data root at a
per-user ``~/.shaggoth`` directory so upgrades and installs never touch
site-packages with user data.

Set ``SHAGGOTH_ROOT`` yourself to override either behaviour.
"""

from __future__ import annotations

import os
from pathlib import Path


def main() -> int:
    if not os.environ.get("SHAGGOTH_ROOT"):
        _pkg_dir = Path(__file__).resolve().parent
        _repo_marker = _pkg_dir.parent / "LICENSE"
        if not _repo_marker.exists():
            # Installed package (no LICENSE at the parent of the package dir).
            os.environ["SHAGGOTH_ROOT"] = str(Path.home() / ".shaggoth")

    from .__main__ import main as _main

    raise SystemExit(_main())


if __name__ == "__main__":
    main()

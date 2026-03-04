from __future__ import annotations

from pathlib import Path
from typing import Any

import tomllib


def load_config(path: str | Path) -> dict[str, Any]:
    cfg_path = Path(path)
    with cfg_path.open("rb") as f:
        return tomllib.load(f)

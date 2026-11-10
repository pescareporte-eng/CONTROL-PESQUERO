from __future__ import annotations

import re
from collections.abc import Iterable, Mapping


def next_vessel_code(rows: Iterable[Mapping[str, object]], prefix: str = "EMB", width: int = 3) -> str:
    """Return the next unused EMB-### code, considering active and inactive vessels."""
    used: set[str] = set()
    highest = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$", re.IGNORECASE)

    for row in rows:
        code = str(row.get("codigo", "") or "").strip().upper()
        if not code:
            continue
        used.add(code)
        match = pattern.fullmatch(code)
        if match:
            highest = max(highest, int(match.group(1)))

    sequence = highest + 1
    candidate = f"{prefix.upper()}-{sequence:0{width}d}"
    while candidate in used:
        sequence += 1
        candidate = f"{prefix.upper()}-{sequence:0{width}d}"
    return candidate

"""Per-source JSON cache with age gating and a status ledger.

Adapted from 02-Maintain/overhang (itself from hangar). This is the module that makes UPLIFT refresh
*periodically* rather than continuously. Every source declares a ``max_age``;
a run only goes out to the network for sources whose cached copy has expired.
Everything else is served from ``data/``.

Two properties matter more than speed here:

1. **A failed fetch must never blank a panel.** If a source raises, the previous
   good payload is kept and the failure is recorded. The page then renders stale
   data with a visible marker, which is honest. An empty panel is not — it is
   indistinguishable from a quiet news day.
2. **Staleness has to be visible.** ``status.json`` carries the last success, the
   last error, and the age of every source so the page can mark what is old.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# How long each source's cached copy stays valid. The refresh workflow runs
# every 6 hours; anything with a longer max_age simply skips most runs. The
# measured sources (METR, Epoch, ARC) update weekly at best, so a day is ample.
MAX_AGE: dict[str, timedelta] = {
    # The registry updates daily; one read a day catches every change within a day.
    "ctgov": timedelta(hours=20),
}

# A source older than STALE_FACTOR x its max_age is reported as stale to the page.
STALE_FACTOR = 3


class NotModified(Exception):
    """Upstream reports its data is unchanged since our last successful fetch.

    Distinct from a failure. CelesTrak, for one, answers a repeat request with
    HTTP 403 and a body saying the data has not updated - which is a courtesy,
    not an error, and must not mark the source as broken.
    """


def _path(name: str) -> Path:
    return DATA_DIR / f"{name}.json"


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_ts(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def load(name: str) -> dict | None:
    """Return the cached envelope ``{fetched_at, data}`` for ``name``, or None."""
    path = _path(name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [WARN] cache unreadable for {name}: {e}")
        return None


def save(name: str, data: Any) -> dict:
    """Write ``data`` under a ``fetched_at`` envelope and return the envelope."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    envelope = {"fetched_at": _now().isoformat(), "data": data}
    _path(name).write_text(
        json.dumps(envelope, indent=1, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return envelope


def age(name: str) -> timedelta | None:
    """Age of the cached copy, or None if there is no usable timestamp."""
    envelope = load(name)
    if not envelope:
        return None
    ts = _parse_ts(envelope.get("fetched_at"))
    return None if ts is None else _now() - ts


def is_fresh(name: str) -> bool:
    """True when the cached copy exists and is younger than its max_age."""
    a = age(name)
    if a is None:
        return False
    return a < MAX_AGE.get(name, timedelta(hours=6))


def refresh(name: str, fetch_fn: Callable[[], Any], force: bool = False) -> Any:
    """Return data for ``name``, fetching only if the cache has expired.

    On fetch failure the previous payload is returned unchanged so a transient
    outage degrades to stale data rather than to an empty panel.
    """
    if not force and is_fresh(name):
        a = age(name)
        print(f"  [SKIP] {name}: cached {_humanize(a)} ago, still fresh")
        envelope = load(name)
        _record(name, ok=True, fetched=False)
        return envelope["data"] if envelope else None

    try:
        data = fetch_fn()
    except NotModified as e:
        # The upstream said its data has not changed. That is a successful
        # outcome, not a failure - keep the cached copy and its original
        # timestamp, and do not mark the source as errored.
        print(f"  [SAME] {name}: {e}")
        _record(name, ok=True, fetched=False)
        envelope = load(name)
        return envelope["data"] if envelope else None
    except Exception as e:  # noqa: BLE001 - any upstream failure must fall back
        print(f"  [FAIL] {name}: {e}")
        _record(name, ok=False, error=f"{type(e).__name__}: {e}")
        envelope = load(name)
        if envelope:
            print(
                f"  [WARN] {name}: serving cached copy from {envelope.get('fetched_at')}"
            )
            return envelope["data"]
        return None

    save(name, data)
    _record(name, ok=True, fetched=True)
    print(f"  [OK]   {name}: refreshed")
    return data


def _humanize(delta: timedelta | None) -> str:
    if delta is None:
        return "never"
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


# --- status ledger -------------------------------------------------------


def _status_path() -> Path:
    return DATA_DIR / "status.json"


def _read_status() -> dict:
    path = _status_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _record(
    name: str, ok: bool, fetched: bool = False, error: str | None = None
) -> None:
    """Update one source's entry in the status ledger."""
    status = _read_status()
    entry = status.get(name, {})
    entry["last_attempt"] = _now().isoformat()
    if ok:
        if fetched:
            entry["last_success"] = _now().isoformat()
        entry.setdefault("last_success", entry.get("last_success"))
        entry["last_error"] = None
    else:
        entry["last_error"] = error
        entry["last_error_at"] = _now().isoformat()
    status[name] = entry
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _status_path().write_text(
        json.dumps(status, indent=1, sort_keys=True), encoding="utf-8"
    )


def status_report() -> dict[str, dict]:
    """Per-source freshness for the page: age, staleness, and last error.

    ``stale`` is deliberately generous - STALE_FACTOR x max_age - so a single
    missed cron run does not paint the page red. It fires when a source has
    genuinely stopped updating.
    """
    status = _read_status()
    report: dict[str, dict] = {}
    for name, max_age in MAX_AGE.items():
        a = age(name)
        entry = status.get(name, {})
        report[name] = {
            "fetched_at": (load(name) or {}).get("fetched_at"),
            "age": _humanize(a),
            "age_seconds": int(a.total_seconds()) if a else None,
            "stale": a is None or a > max_age * STALE_FACTOR,
            "last_error": entry.get("last_error"),
        }
    return report

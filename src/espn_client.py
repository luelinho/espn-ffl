"""HTTP client for ESPN's undocumented Fantasy Football API (v3).

Design notes, mirrored from the FPL project's client:

- Sequential requests only, spaced by a delay — someone else's free service.
- Retries with exponential backoff on transient failures (timeouts, 5xx, 429).
- No retry on 404 — a missing endpoint is a finding, not a failure to paper
  over. 401/403 are reported distinctly too, since for a private league
  they most likely mean the ESPN_S2/ESPN_SWID cookies are wrong or expired,
  not that the resource doesn't exist.
- Never raises on a bad response. Returns a FetchResult so callers can
  record exactly what happened, including the failure.
- Optionally archives every raw response, so parsing can be redone offline
  without re-requesting anything.

Auth: ESPN's private-league endpoints read two cookies, espn_s2 and SWID —
sent as request cookies, not headers. A public league needs neither; this
client sends them whenever they're configured, which is harmless for a
public league too.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests

from . import config


@dataclass
class FetchResult:
    """The complete outcome of one request, success or failure."""

    url: str
    ok: bool
    status_code: Optional[int] = None
    elapsed_ms: Optional[int] = None
    json_body: Optional[Any] = None
    error: Optional[str] = None
    content_type: Optional[str] = None
    attempts: int = 1
    notes: list[str] = field(default_factory=list)

    @property
    def is_json(self) -> bool:
        return self.json_body is not None

    def summary(self) -> str:
        if self.ok:
            return f"HTTP {self.status_code} in {self.elapsed_ms}ms"
        if self.status_code is not None:
            return f"HTTP {self.status_code} — {self.error or 'failed'}"
        return f"no response — {self.error or 'unknown error'}"


class ESPNClient:
    def __init__(
        self,
        delay: float = config.REQUEST_DELAY_SECONDS,
        archive_dir: Optional[Path] = None,
        verbose: bool = True,
    ):
        self.delay = delay
        self.verbose = verbose
        self.archive_dir = archive_dir
        self.request_count = 0
        self._last_request_at = 0.0

        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": config.USER_AGENT, "Accept": "application/json"}
        )
        if config.ESPN_S2 and config.ESPN_SWID:
            self.session.cookies.set("espn_s2", config.ESPN_S2, domain="fantasy.espn.com")
            self.session.cookies.set("SWID", config.ESPN_SWID, domain="fantasy.espn.com")

        if self.archive_dir:
            self.archive_dir.mkdir(parents=True, exist_ok=True)

    # -- internals -------------------------------------------------------

    def _respect_delay(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message, flush=True)

    def _archive(self, path_key: str, body: Any) -> None:
        if not self.archive_dir:
            return
        safe = path_key.strip("/").replace("/", "__") or "root"
        target = self.archive_dir / f"{safe}.json"
        try:
            target.write_text(json.dumps(body, indent=2)[:50_000_000])
        except (TypeError, ValueError, OSError) as exc:
            self._log(f"    (archive failed for {safe}: {exc})")

    # -- public ------------------------------------------------------------

    def get_league(self, league_id: int, season_year: str, views: list[str], archive: bool = True) -> FetchResult:
        """GET a league's data with one or more ?view= params. Never raises."""
        query = "&".join(f"view={v}" for v in views)
        url = f"{config.BASE_URL}/{season_year}/segments/0/leagues/{league_id}?{query}"
        return self._get(url, archive_key=f"league_{league_id}__{'_'.join(views)}", archive=archive)

    def get_season_reference(self, season_year: str, views: list[str], archive: bool = True) -> FetchResult:
        """GET season-wide (not league-scoped) reference data, e.g. real NFL
        pro teams via view=proTeamSchedules. Different URL shape from
        get_league — no /segments/0/leagues/{id} suffix."""
        query = "&".join(f"view={v}" for v in views)
        url = f"{config.BASE_URL}/{season_year}?{query}"
        return self._get(url, archive_key=f"season_ref__{'_'.join(views)}", archive=archive)

    def _get(self, url: str, archive_key: str, archive: bool) -> FetchResult:
        last_error = None
        status = None

        for attempt in range(1, config.MAX_RETRIES + 1):
            self._respect_delay()
            started = time.monotonic()
            try:
                resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT_SECONDS)
                self._last_request_at = time.monotonic()
                self.request_count += 1
                elapsed_ms = int((time.monotonic() - started) * 1000)
                status = resp.status_code
                ctype = resp.headers.get("Content-Type", "")

                if status == 404:
                    return FetchResult(
                        url=url, ok=False, status_code=404,
                        elapsed_ms=elapsed_ms, content_type=ctype,
                        error="not found", attempts=attempt,
                    )

                if status in (401, 403):
                    return FetchResult(
                        url=url, ok=False, status_code=status,
                        elapsed_ms=elapsed_ms, content_type=ctype,
                        error=f"HTTP {status} — likely missing/expired ESPN_S2/ESPN_SWID, "
                              f"or the league is private and no credentials are set",
                        attempts=attempt,
                    )

                if status == 429 or status >= 500:
                    last_error = f"HTTP {status}"
                    if attempt < config.MAX_RETRIES:
                        wait = config.BACKOFF_BASE_SECONDS ** attempt
                        self._log(f"    retry in {wait:.0f}s ({last_error})")
                        time.sleep(wait)
                        continue
                    return FetchResult(
                        url=url, ok=False, status_code=status,
                        elapsed_ms=elapsed_ms, content_type=ctype,
                        error=last_error, attempts=attempt,
                    )

                if status != 200:
                    return FetchResult(
                        url=url, ok=False, status_code=status,
                        elapsed_ms=elapsed_ms, content_type=ctype,
                        error=f"unexpected status {status}", attempts=attempt,
                    )

                try:
                    body = resp.json()
                except ValueError:
                    preview = resp.text[:200].replace("\n", " ")
                    return FetchResult(
                        url=url, ok=False, status_code=status,
                        elapsed_ms=elapsed_ms, content_type=ctype,
                        error="response was not JSON", attempts=attempt,
                        notes=[f"first 200 chars: {preview}"],
                    )

                if archive:
                    self._archive(archive_key, body)

                return FetchResult(
                    url=url, ok=True, status_code=status,
                    elapsed_ms=elapsed_ms, json_body=body,
                    content_type=ctype, attempts=attempt,
                )

            except requests.exceptions.Timeout:
                last_error = "timeout"
            except requests.exceptions.ConnectionError as exc:
                last_error = f"connection error: {exc}"
            except requests.exceptions.RequestException as exc:
                last_error = f"request error: {exc}"

            self._last_request_at = time.monotonic()
            if attempt < config.MAX_RETRIES:
                wait = config.BACKOFF_BASE_SECONDS ** attempt
                self._log(f"    retry in {wait:.0f}s ({last_error})")
                time.sleep(wait)

        return FetchResult(
            url=url, ok=False, status_code=status,
            error=last_error, attempts=config.MAX_RETRIES,
        )

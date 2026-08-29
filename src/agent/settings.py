from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

def _find_root() -> Path:
    """Project root = dir holding config/shifts.yaml: $APP_ROOT, cwd (Docker /app), or the source checkout."""
    import os

    cands = [Path(os.environ["APP_ROOT"])] if os.environ.get("APP_ROOT") else []
    cands += [Path.cwd(), Path(__file__).resolve().parents[2]]
    for c in cands:
        if (c / "config" / "shifts.yaml").is_file():
            return c
    return Path(__file__).resolve().parents[2]


ROOT = _find_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_allowed_group_ids: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    google_service_account_json: str = ""
    sheet_id_map: str = ""
    head_nurse_line_ids: str = ""
    database_url: str = "sqlite:///./agent.db"
    change_ttl_hours: float = 2
    dry_run: bool = False
    log_level: str = "INFO"
    cron_token: str = ""
    roster_layout: str = "table"
    cache_ttl: float = 60        # seconds: sheet metadata / _control / _audit reads
    cache_ttl_roster: float = 10  # seconds: month roster values (kept short — commit re-checks the cells anyway)
    cache_ttl_static: float = 600  # seconds: _staff, _planned, cell colours
    internal_cron: bool = True  # run expire/drift/go-live from inside the process (no external scheduler needed)
    tz: str = "Asia/Bangkok"  # table (PLAN §4) | grid (ER attending week-block sheet)
    clarify_window_min: int = 10
    max_clarify_rounds: int = 2

    @field_validator("openai_model")
    @classmethod
    def _model_required_at_runtime(cls, v: str) -> str:  # never hardcode a model; empty is checked at call time
        return v.strip()

    @property
    def allowed_groups(self) -> set[str]:
        return _csv_set(self.line_allowed_group_ids)

    @property
    def head_nurse_ids(self) -> set[str]:
        return _csv_set(self.head_nurse_line_ids)

    @property
    def sheet_ids(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for part in self.sheet_id_map.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            g, s = part.split(":", 1)
            out[g.strip()] = s.strip()
        return out

    def sheet_id_for(self, group_id: str) -> str | None:
        return self.sheet_ids.get(group_id)

    def service_account_info(self) -> dict:
        raw = self.google_service_account_json.strip()
        if not raw:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON not set")
        if raw.startswith("{"):
            return json.loads(raw)
        return json.loads(Path(raw).read_text(encoding="utf-8"))


def _csv_set(s: str) -> set[str]:
    return {x.strip() for x in s.split(",") if x.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()

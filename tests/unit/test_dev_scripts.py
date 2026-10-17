"""Development scripts must target the local cluster even when a deployment `.env` exists.

Regression for defect D-01 (docs/testing/known-limitations-and-backlog.md): `Settings` also reads
`.env`, whose `DRIKR_MIGRATION_DATABASE_URL` names the Docker host `db`. `scripts/dev-api.sh` set
only `DRIKR_DATABASE_URL`, so `drikr-api migrate` (which uses the owner URL) tried to reach `db`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from drikr_api.config import Settings

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dev-api.sh"
DOCKER_ENV = (
    "DRIKR_MIGRATION_DATABASE_URL=postgresql+psycopg://drikr:owner-password-0123456789@db:5432/drikr\n"
    "DRIKR_DATABASE_URL=postgresql+psycopg://drikr_app:app-password-0123456789@db:5432/drikr\n"
)


def _script_exports() -> dict[str, str]:
    """The script's `export DRIKR_…=value` lines; a value of `$NAME` refers to an earlier export."""
    exports: dict[str, str] = {}
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r'export (DRIKR_[A-Z_]+)="?([^"]*)"?', line.strip())
        if m is None or "${" in m.group(2):  # skip defaults such as ${X:-200}
            continue
        name, value = m.groups()
        exports[name] = exports[value[1:]] if value.startswith("$") else value
    return exports


def test_dev_api_migrates_and_serves_the_local_cluster_despite_a_deployment_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(DOCKER_ENV, encoding="utf-8")
    for key in [k for k in os.environ if k.startswith("DRIKR_")]:
        monkeypatch.delenv(key)
    for key, value in _script_exports().items():
        monkeypatch.setenv(key, value)
    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]
    assert make_url(settings.database_url).host == "127.0.0.1"
    assert make_url(settings.owner_url).host == "127.0.0.1", "migrations would target the Docker host"

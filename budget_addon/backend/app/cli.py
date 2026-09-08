"""Komut satırı araçları.

    python -m app.cli backup
    python -m app.cli seed
    python -m app.cli config
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .config import get_settings
from .database import dispose_engine, get_session_factory
from .services.backup import BackupError, create_backup
from .services.seed import seed_all


def _backup() -> int:
    settings = get_settings()
    try:
        result = create_backup(
            settings.database_path,
            keep=settings.backup_retention,
            timezone_name=settings.timezone,
        )
    except BackupError as exc:
        print(f"Yedekleme başarısız: {exc}", file=sys.stderr)
        return 1
    print(f"Yedek alındı: {result.path} ({result.size_bytes} bayt)")
    if result.removed:
        print(f"Saklama kuralı gereği silinen: {len(result.removed)} eski yedek")
    return 0


def _seed() -> int:
    async def run() -> dict[str, int]:
        settings = get_settings()
        async with get_session_factory()() as session:
            counts = await seed_all(session, settings)
        await dispose_engine()
        return counts

    counts = asyncio.run(run())
    print(f"Başlangıç verisi: {counts}")
    return 0


def _config() -> int:
    """Yapılandırmayı özetler. Bot token gibi sırlar gösterilmez."""
    for key, value in get_settings().safe_summary().items():
        print(f"{key}: {value}")
    return 0


COMMANDS = {"backup": _backup, "seed": _seed, "config": _config}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="Aile Bütçe araçları")
    parser.add_argument("command", choices=sorted(COMMANDS))
    arguments = parser.parse_args(argv)
    return COMMANDS[arguments.command]()


if __name__ == "__main__":
    raise SystemExit(main())

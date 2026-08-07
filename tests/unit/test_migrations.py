import aiosqlite
import pytest

from repositories.migrations import MIGRATIONS, apply_migrations


@pytest.mark.asyncio
async def test_migrations_are_idempotent(tmp_path) -> None:
    conn = await aiosqlite.connect(tmp_path / "scenario.db")
    try:
        latest_version = MIGRATIONS[-1][0]
        assert await apply_migrations(conn) == latest_version
        assert await apply_migrations(conn) == latest_version
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'scenario%'"
        )
        names = {row[0] for row in await cursor.fetchall()}
        assert {"scenarios", "scenario_steps", "scenario_step_versions"} <= names
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_failed_migration_rolls_back(tmp_path) -> None:
    conn = await aiosqlite.connect(tmp_path / "rollback.db")
    broken_version = MIGRATIONS[-1][0] + 1
    broken = (
        *MIGRATIONS,
        (broken_version, ("CREATE TABLE partial_table(id INTEGER)", "INVALID SQL")),
    )
    try:
        with pytest.raises(aiosqlite.OperationalError):
            await apply_migrations(conn, broken)
        cursor = await conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'partial_table'"
        )
        assert await cursor.fetchone() is None
        cursor = await conn.execute("SELECT MAX(version) FROM schema_migrations")
        assert (await cursor.fetchone())[0] == MIGRATIONS[-1][0]
    finally:
        await conn.close()

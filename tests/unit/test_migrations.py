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


@pytest.mark.asyncio
async def test_legacy_sessions_are_migrated_without_changing_source_rows(tmp_path) -> None:
    database = tmp_path / "legacy.db"
    conn = await aiosqlite.connect(database)
    conn.row_factory = aiosqlite.Row
    try:
        await conn.executescript(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY, title TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE task_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, background TEXT, formation TEXT,
                task TEXT, conversation_id TEXT NOT NULL UNIQUE
            );
            INSERT INTO conversations VALUES (
                'legacy-1', 'Legacy operation', '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00'
            );
            INSERT INTO messages(conversation_id, role, content, created_at)
            VALUES ('legacy-1', 'user', 'original prompt', '2026-01-01T00:00:00+00:00');
            INSERT INTO task_configs(background, formation, task, conversation_id)
            VALUES ('legacy background', 'legacy formation', NULL, 'legacy-1');
            """
        )
        await conn.commit()

        assert await apply_migrations(conn) == MIGRATIONS[-1][0]
        assert await apply_migrations(conn) == MIGRATIONS[-1][0]

        cursor = await conn.execute("SELECT COUNT(*), MAX(content) FROM messages")
        assert tuple(await cursor.fetchone()) == (1, "original prompt")
        cursor = await conn.execute("SELECT background, formation, task FROM task_configs")
        assert tuple(await cursor.fetchone()) == (
            "legacy background",
            "legacy formation",
            None,
        )
        cursor = await conn.execute("SELECT id, title FROM scenarios")
        assert tuple(await cursor.fetchone()) == ("legacy-1", "Legacy operation")
        cursor = await conn.execute(
            """
            SELECT step_type, version, output_text FROM scenario_step_versions
            WHERE scenario_id = 'legacy-1' ORDER BY step_type
            """
        )
        assert [tuple(row) for row in await cursor.fetchall()] == [
            ("background", 1, "legacy background"),
            ("formation", 1, "legacy formation"),
        ]
        cursor = await conn.execute("SELECT COUNT(*) FROM legacy_session_migrations")
        assert (await cursor.fetchone())[0] == 1
    finally:
        await conn.close()

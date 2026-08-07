from collections.abc import Sequence
from datetime import datetime, timezone
import logging

import aiosqlite


logger = logging.getLogger("ScenarioAgent")

Migration = tuple[int, Sequence[str]]

MIGRATIONS: tuple[Migration, ...] = (
    (
        1,
        (
            """
            CREATE TABLE scenarios (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                current_step TEXT NOT NULL,
                status TEXT NOT NULL,
                final_output TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE scenario_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_id TEXT NOT NULL,
                step_type TEXT NOT NULL,
                input_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                current_version INTEGER NULL,
                confirmed_version INTEGER NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (scenario_id, step_type),
                FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE scenario_step_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_id TEXT NOT NULL,
                step_type TEXT NOT NULL,
                version INTEGER NOT NULL,
                input_snapshot_json TEXT NOT NULL,
                context_snapshot_json TEXT NOT NULL,
                output_text TEXT NOT NULL,
                sources_json TEXT NOT NULL DEFAULT '[]',
                generation_mode TEXT NOT NULL,
                revision_instruction TEXT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (scenario_id, step_type, version),
                FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE generation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                scenario_id TEXT NOT NULL,
                step_type TEXT NOT NULL,
                status TEXT NOT NULL,
                error_code TEXT NULL,
                error_message TEXT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NULL,
                standard_hit_count INTEGER NOT NULL DEFAULT 0,
                lightrag_fallback INTEGER NOT NULL DEFAULT 0,
                model TEXT NULL,
                duration_ms INTEGER NULL,
                FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX idx_scenario_versions_lookup ON scenario_step_versions(scenario_id, step_type, version)",
            "CREATE INDEX idx_generation_runs_scenario ON generation_runs(scenario_id)",
        ),
    ),
    (
        2,
        (
            "ALTER TABLE generation_runs ADD COLUMN result_version INTEGER NULL",
            "ALTER TABLE generation_runs ADD COLUMN previous_step_status TEXT NULL",
        ),
    ),
    (
        3,
        (
            "ALTER TABLE generation_runs ADD COLUMN request_payload_json TEXT NULL",
        ),
    ),
)


async def _table_counts(conn: aiosqlite.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in ("scenarios", "scenario_steps", "scenario_step_versions", "generation_runs"):
        cursor = await conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        )
        if await cursor.fetchone():
            cursor = await conn.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = (await cursor.fetchone())[0]
    return counts


async def apply_migrations(
    conn: aiosqlite.Connection,
    migrations: Sequence[Migration] = MIGRATIONS,
) -> int:
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    await conn.commit()
    cursor = await conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
    current_version = (await cursor.fetchone())[0]

    for version, statements in migrations:
        if version <= current_version:
            continue
        before = await _table_counts(conn)
        try:
            await conn.execute("BEGIN IMMEDIATE")
            for statement in statements:
                await conn.execute(statement)
            await conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        after = await _table_counts(conn)
        logger.info("Applied schema migration %s; counts before=%s after=%s", version, before, after)
        current_version = version

    return current_version

from collections.abc import Sequence
from datetime import datetime, timezone
import logging
import json

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
    (
        4,
        (
            """
            CREATE TABLE IF NOT EXISTS legacy_session_migrations (
                conversation_id TEXT PRIMARY KEY,
                migrated_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """,
        ),
    ),
    # V5 records the read-time scenario input contract migration. Historical
    # snapshots and generated outputs remain untouched by design.
    (5, ()),
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

    await migrate_legacy_sessions(conn)
    return current_version


async def _table_exists(conn: aiosqlite.Connection, table: str) -> bool:
    cursor = await conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    )
    return await cursor.fetchone() is not None


async def migrate_legacy_sessions(conn: aiosqlite.Connection) -> int:
    """Copy legacy conversations into the scenario model without deleting source rows.

    The operation is deliberately idempotent: a marker is written for every source
    conversation and each generated legacy step uses a unique version key.
    """
    if not await _table_exists(conn, "conversations"):
        return 0
    if not await _table_exists(conn, "legacy_session_migrations"):
        return 0

    cursor = await conn.execute(
        "SELECT id, title, created_at, updated_at FROM conversations ORDER BY created_at"
    )
    conversations = await cursor.fetchall()
    if not conversations:
        return 0

    config_by_conversation: dict[str, dict[str, str | None]] = {}
    if await _table_exists(conn, "task_configs"):
        cursor = await conn.execute(
            "SELECT conversation_id, background, formation, task FROM task_configs"
        )
        for row in await cursor.fetchall():
            config_by_conversation[row["conversation_id"]] = {
                "background": row["background"],
                "formation": row["formation"],
                "task": row["task"],
            }

    migrated = 0
    await conn.execute("BEGIN IMMEDIATE")
    try:
        for conversation in conversations:
            conversation_id = conversation["id"]
            marker = await conn.execute(
                "SELECT 1 FROM legacy_session_migrations WHERE conversation_id = ?",
                (conversation_id,),
            )
            if await marker.fetchone():
                continue

            await conn.execute(
                """
                INSERT OR IGNORE INTO scenarios(
                    id, title, current_step, status, final_output, created_at, updated_at
                ) VALUES (?, ?, 'background', 'active', NULL, ?, ?)
                """,
                (
                    conversation_id,
                    conversation["title"] or "Legacy scenario",
                    conversation["created_at"],
                    conversation["updated_at"],
                ),
            )
            await conn.executemany(
                """
                INSERT OR IGNORE INTO scenario_steps(
                    scenario_id, step_type, input_json, status,
                    current_version, confirmed_version, created_at, updated_at
                ) VALUES (?, ?, '{}', 'empty', NULL, NULL, ?, ?)
                """,
                [
                    (conversation_id, step, conversation["created_at"], conversation["updated_at"])
                    for step in ("background", "formation", "task", "final")
                ],
            )

            configs = config_by_conversation.get(conversation_id, {})
            for step in ("background", "formation", "task"):
                output = configs.get(step)
                if not output:
                    continue
                existing = await conn.execute(
                    """
                    SELECT 1 FROM scenario_step_versions
                    WHERE scenario_id = ? AND step_type = ? AND version = 1
                    """,
                    (conversation_id, step),
                )
                if await existing.fetchone():
                    continue
                await conn.execute(
                    """
                    INSERT INTO scenario_step_versions(
                        scenario_id, step_type, version, input_snapshot_json,
                        context_snapshot_json, output_text, sources_json,
                        generation_mode, revision_instruction, created_at
                    ) VALUES (?, ?, 1, '{}', '{}', ?, '[]', 'generate', NULL, ?)
                    """,
                    (conversation_id, step, output, conversation["updated_at"]),
                )
                await conn.execute(
                    """
                    UPDATE scenario_steps
                    SET status = 'generated', current_version = 1, updated_at = ?
                    WHERE scenario_id = ? AND step_type = ?
                    """,
                    (conversation["updated_at"], conversation_id, step),
                )

            await conn.execute(
                """
                INSERT INTO legacy_session_migrations(conversation_id, migrated_at)
                VALUES (?, ?)
                """,
                (conversation_id, datetime.now(timezone.utc).isoformat()),
            )
            migrated += 1

        await conn.commit()
    except Exception:
        await conn.rollback()
        raise

    if migrated:
        logger.info("Migrated %s legacy conversation(s) into scenario workflow", migrated)
    return migrated

import argparse
import asyncio
import json
from pathlib import Path

from utils.chat_history_handler import AsyncConversationStore


TABLES = (
    "conversations",
    "messages",
    "task_configs",
    "scenarios",
    "scenario_steps",
    "scenario_step_versions",
    "generation_runs",
)


async def inspect_database(database_path: Path) -> dict[str, object]:
    if not database_path.is_file():
        raise FileNotFoundError(database_path)
    store = await AsyncConversationStore.create(str(database_path))
    try:
        cursor = await store.conn.execute("SELECT MAX(version) FROM schema_migrations")
        schema_version = (await cursor.fetchone())[0]
        counts: dict[str, int] = {}
        for table in TABLES:
            cursor = await store.conn.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = (await cursor.fetchone())[0]
        return {"schema_version": schema_version, "counts": counts}
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply and inspect Scenario migrations on an explicit database copy."
    )
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(inspect_database(args.database)), indent=2))


if __name__ == "__main__":
    main()

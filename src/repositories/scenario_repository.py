from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
import uuid

import aiosqlite

from schemas.scenario import GenerationMode, StepStatus, StepType


STEP_ORDER = tuple(StepType)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScenarioRepository:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def create(self, title: str) -> str:
        scenario_id = uuid.uuid4().hex
        now = _now()
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            await self.conn.execute(
                "INSERT INTO scenarios VALUES (?, ?, ?, ?, NULL, ?, ?)",
                (scenario_id, title, StepType.BACKGROUND, "active", now, now),
            )
            await self.conn.executemany(
                """
                INSERT INTO scenario_steps(
                    scenario_id, step_type, input_json, status, created_at, updated_at
                ) VALUES (?, ?, '{}', ?, ?, ?)
                """,
                [
                    (scenario_id, step, StepStatus.EMPTY, now, now)
                    for step in STEP_ORDER
                ],
            )
            await self.conn.commit()
        except Exception:
            await self.conn.rollback()
            raise
        return scenario_id

    async def list(self) -> list[dict[str, Any]]:
        cursor = await self.conn.execute(
            "SELECT * FROM scenarios ORDER BY updated_at DESC"
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get(self, scenario_id: str) -> dict[str, Any] | None:
        cursor = await self.conn.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,))
        scenario = await cursor.fetchone()
        if scenario is None:
            return None
        cursor = await self.conn.execute(
            "SELECT * FROM scenario_steps WHERE scenario_id = ? ORDER BY id",
            (scenario_id,),
        )
        result = dict(scenario)
        result["steps"] = []
        for row in await cursor.fetchall():
            step = dict(row)
            step["input"] = json.loads(step.pop("input_json"))
            result["steps"].append(step)
        return result

    async def get_step(self, scenario_id: str, step: StepType) -> dict[str, Any] | None:
        cursor = await self.conn.execute(
            "SELECT * FROM scenario_steps WHERE scenario_id = ? AND step_type = ?",
            (scenario_id, step),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def save_input(self, scenario_id: str, step: StepType, input_data: dict[str, Any]) -> None:
        current = await self.get_step(scenario_id, step)
        if current is None:
            raise KeyError(scenario_id)
        serialized = json.dumps(input_data, ensure_ascii=False, sort_keys=True)
        if serialized == current["input_json"]:
            return
        now = _now()
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            await self.conn.execute(
                """
                UPDATE scenario_steps
                SET input_json = ?, status = ?, confirmed_version = NULL, updated_at = ?
                WHERE scenario_id = ? AND step_type = ?
                """,
                (serialized, StepStatus.DRAFT, now, scenario_id, step),
            )
            downstream = STEP_ORDER[STEP_ORDER.index(step) + 1 :]
            if current["status"] == StepStatus.CONFIRMED and downstream:
                placeholders = ",".join("?" for _ in downstream)
                await self.conn.execute(
                    f"""
                    UPDATE scenario_steps
                    SET status = ?, confirmed_version = NULL, updated_at = ?
                    WHERE scenario_id = ? AND step_type IN ({placeholders})
                    """,
                    (StepStatus.STALE, now, scenario_id, *downstream),
                )
            await self.conn.execute(
                "UPDATE scenarios SET current_step = ?, updated_at = ? WHERE id = ?",
                (step, now, scenario_id),
            )
            await self.conn.commit()
        except Exception:
            await self.conn.rollback()
            raise

    async def add_version(
        self,
        scenario_id: str,
        step: StepType,
        output_text: str,
        context: dict[str, Any],
        sources: list[dict[str, Any]],
        mode: GenerationMode = GenerationMode.GENERATE,
        revision_instruction: str | None = None,
    ) -> int:
        current = await self.get_step(scenario_id, step)
        if current is None:
            raise KeyError(scenario_id)
        cursor = await self.conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM scenario_step_versions WHERE scenario_id = ? AND step_type = ?",
            (scenario_id, step),
        )
        version = (await cursor.fetchone())[0]
        now = _now()
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            await self.conn.execute(
                """
                INSERT INTO scenario_step_versions(
                    scenario_id, step_type, version, input_snapshot_json,
                    context_snapshot_json, output_text, sources_json,
                    generation_mode, revision_instruction, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scenario_id,
                    step,
                    version,
                    current["input_json"],
                    json.dumps(context, ensure_ascii=False, sort_keys=True),
                    output_text,
                    json.dumps(sources, ensure_ascii=False, sort_keys=True),
                    mode,
                    revision_instruction,
                    now,
                ),
            )
            await self.conn.execute(
                """
                UPDATE scenario_steps SET status = ?, current_version = ?, updated_at = ?
                WHERE scenario_id = ? AND step_type = ?
                """,
                (StepStatus.GENERATED, version, now, scenario_id, step),
            )
            await self.conn.commit()
        except Exception:
            await self.conn.rollback()
            raise
        return version

    async def confirm(self, scenario_id: str, step: StepType, version: int) -> bool:
        now = _now()
        cursor = await self.conn.execute(
            """
            UPDATE scenario_steps SET status = ?, confirmed_version = ?, updated_at = ?
            WHERE scenario_id = ? AND step_type = ? AND current_version = ? AND status = ?
            """,
            (
                StepStatus.CONFIRMED,
                version,
                now,
                scenario_id,
                step,
                version,
                StepStatus.GENERATED,
            ),
        )
        if cursor.rowcount != 1:
            await self.conn.rollback()
            return False
        next_index = STEP_ORDER.index(step) + 1
        current_step = STEP_ORDER[next_index] if next_index < len(STEP_ORDER) else StepType.FINAL
        await self.conn.execute(
            "UPDATE scenarios SET current_step = ?, updated_at = ? WHERE id = ?",
            (current_step, now, scenario_id),
        )
        await self.conn.commit()
        return True

    async def list_versions(self, scenario_id: str, step: StepType) -> list[dict[str, Any]]:
        cursor = await self.conn.execute(
            """
            SELECT * FROM scenario_step_versions
            WHERE scenario_id = ? AND step_type = ? ORDER BY version DESC
            """,
            (scenario_id, step),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def delete(self, scenario_id: str) -> bool:
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            for table in ("generation_runs", "scenario_step_versions", "scenario_steps"):
                await self.conn.execute(f"DELETE FROM {table} WHERE scenario_id = ?", (scenario_id,))
            cursor = await self.conn.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
            await self.conn.execute("DELETE FROM task_configs WHERE conversation_id = ?", (scenario_id,))
            await self.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (scenario_id,))
            await self.conn.execute("DELETE FROM conversations WHERE id = ?", (scenario_id,))
            await self.conn.commit()
            return cursor.rowcount == 1
        except Exception:
            await self.conn.rollback()
            raise

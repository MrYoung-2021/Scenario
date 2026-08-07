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
            """
            SELECT s.*, v.output_text AS current_output,
                   v.sources_json AS current_sources_json,
                   v.created_at AS current_version_created_at
            FROM scenario_steps s
            LEFT JOIN scenario_step_versions v
              ON v.scenario_id = s.scenario_id
             AND v.step_type = s.step_type
             AND v.version = s.current_version
            WHERE s.scenario_id = ?
            ORDER BY s.id
            """,
            (scenario_id,),
        )
        result = dict(scenario)
        result["steps"] = []
        for row in await cursor.fetchall():
            step = dict(row)
            step["input"] = json.loads(step.pop("input_json"))
            sources_json = step.pop("current_sources_json")
            step["current_sources"] = json.loads(sources_json) if sources_json else []
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

    async def get_version(
        self,
        scenario_id: str,
        step: StepType,
        version: int,
    ) -> dict[str, Any] | None:
        cursor = await self.conn.execute(
            """
            SELECT * FROM scenario_step_versions
            WHERE scenario_id = ? AND step_type = ? AND version = ?
            """,
            (scenario_id, step, version),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        for field in ("input_snapshot_json", "context_snapshot_json", "sources_json"):
            result[field.removesuffix("_json")] = json.loads(result.pop(field))
        return result

    async def get_confirmed_context(
        self,
        scenario_id: str,
        steps: tuple[StepType, ...],
    ) -> dict[str, dict[str, Any]]:
        context: dict[str, dict[str, Any]] = {}
        for step in steps:
            cursor = await self.conn.execute(
                """
                SELECT v.* FROM scenario_steps s
                JOIN scenario_step_versions v
                  ON v.scenario_id = s.scenario_id
                 AND v.step_type = s.step_type
                 AND v.version = s.confirmed_version
                WHERE s.scenario_id = ? AND s.step_type = ? AND s.status = ?
                """,
                (scenario_id, step, StepStatus.CONFIRMED),
            )
            row = await cursor.fetchone()
            if row is not None:
                version = dict(row)
                context[str(step)] = {
                    "version": version["version"],
                    "input": json.loads(version["input_snapshot_json"]),
                    "output": version["output_text"],
                    "sources": json.loads(version["sources_json"]),
                }
        return context

    async def get_generation_run(self, request_id: str) -> dict[str, Any] | None:
        cursor = await self.conn.execute(
            "SELECT * FROM generation_runs WHERE request_id = ?",
            (request_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def begin_generation(
        self,
        scenario_id: str,
        step: StepType,
        request_id: str,
        request_payload: dict[str, Any],
        model: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        now = _now()
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = await self.conn.execute(
                "SELECT * FROM generation_runs WHERE request_id = ?",
                (request_id,),
            )
            existing = await cursor.fetchone()
            if existing is not None:
                await self.conn.commit()
                return dict(existing), False

            cursor = await self.conn.execute(
                "SELECT status FROM scenario_steps WHERE scenario_id = ? AND step_type = ?",
                (scenario_id, step),
            )
            step_row = await cursor.fetchone()
            if step_row is None:
                raise KeyError(scenario_id)
            previous_status = step_row["status"]
            if previous_status == StepStatus.GENERATING:
                raise RuntimeError("generation already in progress")

            await self.conn.execute(
                """
                INSERT INTO generation_runs(
                    request_id, scenario_id, step_type, status, started_at,
                    previous_step_status, request_payload_json, model
                ) VALUES (?, ?, ?, 'running', ?, ?, ?, ?)
                """,
                (
                    request_id,
                    scenario_id,
                    step,
                    now,
                    previous_status,
                    json.dumps(request_payload, ensure_ascii=False, sort_keys=True),
                    model,
                ),
            )
            await self.conn.execute(
                """
                UPDATE scenario_steps SET status = ?, updated_at = ?
                WHERE scenario_id = ? AND step_type = ?
                """,
                (StepStatus.GENERATING, now, scenario_id, step),
            )
            await self.conn.commit()
        except Exception:
            await self.conn.rollback()
            raise
        run = await self.get_generation_run(request_id)
        assert run is not None
        return run, True

    async def complete_generation(
        self,
        request_id: str,
        output_text: str,
        context: dict[str, Any],
        sources: list[dict[str, Any]],
        mode: GenerationMode,
        revision_instruction: str | None,
    ) -> int:
        now = _now()
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = await self.conn.execute(
                "SELECT * FROM generation_runs WHERE request_id = ? AND status = 'running'",
                (request_id,),
            )
            run_row = await cursor.fetchone()
            if run_row is None:
                raise RuntimeError("generation run is not active")
            run = dict(run_row)
            scenario_id = run["scenario_id"]
            step = StepType(run["step_type"])
            cursor = await self.conn.execute(
                "SELECT input_json FROM scenario_steps WHERE scenario_id = ? AND step_type = ?",
                (scenario_id, step),
            )
            input_json = (await cursor.fetchone())["input_json"]
            cursor = await self.conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM scenario_step_versions WHERE scenario_id = ? AND step_type = ?",
                (scenario_id, step),
            )
            version = (await cursor.fetchone())[0]
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
                    input_json,
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
                UPDATE scenario_steps
                SET status = ?, current_version = ?, updated_at = ?
                WHERE scenario_id = ? AND step_type = ?
                """,
                (StepStatus.GENERATED, version, now, scenario_id, step),
            )
            if run["previous_step_status"] == StepStatus.CONFIRMED:
                downstream = STEP_ORDER[STEP_ORDER.index(step) + 1 :]
                if downstream:
                    placeholders = ",".join("?" for _ in downstream)
                    await self.conn.execute(
                        f"""
                        UPDATE scenario_steps
                        SET status = ?, confirmed_version = NULL, updated_at = ?
                        WHERE scenario_id = ? AND step_type IN ({placeholders})
                        """,
                        (StepStatus.STALE, now, scenario_id, *downstream),
                    )
            started_at = datetime.fromisoformat(run["started_at"])
            duration_ms = max(
                0,
                int((datetime.fromisoformat(now) - started_at).total_seconds() * 1000),
            )
            await self.conn.execute(
                """
                UPDATE generation_runs
                SET status = 'completed', finished_at = ?, result_version = ?, duration_ms = ?
                WHERE request_id = ?
                """,
                (now, version, duration_ms, request_id),
            )
            if step == StepType.FINAL:
                await self.conn.execute(
                    "UPDATE scenarios SET final_output = ?, status = 'generated', updated_at = ? WHERE id = ?",
                    (output_text, now, scenario_id),
                )
            await self.conn.commit()
            return version
        except Exception:
            await self.conn.rollback()
            raise

    async def fail_generation(
        self,
        request_id: str,
        code: str,
        message: str,
    ) -> None:
        now = _now()
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = await self.conn.execute(
                "SELECT scenario_id, step_type FROM generation_runs WHERE request_id = ? AND status = 'running'",
                (request_id,),
            )
            run = await cursor.fetchone()
            if run is not None:
                cursor = await self.conn.execute(
                    "SELECT started_at FROM generation_runs WHERE request_id = ?",
                    (request_id,),
                )
                started_at = (await cursor.fetchone())["started_at"]
                duration_ms = max(
                    0,
                    int(
                        (
                            datetime.fromisoformat(now)
                            - datetime.fromisoformat(started_at)
                        ).total_seconds()
                        * 1000
                    ),
                )
                await self.conn.execute(
                    """
                    UPDATE generation_runs
                    SET status = 'failed', error_code = ?, error_message = ?,
                        finished_at = ?, duration_ms = ?
                    WHERE request_id = ?
                    """,
                    (code, message, now, duration_ms, request_id),
                )
                await self.conn.execute(
                    """
                    UPDATE scenario_steps SET status = ?, updated_at = ?
                    WHERE scenario_id = ? AND step_type = ? AND status = ?
                    """,
                    (
                        StepStatus.FAILED,
                        now,
                        run["scenario_id"],
                        run["step_type"],
                        StepStatus.GENERATING,
                    ),
                )
            await self.conn.commit()
        except Exception:
            await self.conn.rollback()
            raise

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
        if step == StepType.FINAL:
            await self.conn.execute(
                "UPDATE scenarios SET current_step = ?, status = 'finalized', updated_at = ? WHERE id = ?",
                (current_step, now, scenario_id),
            )
        else:
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
        versions: list[dict[str, Any]] = []
        for row in await cursor.fetchall():
            version = dict(row)
            for field in ("input_snapshot_json", "context_snapshot_json", "sources_json"):
                version[field.removesuffix("_json")] = json.loads(version.pop(field))
            versions.append(version)
        return versions

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

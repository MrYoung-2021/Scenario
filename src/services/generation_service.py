from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
import json
import logging
from time import perf_counter
from typing import Any, Protocol

from repositories.scenario_repository import ScenarioRepository
from schemas.scenario import GenerationMode, GenerationRequest, StepStatus, StepType
from services.scenario_service import PREREQUISITES, ScenarioService, ScenarioServiceError
from utils.logger import log_event


logger = logging.getLogger("ScenarioAgent")


class ScenarioGenerator(Protocol):
    def stream(
        self,
        step: StepType,
        mode: GenerationMode,
        input_data: dict[str, Any],
        confirmed_context: dict[str, Any],
        current_output: str | None = None,
        revision_instruction: str | None = None,
    ) -> AsyncIterator[str | dict[str, Any]]: ...


@dataclass(frozen=True)
class PreparedGeneration:
    scenario_id: str
    step: StepType
    request: GenerationRequest
    input_data: dict[str, Any]
    confirmed_context: dict[str, Any]
    current_output: str | None = None
    replay_run: dict[str, Any] | None = None


class GenerationService:
    def __init__(
        self,
        repository: ScenarioRepository,
        scenario_service: ScenarioService,
        generator: ScenarioGenerator,
    ):
        self.repository = repository
        self.scenario_service = scenario_service
        self.generator = generator

    async def prepare(
        self,
        scenario_id: str,
        step: StepType,
        request: GenerationRequest,
    ) -> PreparedGeneration:
        scenario = await self.scenario_service.get(scenario_id)
        existing = await self.repository.get_generation_run(request.request_id)
        if existing is not None:
            if existing["scenario_id"] != scenario_id or existing["step_type"] != step:
                raise ScenarioServiceError(
                    "REQUEST_ID_CONFLICT",
                    "request_id already belongs to another generation request",
                    409,
                )
            stored_payload = existing.get("request_payload_json")
            current_payload = json.dumps(
                request.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
            )
            if stored_payload is not None and stored_payload != current_payload:
                raise ScenarioServiceError(
                    "REQUEST_ID_CONFLICT",
                    "request_id was reused with a different request payload",
                    409,
                )
            if existing["status"] == "running":
                raise ScenarioServiceError(
                    "GENERATION_IN_PROGRESS",
                    "This generation request is still running",
                    409,
                    request_id=request.request_id,
                )
            return PreparedGeneration(
                scenario_id,
                step,
                request,
                {},
                {},
                replay_run=existing,
            )

        await self.scenario_service.validate_prerequisites(scenario_id, step)
        step_record = next(item for item in scenario["steps"] if item["step_type"] == step)
        if step != StepType.FINAL and not step_record["input"]:
            raise ScenarioServiceError(
                "STEP_INPUT_REQUIRED",
                "Step input must be saved before generation",
                409,
                step=step,
            )
        if step_record["status"] == StepStatus.GENERATING:
            raise ScenarioServiceError(
                "GENERATION_IN_PROGRESS",
                "Another generation request is already running for this step",
                409,
                step=step,
            )
        if request.mode == GenerationMode.GENERATE and step_record["current_version"] is not None:
            raise ScenarioServiceError(
                "GENERATION_MODE_CONFLICT",
                "Use regenerate when a successful version already exists",
                409,
            )
        if request.mode == GenerationMode.REGENERATE and step_record["current_version"] is None:
            raise ScenarioServiceError(
                "GENERATION_MODE_CONFLICT",
                "Regenerate requires an existing successful version",
                409,
            )

        current_output = None
        if request.mode == GenerationMode.REVISE:
            if request.base_version != step_record["current_version"]:
                raise ScenarioServiceError(
                    "VERSION_CONFLICT",
                    "The base version is no longer current",
                    409,
                    version=request.base_version,
                )
            version = await self.repository.get_version(
                scenario_id,
                step,
                request.base_version,
            )
            if version is None:
                raise ScenarioServiceError(
                    "VERSION_NOT_FOUND",
                    "The base version does not exist",
                    404,
                )
            current_output = version["output_text"]

        prerequisites = PREREQUISITES[step]
        confirmed_context = await self.repository.get_confirmed_context(
            scenario_id,
            prerequisites,
        )
        if len(confirmed_context) != len(prerequisites):
            raise ScenarioServiceError(
                "CONFIRMED_CONTEXT_MISSING",
                "Confirmed prerequisite snapshot is incomplete",
                409,
            )
        try:
            _, started = await self.repository.begin_generation(
                scenario_id,
                step,
                request.request_id,
                request.model_dump(mode="json"),
                getattr(self.generator, "model_name", None),
            )
        except RuntimeError as exc:
            raise ScenarioServiceError(
                "GENERATION_IN_PROGRESS",
                "Another generation request is already running for this step",
                409,
                step=step,
            ) from exc
        if not started:
            raise ScenarioServiceError(
                "REQUEST_ID_CONFLICT",
                "request_id was accepted concurrently",
                409,
            )
        return PreparedGeneration(
            scenario_id,
            step,
            request,
            step_record["input"],
            confirmed_context,
            current_output=current_output,
        )

    async def stream_events(
        self,
        prepared: PreparedGeneration,
    ) -> AsyncIterator[dict[str, Any]]:
        replay = prepared.replay_run
        if replay is not None:
            if replay["status"] == "completed":
                yield {
                    "type": "done",
                    "version": replay["result_version"],
                    "status": StepStatus.GENERATED,
                    "replayed": True,
                }
            else:
                yield {
                    "type": "error",
                    "code": replay["error_code"] or "GENERATION_FAILED",
                    "message": replay["error_message"] or "Generation failed",
                    "replayed": True,
                }
            return

        request_id = prepared.request.request_id
        started_at = perf_counter()
        try:
            yield {
                "type": "progress",
                "stage": "retrieval",
                "message": "Preparing confirmed context and knowledge retrieval",
            }
            yield {
                "type": "progress",
                "stage": "generation",
                "message": f"Generating {prepared.step} content",
            }
            chunks: list[str] = []
            sources: list[dict[str, Any]] = []
            async for chunk in self.generator.stream(
                prepared.step,
                prepared.request.mode,
                prepared.input_data,
                prepared.confirmed_context,
                prepared.current_output,
                prepared.request.revision_instruction,
            ):
                if isinstance(chunk, dict):
                    source = chunk.get("source")
                    if not isinstance(source, dict):
                        raise TypeError("Agent source events must contain a source object")
                    sources.append(source)
                    yield {"type": "source", "source": source}
                elif isinstance(chunk, str) and chunk:
                    chunks.append(chunk)
                    yield {"type": "content", "delta": chunk}
                elif not isinstance(chunk, str):
                    raise TypeError("Agent stream chunks must be strings or source events")
            output_text = "".join(chunks).strip()
            if not output_text:
                raise RuntimeError("Agent returned empty content")
            version = await self.repository.complete_generation(
                request_id,
                output_text,
                prepared.confirmed_context,
                sources,
                prepared.request.mode,
                prepared.request.revision_instruction,
            )
            log_event(
                logger,
                logging.INFO,
                "generation_completed",
                scenario_id=prepared.scenario_id,
                step=prepared.step,
                request_id=request_id,
                duration_ms=round((perf_counter() - started_at) * 1000),
            )
            yield {
                "type": "done",
                "version": version,
                "status": StepStatus.GENERATED,
            }
        except asyncio.CancelledError:
            log_event(
                logger,
                logging.WARNING,
                "generation_cancelled",
                scenario_id=prepared.scenario_id,
                step=prepared.step,
                request_id=request_id,
                duration_ms=round((perf_counter() - started_at) * 1000),
            )
            await self.repository.fail_generation(
                request_id,
                "GENERATION_CANCELLED",
                "Generation was interrupted",
            )
            raise
        except Exception:
            logger.exception("Generation failed")
            log_event(
                logger,
                logging.ERROR,
                "generation_failed",
                scenario_id=prepared.scenario_id,
                step=prepared.step,
                request_id=request_id,
                duration_ms=round((perf_counter() - started_at) * 1000),
            )
            await self.repository.fail_generation(
                request_id,
                "GENERATION_FAILED",
                "Generation failed",
            )
            yield {
                "type": "error",
                "code": "GENERATION_FAILED",
                "message": "Generation failed",
            }


async def encode_ndjson(
    events: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[str]:
    async for event in events:
        yield json.dumps(event, ensure_ascii=False) + "\n"

"""Claude client: structured output, prompt caching, and Message Batches.

Structured output takes one of two routes, chosen by model:
- Haiku 4.5 (the extract model): forced tool use, as the spike did.
- Opus 5.5 / Sonnet 5.5 reject forced tool_choice, so they use structured outputs
  (`messages.parse` with a Pydantic model) plus server-side refusal fallbacks.

Pipeline code depends on the `LLM` protocol so tests can swap in a fake.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

FORCED_TOOL_MODELS = ("claude-haiku-4-5",)
FALLBACK_BETA = "server-side-fallback-2026-07-01"
TOOL_NAME = "submit"
POLL_SECONDS = 30


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class Job:
    """One structured request inside a batch or parallel run."""

    custom_id: str
    user: str


class LLM(Protocol):
    def structured(
        self, *, model: str, system: str, user: str, output: type[T], max_tokens: int,
        effort: str | None = None,
    ) -> T: ...

    def many(
        self, *, model: str, system: str, jobs: Sequence[Job], output: type[T], max_tokens: int,
        use_batch: bool = False,
    ) -> dict[str, T | LLMError]: ...


def uses_forced_tool(model: str) -> bool:
    return model.startswith(FORCED_TOOL_MODELS)


def cached_system(system: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


def tool_for(output: type[BaseModel]) -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": "Submit the structured result.",
        "input_schema": output.model_json_schema(),
    }


def forced_tool_params(
    *, model: str, system: str, user: str, output: type[BaseModel], max_tokens: int
) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": cached_system(system),
        "tools": [tool_for(output)],
        "tool_choice": {"type": "tool", "name": TOOL_NAME},
        "messages": [{"role": "user", "content": user}],
    }


def parse_tool_message(message: Any, output: type[T]) -> T:
    if message.stop_reason == "refusal":
        raise LLMError("model declined the request")
    call = next((b for b in message.content if b.type == "tool_use"), None)
    if call is None:
        raise LLMError(f"no tool call (stop_reason={message.stop_reason})")
    try:
        return output.model_validate(call.input)
    except ValidationError as exc:
        raise LLMError(f"tool input failed validation: {exc}") from exc


class ClaudeLLM:
    def __init__(self, client: Any | None = None, concurrency: int = 8) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        self.concurrency = concurrency

    def structured(
        self, *, model: str, system: str, user: str, output: type[T], max_tokens: int,
        effort: str | None = None,
    ) -> T:
        if uses_forced_tool(model):
            params = forced_tool_params(
                model=model, system=system, user=user, output=output, max_tokens=max_tokens
            )
            return parse_tool_message(self.client.messages.create(**params), output)
        response = self.client.beta.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=cached_system(system),
            messages=[{"role": "user", "content": user}],
            output_format=output,
            output_config={"effort": effort or "high"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise LLMError("model and fallbacks declined the request")
        if response.parsed_output is None:
            raise LLMError(f"no parsed output (stop_reason={response.stop_reason})")
        return response.parsed_output

    def many(
        self, *, model: str, system: str, jobs: Sequence[Job], output: type[T], max_tokens: int,
        use_batch: bool = False,
    ) -> dict[str, T | LLMError]:
        if use_batch:
            return self._batch(model=model, system=system, jobs=jobs, output=output,
                               max_tokens=max_tokens)

        def run(job: Job) -> tuple[str, T | LLMError]:
            try:
                return job.custom_id, self.structured(
                    model=model, system=system, user=job.user, output=output,
                    max_tokens=max_tokens,
                )
            except LLMError as exc:
                return job.custom_id, exc

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            return dict(pool.map(run, jobs))

    def _batch(
        self, *, model: str, system: str, jobs: Sequence[Job], output: type[T], max_tokens: int,
    ) -> dict[str, T | LLMError]:
        """Submit through the Message Batches API (50% price) and poll until done.

        Batches reject server-side fallbacks, so only forced-tool models are batched.
        """
        if not uses_forced_tool(model):
            raise LLMError(f"--batch is only supported for {FORCED_TOOL_MODELS}")
        if not jobs:
            return {}
        requests = [
            {
                "custom_id": job.custom_id,
                "params": forced_tool_params(
                    model=model, system=system, user=job.user, output=output,
                    max_tokens=max_tokens,
                ),
            }
            for job in jobs
        ]
        batch = self.client.messages.batches.create(requests=requests)
        print(f"  batch {batch.id} submitted with {len(requests)} requests")
        while (batch := self.client.messages.batches.retrieve(batch.id)).processing_status != "ended":
            counts = batch.request_counts
            print(f"  batch {batch.id}: {counts.processing} processing, {counts.succeeded} done")
            time.sleep(POLL_SECONDS)
        return {
            item.custom_id: self._batch_result(item.result, output)
            for item in self.client.messages.batches.results(batch.id)
        }

    @staticmethod
    def _batch_result(result: Any, output: type[T]) -> T | LLMError:
        if result.type != "succeeded":
            return LLMError(f"batch request {result.type}")
        try:
            return parse_tool_message(result.message, output)
        except LLMError as exc:
            return exc

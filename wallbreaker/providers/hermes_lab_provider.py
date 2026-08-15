from __future__ import annotations

from collections.abc import AsyncIterator

from ..agent.messages import Message, StopEvent, StreamEvent, TextBlock, TextDelta, UsageEvent
from ..hermes_lab import CleanupReceipt, HermesLabEvidence, HermesLabReplica, HermesLabResult
from .base import DEFAULT_TIMEOUT, Provider, ProviderError


class HermesLabProvider(Provider):
    supports_native_prefill = False

    def __init__(self, endpoint, timeout: float = DEFAULT_TIMEOUT) -> None:
        super().__init__(endpoint, timeout=timeout)
        self.last_stop_reason: str | None = None
        self.last_completion_empty = False
        self.last_cleanup: CleanupReceipt | None = None
        self.last_replica_changed = False
        self.last_evidence: HermesLabEvidence | None = None
        self._replicas: set[HermesLabReplica] = set()

    def _validate_request(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        system: str | None,
        max_tokens: int,
        temperature: float | None,
    ) -> str:
        if tools:
            raise ProviderError("Hermes laboratory targets do not accept tools.")
        if system:
            raise ProviderError("Hermes laboratory targets build their own system prompt.")
        if temperature is not None:
            raise ProviderError("Hermes laboratory targets do not accept temperature overrides.")
        if not 1 <= max_tokens <= 8192:
            raise ProviderError("Hermes laboratory max_tokens must be between 1 and 8192.")
        if len(messages) != 1 or messages[0].role != "user":
            raise ProviderError("Hermes laboratory targets accept one user turn only.")
        message = messages[0]
        if (
            len(message.content) != 1
            or not isinstance(message.content[0], TextBlock)
            or message.reasoning
            or message.reasoning_details
        ):
            raise ProviderError("Hermes laboratory targets accept plain text only.")
        return message.content[0].text

    async def _execute(
        self,
        prompt: str,
        max_tokens: int,
        *,
        allowed_state_paths: frozenset[str] = frozenset(),
        observe_tool_attempts: bool = False,
    ) -> HermesLabResult:
        replica = HermesLabReplica(self.endpoint, self.timeout)
        self._replicas.add(replica)
        try:
            result = await replica.execute(
                prompt,
                max_tokens,
                allowed_state_paths=allowed_state_paths,
                observe_tool_attempts=observe_tool_attempts,
            )
        finally:
            self._replicas.discard(replica)
            self.last_cleanup = replica.cleanup_receipt
        self.last_replica_changed = result.replica_changed
        self.last_evidence = result.evidence
        self.last_stop_reason = "end_turn"
        self.last_completion_empty = not result.text
        return result

    async def _run(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        system: str | None,
        max_tokens: int,
        temperature: float | None,
    ):
        prompt = self._validate_request(messages, tools, system, max_tokens, temperature)
        return await self._execute(prompt, max_tokens)

    async def fire(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        allowed_state_paths: frozenset[str] = frozenset(),
    ) -> HermesLabResult:
        prompt = self._validate_request(messages, None, None, max_tokens, None)
        return await self._execute(
            prompt,
            max_tokens,
            allowed_state_paths=allowed_state_paths,
            observe_tool_attempts=True,
        )

    async def complete_with_reasoning(
        self,
        messages: list[Message],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> tuple[str, str]:
        result = await self._run(messages, None, system, max_tokens, temperature)
        return result.text, ""

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float | None = None,
    ) -> AsyncIterator[StreamEvent]:
        result = await self._run(messages, tools, system, max_tokens, temperature)
        yield TextDelta(result.text)
        yield UsageEvent(result.input_tokens, result.output_tokens)
        yield StopEvent("end_turn")

    async def aclose(self) -> None:
        replicas = tuple(self._replicas)
        self._replicas.clear()
        for replica in replicas:
            await replica.close("cancelled")

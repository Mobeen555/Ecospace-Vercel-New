"""A bounded Groq adapter for CrewAI, with session-private task storage."""
from __future__ import annotations

from collections import deque
import hashlib
import math
import threading
import time
from typing import Any

import requests
from pydantic import PrivateAttr

from backend.crew_config import (MAX_LLM_CALLS, MAX_OUTPUT_TOKENS, MAX_INPUT_CHARACTERS,
                         MAX_RUN_SECONDS, DEFAULT_TOKENS_PER_MINUTE)
from crewai import BaseLLM, Crew


class CrewRunError(RuntimeError):
    """A sanitized, user-readable stop; provider response bodies stay private."""


class RunBudget:
    def __init__(self, max_calls=MAX_LLM_CALLS, seconds=MAX_RUN_SECONDS):
        self.max_calls = max_calls
        self.deadline = time.monotonic() + seconds
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.error = ""

    def check(self):
        if self.error:
            raise CrewRunError(self.error)
        if time.monotonic() >= self.deadline:
            self.error = "The AI run reached its time budget. Completed agent notes remain available."
            raise CrewRunError(self.error)
        if self.calls >= self.max_calls:
            self.error = "The AI run reached its request budget. Ask a narrower question."
            raise CrewRunError(self.error)

    def fail(self, message):
        self.error = message
        raise CrewRunError(message)


# One conservative rolling budget per key/model inside this server process.
# Only SHA-256 key digests are held here; actual credentials stay on the LLM instance.
_RATE_LOCK = threading.Lock()
_RATE_BUCKETS = {}


def reserve_rate_slot(key_hash, estimated_tokens, tokens_per_minute, budget, notify=None):
    if estimated_tokens > tokens_per_minute:
        budget.fail("This AI request exceeds the configured token-per-minute budget. Use a narrower question or adjust the budget to your Groq account limit.")
    last_notice = 0.0
    while True:
        budget.check()
        now = time.monotonic()
        with _RATE_LOCK:
            # Remove expired account buckets; no credentials or prompts are stored.
            for old_key in list(_RATE_BUCKETS):
                q = _RATE_BUCKETS[old_key]
                while q and now - q[0][0] >= 61:
                    q.popleft()
                if not q:
                    del _RATE_BUCKETS[old_key]
            queue = _RATE_BUCKETS.setdefault(key_hash, deque())
            if len(queue) < 15 and sum(n for _, n in queue) + estimated_tokens <= tokens_per_minute:
                queue.append((now, estimated_tokens))
                return
            wait = max(.1, 61 - (now - queue[0][0]))
        if notify and now - last_notice > 10:
            notify({"event": "rate_pause", "seconds": round(wait)})
            last_notice = now
        time.sleep(min(1.0, wait))


class GroqEvidenceLLM(BaseLLM):
    """CrewAI's ReAct tool loop uses this adapter's plain text responses.

    Only role/content message fields are sent. No LiteLLM prompt cache metadata,
    implicit OpenAI credentials, arbitrary endpoints or provider-side tools.
    """
    _credential: str = PrivateAttr(default="")
    _budget: Any = PrivateAttr()
    _notify: Any = PrivateAttr(default=None)
    _tokens_per_minute: int = PrivateAttr(default=DEFAULT_TOKENS_PER_MINUTE)
    _key_hash: str = PrivateAttr(default="")

    def __init__(self, key, model, budget=None, notify=None, tokens_per_minute=DEFAULT_TOKENS_PER_MINUTE):
        if not key or not key.strip():
            raise CrewRunError("Set GROQ_API_KEY in your Vercel environment variables.")
        if not model or len(model) > 150 or any(c.isspace() for c in model):
            raise CrewRunError("Enter a valid Groq model ID.")
        super().__init__(model=model, temperature=.1, provider="groq", max_tokens=MAX_OUTPUT_TOKENS)
        self._credential = key.strip()
        self._budget = budget or RunBudget()
        self._notify = notify
        self._tokens_per_minute = max(2000, min(100000, int(tokens_per_minute)))
        self._key_hash = hashlib.sha256((self._credential + "|" + model).encode()).hexdigest()

    def supports_function_calling(self):
        # Tools execute through CrewAI's bounded ReAct executor, not recursive HTTP calls.
        return False

    def supports_stop_words(self):
        return False

    def get_context_window_size(self):
        return 16384

    def call(self, messages, tools=None, callbacks=None, available_functions=None, **kwargs):
        self._budget.check()
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        clean = []
        for message in messages:
            role, content = message.get("role"), message.get("content")
            if role not in ("system", "user", "assistant") or not isinstance(content, str):
                self._budget.fail("The AI framework produced an unsupported message format. Analysis results are preserved.")
            clean.append({"role": role, "content": content})
        characters = sum(len(m["content"]) for m in clean)
        if characters > MAX_INPUT_CHARACTERS:
            self._budget.fail("The AI context is too large for this bounded workflow. Ask a more focused question or analyse fewer modules.")
        estimate = math.ceil(characters / 3.5) + MAX_OUTPUT_TOKENS
        reserve_rate_slot(self._key_hash, estimate, self._tokens_per_minute, self._budget, self._notify)
        self._budget.check()
        self._budget.calls += 1
        if self._notify:
            self._notify({"event": "model_request", "call": self._budget.calls})
        payload = {"model": self.model, "messages": clean, "temperature": .1,
                   "max_completion_tokens": MAX_OUTPUT_TOKENS}
        if self.model in ("openai/gpt-oss-120b", "openai/gpt-oss-20b"):
            payload["reasoning_effort"] = "low"
            payload["reasoning_format"] = "hidden"
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions", json=payload,
                headers={"Authorization": "Bearer " + self._credential, "Content-Type": "application/json"},
                timeout=(8, min(55, max(1, self._budget.deadline - time.monotonic()))),
            )
        except requests.RequestException:
            self._budget.fail("Groq did not respond. The AI review stopped; your environmental results remain available.")
        if response.status_code != 200:
            messages_by_status = {
                401: "Groq rejected the API key. Check the server GROQ_API_KEY setting.",
                403: "The Groq key or model is not permitted for this account.",
                404: "Groq could not find this model. Check the model ID in the AI connection settings.",
                429: "Groq's rate or token limit was reached. Wait before retrying; completed agent notes are preserved.",
            }
            self._budget.fail(messages_by_status.get(response.status_code, f"Groq returned HTTP {response.status_code}. Check model support and account limits; the AI review stopped."))
        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            usage = data.get("usage", {})
            self._budget.prompt_tokens += int(usage.get("prompt_tokens", 0))
            self._budget.completion_tokens += int(usage.get("completion_tokens", 0))
        except (ValueError, KeyError, IndexError, TypeError):
            self._budget.fail("Groq returned an unreadable response. No final review was accepted.")
        if choice.get("finish_reason") == "length":
            self._budget.fail("The model response was cut off by its output budget. Ask a shorter question; no incomplete final report was accepted.")
        if not isinstance(content, str) or not content.strip():
            self._budget.fail("Groq returned no usable answer. Try a more focused question or another supported model.")
        # A model must not invent a tool observation. CrewAI inserts real tool results.
        for marker in ("\nObservation:", *self.stop_sequences):
            if marker and marker in content:
                content = content.split(marker, 1)[0]
        return content.strip()


class SessionTaskOutputs:
    """Disable CrewAI's shared latest-kickoff SQLite log; the UI owns session output."""
    def reset(self):
        pass

    def update(self, task_index, log):
        pass

    def load(self):
        return []


class SessionCrew(Crew):
    # This extension point is covered by tests and pinned to CrewAI 1.15.22.
    _task_output_handler: Any = PrivateAttr(default_factory=SessionTaskOutputs)

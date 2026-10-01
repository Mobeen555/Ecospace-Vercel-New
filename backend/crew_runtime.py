"""A bounded Groq adapter for CrewAI, with session-private task storage."""
from __future__ import annotations

from collections import deque
import hashlib
import json
import math
import re
import threading
import time
from typing import Any

import requests
from pydantic import PrivateAttr

from backend.crew_config import (MAX_LLM_CALLS, MAX_OUTPUT_TOKENS, MAX_INPUT_CHARACTERS,
                         MAX_RUN_SECONDS, DEFAULT_TOKENS_PER_MINUTE, TOOL_NAMES)
from crewai import BaseLLM, Crew


class CrewRunError(RuntimeError):
    """A sanitized, user-readable stop; provider response bodies stay private."""


REACT_REMINDER = ("Reply in plain text only. Do not use native function calls, channels or tool-call syntax. "
                  "Either write 'Thought: ...' then 'Action: <tool name>' then 'Action Input: {json}', "
                  "or write 'Final Answer: ...'.")


def _json_object(text):
    """First balanced JSON object in text, or None."""
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                esc = (ch == "\\" and not esc)
                if ch == '"' and not esc:
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start:i + 1])
                        return value if isinstance(value, dict) else None
                    except ValueError:
                        break
        start = text.find("{", start + 1)
    return None


def recover_tool_call(failed_generation):
    """Turn a Groq ``failed_generation`` into CrewAI ReAct text, or return None.

    gpt-oss sometimes answers a ReAct prompt with a native tool call. Groq then rejects the request
    (400 tool_use_failed) because the adapter declares no ``tools``. The attempted call is still in
    ``failed_generation``; only calls to this app's own three tools are accepted.
    """
    if not isinstance(failed_generation, str) or not failed_generation.strip():
        return None
    text = failed_generation.strip()
    if "Final Answer:" in text:
        return text
    name, args = None, None
    match = (re.search(r"<function=([A-Za-z_][\w]*)\s*>?", text) or
             re.search(r"to=(?:functions\.)?([A-Za-z_][\w]*)", text) or
             re.search(r"^\s*Action:\s*([A-Za-z_][\w]*)", text, re.M))
    if match:
        name = match.group(1)
        args = _json_object(text[match.end():])
    obj = _json_object(text)
    if name is None and obj and isinstance(obj.get("name"), str):
        name, args = obj["name"], obj.get("arguments", obj.get("parameters"))
    elif obj and name in (obj.get("name"),) and args is None:
        args = obj.get("arguments", obj.get("parameters"))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = None
    if name not in TOOL_NAMES:
        return None
    if not isinstance(args, dict):
        args = {}
    return f"Thought: I need the saved evidence before answering.\nAction: {name}\nAction Input: {json.dumps(args)}"


def groq_error(response):
    """(code, retry_after_seconds) from a failed Groq response; never raises, never exposes the body."""
    code, failed = "", ""
    try:
        err = (response.json() or {}).get("error") or {}
        if isinstance(err, dict):
            code = str(err.get("code") or err.get("type") or "")[:60]
            failed = err.get("failed_generation") or ""
    except Exception:
        pass
    retry = None
    try:
        retry = float((getattr(response, "headers", None) or {}).get("retry-after"))
    except (TypeError, ValueError):
        pass
    return code, failed, retry


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
        if wait > budget.deadline - time.monotonic() - 20:
            budget.fail(f"Groq's token-per-minute window is full. Wait about {math.ceil(wait)} seconds, then resume the saved review.")
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
        payload = {"model": self.model, "messages": clean, "temperature": .1,
                   "max_completion_tokens": MAX_OUTPUT_TOKENS}
        if self.model in ("openai/gpt-oss-120b", "openai/gpt-oss-20b"):
            payload["reasoning_effort"] = "low"
            payload["reasoning_format"] = "hidden"
        reminded = waited = False
        while True:
            reserve_rate_slot(self._key_hash, estimate, self._tokens_per_minute, self._budget, self._notify)
            self._budget.check()
            self._budget.calls += 1
            if self._notify:
                self._notify({"event": "model_request", "call": self._budget.calls})
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions", json=payload,
                    headers={"Authorization": "Bearer " + self._credential, "Content-Type": "application/json"},
                    timeout=(8, min(55, max(1, self._budget.deadline - time.monotonic()))),
                )
            except requests.RequestException:
                self._budget.fail("Groq did not respond. The AI review stopped; your environmental results remain available.")
            if response.status_code == 200:
                break
            code, failed, retry_after = groq_error(response)
            if response.status_code == 400 and code == "tool_use_failed":
                # gpt-oss tried a native tool call although none were declared: keep the intended call.
                recovered = recover_tool_call(failed)
                if recovered:
                    return recovered
                if not reminded:
                    reminded = True
                    payload["messages"] = clean + [{"role": "user", "content": REACT_REMINDER}]
                    continue
                self._budget.fail("The model kept attempting a native tool call instead of the required text format. Retry this stage, or set GROQ_MODEL to another supported model.")
            if response.status_code == 429 and not waited and retry_after and retry_after <= 20 and \
                    retry_after < self._budget.deadline - time.monotonic() - 25:
                waited = True
                time.sleep(retry_after + .5)   # one short wait for Groq's own window, then give up
                self._budget.calls -= 1        # a refused request is not a completed model call
                continue
            messages_by_status = {
                400: "Groq rejected the request" + (f" ({code})" if code else "") + ". Check GROQ_MODEL is a supported chat model.",
                401: "Groq rejected the API key. Check the server GROQ_API_KEY setting.",
                403: "The Groq key or model is not permitted for this account.",
                404: "Groq could not find this model. Check the model ID in the AI connection settings.",
                413: "The request is too large for this Groq model or tier. Ask a narrower question.",
                429: "Groq's rate or token limit was reached. Wait a minute, then resume; completed agent notes are preserved.",
                503: "Groq is temporarily over capacity. Resume the saved review in a minute.",
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

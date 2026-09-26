"""Scripted stand-in for the OpenAI-compatible DeepSeek client (no network, no key).

A script is a list of steps; each step is a function ``(messages) -> (content, calls)``
where ``calls`` is a list of ``(tool_name, args_dict)``. The step can read the tool
results already in ``messages``, so the scripted "LLM" reacts to real tool output.
The token counts in ``usage`` are fixed test values, not measurements.
"""
from __future__ import annotations
import json
from types import SimpleNamespace


class _Message:
    def __init__(self, content, calls, step):
        self.content = content
        self.reasoning_content = None
        self.model_extra = {}
        self.tool_calls = [
            SimpleNamespace(id=f"call_{step}_{i}", type="function",
                            function=SimpleNamespace(name=name, arguments=json.dumps(args)))
            for i, (name, args) in enumerate(calls)
        ] or None

    def model_dump(self):
        out = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            out["tool_calls"] = [
                {"id": t.id, "type": "function",
                 "function": {"name": t.function.name, "arguments": t.function.arguments}}
                for t in self.tool_calls]
        return out


class FakeClient:
    def __init__(self, script, prompt_tokens=100, completion_tokens=20):
        self.script = list(script)
        self.requests = []
        self._usage = (prompt_tokens, completion_tokens)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        step = len(self.requests)
        self.requests.append(kwargs)
        if step >= len(self.script):
            raise AssertionError(f"fake LLM script exhausted at call {step}")
        content, calls = self.script[step](kwargs["messages"])
        p, c = self._usage
        return SimpleNamespace(
            choices=[SimpleNamespace(message=_Message(content, calls, step))],
            usage=SimpleNamespace(prompt_tokens=p, completion_tokens=c, total_tokens=p + c))


def tool_result(messages, name):
    """Return the parsed result of the most recent call to tool `name` in `messages`."""
    ids = {}
    for m in messages:
        for tc in (m.get("tool_calls") or []) if isinstance(m, dict) else []:
            ids[tc["id"]] = tc["function"]["name"]
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "tool" and ids.get(m["tool_call_id"]) == name:
            return json.loads(m["content"])
    raise KeyError(f"no result for tool {name!r} in messages")

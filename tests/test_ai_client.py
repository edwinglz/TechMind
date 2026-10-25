"""Live-mode reply handling, with a fake Claude client (no network, no API key)."""

import json
from types import SimpleNamespace

from app.ai import client

VALID = {"summary": "s", "symptom_interpretation": "i", "probable_causes": [
    {"cause": "Carbonator pump failure", "likelihood": "high", "evidence": "e"}],
    "questions_for_reporter": [{"question": "What does the gauge read?", "why": "w", "kind": "reading"}]}


def _reply(text, stop="end_turn"):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
                           usage=SimpleNamespace(input_tokens=10, output_tokens=20))


class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.replies.pop(0)


def test_cut_off_reply_is_asked_again_from_scratch(monkeypatch):
    fake = FakeClient([_reply('{"summary": "too lo', stop="max_tokens"), _reply(json.dumps(VALID))])
    monkeypatch.setattr(client, "_client", lambda: fake)
    brief, tokens_in, tokens_out = client.diagnose("system", "user", None)
    assert brief.questions_for_reporter[0].kind == "reading"
    assert (tokens_in, tokens_out) == (20, 40)
    # The retry doesn't carry the broken half-reply, just a reminder to be shorter.
    retry = fake.calls[1]["messages"]
    assert len(retry) == 1 and "too long" in retry[0]["content"][-1]["text"]


def test_invalid_json_gets_one_correction(monkeypatch):
    fake = FakeClient([_reply("```json\n{not json}\n```"), _reply("Here you go: " + json.dumps(VALID))])
    monkeypatch.setattr(client, "_client", lambda: fake)
    brief, _, _ = client.diagnose("system", "user", None)
    assert brief.probable_causes[0].cause == "Carbonator pump failure"

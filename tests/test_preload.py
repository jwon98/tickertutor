"""Ready-made answers to the Research desk's examples: prepared once per data day, replayed at a readable pace,
recorded in the conversation, shared with anyone who clicks while one is still being prepared."""

from __future__ import annotations

import json
import shutil
import threading
import time

import pytest

from tickertutor import agents, config, data, preload


@pytest.fixture
def examples(fake_llm, demo_db, tmp_path, monkeypatch):
    """A copy of the demo database in its own folder (so the saved answers land there), with preparing turned on."""
    db = tmp_path / "tickertutor.duckdb"
    shutil.copy(demo_db, db)
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setenv("PRELOAD_EXAMPLES", "1")
    data.set_db(db)
    preload._cache.clear()
    preload._jobs.clear()
    preload._failed.clear()
    monkeypatch.setattr(preload, "_loaded_from", None)
    yield fake_llm
    data.set_db(demo_db)
    preload._cache.clear()
    monkeypatch.setattr(preload, "_loaded_from", None)


class Clock:
    """Stands in for time.sleep and time.time, and records how long a replay would have taken."""

    def __init__(self):
        self.t0 = time.time()
        self.total = 0.0

    def __call__(self, s):
        self.total += s

    def now(self):
        return self.t0 + self.total


def _collect(question, session_id=None, sleep=None):
    events = []
    clock = sleep or Clock()
    assert preload.stream(question, session_id, events.append, sleep=clock, now=clock.now)
    return events


def test_all_examples_are_prepared_saved_and_valid_for_this_data_day(examples):
    s = preload.warm(wait=60)
    assert s["ready"] == [q for q, _ in preload.EXAMPLES] and not s["preparing"]
    saved = json.loads((config.DB_PATH.parent / preload.FILE_NAME).read_text(encoding="utf-8"))
    as_of = data.db().meta()["as_of"]
    assert len(saved["examples"]) == len(preload.EXAMPLES)
    assert all(e["as_of"] == as_of and e["model"] == config.GEMINI_MODEL for e in saved["examples"])
    nvda = next(e for e in saved["examples"] if "Nvidia" in e["question"])
    assert "plan" in [ev["type"] for _, ev in nvda["events"]][:2] and nvda["events"][-1][1]["type"] == "done"
    assert preload.warm(wait=5)["ready"] == s["ready"]                  # nothing more to do
    assert preload._warm_thread is None or not preload._warm_thread.is_alive()
    # A new data day (or another model) makes them stale, and they're prepared again.
    preload._cache[preload.key(preload.EXAMPLES[0][0])]["as_of"] = "2000-01-01"
    assert preload.EXAMPLES[0][0] in preload.status()["waiting"]


def test_clicking_a_ready_example_replays_every_step_in_about_ten_seconds(examples):
    preload.warm(wait=60)
    q = "Why is Nvidia down so much lately?"
    clock = Clock()
    events = _collect(q, sleep=clock)
    kinds = [e["type"] for e in events]
    assert "plan" in kinds[:2] and "researcher_start" in kinds and "tool_call" in kinds and "writing" in kinds
    assert kinds[-1] == "done" and kinds.count("done") == 1
    assert preload.REPLAY_MIN - 0.5 <= clock.total <= preload.REPLAY_MAX + 0.5
    done = events[-1]
    assert done["prepared"]["as_of"] == data.db().meta()["as_of"] and done["prepared"]["seconds"] is not None
    assert any(c["name"] == "get_price_move" for c in done["tool_calls"])
    # The answer is part of the conversation, so a follow-up works like after any other answer.
    session = agents.sessions.get(done["session_id"])
    assert session["turns"][-1]["user"] == q and session["turns"][-1]["assistant"] == done["response"]
    follow = agents.answer("How does that compare over five years?", done["session_id"])
    assert follow["session_id"] == done["session_id"] and len(session["turns"]) == 2


def test_two_visitors_get_separate_conversations(examples):
    preload.warm(wait=60)
    q = preload.EXAMPLES[0][0]
    a, b = _collect(q)[-1], _collect(q)[-1]
    assert a["session_id"] != b["session_id"]
    assert len(agents.sessions.get(a["session_id"])["turns"]) == 1


def test_the_clarifying_example_stays_quick_and_remembers_the_question(examples):
    preload.warm(wait=60)
    clock = Clock()
    events = _collect("What should I buy?", sleep=clock)
    plan = next(e for e in events if e["type"] == "plan")
    assert plan["plan"]["action"] == "clarify" and clock.total <= preload.REPLAY_QUICK + 0.5
    session = agents.sessions.get(events[-1]["session_id"])
    assert session["pending"]["question"] == "What should I buy?"
    reply = agents.answer("Dividend payers", events[-1]["session_id"])
    assert any(c["name"] == "screen_stocks" for c in reply["tool_calls"])


def test_clicking_while_it_is_being_prepared_follows_that_same_run(examples, monkeypatch):
    q = "Does buying the dip work for S&P 500 stocks? What has happened after big one-day drops?"
    gate = threading.Event()
    real_run = agents.Run.run
    runs = []

    def slow(self):
        runs.append(self.question)
        gate.wait(5)
        return real_run(self)

    monkeypatch.setattr(agents.Run, "run", slow)
    out = []
    t = threading.Thread(target=lambda: out.append(_collect(q)))
    t.start()
    time.sleep(0.2)
    second = []
    t2 = threading.Thread(target=lambda: second.append(_collect(q)))
    t2.start()
    time.sleep(0.2)
    gate.set()
    t.join(30)
    t2.join(30)
    assert out[0][-1]["type"] == "done" and second[0][-1]["type"] == "done"
    assert out[0][-1]["response"] == second[0][-1]["response"]
    assert out[0][-1]["session_id"] != second[0][-1]["session_id"]
    assert runs == [q]                                                      # one run, two viewers
    assert preload.ready(q) is not None and preload.key(q) not in preload._jobs


def test_failed_runs_are_not_saved_and_wait_before_trying_again(examples, monkeypatch):
    def broken(self):
        raise agents.llm.LLMError("Vertex AI said: quota exceeded")

    monkeypatch.setattr(agents.Run, "run", broken)
    s = preload.warm(wait=30)
    assert s["ready"] == [] and not (config.DB_PATH.parent / preload.FILE_NAME).exists()
    events = []
    clock = Clock()
    assert preload.stream("Why is Nvidia down so much lately?", None, events.append, sleep=clock, now=clock.now)
    assert events[-1]["type"] == "error" and "quota" in events[-1]["error"]
    assert preload._missing() == []                                         # not retried right away


def test_other_questions_and_demo_data_are_answered_live(fake_llm, monkeypatch):
    monkeypatch.delenv("PRELOAD_EXAMPLES", raising=False)
    assert preload.auto_enabled() is False                                  # the demo data is synthetic
    assert preload.stream("How volatile is KO?", None, lambda e: None) is False
    assert preload.stream("Why is Nvidia down so much lately?", None, lambda e: None) is False
    assert preload.is_example("  why is NVIDIA down so much lately ") is True


def test_chat_endpoints_use_ready_answers(examples):
    from fastapi.testclient import TestClient

    import app as app_module

    preload.warm(wait=60)
    c = TestClient(app_module.app)
    ex = c.get("/api/research/examples").json()["examples"]
    assert [x["q"] for x in ex] == [q for q, _ in preload.EXAMPLES] and all(x["ready"] for x in ex)
    q = preload.EXAMPLES[1][0]
    body = c.post("/chat", json={"message": q}).json()
    assert set(body) >= {"response", "session_id", "tool_calls"} and all("agent" in t for t in body["tool_calls"])
    assert c.get(f"/api/chat/{body['session_id']}").json()["turns"][0]["user"] == q
    assert c.post("/api/research/preload").json()["ready"]

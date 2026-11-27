"""Python 与 Java 的行为对照：事件序列、工具回环、注入、BUSY/取消、重放。"""

import httpx

from helpers import create_run, create_session, messages, stream_events, wait_run

PAIR = ("python_client", "java_client")


def _both(request, name: str):
    return request.getfixturevalue(name)


def test_text_run_behaviour(request) -> None:
    results = {}
    for name in PAIR:
        client = _both(request, name)
        session_id = create_session(client, f"parity-text-{name}")
        run = create_run(client, session_id, "请简短回复")
        events = stream_events(client, run["id"])
        final = wait_run(client, run["id"])
        results[name] = {
            "events": events,
            "status": final["status"],
            "kinds": [item["kind"] for item in messages(client, session_id)],
            "step_count": final["step_count"],
        }

    py, java = results["python_client"], results["java_client"]
    assert py["status"] == java["status"] == "succeeded"
    assert py["events"] == java["events"], (py["events"], java["events"])
    assert py["kinds"] == java["kinds"]
    assert py["step_count"] == java["step_count"]


def test_tool_loop_behaviour(request) -> None:
    results = {}
    for name in PAIR:
        client = _both(request, name)
        workspace = client.post("/api/v1/workspaces", json={"name": f"parity-tool-{name}"})
        assert workspace.status_code in {200, 201}, workspace.text
        workspace_id = workspace.json()["id"]
        session_id = create_session(client, f"parity-tool-{name}")
        bound = client.post(
            f"/api/v1/sessions/{session_id}/workspace",
            json={"workspace_id": workspace_id},
        )
        assert bound.status_code == 200, bound.text
        run = create_run(client, session_id, "[[tool:file_list]] 列出文件")
        events = stream_events(client, run["id"])
        final = wait_run(client, run["id"])
        calls = client.get(f"/api/v1/runs/{run['id']}/tool-calls")
        assert calls.status_code == 200, calls.text
        items = calls.json()["items"]
        results[name] = {
            "events": events,
            "status": final["status"],
            "tools": [(item["tool_name"], item["status"]) for item in items],
        }

    py, java = results["python_client"], results["java_client"]
    assert py["status"] == java["status"] == "succeeded"
    assert py["events"] == java["events"], (py["events"], java["events"])
    assert py["tools"] == java["tools"], (py["tools"], java["tools"])
    assert any(tool[0] == "file_list" and tool[1] == "succeeded" for tool in py["tools"])


def test_skill_injection_behaviour(request) -> None:
    results = {}
    for name in PAIR:
        client = _both(request, name)
        session_id = create_session(client, f"parity-skill-{name}")
        run = create_run(client, session_id, "按技能回答", skill_name="prism-demo")
        stream_events(client, run["id"])
        wait_run(client, run["id"])
        results[name] = [item["kind"] for item in messages(client, session_id)]

    assert results["python_client"] == results["java_client"]
    assert results["python_client"][:2] == ["skill_context", "text"]


def test_busy_and_cancel_behaviour(request) -> None:
    results = {}
    for name in PAIR:
        client = _both(request, name)
        session_id = create_session(client, f"parity-busy-{name}")
        slow = create_run(client, session_id, "[[slow]] 等待")
        second = create_run(client, session_id, "再来一次", expect=409)
        cancelled = client.post(f"/api/v1/runs/{slow['id']}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        final = wait_run(client, slow["id"])
        results[name] = {
            "busy_code": second["error"]["code"],
            "status": final["status"],
            "events": stream_events(client, slow["id"]),
        }

    py, java = results["python_client"], results["java_client"]
    assert py["busy_code"] == java["busy_code"]
    assert py["status"] == java["status"] == "cancelled"
    assert "run.cancelled" in py["events"] and "run.cancelled" in java["events"]
    assert py["events"] == java["events"], (py["events"], java["events"])


def test_event_replay_behaviour(request) -> None:
    results = {}
    for name in PAIR:
        client = _both(request, name)
        session_id = create_session(client, f"parity-replay-{name}")
        run = create_run(client, session_id, "请简短回复")
        stream_events(client, run["id"])
        wait_run(client, run["id"])
        replay = client.get(
            f"/api/v1/runs/{run['id']}/events",
            headers={"Last-Event-ID": "0"},
        )
        assert replay.status_code == 200, replay.text
        ids = []
        types = []
        name_line = None
        for line in replay.text.splitlines():
            if line.startswith("id:"):
                ids.append(int(line[3:].strip()))
            elif line.startswith("event:"):
                name_line = line[6:].strip()
                types.append(name_line)
        results[name] = {"ids": ids, "types": types}

    py, java = results["python_client"], results["java_client"]
    assert py["types"] == java["types"]
    assert py["ids"] == sorted(py["ids"]) and java["ids"] == sorted(java["ids"])
    assert py["ids"][-1] == max(py["ids"]) and java["ids"][-1] == max(java["ids"])


def test_context_usage_behaviour(request) -> None:
    results = {}
    for name in PAIR:
        client = _both(request, name)
        session_id = create_session(client, f"parity-ctx-{name}")
        run = create_run(client, session_id, "请简短回复")
        stream_events(client, run["id"])
        wait_run(client, run["id"])
        body = client.get(f"/api/v1/sessions/{session_id}/context").json()
        results[name] = body

    py, java = results["python_client"], results["java_client"]
    assert py["budget_tokens"] == java["budget_tokens"]
    assert py["used_tokens"] > 0 and java["used_tokens"] > 0
    assert abs(py["percent"] - java["percent"]) <= 10

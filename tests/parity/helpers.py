"""行为 parity 的通用操作。"""

import time

import httpx

TERMINAL = {"run.completed", "run.failed", "run.cancelled"}


def create_session(client: httpx.Client, title: str) -> str:
    response = client.post("/api/v1/sessions", json={"title": title})
    assert response.status_code in {200, 201}, response.text
    return response.json()["id"]


def create_run(
    client: httpx.Client,
    session_id: str,
    text: str,
    *,
    skill_name: str | None = None,
    expect: int = 202,
) -> dict:
    payload: dict[str, object] = {"input": text}
    if skill_name is not None:
        payload["skill_name"] = skill_name
    response = client.post(f"/api/v1/sessions/{session_id}/runs", json=payload)
    assert response.status_code == expect, response.text
    return response.json()


def stream_events(client: httpx.Client, run_id: str) -> list[str]:
    """从事件 0 重放并读到终态，返回事件类型序列。"""
    events: list[str] = []
    with client.stream(
        "GET",
        f"/api/v1/runs/{run_id}/events",
        headers={"Last-Event-ID": "0"},
        timeout=60.0,
    ) as response:
        assert response.status_code == 200, response.text
        name = None
        for line in response.iter_lines():
            if not line:
                if name is not None:
                    events.append(name)
                    if name in TERMINAL:
                        break
                name = None
                continue
            if line.startswith("event:"):
                name = line[6:].strip()
    return events


def wait_run(client: httpx.Client, run_id: str, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/v1/runs/{run_id}").json()
        if body["status"] in {"succeeded", "failed", "cancelled"}:
            return body
        time.sleep(0.3)
    raise AssertionError(f"Run 未在 {timeout}s 内终止: {run_id}")


def messages(client: httpx.Client, session_id: str) -> list[dict]:
    response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert response.status_code == 200, response.text
    return response.json()["items"]

"""零依赖模型桩：确定性 OpenAI-compatible SSE，供行为 parity 与 E2E 使用。

场景由最后一条 user 内容中的关键字决定（优先于 X-Mock-Scenario）：
- `[[tool:file_list]]`：首次请求返回 file_list 工具调用；带 tool 结果后返回最终文本
- `[[tool:file_write]]`：同上，参数 {"path": "parity.txt", "content": "hello"}
- `[[slow]]`：先等待 6 秒再返回文本（用于取消/ BUSY）
- 其它：返回文本“你好”

用法：python3 tests/mock-model/server.py --host 0.0.0.0 --port 19000
"""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TEXT = [
    {"choices": [{"delta": {"content": "你"}}]},
    {"choices": [{"delta": {"content": "好"}, "finish_reason": None}]},
    {
        "choices": [{"delta": {}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    },
]


def _last_user_text(body: dict) -> str:
    for message in reversed(body.get("messages", [])):
        if message.get("role") == "user":
            content = message.get("content")
            return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return ""


def _has_tool_result(body: dict) -> bool:
    return any(message.get("role") == "tool" for message in body.get("messages", []))


def _tool_chunks(name: str) -> list[dict]:
    if name == "file_write":
        arguments = json.dumps({"path": "parity.txt", "content": "hello"}, ensure_ascii=False)
    else:
        arguments = "{}"
    return [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_parity",
                                "function": {"name": name, "arguments": arguments},
                            }
                        ]
                    }
                }
            ]
        },
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]


def chunks_for(header_scenario: str, body: dict) -> list[dict]:
    text = _last_user_text(body)
    scenario = header_scenario or "text"
    for name in ("file_list", "file_write"):
        if f"[[tool:{name}]]" in text:
            if _has_tool_result(body):
                return TEXT
            return _tool_chunks(name)
    if "[[slow]]" in text or scenario == "slow":
        time.sleep(6)
    return TEXT


class Handler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server 约定
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        scenario = self.headers.get("X-Mock-Scenario", "")
        Handler.requests.append(
            {"path": self.path, "body": body, "scenario": scenario, "prompt": _last_user_text(body)}
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in chunks_for(scenario, body):
            self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=19000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"mock model listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

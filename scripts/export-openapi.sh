#!/usr/bin/env bash
set -euo pipefail
# 从 Python 后端导出 OpenAPI 快照；不启动服务，直接用 create_app()。
cd "$(dirname "$0")/.."
mkdir -p contracts/openapi
uv run --project backend python - <<'PY'
import pathlib

import yaml

from prism_agent_kit.main import create_app

spec = create_app().openapi()
path = pathlib.Path("contracts/openapi/prism-agent-api.yaml")
path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(f"wrote {path} ({len(spec.get('paths', {}))} paths)")
PY

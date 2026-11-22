import hashlib
import json

from pydantic import JsonValue


def canonical_json_digest(value: JsonValue) -> str:
    """对 JSON 值生成与键顺序无关的稳定摘要。"""
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"

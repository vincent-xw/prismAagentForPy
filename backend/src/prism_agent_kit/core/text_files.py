"""文本文件的边界安全解码工具。"""


def decode_utf8_prefix(raw: bytes) -> str:
    """解码可能被字节截断的 UTF-8 前缀，最多回退 3 个字节保证不切断汉字。"""
    trimmed = raw
    for _ in range(4):
        try:
            return trimmed.decode("utf-8")
        except UnicodeDecodeError:
            if not trimmed:
                raise
            trimmed = trimmed[:-1]
    return trimmed.decode("utf-8", errors="replace")

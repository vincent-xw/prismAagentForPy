from pydantic import BaseModel

from prism_agent_kit.core.errors import AgentKitError, ErrorCode


class Prompt(BaseModel):
    """带显式版本号的系统提示词。"""

    name: str
    version: str
    content: str

    @property
    def ref(self) -> str:
        """返回 name@version 形式的引用。"""
        return f"{self.name}@{self.version}"


class PromptRegistry:
    """进程内 Prompt 注册表。不接受省略版本号的查找。"""

    def __init__(self) -> None:
        self._prompts: dict[tuple[str, str], Prompt] = {}

    def register(self, *, name: str, version: str, prompt: str) -> Prompt:
        """注册固定版本。同名同版本重复注册会失败。"""
        if not name or not version:
            raise AgentKitError(
                ErrorCode.INVALID_PROMPT_REF,
                "Prompt 名称和版本不能为空",
                http_status=400,
            )
        key = (name, version)
        if key in self._prompts:
            raise AgentKitError(
                ErrorCode.INVALID_PROMPT_REF,
                "Prompt 版本已注册",
                http_status=400,
                details={"prompt_ref": f"{name}@{version}"},
            )
        registered = Prompt(name=name, version=version, content=prompt)
        self._prompts[key] = registered
        return registered

    def get(self, *, name: str, version: str) -> Prompt:
        """按名称和版本读取 Prompt。"""
        prompt = self._prompts.get((name, version))
        if prompt is None:
            raise AgentKitError(
                ErrorCode.PROMPT_NOT_FOUND,
                "Prompt 版本不存在",
                http_status=404,
                details={"prompt_ref": f"{name}@{version}"},
            )
        return prompt

    def get_by_ref(self, ref: str) -> Prompt:
        """按 name@version 读取 Prompt。缺少版本号时直接拒绝。"""
        name, separator, version = ref.partition("@")
        if not separator or not name or not version or "@" in version:
            raise AgentKitError(
                ErrorCode.INVALID_PROMPT_REF,
                "prompt_ref 必须使用 name@version 格式",
                http_status=400,
                details={"prompt_ref": ref},
            )
        return self.get(name=name, version=version)

# Phase 3b-1 实施计划：模型档案与 UI 凭据（Python + Java）

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让模型密钥可以在 UI 配置并落库，配完后不再依赖 `MODEL_API_KEY` 环境变量；Python 与 Java 两端提供同一份 `/model-profiles` 契约（v1.2）。

**Architecture:** `model_profiles` 增加可空 `api_key` 列；密钥解析顺序为“库内 → `api_key_env` 环境变量 → 422”。接口只读 `has_key`，永不回显密钥。Java 复用同一语义，并在创建 Run 时快照档案字段。

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy + Alembic；Java 21 + Spring Boot 3.5 + MyBatis-Plus + Flyway；UI Vue 3 + zod；契约测试 pytest + httpx。

**Spec:** `docs/superpowers/specs/2026-11-27-java-runtime-v14-parity-phase3b-design.md`

## Global Constraints

- 密钥**只**出现在数据库列与内存中；任何 API 响应、日志、SSE、错误 details、轨迹都不得包含它。
- 对外只暴露 `has_key: bool`；`api_key` 是只写入字段。
- PATCH 语义：字段省略 = 不修改；`api_key: ""` = 清除；`api_key: "..."` = 覆盖。
- 保留环境变量回退：库内为空时用 `api_key_env` 指向的环境变量，读不到 → 422 `MODEL_PROFILE_INVALID`。
- `MODEL_TOKEN_ENCODING`：无档案时必须显式配置；有激活档案且未配置时默认 `cl100k_base`。
- 契约扩展 v1.2：path/operation 数量不变，只新增字段；Python 与 Java 必须同时实现。
- 不改动 Run/SSE 的既有字段与事件；不改压缩/轨迹算法。
- 质量门槛：`backend` 的 ruff/mypy/pytest；`backend-java` 的 `./mvnw verify`；UI 的 `pnpm check && pnpm test`。

## Review Focus

1. **密钥泄漏**：响应体、错误 details、日志、`probe` 失败信息里出现 `sk-...` —— 在 Task 1/5 的断言里钉住。
2. **PATCH 丢密钥**：编辑档案时只改 model 却把 key 清空 —— 在 Task 1/5 的“省略不修改”用例里钉住。
3. **优先级错**：库内 key 存在却仍去读 env，或 env 缺失时报 500 而不是 422 —— 在 Task 2/6 钉住。
4. **迁移不可逆**：Alembic/Flyway 的 downgrade/undo 未写或与 upgrade 不对称 —— 在 Task 1/5 的迁移往返里钉住。
5. **契约漂移**：Java 的 `has_key` 类型/命名与 Python 不一致，UI zod 直接拒绝 —— 在 Task 4/7 的契约测试里钉住。

---

## 文件结构

```text
backend/
├── migrations/versions/20261127_0008_profile_api_key.py   # 新增
├── src/prism_agent_kit/
│   ├── api/schemas.py                # ModelProfileCreate.api_key, ModelProfileView.has_key
│   ├── api/routes/model_profiles.py  # 透传 api_key；probe 用库内 key
│   ├── application/model_profile_service.py
│   ├── application/provider_factory.py
│   ├── application/run_service.py    # 预检改用库内 key
│   ├── application/container.py      # encoding 默认
│   ├── core/models.py                # ModelProfile.api_key
│   └── db/{models,mappers,repositories/model_profiles}.py
└── tests/application/test_model_profile_credentials.py     # 新增

backend-java/src/main/
├── resources/db/migration/V3__model_profiles.sql           # 新增
├── java/com/prism/agent/{api/dto,api/controller,application/service,persistence}/...
└── application/engine/SimpleAgentEngine.java（改用 ProviderResolver）

ui/src/
├── lib/api/contracts.ts              # has_key / api_key
├── lib/api/client.ts                 # 无需改（泛型透传）
└── features/models/{models.ts,ModelProfilesPage.vue}

tests/contract/test_model_profiles.py # 新增（两端共用）
contracts/openapi/prism-agent-api.yaml
docs/compatibility/feature-parity.md
```

---

### Task 1: Python 存储与 API 扩展

**Files:**
- Create: `backend/migrations/versions/20261127_0008_profile_api_key.py`
- Modify: `backend/src/prism_agent_kit/core/models.py`、`db/models.py`、`db/mappers.py`、`db/repositories/model_profiles.py`
- Modify: `backend/src/prism_agent_kit/application/model_profile_service.py`
- Modify: `backend/src/prism_agent_kit/api/schemas.py`、`api/routes/model_profiles.py`
- Test: `backend/tests/application/test_model_profile_credentials.py`

**Interfaces:**
- Consumes: 现有 `ModelProfileService`、`ModelProfileView`
- Produces:
  - `ModelProfile.api_key: str | None`
  - `ModelProfileInput.api_key: str | None`，`ModelProfileCreate.api_key: str | None`
  - `ModelProfileView.has_key: bool`（`= bool(profile.api_key) or bool(os.environ.get(profile.api_key_env))`）
  - `ModelProfileService.update(..., api_key: str | None | Unset)`：用哨兵区分“省略”与“清空”

- [ ] **Step 1: 写失败测试**

```python
async def test_create_with_api_key_never_returns_it(service, client):
    response = await client.post("/api/v1/model-profiles", json={
        "name": "p1", "base_url": "https://api.example.com/v1", "model": "m",
        "api_key_env": "DEEPSEEK_API_KEY", "api_key": "sk-secret",
        "context_window": 8192, "max_output_tokens": 1024,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["has_key"] is True
    assert "api_key" not in body
    assert "sk-secret" not in response.text

async def test_patch_without_api_key_keeps_existing_key(service, client):
    created = await create_profile(client, api_key="sk-secret")
    patched = await client.patch(f"/api/v1/model-profiles/{created['id']}", json={
        "name": "p1", "base_url": "https://api.example.com/v1", "model": "m2",
        "api_key_env": "DEEPSEEK_API_KEY", "context_window": 8192, "max_output_tokens": 1024,
    })
    assert patched.json()["has_key"] is True

async def test_patch_with_empty_api_key_clears_it(service, client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    created = await create_profile(client, api_key="sk-secret")
    patched = await client.patch(..., json={..., "api_key": ""})
    assert patched.json()["has_key"] is False
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/application/test_model_profile_credentials.py -q`
Expected: FAIL —— `api_key` 不是合法字段 / 响应无 `has_key`

- [ ] **Step 3: 实现**

- Alembic：`add_column("model_profiles", sa.Column("api_key", sa.Text(), nullable=True))`；downgrade `drop_column`。
- `ModelProfileRow` / Pydantic `ModelProfile` 加 `api_key`；mapper 双向映射。
- `ModelProfileInput/ Create` 加 `api_key: str | None = None`，校验非空时 `strip()` 后不得以空白开头结尾。
- `ModelProfileView` 加 `has_key`；`_to_view` 计算时**不读取** key 值以外的任何信息。
- `update`：`api_key` 用 `UNSET` 哨兵；省略→保持，`""`→写 NULL，其他→覆盖。
- 路由 `probe`：先 `factory.build(profile)`（Task 2 会改成优先用库内 key）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/application/test_model_profile_credentials.py -q && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: PASS；迁移往返成功

- [ ] **Step 5: 提交** `git commit -am "feat(backend): 模型档案支持 UI 配置密钥（只读 has_key）"`

---

### Task 2: Python 密钥优先级与 encoding 默认

**Files:**
- Modify: `backend/src/prism_agent_kit/application/provider_factory.py`
- Modify: `backend/src/prism_agent_kit/application/run_service.py`
- Modify: `backend/src/prism_agent_kit/application/container.py`
- Test: `backend/tests/application/test_model_profile_credentials.py`（追加）

**Interfaces:**
- Produces: `ProviderFactory.build(profile)` 读取顺序 `profile.api_key` → `os.environ[profile.api_key_env]` → `AgentKitError(MODEL_PROFILE_INVALID, 422)`；缓存键仍是 `(profile.id, profile.updated_at)`
- Produces: 创建 Run 预检：有档案时 `profile.api_key or os.environ.get(profile.api_key_env)` 为空 → 422

- [ ] **Step 1: 写失败测试**

```python
def test_provider_prefers_stored_key(monkeypatch, captured_provider_class):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    factory = build_factory()
    factory.build(make_profile(api_key="sk-db"))
    assert captured_provider_class.last_kwargs["api_key"].get_secret_value() == "sk-db"

def test_provider_falls_back_to_env(monkeypatch, captured_provider_class):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    factory = build_factory()
    factory.build(make_profile(api_key=None))
    assert captured_provider_class.last_kwargs["api_key"].get_secret_value() == "sk-env"

def test_missing_key_raises_422(profile_factory, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(AgentKitError) as error:
        profile_factory.build(make_profile(api_key=None))
    assert error.value.code == ErrorCode.MODEL_PROFILE_INVALID
    assert error.value.http_status == 422
```

- [ ] **Step 2: 运行确认失败** → `uv run pytest ... -q`，Expected: FAIL（仍读 env）

- [ ] **Step 3: 实现**

- `provider_factory.build`：`api_key = profile.api_key or os.environ.get(profile.api_key_env)`；空则 422，错误 details 只带 `profile_id`。
- `run_service.create`：预检同上，不再直接读 env。
- `container` 的 encoding：
  ```python
  if active_profile is not None and not settings.model_token_encoding:
      encoding_name = "cl100k_base"
  else:
      encoding_name = self._require_text("MODEL_TOKEN_ENCODING", settings.model_token_encoding)
  ```

- [ ] **Step 4: 运行确认通过** → 追加测试 + 现有 `tests/application` 全绿
- [ ] **Step 5: 提交** `git commit -am "feat(backend): 密钥优先取库内值并保留 env 回退"`

---

### Task 3: UI 支持填写与回显 `has_key`

**Files:**
- Modify: `ui/src/lib/api/contracts.ts`
- Modify: `ui/src/features/models/models.ts`
- Modify: `ui/src/features/models/ModelProfilesPage.vue`
- Test: `ui/src/features/models/models.test.ts`（若不存在则创建）

**Interfaces:**
- Produces: `modelProfileSchema` 增加 `has_key: z.boolean()`；`ModelProfilePayload` 增加 `api_key?: string`
- Produces: 表单新增“API Key（可选）”密码框；编辑时显示“已配置 / 未配置”，留空表示不修改

- [ ] **Step 1: 写失败测试**

```typescript
it('parseModelProfile keeps has_key and rejects missing field', () => {
  const parsed = modelProfileSchema.parse({ ...baseProfile, has_key: true })
  expect(parsed.has_key).toBe(true)
  expect(() => modelProfileSchema.parse(baseProfile)).toThrow()
})

it('save forwards api_key only when filled', async () => {
  await state.save({ ...payload, api_key: 'sk-new' })
  expect(client.createModelProfile).toHaveBeenCalledWith(expect.objectContaining({ api_key: 'sk-new' }))
})
```

- [ ] **Step 2: 运行确认失败** → `cd ui && pnpm test --run src/features/models/models.test.ts`
- [ ] **Step 3: 实现**（schema、payload、页面字段、保存时 trim；空串不传；编辑态不回填密钥）
- [ ] **Step 4: 运行确认通过** → `cd ui && pnpm check && pnpm test`
- [ ] **Step 5: 提交** `git commit -am "feat(ui): 模型档案支持填写 API Key 并显示是否已配置"`

---

### Task 4: 契约快照 v1.2 与共享契约测试

**Files:**
- Modify: `contracts/openapi/prism-agent-api.yaml`（脚本重导出）
- Create: `tests/contract/test_model_profiles.py`
- Modify: `contracts/README.md`（v1.2 说明）

**Interfaces:**
- Produces: 契约测试用例 `test_create_profile_returns_has_key_without_secret`、`test_patch_omitting_api_key_keeps_it`、`test_clear_api_key_with_empty_string`（清理：测试结束删除自己创建的档案）

- [ ] **Step 1: 写失败测试**（对 Python 后端先跑）
- [ ] **Step 2: 运行确认失败**（在 Task 1/2 实现前应先红；若 Task 1 已合并则直接对 Java 跑红）
- [ ] **Step 3: 导出快照** `bash scripts/export-openapi.sh`；确认 `35 paths` 不变且 `ModelProfileCreate` 含 `api_key`、`ModelProfileView` 含 `has_key`
- [ ] **Step 4: 运行确认通过**（Python 端）
- [ ] **Step 5: 提交** `git commit -am "test(contract): 模型档案 v1.2 契约用例与快照"`

---

### Task 5: Java 档案表、API 与密钥解析

**Files:**
- Create: `backend-java/src/main/resources/db/migration/V3__model_profiles.sql`
- Create: `backend-java/src/main/java/com/prism/agent/persistence/{entity/ModelProfileEntity,mapper/ModelProfileMapper,repository/ModelProfileRepository,repository/MyBatisModelProfileRepository}.java`
- Create: `backend-java/src/main/java/com/prism/agent/core/domain/ModelProfile.java`
- Create: `backend-java/src/main/java/com/prism/agent/application/service/ModelProfileService.java`
- Create: `backend-java/src/main/java/com/prism/agent/application/service/ProfileCredentialResolver.java`
- Create: `backend-java/src/main/java/com/prism/agent/api/dto/{ModelProfileRequest,ModelProfileView,ModelProfileProbeView}.java`
- Create: `backend-java/src/main/java/com/prism/agent/api/controller/ModelProfileController.java`
- Test: `backend-java/src/test/java/com/prism/agent/api/ModelProfileApiTest.java`

**Interfaces:**
- Consumes: `ErrorCode`、`TransactionTemplate`
- Produces:
  - `record ModelProfile(String id, String name, String baseUrl, String model, String apiKeyEnv, String apiKey, int contextWindow, int maxOutputTokens, boolean active, Instant createdAt, Instant updatedAt)`
  - `ModelProfileRequest(name, baseUrl, model, apiKeyEnv, apiKey, contextWindow, maxOutputTokens)`（`apiKey` 可空）
  - `ModelProfileView(..., boolean hasKey)` —— 永不包含 `apiKey`
  - `ProfileCredentialResolver.resolve(ModelProfile)` → `String`（库内 → `System.getenv(apiKeyEnv)` → `ApiException(MODEL_PROFILE_INVALID, 422)`）
  - `POST/GET/PATCH/DELETE /model-profiles`、`/{id}/activate`、`/{id}/probe`

- [ ] **Step 1: 写失败测试**

```java
@Test void createReturnsHasKeyAndNeverEchoesSecret() { /* POST 带 api_key → 200, has_key=true, body 不含 sk- */ }
@Test void patchOmittingApiKeyKeepsIt() { /* PATCH 不带 api_key → has_key 仍 true */ }
@Test void patchEmptyStringClearsIt() { /* 无 env 时 has_key=false */ }
@Test void activatingSecondProfileSwitchesActiveFlag() { /* activate A 再 activate B → A.is_active=false, B.is_active=true */ }
@Test void deleteActiveProfileIs409() { /* MODEL_PROFILE_IN_USE */ }
@Test void probeWithoutAnyKeyIsOkFalseWithError() { /* 200 + ok=false，error 不含密钥 */ }
```

- [ ] **Step 2: 运行确认失败** → 404
- [ ] **Step 3: 实现**
  - `V3`：建 `model_profiles`（`api_key TEXT NULL`、`active_marker` 生成列 UNIQUE、`name` UNIQUE）。
  - PATCH 用 `Optional<String>` 区分省略/空串；service 层同样用哨兵。
  - `probe`：用 resolver 拿 key；失败返回 200 `{ok:false, latency_ms:null, error:"..."}`，`error` 只允许异常类型名或固定文案。
- [ ] **Step 4: 运行确认通过** → `./mvnw -q -Dtest=ModelProfileApiTest test`
- [ ] **Step 5: 提交** `git commit -am "feat(java): 模型档案 API 与库内密钥解析"`

---

### Task 6: Java Provider 按 Run 解析档案

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/providers/ProviderResolver.java`
- Modify: `backend-java/src/main/java/com/prism/agent/application/service/RunService.java`（快照档案）
- Modify: `backend-java/src/main/java/com/prism/agent/core/engine/SimpleAgentEngine.java`（改用 resolver）
- Modify: `backend-java/src/main/java/com/prism/agent/config/EngineConfiguration.java`
- Test: `backend-java/src/test/java/com/prism/agent/application/ProviderResolutionTest.java`

**Interfaces:**
- Produces: `ProviderResolver.forRun(Run run)`：`run.modelProfileId == null` → 默认 Provider；否则按档案构造（`apiKey → env → 422`），缓存键 `(id, updatedAt)`
- Produces: `RunService.create` 读取 active profile，写快照 `modelProfileId/model/contextWindow/maxOutputTokens`；无 key → 422 `MODEL_PROFILE_INVALID`，**不创建 Run**

- [ ] **Step 1: 写失败测试**

```java
@Test void activeProfileIsSnapshottedOnRun() { ... assert run.model().equals(profile.model()) }
@Test void missingKeyRejectsRunCreationWith422() { ... }
@Test void resolverPrefersStoredKey() { ... }   // 用 Provider 的 apiKey 断言或 stub 服务器
@Test void resolverFallsBackToEnv() { ... }
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：`RunService.create` 在事务内读 active profile 并在插入 Run 前完成 key 预检；`SimpleAgentEngine` 用 `resolver.forRun(run)`，其余逻辑不变。
- [ ] **Step 4: 运行确认通过** → `./mvnw verify`
- [ ] **Step 5: 提交** `git commit -am "feat(java): 按 Run 快照解析模型档案与密钥"`

---

### Task 7: 双端契约验证与文档收口

**Files:**
- Modify: `docs/compatibility/feature-parity.md`
- Modify: `backend/README.md`、`ui/README.md`
- Modify: `AGENTS.md`（密钥落库后的安全约束）

**Interfaces:**
- Consumes: Task 4 的契约用例
- Produces: parity 表 `Model Profile` 行 = `Contract Passed`（两端跑同一用例全绿）

- [ ] **Step 1: 双端跑契约**

```bash
cd tests/contract
PRISM_CONTRACT_BASE_URL=http://192.168.31.90:8000 ... pytest test_model_profiles.py -q
PRISM_CONTRACT_BASE_URL=http://192.168.31.90:8001 ... pytest test_model_profiles.py -q
```

- [ ] **Step 2: 更新文档**
  - `backend/README.md` 删除“密钥只从环境变量读取、不写入 SQLite”，改为“密钥可存库（0600），env 回退保留；备份即密钥备份”。
  - `AGENTS.md` 追加：禁止在日志/响应/轨迹输出密钥；只暴露 `has_key`。
  - parity 表更新。
- [ ] **Step 3: 全量验证**：`uv run pytest`、`./mvnw verify`、`pnpm check && pnpm test`、两端契约
- [ ] **Step 4: 提交** `git commit -am "docs: 模型档案 UI 凭据的契约、安全边界与 parity 更新"`

---

## 自检记录

- **Spec 覆盖**：3b 设计 §2（档案与凭据）、§6（契约 v1.2）、§7（安全）落到 Task 1–7；压缩/轨迹/标题明确留到 3b-2。
- **步骤扫描**：每个 Step 一个可检查结果；迁移、PATCH 哨兵语义、密钥优先级是“精确语义”，给了完整断言。
- **类型一致性**：`has_key` 两端同名同类型；`api_key` 只写入；`ProfileCredentialResolver` 与 `ProviderResolver` 职责分开（凭据 vs 协议对象）。
- **Review Focus**：五条分别落在 Task 1（泄漏/省略）、Task 2（优先级）、Task 1/5（迁移）、Task 4/7（契约）。
- **比例**：7 个任务、两端各约 6 个文件；未展开 3b-2。

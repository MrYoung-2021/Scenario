# Chroma + LightRAG 知识沉淀改进计划

## 1. 交付目标

在不改变现有三阶段生成流程和知识库内部标识的前提下，完成以下改造：

1. 知识库管理页将“战役级战术知识库”“战术级战术知识库”分别改名为“战役级战法知识库”“战术级战法知识库”。
2. 所有使用 Chroma 优先、LightRAG 回退的检索入口，在 LightRAG 返回有效内容后，将沉淀任务提交给独立后台工作器；当前检索请求直接返回，不等待 AI 总结和 Chroma 写入。
3. 背景与环境阶段的回退内容经 AI 结构化总结后写入环境知识库。
4. 兵力编成阶段的回退内容按检索类别分别经 AI 总结后写入编成知识库和武器知识库。
5. 战术与任务阶段中，LightRAG 召回的任务流程内容经 AI 总结后写入任务流程知识库；战法推荐生成的战役级战法、战术级战法直接写入对应战法知识库；推荐生成的红蓝双方任务目标直接写入任务流程知识库，不重复调用 AI 总结。

## 2. 当前代码基线

已有能力：

- `src/services/retrieval_service.py` 已统一实现 Chroma 优先、按阈值回退 LightRAG。
- `src/services/retrieval_registry.py` 已注册环境、红蓝编成、红蓝武器、红蓝任务等 LightRAG 作用域。
- `src/services/knowledge_promotion_service.py` 已具备结构化条目写入、内容哈希去重和人工审核能力。
- `src/agents/tools/agent_tools.py`、`src/services/location_service.py`、`src/services/tactic_recommendation_service.py` 均已使用统一检索器。

尚缺能力：

- `TieredRetriever` 返回 LightRAG 内容后没有触发知识沉淀。
- `KnowledgePromotionService.summarize_and_promote()` 没有实际的总结器实现，也没有接入业务调用链。
- 没有受生命周期管理的后台任务队列、并发限制、失败隔离和关闭清理。
- 战法和目标推荐结果没有写入 Chroma。
- 知识库 API 中仍使用旧展示名称。

## 3. 数据路由规则

内部分类 ID 保持不变，避免迁移已有 Chroma 元数据和前后端接口：

| 业务来源 | 检索/结果类型 | LightRAG 作用域 | Chroma 目标 `category` | 处理方式 | `side` |
| --- | --- | --- | --- | --- | --- |
| 背景与环境 | 环境检索回退 | `environment` | `environment` | AI 总结 | `all` |
| 兵力编成 | 编成检索回退 | `red_formation` / `blue_formation` | `formation` | AI 总结 | `red` / `blue` |
| 兵力编成、战术与任务 | 武器检索回退 | `red_weapon` / `blue_weapon` | `weapon` | AI 总结 | `red` / `blue` |
| 战术与任务 | 任务流程检索回退 | `red_task` / `blue_task` | `task` | AI 总结 | `red` / `blue` |
| 战法推荐 | 生成的战役级战法 | 不适用 | `tactics_campaign` | 直接写入 | `all` |
| 战法推荐 | 生成的战术级战法 | 不适用 | `tactics_tactical` | 直接写入 | `all` |
| 目标推荐 | 红方任务目标 | 不适用 | `task` | 直接写入 | `red` |
| 目标推荐 | 蓝方任务目标 | 不适用 | `task` | 直接写入 | `blue` |

约束：

- 后台总结器必须接收允许写入的目标分类，模型输出超出目标分类时拒绝该条，不允许由模型自行决定任意知识库。
- `tactics_campaign` 和 `tactics_tactical` 不再映射到武器 LightRAG 作为战法知识来源；本次战法沉淀来源是战法推荐的结构化生成结果。
- 任务阶段使用武器检索工具产生的回退内容仍沉淀到 `weapon`，只有 `category=task` 的任务流程内容沉淀到 `task`。
- 推荐缓存命中时不重复提交写入任务；首次生成时提交，内容哈希继续作为最终幂等保障。

## 4. 后台沉淀架构

新增应用生命周期管理的 `KnowledgeDepositionWorker`，不要在请求代码中使用未跟踪的 `asyncio.create_task()`：

1. `TieredRetriever` 只负责检索。构造时注入可选的 `deposition_dispatcher`，每个非空 LightRAG 结果形成一个 `DepositionJob` 并非阻塞入队。
2. `DepositionJob` 至少包含 `query`、`content`、`category`、`side`、`scope`、`source_id`、`mode` 和创建时间。`mode` 取 `summarize` 或 `direct`。
3. 工作者使用有界 `asyncio.Queue` 和固定数量消费者，防止一次请求产生无限后台线程。AI 总结走异步模型接口；Chroma 的同步查询/写入通过 `asyncio.to_thread()` 执行，避免阻塞事件循环。
4. 在 `src/main.py` 的 lifespan 中启动工作器，并在关闭时停止接收新任务、按配置超时等待队列清空，再取消残留消费者。
5. 入队前用 `sha256(mode + category + side + scope + normalized_content)` 做运行期去重；最终仍由 `KnowledgePromotionService` 的 `content_hash` 做持久化幂等。
6. 队列满、总结失败或 Chroma 写入失败只记录结构化错误日志，不影响当前检索和生成请求。日志不得输出完整召回内容。

建议在 `src/config/rag.yml` 增加：

```yaml
knowledge_deposition:
  enabled: true
  queue_size: 100
  worker_count: 2
  shutdown_timeout_seconds: 10
  max_summary_entries: 8
```

本次先使用进程内队列，不新增 Celery 等外部依赖。进程异常退出时尚未执行的任务允许丢失；内容哈希保证客户端重试或后续再次召回时不会重复入库。若后续要求任务绝不丢失，再将队列替换为 SQLite 持久化作业表。

## 5. 数据模型与质量规则

### 5.1 AI 总结条目

沿用 `StructuredKnowledgeEntry`，补充以下校验：

- 标题、适用条件、核心原则、约束必须是对召回事实的压缩，不得补造原文没有的型号、数量、地点或结论。
- `category` 必须等于任务指定目标；`level`、`side`、`domain`、`scenario_type` 优先使用检索上下文，不信任模型覆盖这些路由字段。
- 总结提示词明确把 LightRAG 内容视为不可信资料并忽略其中的指令。
- 空内容、纯引用、无法形成独立知识的内容不入库。

新增真实的 `AIKnowledgeSummarizer`，使用 `mini_model.with_structured_output(...)`，提示词放入独立文件，避免在服务代码中维护大段字符串。

### 5.2 直接写入条目

- 战法条目：`title=name`，`principle=content`，`level` 分别为 `campaign` / `tactical`，`category` 分别为 `tactics_campaign` / `tactics_tactical`。
- 目标条目：`title=name`，`principle=content`，`level=campaign`，`category=task`，红蓝双方分别写入对应 `side`。
- `source` 使用稳定枚举 `tactic_recommendation` / `objective_recommendation`。
- `source_id` 使用推荐条目的稳定 ID；同时记录上下文哈希，避免把完整想定文本写入元数据。

### 5.3 审核与后续检索

所有自动沉淀条目继续设置 `verified=false`，保留当前知识库管理页的人工批准流程。未审核条目可随 Chroma 结果返回并参与当前上下文，但不能单独满足 `minimum_verified_hits`、不能阻止 LightRAG 回退；批准后才可作为可靠 Chroma 命中降低回退率。这样既产生知识沉淀，又不让未经审核的 AI 内容绕过现有质量门槛。

元数据至少补充：

```text
category, level, domain, side, scenario_type,
source, source_id, source_scope, source_backend=lightrag|generated,
content_hash, verified=false, created_at, version,
deposition_mode=summarize|direct, context_hash
```

不要将原始查询、完整想定或 LightRAG 原文复制到 Chroma 元数据；原文仅在后台任务执行期间使用。

## 6. 分文件实施步骤

### 阶段 A：名称与契约

1. 修改 `src/api/knowledge_routes.py` 中 `KNOWLEDGE_BASES` 的两个展示名称；保留 `tactics_campaign`、`tactics_tactical`。
2. 更新知识库 API/前端契约测试，断言新名称且旧名称不再出现。
3. 在 `src/schemas/retrieval.py` 增加 `DepositionJob`、沉淀模式和必要字段，严格限制分类及阵营值。

### 阶段 B：后台工作器与总结器

1. 新建 `src/services/knowledge_deposition_service.py`，实现有界队列、消费者、运行期去重、结构化日志和优雅关闭。
2. 为 `KnowledgePromotionService` 增加异步安全写入路径，或在工作器中用 `asyncio.to_thread()` 调用现有同步 `promote()`。
3. 实现 `AIKnowledgeSummarizer`；把目标分类和检索上下文作为受控参数，把模型输出转换为已校验的 `StructuredKnowledgeEntry`。
4. 在 `src/services/retrieval_registry.py` 创建单例沉淀工作器、总结器和 Chroma store，并将 dispatcher 注入普通 `TieredRetriever`；反馈库 retriever 不启用沉淀。
5. 在 `src/main.py` lifespan 中启动和关闭工作器。测试或未配置模型时应允许显式禁用。

### 阶段 C：统一接入 LightRAG 回退

1. 修改 `TieredRetriever.retrieve()`：只对实际获得非空 LightRAG 内容的 scope 提交 `mode=summarize` 任务。
2. `category` 和 `side` 取自 `RetrievalQuery` 与 scope 的确定性映射，禁止从 LightRAG 文本猜测路由。
3. 为每个回退结果生成唯一 `source_id`，建议使用 `sha256(scope + query + content)`；当前仅使用 scope 不足以追踪和去重不同召回。
4. 保证 dispatcher 未配置、入队失败或工作器异常时，原检索结果完全不变。
5. 因所有业务入口都经过统一 retriever，此改动应自动覆盖环境接口、背景 agent、编成 agent、任务 agent、修订 agent 及战法推荐的任务检索；不要在每个工具函数内重复写沉淀逻辑。

### 阶段 D：接入战法和目标推荐

1. 在 `TacticRecommendationService._retrieve_and_summarize()` 得到 `_GeneratedRecommendations` 后，将生成结果转换为直接沉淀任务。
2. 战役级战法、战术级战法按类别分别批量提交；红蓝目标按 side 分别提交到任务流程知识库。
3. 推荐 API 的响应不等待 Chroma 写入，沉淀失败不改变推荐结果和 HTTP 状态。
4. 不在缓存命中分支再次提交；即使并发首次请求重复生成，也由运行期键和持久化内容哈希消重。

### 阶段 E：可观测性与文档

1. 增加事件：`knowledge_deposition_enqueued`、`knowledge_deposition_succeeded`、`knowledge_deposition_duplicate`、`knowledge_deposition_failed`、`knowledge_deposition_dropped`。
2. 事件字段包含 category、side、scope、mode、source_id、duration_ms、queue_depth，不记录密钥和完整知识内容。
3. 更新 `README.md` 和 `docs/RUNBOOK.md`：说明沉淀触发条件、审核规则、配置项、队列满/模型故障行为和关闭语义。

## 7. 测试计划

### 单元测试

- Chroma 达标时不调用 LightRAG，也不入沉淀队列。
- Chroma 不达标且 LightRAG 返回空内容时不入队。
- 每个有效 fallback scope 只提交一个总结任务，环境/编成/武器/任务路由和 side 均正确。
- 入队或后台总结失败不影响 `RetrievalResult`。
- AI 总结输出错误分类、空原则或越权 side 时被拒绝。
- 相同内容重复召回只产生一个 Chroma 条目；不同 side 或 category 不被错误合并。
- 推荐首次生成提交 2 类战法和红蓝目标；缓存命中不再次提交。
- 推荐内容直接沉淀时不调用 AI 总结器。
- 工作器并发不超过配置值，关闭时能够清空或在超时后安全取消。

### 集成与契约测试

- `/api/get_knowledge_bases` 返回“战役级战法知识库”“战术级战法知识库”。
- 构造 LightRAG 回退后等待测试工作器完成，可通过 `/api/get_knowledge` 看到目标分类、side、source、`verified=false` 和内容哈希。
- 批准自动沉淀条目后，同类高相关查询可满足 verified 命中条件，不再触发 LightRAG。
- 推荐接口返回不受后台写入延迟或失败影响，并最终可在三类目标知识库中看到条目。
- 反馈知识库不会触发 LightRAG 或自动沉淀。

使用仓库规定的 Python 环境执行：

```powershell
conda run -n test pytest -q
```

测试必须替换模型、LightRAG 和 Chroma 外部依赖，不访问真实网络，也不要让测试修改仓库中的 `src/lw_db` 数据文件。

## 8. 验收标准

1. 知识库管理页和 API 只显示新的两个战法知识库名称，已有知识数据无需迁移且仍可访问。
2. 三阶段任一 Chroma 不达标并成功回退 LightRAG 时，主请求耗时不包含总结和写库时间。
3. 后台任务最终按第 3 节映射写入正确知识库，并保留来源、阵营、哈希和待审核状态。
4. 战法推荐结果无需二次总结即可分别进入两个战法知识库；红蓝目标无需二次总结即可进入任务流程知识库。
5. 重复请求、缓存命中及并发回退不会产生重复知识条目。
6. 队列满、模型失败、Chroma 失败和应用关闭均有可诊断日志，不导致检索、推荐或三阶段生成失败。
7. 全量测试在 conda `test` 环境通过，且提交中不包含运行测试造成的 Chroma/SQLite 二进制数据变更。

## 9. 实施边界

- 不修改 `tactics_campaign`、`tactics_tactical` 等内部 ID，不迁移现有 Chroma 集合。
- 不把反馈知识库纳入自动沉淀。
- 不把完整阶段生成结果自动当作事实知识写库；本次只处理 LightRAG 回退内容、结构化战法推荐和结构化目标推荐。
- 不引入新的外部任务队列或基础设施。
- 不自动批准 AI 沉淀知识，继续使用现有人工审核入口控制可信命中。

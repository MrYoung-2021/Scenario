# Scenario

军事想定工作区：按背景、编成、任务和定稿四步生成、确认并恢复想定。

## 快速开始

要求 Windows PowerShell、Conda 和 Python 3.11/3.12。

```powershell
conda create --prefix .\.venv python=3.12 pip -y
conda activate .\.venv
python -m pip install -r requirements.txt
```

模型、LightRAG 和可选地址 Provider 只从服务端环境变量读取密钥：

```powershell
$env:DASHSCOPE_API_KEY = "<your-key>"
$env:OPENAI_API_KEY = $env:DASHSCOPE_API_KEY
```

不调用生成接口时，健康检查、工作流页面和知识库管理不需要有效模型密钥。

## 数据库迁移

默认数据库为 `src/lw_db/chat_history.db`。开发和测试请始终使用副本：

```powershell
$env:SCENARIO_DB_PATH = "$env:TEMP\scenario-development.db"
Copy-Item .\src\lw_db\chat_history.db "$env:TEMP\scenario-development.db"
python .\scripts\validate_migration.py "$env:TEMP\scenario-development.db"
```

迁移会创建或升级场景工作流表，并将旧 `conversations`、`task_configs` 中可用的背景、编成、任务文本复制为版本 1。旧表和消息不会删除，迁移标记保证重复运行不会产生重复场景或版本。真实数据库操作前先停止服务并保留带时间戳备份，详见 [docs/RUNBOOK.md](docs/RUNBOOK.md)。

## 分级知识检索

`src/config/rag.yml` 的 `retrieval` 配置控制普通 Chroma 优先检索：

- `score_threshold`：普通结果最低相关度。
- `standard_top_k`：普通库候选数量。
- `lightrag_top_k`：回退到对应 LightRAG 时的数量。
- `minimum_verified_hits`：无需回退所需的已审核命中数。

普通结果包含类别、层级、阵营、来源、来源 ID、审核状态和内容哈希。低分、空结果或仅未审核结果才会回退到匹配的环境、红/蓝编成、武器或任务库。LightRAG 回退结果会异步提交到有界沉淀队列，经结构化总结、哈希去重、来源绑定后写入 Chroma，并默认为 `verified=false`；队列或模型失败不会影响当前检索。

沉淀由 `src/config/rag.yml` 的 `knowledge_deposition` 控制。背景环境回退进入环境库，编成/武器/任务回退进入对应库；战法推荐和红蓝目标推荐以结构化结果直接进入战法库或任务流程库。自动沉淀内容仍需人工批准后才计入可靠命中数，反馈知识库不参与自动沉淀。

知识库管理页支持查看来源、层级、审核状态和批准条目。反馈内容独立写入 `feedback` 集合，不与事实知识混存。

## 启动与检查

```powershell
conda activate .\.venv
python -m uvicorn main:app --app-dir src --host 127.0.0.1 --port 8000
```

- 页面：[http://127.0.0.1:8000/static/new_new.html](http://127.0.0.1:8000/static/new_new.html)
- 健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

旧 `/api/chat` 接口仍保留以兼容已有调用，并标记为弃用；新页面使用 `/api/scenarios` 工作流接口。

## 测试

```powershell
python -m pytest -q
python -m compileall -q src
python -m pip check
```

测试不调用真实地址服务、模型或 LightRAG 网络接口；相关依赖均通过替身或临时数据库验证。生成和检索日志包含 `scenario_id`、`step`、`request_id`、耗时、普通命中数和 LightRAG 回退率，日志处理器会脱敏 API key、token 和 bearer 值。

# Scenario 运行手册

## 环境要求

- Windows PowerShell
- Conda
- Python 3.11 或 3.12；当前开发环境使用 Python 3.12

在仓库根目录创建并激活隔离环境：

```powershell
conda create --prefix .\.venv python=3.12 pip -y
conda activate .\.venv
python -m pip install -r requirements.txt
```

## 配置

模型与 LightRAG 使用服务端环境变量。不要把密钥写入配置文件或提交到仓库。

```powershell
$env:DASHSCOPE_API_KEY = "<your-key>"
$env:OPENAI_API_KEY = $env:DASHSCOPE_API_KEY
```

默认 SQLite 文件为 `src/lw_db/chat_history.db`。开发和测试时可通过服务端环境变量指向数据库副本：

```powershell
$env:SCENARIO_DB_PATH = "$env:TEMP\scenario-development.db"
```

不调用生成接口时，健康检查和现有页面无需有效模型密钥。

## 数据库备份

数据库默认为 `src/lw_db/chat_history.db`。迁移或手工维护前，先停止服务，再创建带时间戳的副本：

```powershell
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item -LiteralPath .\src\lw_db\chat_history.db -Destination ".\src\lw_db\chat_history.$timestamp.backup.db"
```

备份文件可能包含用户输入和模型输出，不应提交到 Git。恢复时先停止服务，并保留当前数据库作为另一份备份。

在迁移真实数据库前，先复制数据库并对副本执行验证：

```powershell
Copy-Item -LiteralPath .\src\lw_db\chat_history.db -Destination $env:TEMP\scenario-migration-test.db
$env:PYTHONPATH = "src"
python .\scripts\validate_migration.py $env:TEMP\scenario-migration-test.db
```

迁移是可重复执行的。首次运行会把旧 `conversations` 和 `task_configs` 中的背景、编成、任务文本复制到场景工作流的版本 1，并写入 `legacy_session_migrations` 标记；原有会话、消息和任务配置保留不动。再次运行只检查已存在的标记，不会创建重复场景或版本。验证脚本应始终指向副本，不要直接指向生产或用户数据库。

迁移日志会记录每个版本的执行前后表数量。生成日志使用 `event=generation_completed`、`event=generation_failed` 等结构化事件，并包含 `scenario_id`、`step`、`request_id` 和 `duration_ms`。分级检索使用 `event=rag_retrieval` 记录普通候选数、已审核命中数、回退数和回退率；日志处理器会移除 API key、token、bearer 和 password 值。

知识沉淀由 `config/rag.yml` 中的 `knowledge_deposition` 配置控制。LightRAG 回退内容进入有界进程内队列，由固定数量消费者异步总结并写入 Chroma；队列满、模型失败或写入失败只记录 `knowledge_deposition_*` 事件，不影响检索和生成。自动写入条目默认为 `verified=false`，需在知识库管理页人工批准。应用关闭时最多等待 `shutdown_timeout_seconds` 秒清空队列，超时任务会被取消；进程异常退出时未执行任务允许丢失，重复召回由内容哈希去重。

## 启动与检查

从仓库根目录启动服务：

```powershell
conda activate .\.venv
python -m uvicorn main:app --app-dir src --host 127.0.0.1 --port 8000
```

访问：

- 页面：`http://127.0.0.1:8000/static/new_new.html`
- 健康检查：`http://127.0.0.1:8000/api/health`

运行当前自动化测试：

```powershell
python -m pytest
```

阶段 6 交付前还应执行：

```powershell
python -m pytest -q
python -m compileall -q src
python -m pip check
```

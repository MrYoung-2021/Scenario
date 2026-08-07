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

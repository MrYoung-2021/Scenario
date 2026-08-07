import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional

import aiosqlite
from utils.path_tools import get_abs_path
from utils.config_handler import db_conf
from repositories.migrations import apply_migrations

class ConversationStore:
    """基于 SQLite 的对话存储，只需传入文件路径即可。"""

    def __init__(self, db_path: str):
        """
        db_path: SQLite 数据库文件路径，如 'conversations.db'
        """
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # 让查询结果可通过列名访问
        self._create_tables()

    def _create_tables(self):
        """创建 conversations 和 messages 表（如果不存在）。"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)
        self.conn.commit()

    def create_conversation(self, title: Optional[str] = None) -> str:
        """
        新建一个会话，返回会话ID。
        title: 可选标题，若不提供则使用时间戳作为默认标题。
        """
        conv_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        title = title or f"Conversation {now[:19]}"
        self.conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now)
        )
        self.conn.commit()
        return conv_id
    
    def create_conversation_with_id(self, conv_id: str, title: Optional[str] = None):
        """
        使用指定ID创建会话
        """
        exists = self.conn.execute(
            "SELECT 1 FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        if exists:
            # raise ValueError(f"Conversation with id '{conv_id}' already exists.")
            return
        now = datetime.now(timezone.utc).isoformat()
        title = title or f"Conversation {now[:19]}"
        self.conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now)
        )
        self.conn.commit()

    def add_message(self, conversation_id: str, role: str, content: str) -> int:
        """
        向指定会话添加一条消息。
        role: 'user' 或 'assistant'
        返回消息的本地 ID（自增）。
        """
        # 更新会话的 updated_at
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id)
        )
        cur = self.conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, now)
        )
        self.conn.commit()
        return cur.lastrowid
    
    
    def add_turn(self, conversation_id: str, user_msg: str, assistant_msg: str):
        """
        一次性添加一轮完整对话（用户消息 + 助手回复）。
        这是最常用的便利方法。
        """
        self.add_message(conversation_id, "user", user_msg)
        self.add_message(conversation_id, "assistant", assistant_msg)
    
    def get_messages_formatted(self, conversation_id: str) -> List[Dict[str, str]]:
        """
        返回形如 [] 的对话历史
        """
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,)
        ).fetchall()

        return [{"role": row['role'], "content": row['content']} for row in rows]


    def get_messages(self, conversation_id: str) -> List[Dict]:
        """
        按时间顺序获取某个会话的全部消息。
        返回字典列表，每项含：id, role, content, created_at
        """
        rows = self.conn.execute(
            "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def get_conversations(self, limit: int = 50) -> List[Dict]:
        """
        获取所有会话列表，按更新时间倒序。
        """
        rows = self.conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
    
    def get_conversation_id_title_list(self, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, str]]:
        """
        返回会话的 id 和 title 列表，按 updated_at 降序排列。

        参数:
            limit: 可选，限制返回数量，None 表示返回全部
            offset: 偏移量，默认 0

        返回:
            列表，每个元素为 {'id': '...', 'title': '...'}
        """
        query = "SELECT id, title FROM conversations ORDER BY updated_at DESC"
        params = []
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        rows = self.conn.execute(query, params).fetchall()
        return [{"conv_id": row["id"], "title": row["title"]} for row in rows]
    
    def get_turn_count(self, conversation_id: str) -> int:
        """
        返回指定会话的对话轮次数（用户消息的数量）。
        若会话不存在或没有消息，返回 0。
        """
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ? AND role = 'user'",
            (conversation_id,)
        ).fetchone()
        return row["cnt"]

    def delete_conversation(self, conversation_id: str):
        """删除一个会话及其所有消息。"""
        self.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        self.conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        self.conn.commit()

    def close(self):
        """关闭数据库连接。"""
        self.conn.close()

# conv_store = ConversationStore(get_abs_path(os.path.join(db_conf["directory"], "chat_history.db")))



class AsyncConversationStore:
    """基于 SQLite 的异步对话存储，使用 aiosqlite。"""

    def __init__(self, conn: aiosqlite.Connection):
        """
        不要直接调用 __init__，请使用类方法 create(db_path)。
        """
        self.conn = conn

    @classmethod
    async def create(cls, db_path: str) -> "AsyncConversationStore":
        """异步工厂方法：建立连接，建表，返回实例。"""
        conn = await aiosqlite.connect(db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS task_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                background TEXT,
                formation TEXT,
                task TEXT,
                conversation_id TEXT NOT NULL UNIQUE,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)
        await conn.commit()
        await apply_migrations(conn)
        return cls(conn)

    async def create_conversation(self, title: Optional[str] = None) -> str:
        conv_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        title = title or f"Conversation {now[:19]}"
        await self.conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now)
        )
        await self.conn.commit()
        return conv_id

    async def create_conversation_with_id(self, conv_id: str, title: Optional[str] = None):
        cursor = await self.conn.execute(
            "SELECT 1 FROM conversations WHERE id = ?", (conv_id,)
        )
        exists = await cursor.fetchone()
        if exists:
            return
        now = datetime.now(timezone.utc).isoformat()
        title = title or f"Conversation {now[:19]}"
        await self.conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now)
        )
        await self.conn.commit()

    async def add_message(self, conversation_id: str, role: str, content: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        await self.conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id)
        )
        cursor = await self.conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, now)
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def add_turn(self, conversation_id: str, user_msg: str, assistant_msg: str):
        await self.add_message(conversation_id, "user", user_msg)
        await self.add_message(conversation_id, "assistant", assistant_msg)

    # 类属性，可允许的字段名
    VALID_CONFIG_FIELDS = {"background", "formation", "task"}
    async def set_config_field(self, conversation_id: str, field: str, value: str):
        """
        设置指定会话的某个配置字段的文本值。
        若该会话尚无配置记录，会自动创建；若已有记录则更新该字段。
        字段名不合法时抛出 ValueError。
        """
        if field not in self.VALID_CONFIG_FIELDS:
            raise ValueError(f"字段名无效: {field}，仅允许 {self.VALID_CONFIG_FIELDS}")
        query = f"""INSERT INTO task_configs (conversation_id, {field}) 
                    VALUES (?, ?) 
                    ON CONFLICT(conversation_id) DO UPDATE SET {field} = excluded.{field}"""
        await self.conn.execute(query, (conversation_id, value))
        await self.conn.commit()

    async def get_config_field(self, conversation_id: str, field: str) -> Optional[str]:
        """
        获取指定会话的某个配置字段的文本值。
        若字段名不合法，抛出 ValueError。
        若没有该会话的配置记录或字段为空，返回 None。
        """
        if field not in self.VALID_CONFIG_FIELDS:
            raise ValueError(f"字段名无效: {field}，仅允许 {self.VALID_CONFIG_FIELDS}")
        # 字段名已经过白名单校验，可直接拼接进 SQL
        query = f"SELECT {field} FROM task_configs WHERE conversation_id = ?"
        cursor = await self.conn.execute(query, (conversation_id,))
        row = await cursor.fetchone()
        return row[field] if row else None


    async def get_messages_formatted(self, conversation_id: str) -> List[Dict[str, str]]:
        cursor = await self.conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,)
        )
        rows = await cursor.fetchall()

        return [{"role": row["role"], "content": row["content"]} for row in rows]

    async def get_messages(self, conversation_id: str) -> List[Dict]:
        cursor = await self.conn.execute(
            "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_conversations(self, limit: int = 50) -> List[Dict]:
        cursor = await self.conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_conversation_id_title_list(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> List[Dict[str, str]]:
        query = "SELECT id, title FROM conversations ORDER BY updated_at DESC"
        params = []
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = await self.conn.execute(query, params)
        rows = await cursor.fetchall()
        return [{"conv_id": row["id"], "title": row["title"]} for row in rows]
    
    async def get_latest_assistant_message(self, conversation_id: str) -> Optional[str]:
        """
        返回指定会话中最新一条助手消息的文本内容。
        如果没有助手消息，返回 None。
        """
        cursor = await self.conn.execute(
            "SELECT content FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY created_at DESC LIMIT 1",
            (conversation_id,)
        )
        row = await cursor.fetchone()
        return row["content"] if row else None

    async def get_turn_count(self, conversation_id: str) -> int:
        cursor = await self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ? AND role = 'assistant'",
            (conversation_id,)
        )
        row = await cursor.fetchone()
        return row["cnt"]
    

    async def delete_conversation(self, conversation_id: str):
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            await self.conn.execute("DELETE FROM task_configs WHERE conversation_id = ?", (conversation_id,))
            await self.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            await self.conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            await self.conn.commit()
        except Exception:
            await self.conn.rollback()
            raise

    async def close(self):
        await self.conn.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()


# 全局单例懒加载（异步）
_conv_store: Optional[AsyncConversationStore] = None

async def get_conv_store(db_path: Optional[str] = None) -> AsyncConversationStore:
    global _conv_store
    if _conv_store is None:
        if db_path is None:
            db_path = os.environ.get(
                "SCENARIO_DB_PATH",
                get_abs_path(os.path.join(db_conf["directory"], "chat_history.db")),
            )
        _conv_store = await AsyncConversationStore.create(db_path)
    return _conv_store

if __name__ == '__main__':

    # 2. 创建一个新会话
    # conv_id = conv_store.create_conversation(title="帮忙写周报")

    # 3. 模拟多轮对话
    # conv_store.add_turn(conv_id, "帮我写一份本周的周报。", "好的，请告诉我本周的主要工作内容。")
    # conv_store.add_turn(conv_id, "我本周完成了项目A的接口开发和联调。", "根据你的描述，我为你生成了以下周报...（略）")

    # 4. 查询这个会话的完整历史
    # messages = conv_store.get_messages_formatted(conv_id)
    # print(messages)
    # messages = store.get_messages(conv_id)
    # for msg in messages:
    #     print(f"[{msg['role']}] {msg['content']}")

    # 5. 列出所有会话
    # convs = store.get_conversations()
    # for c in convs:
    #     print(c['id'], c['title'], c['updated_at'])

    # 6. 不再使用时关闭
    # conv_store.close()
    pass

"""SQL execution tools for MCP Server."""

import aiosqlite
from pathlib import Path
from typing import Any

from ..config import config


class SQLExecutorTools:
    """SQL 执行工具集"""

    def __init__(self):
        self.current_db: str = config.DEFAULT_DATABASE
        self._db_path: Path = config.get_db_path(self.current_db)

    @property
    def db_path(self) -> Path:
        """获取当前数据库路径"""
        return config.get_db_path(self.current_db)

    async def list_databases(self) -> list[str]:
        """列出所有可用数据库"""
        return config.list_databases()

    async def switch_database(self, db_name: str) -> dict[str, Any]:
        """切换当前数据库"""
        available = await self.list_databases()
        if db_name not in available:
            return {
                "success": False,
                "error": f"数据库 '{db_name}' 不存在。可用数据库: {', '.join(available[:10])}..."
            }

        self.current_db = db_name
        self._db_path = config.get_db_path(db_name)
        return {
            "success": True,
            "message": f"已切换到数据库: {db_name}",
            "current_db": db_name
        }

    async def get_schema(self) -> dict[str, Any]:
        """获取当前数据库的 Schema 信息"""
        if not self.db_path.exists():
            return {"error": f"数据库文件不存在: {self.db_path}"}

        schema_info = {"tables": [], "relations": []}

        async with aiosqlite.connect(self.db_path) as db:
            # 获取所有表
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ) as cursor:
                tables = [row[0] for row in await cursor.fetchall()]

            # 获取每个表的结构
            for table in tables:
                table_info = {"name": table, "columns": [], "primary_key": []}

                # 获取列信息
                async with db.execute(f"PRAGMA table_info({table})") as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        col_info = {
                            "name": row[1],
                            "type": row[2],
                            "notnull": bool(row[3]),
                            "default": row[4],
                            "is_pk": bool(row[5])
                        }
                        table_info["columns"].append(col_info)
                        if row[5]:
                            table_info["primary_key"].append(row[1])

                # 获取外键信息
                async with db.execute(f"PRAGMA foreign_key_list({table})") as cursor:
                    fk_rows = await cursor.fetchall()
                    for fk in fk_rows:
                        table_info["foreign_keys"] = table_info.get("foreign_keys", [])
                        table_info["foreign_keys"].append({
                            "column": fk[3],
                            "ref_table": fk[2],
                            "ref_column": fk[4]
                        })
                        schema_info["relations"].append({
                            "from_table": table,
                            "from_column": fk[3],
                            "to_table": fk[2],
                            "to_column": fk[4]
                        })

                schema_info["tables"].append(table_info)

        return schema_info

    async def get_schema_text(self) -> str:
        """获取 Schema 的文本描述（适合 LLM 理解）"""
        schema = await self.get_schema()
        if "error" in schema:
            return schema["error"]

        lines = [f"数据库: {self.current_db}\n"]

        for table in schema["tables"]:
            lines.append(f"表 {table['name']}:")
            for col in table["columns"]:
                pk_marker = " [PRIMARY KEY]" if col["is_pk"] else ""
                notnull_marker = " NOT NULL" if col["notnull"] and not col["is_pk"] else ""
                lines.append(f"  - {col['name']}: {col['type']}{pk_marker}{notnull_marker}")

            if table.get("foreign_keys"):
                lines.append("  外键关系:")
                for fk in table["foreign_keys"]:
                    lines.append(f"    {fk['column']} -> {fk['ref_table']}.{fk['ref_column']}")
            lines.append("")

        return "\n".join(lines)

    async def execute_sql(self, sql: str) -> dict[str, Any]:
        """执行 SQL 查询并返回结果"""
        if not self.db_path.exists():
            return {"error": f"数据库文件不存在: {self.db_path}"}

        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 执行 SQL
                async with db.execute(sql) as cursor:
                    # 检查是否有结果
                    if cursor.description:
                        columns = [d[0] for d in cursor.description]
                        rows = await cursor.fetchall()
                        return {
                            "success": True,
                            "columns": columns,
                            "rows": [list(row) for row in rows],
                            "row_count": len(rows)
                        }
                    else:
                        # INSERT/UPDATE/DELETE 等操作
                        await db.commit()
                        return {
                            "success": True,
                            "message": f"执行成功，影响 {cursor.rowcount} 行",
                            "row_count": cursor.rowcount
                        }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "sql": sql
            }

    async def explain_schema(self, table_name: str | None = None) -> str:
        """用自然语言解释表结构"""
        schema = await self.get_schema()
        if "error" in schema:
            return schema["error"]

        if table_name:
            tables = [t for t in schema["tables"] if t["name"] == table_name]
            if not tables:
                return f"表 '{table_name}' 不存在"
        else:
            tables = schema["tables"]

        explanations = []
        for table in tables:
            cols = ", ".join([c["name"] for c in table["columns"]])
            pk = ", ".join(table["primary_key"]) if table["primary_key"] else "无"
            explanation = f"表 '{table['name']}' 包含字段: {cols}。主键: {pk}。"

            if table.get("foreign_keys"):
                fk_desc = []
                for fk in table["foreign_keys"]:
                    fk_desc.append(f"{fk['column']} 关联到 {fk['ref_table']}.{fk['ref_column']}")
                explanation += f" 外键关系: {'; '.join(fk_desc)}。"

            explanations.append(explanation)

        return "\n\n".join(explanations)

    def get_current_db(self) -> str:
        """获取当前数据库名称"""
        return self.current_db


# 全局工具实例
tools = SQLExecutorTools()
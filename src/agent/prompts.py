"""Prompt templates for Text-to-SQL Agent."""


def build_system_prompt(schema_text: str) -> str:
    """构建系统提示词"""
    return f"""你是一个专业的 SQL 助手。根据用户的问题和数据库 Schema，生成正确的 SQL 查询语句。

## 当前数据库 Schema
{schema_text}

## 规则
1. 只返回 SQL 语句，用 ```sql 和 ``` 包裹
2. 使用标准 SQLite 语法
3. 注意表名和字段名的大小写（参考 Schema 中的名称）
4. 如果问题无法用现有 Schema 解答，返回错误信息
5. 复杂查询时，优先使用 JOIN 而不是子查询
6. 对于聚合查询，注意 GROUP BY 和 HAVING 的使用

## 示例
用户问题: 找出所有价格低于5元的商品
SQL:
```sql
SELECT * FROM goods WHERE Price < 5;
```
"""


def build_user_prompt(question: str, conversation_history: list | None = None) -> str:
    """构建用户提示词"""
    prompt = ""

    # 添加对话历史
    if conversation_history:
        prompt += "## 对话历史\n"
        for turn in conversation_history[-3:]:  # 最近3轮
            prompt += f"问: {turn.question}\n"
            prompt += f"答: {turn.sql}\n\n"

    # 添加当前问题
    prompt += f"## 当前问题\n{question}\n\n请生成 SQL 查询语句。"

    return prompt


def build_fix_prompt(
    sql: str,
    error: str,
    question: str,
    schema_text: str | None = None,
    fix_history: list | None = None
) -> str:
    """构建 SQL 修复提示词

    Args:
        sql: 执行失败的 SQL
        error: 错误信息
        question: 原始用户问题
        schema_text: 数据库 Schema（可选，提供更好的修复上下文）
        fix_history: 之前的修复历史（可选，避免重复相同错误）
    """
    prompt_parts = ["之前的 SQL 执行失败了，请分析错误并修复。"]

    # 添加 Schema 信息
    if schema_text:
        prompt_parts.append(f"""
## 数据库 Schema
{schema_text[:2000]}  # 限制长度避免过长
""")

    # 添加原始问题
    prompt_parts.append(f"""
## 原始问题
{question}

## 错误的 SQL
```sql
{sql}
```

## 错误信息
{error}
""")

    # 添加修复历史
    if fix_history:
        history_text = "\n".join([
            f"- 第{h['attempt']}次尝试: {h['sql']}\n  错误: {h['error']}"
            for h in fix_history[-3:]  # 最近3次
        ])
        prompt_parts.append(f"""
## 之前的修复尝试
{history_text}

注意：不要重复之前失败的修复方案，请尝试不同的方法。
""")

    prompt_parts.append("""
## 修复要求
1. 仔细分析错误信息，确定根本原因
2. 检查表名和字段名是否正确（参考 Schema）
3. 检查 SQL 语法是否符合 SQLite 规范
4. 如果是字段名错误，尝试使用相似的字段名
5. 只返回修正后的 SQL 语句，用 ```sql 包裹

修正后的 SQL：""")

    return "\n".join(prompt_parts)


def build_explain_prompt(sql: str, result: dict) -> str:
    """构建结果解释提示词"""
    rows_preview = result.get("rows", [])[:5]  # 只展示前5行
    return f"""请用简洁的语言解释以下 SQL 查询的结果。

## SQL 查询
```sql
{sql}
```

## 查询结果（前5行）
{rows_preview}

## 总行数
{result.get("row_count", 0)}

请解释这个查询找到了什么信息。用1-2句话概括。
"""


def extract_sql(response: str) -> str:
    """从 LLM 响应中提取 SQL 语句"""
    # 尝试提取 ```sql ... ``` 中的内容
    if "```sql" in response:
        start = response.find("```sql") + 6
        end = response.find("```", start)
        if end > start:
            return response[start:end].strip()

    # 尝试提取 ``` ... ``` 中的内容
    if "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        if end > start:
            return response[start:end].strip()

    # 如果没有代码块，直接返回整个响应（假设就是 SQL）
    return response.strip()
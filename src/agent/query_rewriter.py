"""Query rewriter for SQL queries with time conversion and clarification."""

import re
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Any
import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


@dataclass
class SQLQueryRewriteResult:
    """Result of SQL query rewriting."""
    original: str
    rewritten: str
    time_expressions: list[dict[str, Any]] = field(default_factory=list)
    entities: dict[str, list[str]] = field(default_factory=dict)
    clarification: str = ""
    changes: list[str] = field(default_factory=list)

    def get_summary(self) -> str:
        """Get a summary of changes made."""
        if not self.changes:
            return "无需重写"
        return "; ".join(self.changes)


class TimeExpressionParser:
    """Parse natural language time expressions to SQL format."""

    # 中文数字映射
    CN_NUM = {
        '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
        '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
        '十': 10, '廿': 20, '卅': 30
    }

    # 时间单位映射
    TIME_UNITS = {
        '年': 'year', '个月': 'month', '月': 'month',
        '周': 'week', '星期': 'week',
        '天': 'day', '日': 'day',
        '小时': 'hour', '时': 'hour',
        '分钟': 'minute', '分': 'minute',
        '秒': 'second'
    }

    def __init__(self, reference_time: datetime | None = None):
        self.reference_time = reference_time or datetime.now()

    def parse(self, text: str) -> list[dict[str, Any]]:
        """Parse all time expressions in text.

        Returns:
            List of dicts with 'original', 'sql_value', 'type' keys
        """
        results = []

        # 相对时间模式
        relative_patterns = [
            (r'今[天日]', 'today'),
            (r'昨[天日]', 'yesterday'),
            (r'前[天日]', 'day_before_yesterday'),
            (r'后[天日]', 'day_after_tomorrow'),
            (r'明[天日]', 'tomorrow'),
            (r'本[周星期]', 'this_week'),
            (r'上[周星期]', 'last_week'),
            (r'下[周星期]', 'next_week'),
            (r'本[个月]?月', 'this_month'),
            (r'上[个月]?月', 'last_month'),
            (r'下[个月]?月', 'next_month'),
            (r'今年', 'this_year'),
            (r'去年', 'last_year'),
            (r'明年', 'next_year'),
        ]

        for pattern, time_type in relative_patterns:
            for match in re.finditer(pattern, text):
                original = match.group()
                sql_value = self._convert_relative_time(time_type)
                if sql_value:
                    results.append({
                        'original': original,
                        'sql_value': sql_value,
                        'type': time_type,
                        'start': match.start(),
                        'end': match.end()
                    })

        # 相对时间偏移模式 (如 "最近3天", "过去一周", "未来7天")
        offset_patterns = [
            (r'最近(\d+)[天日周]', 'last_n'),
            (r'过去(\d+)[天日周]', 'last_n'),
            (r'前(\d+)[天日周]', 'last_n'),
            (r'未来(\d+)[天日周]', 'next_n'),
            (r'后(\d+)[天日周]', 'next_n'),
            (r'最近(\d+)[个]?月', 'last_n_months'),
            (r'过去(\d+)[个]?月', 'last_n_months'),
        ]

        for pattern, time_type in offset_patterns:
            for match in re.finditer(pattern, text):
                original = match.group()
                number = match.group(1)
                sql_value = self._convert_offset_time(time_type, int(number))
                if sql_value:
                    results.append({
                        'original': original,
                        'sql_value': sql_value,
                        'type': time_type,
                        'number': int(number),
                        'start': match.start(),
                        'end': match.end()
                    })

        # 具体日期模式 (如 "2024年1月1日", "2024-01-01")
        date_patterns = [
            (r'(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})[日]?', 'ymd'),
            (r'(\d{4})[年](\d{1,2})[月]', 'ym'),
            (r'(\d{1,2})[月](\d{1,2})[日]', 'md'),
        ]

        for pattern, date_type in date_patterns:
            for match in re.finditer(pattern, text):
                original = match.group()
                sql_value = self._convert_date(date_type, match.groups())
                if sql_value:
                    results.append({
                        'original': original,
                        'sql_value': sql_value,
                        'type': date_type,
                        'start': match.start(),
                        'end': match.end()
                    })

        # 时间范围模式 (如 "1月到3月", "2024年上半年")
        range_patterns = [
            (r'(\d{4})[年]上半[年]', 'first_half_year'),
            (r'(\d{4})[年]下半[年]', 'second_half_year'),
            (r'(\d{4})[年]第一[季度]', 'q1'),
            (r'(\d{4})[年]第二[季度]', 'q2'),
            (r'(\d{4})[年]第三[季度]', 'q3'),
            (r'(\d{4})[年]第四[季度]', 'q4'),
            (r'(\d{4})[年]Q([1-4])', 'quarter'),
        ]

        for pattern, range_type in range_patterns:
            for match in re.finditer(pattern, text):
                original = match.group()
                sql_value = self._convert_range(range_type, match.groups())
                if sql_value:
                    results.append({
                        'original': original,
                        'sql_value': sql_value,
                        'type': range_type,
                        'start': match.start(),
                        'end': match.end()
                    })

        return results

    def _convert_relative_time(self, time_type: str) -> dict[str, str] | None:
        """Convert relative time expression to SQL conditions."""
        today = self.reference_time.date()

        conversions = {
            'today': {
                'start': today.strftime("'%Y-%m-%d'"),
                'end': today.strftime("'%Y-%m-%d'"),
                'description': '今天'
            },
            'yesterday': {
                'start': (today - timedelta(days=1)).strftime("'%Y-%m-%d'"),
                'end': (today - timedelta(days=1)).strftime("'%Y-%m-%d'"),
                'description': '昨天'
            },
            'day_before_yesterday': {
                'start': (today - timedelta(days=2)).strftime("'%Y-%m-%d'"),
                'end': (today - timedelta(days=2)).strftime("'%Y-%m-%d'"),
                'description': '前天'
            },
            'tomorrow': {
                'start': (today + timedelta(days=1)).strftime("'%Y-%m-%d'"),
                'end': (today + timedelta(days=1)).strftime("'%Y-%m-%d'"),
                'description': '明天'
            },
            'day_after_tomorrow': {
                'start': (today + timedelta(days=2)).strftime("'%Y-%m-%d'"),
                'end': (today + timedelta(days=2)).strftime("'%Y-%m-%d'"),
                'description': '后天'
            },
            'this_week': {
                'start': (today - timedelta(days=today.weekday())).strftime("'%Y-%m-%d'"),
                'end': (today + timedelta(days=6 - today.weekday())).strftime("'%Y-%m-%d'"),
                'description': '本周'
            },
            'last_week': {
                'start': (today - timedelta(days=today.weekday() + 7)).strftime("'%Y-%m-%d'"),
                'end': (today - timedelta(days=today.weekday() + 1)).strftime("'%Y-%m-%d'"),
                'description': '上周'
            },
            'next_week': {
                'start': (today + timedelta(days=7 - today.weekday())).strftime("'%Y-%m-%d'"),
                'end': (today + timedelta(days=13 - today.weekday())).strftime("'%Y-%m-%d'"),
                'description': '下周'
            },
            'this_month': {
                'start': today.replace(day=1).strftime("'%Y-%m-%d'"),
                'end': (today.replace(day=1) + timedelta(days=32)).replace(day=1).strftime("'%Y-%m-%d'"),
                'description': '本月'
            },
            'last_month': {
                'start': (today.replace(day=1) - timedelta(days=1)).replace(day=1).strftime("'%Y-%m-%d'"),
                'end': today.replace(day=1).strftime("'%Y-%m-%d'"),
                'description': '上月'
            },
            'next_month': {
                'start': (today.replace(day=1) + timedelta(days=32)).replace(day=1).strftime("'%Y-%m-%d'"),
                'end': (today.replace(day=1) + timedelta(days=62)).replace(day=1).strftime("'%Y-%m-%d'"),
                'description': '下月'
            },
            'this_year': {
                'start': today.replace(month=1, day=1).strftime("'%Y-%m-%d'"),
                'end': today.replace(month=12, day=31).strftime("'%Y-%m-%d'"),
                'description': '今年'
            },
            'last_year': {
                'start': today.replace(year=today.year - 1, month=1, day=1).strftime("'%Y-%m-%d'"),
                'end': today.replace(year=today.year - 1, month=12, day=31).strftime("'%Y-%m-%d'"),
                'description': '去年'
            },
            'next_year': {
                'start': today.replace(year=today.year + 1, month=1, day=1).strftime("'%Y-%m-%d'"),
                'end': today.replace(year=today.year + 1, month=12, day=31).strftime("'%Y-%m-%d'"),
                'description': '明年'
            },
        }

        return conversions.get(time_type)

    def _convert_offset_time(self, time_type: str, number: int) -> dict[str, str] | None:
        """Convert offset time expression to SQL conditions."""
        today = self.reference_time.date()

        if time_type == 'last_n':
            # 最近 N 天
            unit = 'days'
            return {
                'start': (today - timedelta(days=number)).strftime("'%Y-%m-%d'"),
                'end': today.strftime("'%Y-%m-%d'"),
                'description': f'最近{number}天'
            }
        elif time_type == 'next_n':
            # 未来 N 天
            return {
                'start': today.strftime("'%Y-%m-%d'"),
                'end': (today + timedelta(days=number)).strftime("'%Y-%m-%d'"),
                'description': f'未来{number}天'
            }
        elif time_type == 'last_n_months':
            # 最近 N 个月
            return {
                'start': (today - timedelta(days=number * 30)).strftime("'%Y-%m-%d'"),
                'end': today.strftime("'%Y-%m-%d'"),
                'description': f'最近{number}个月'
            }

        return None

    def _convert_date(self, date_type: str, groups: tuple) -> dict[str, str] | None:
        """Convert specific date format to SQL format."""
        try:
            if date_type == 'ymd':
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                date_str = f"'{year:04d}-{month:02d}-{day:02d}'"
                return {
                    'start': date_str,
                    'end': date_str,
                    'description': f'{year}年{month}月{day}日'
                }
            elif date_type == 'ym':
                year, month = int(groups[0]), int(groups[1])
                return {
                    'start': f"'{year:04d}-{month:02d}-01'",
                    'end': f"'{year:04d}-{month:02d}-31'",
                    'description': f'{year}年{month}月'
                }
            elif date_type == 'md':
                month, day = int(groups[0]), int(groups[1])
                year = self.reference_time.year
                return {
                    'start': f"'{year:04d}-{month:02d}-{day:02d}'",
                    'end': f"'{year:04d}-{month:02d}-{day:02d}'",
                    'description': f'{month}月{day}日'
                }
        except (ValueError, IndexError):
            pass

        return None

    def _convert_range(self, range_type: str, groups: tuple) -> dict[str, str] | None:
        """Convert range expressions to SQL conditions."""
        try:
            if range_type in ('first_half_year', 'second_half_year'):
                year = int(groups[0])
                if range_type == 'first_half_year':
                    return {
                        'start': f"'{year}-01-01'",
                        'end': f"'{year}-06-30'",
                        'description': f'{year}年上半年'
                    }
                else:
                    return {
                        'start': f"'{year}-07-01'",
                        'end': f"'{year}-12-31'",
                        'description': f'{year}年下半年'
                    }
            elif range_type in ('q1', 'q2', 'q3', 'q4'):
                year = int(groups[0])
                quarters = {
                    'q1': (1, 3), 'q2': (4, 6), 'q3': (7, 9), 'q4': (10, 12)
                }
                start_m, end_m = quarters[range_type]
                return {
                    'start': f"'{year}-{start_m:02d}-01'",
                    'end': f"'{year}-{end_m:02d}-31'",
                    'description': f'{year}年第{["一","二","三","四"][start_m//3]}季度'
                }
            elif range_type == 'quarter':
                year = int(groups[0])
                q = int(groups[1])
                quarters = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
                start_m, end_m = quarters[q]
                return {
                    'start': f"'{year}-{start_m:02d}-01'",
                    'end': f"'{year}-{end_m:02d}-31'",
                    'description': f'{year}年Q{q}'
                }
        except (ValueError, IndexError):
            pass

        return None


class SQLQueryRewriter:
    """Rewrite SQL queries with time conversion and clarification."""

    def __init__(
        self,
        llm_client: AsyncOpenAI | None = None,
        model: str = "qwen2.5",
        reference_time: datetime | None = None
    ):
        self.llm = llm_client
        self.model = model
        self.time_parser = TimeExpressionParser(reference_time)

    async def rewrite(
        self,
        query: str,
        schema_text: str | None = None,
        history: list | None = None
    ) -> SQLQueryRewriteResult:
        """Rewrite SQL query with time conversion and clarification.

        Args:
            query: Original user query
            schema_text: Optional database schema for context
            history: Optional conversation history

        Returns:
            SQLQueryRewriteResult with rewritten query and metadata
        """
        result = SQLQueryRewriteResult(original=query, rewritten=query)
        changes = []

        # Step 1: Parse and convert time expressions
        time_exprs = self.time_parser.parse(query)
        if time_exprs:
            result.time_expressions = time_exprs
            for expr in time_exprs:
                changes.append(f"时间转换: {expr['original']} -> {expr['sql_value'].get('description', '')}")

        # Step 2: Clarify ambiguous queries using LLM
        if self.llm and self._needs_clarification(query):
            clarified = await self._clarify_query(query, schema_text, history)
            if clarified and clarified != query:
                result.clarification = clarified
                result.rewritten = clarified
                changes.append(f"问题澄清: {query} -> {clarified}")

        # Step 3: Extract entities if LLM available
        if self.llm and schema_text:
            entities = await self._extract_entities(query, schema_text)
            if entities:
                result.entities = entities

        result.changes = changes
        logger.debug(f"Query rewrite: {query} -> {result.rewritten}, changes: {changes}")

        return result

    def _needs_clarification(self, query: str) -> bool:
        """Check if query needs clarification."""
        ambiguity_indicators = [
            '它', '这个', '那个', '上面', '刚才', '之前',
            '之后', '后者', '前者', '同', '这类', '这些'
        ]
        return any(indicator in query for indicator in ambiguity_indicators)

    async def _clarify_query(
        self,
        query: str,
        schema_text: str | None,
        history: list | None
    ) -> str:
        """Clarify ambiguous query using LLM."""
        context = ""

        if schema_text:
            # Truncate schema for context
            schema_preview = schema_text[:500] + "..." if len(schema_text) > 500 else schema_text
            context += f"数据库结构:\n{schema_preview}\n\n"

        if history:
            recent = history[-3:] if len(history) > 3 else history
            context += "对话历史:\n"
            for turn in recent:
                context += f"问: {turn.question}\n"
                if hasattr(turn, 'sql'):
                    context += f"SQL: {turn.sql}\n"

        prompt = f"""你是一个 SQL 查询澄清专家。根据上下文，澄清用户问题中的模糊指代。

{context}

用户问题: {query}

要求:
1. 如果问题中有模糊指代（如"它"、"这个"、"那个"等），用具体实体替换
2. 保持问题的原始意图
3. 只输出澄清后的问题，不要其他解释
4. 如果问题不需要澄清，直接输出原问题

澄清后的问题:"""

        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200
        )

        return response.choices[0].message.content.strip() or query

    async def _extract_entities(self, query: str, schema_text: str) -> dict[str, list[str]]:
        """Extract entities from query that match schema."""
        schema_preview = schema_text[:800] if len(schema_text) > 800 else schema_text

        prompt = f"""从用户问题中提取可能的数据库实体（表名、字段名、值）。

数据库结构:
{schema_preview}

用户问题: {query}

请以 JSON 格式输出提取的实体:
{{
    "tables": ["可能涉及的表名"],
    "fields": ["可能涉及的字段名"],
    "values": ["查询条件中的值"]
}}

只输出 JSON，不要其他内容。"""

        try:
            response = await self.llm.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300
            )

            import json
            content = response.choices[0].message.content or "{}"

            # Extract JSON from response
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()

            return json.loads(content)
        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return {}

    def get_sql_time_condition(
        self,
        time_expr: dict,
        date_column: str = "date"
    ) -> str:
        """Generate SQL WHERE condition for time expression.

        Args:
            time_expr: Time expression dict from parser
            date_column: Name of the date/datetime column

        Returns:
            SQL condition string
        """
        sql_value = time_expr.get('sql_value', {})
        start = sql_value.get('start')
        end = sql_value.get('end')

        if not start or not end:
            return ""

        if start == end:
            return f"{date_column} = {start}"
        else:
            return f"{date_column} BETWEEN {start} AND {end}"


# Convenience function
def parse_time_expressions(text: str, reference_time: datetime | None = None) -> list[dict]:
    """Parse time expressions from text without LLM.

    Args:
        text: Text containing time expressions
        reference_time: Reference time for relative expressions

    Returns:
        List of parsed time expressions
    """
    parser = TimeExpressionParser(reference_time)
    return parser.parse(text)
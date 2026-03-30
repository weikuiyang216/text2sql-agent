"""Query rewriter for improving retrieval effectiveness."""

import logging
import re
from dataclasses import dataclass, field

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


@dataclass
class RewrittenQuery:
    """Container for rewritten query."""
    original: str
    expanded: list[str] = field(default_factory=list)
    clarified: str = ""
    sub_queries: list[str] = field(default_factory=list)

    def all_queries(self) -> list[str]:
        """Get all query variations for retrieval."""
        queries = [self.original]
        if self.clarified:
            queries.append(self.clarified)
        queries.extend(self.expanded)
        queries.extend(self.sub_queries)
        return list(dict.fromkeys(queries))  # Remove duplicates, preserve order


class QueryRewriter:
    """Rewrite queries for better retrieval."""

    def __init__(
        self,
        llm_client: AsyncOpenAI,
        model: str = "qwen2.5"
    ):
        self.llm = llm_client
        self.model = model

    async def rewrite(self, query: str, history: list | None = None) -> RewrittenQuery:
        """Rewrite query for better retrieval.

        Args:
            query: Original user query
            history: Optional conversation history

        Returns:
            RewrittenQuery with expanded variants
        """
        result = RewrittenQuery(original=query)

        # Step 1: Query expansion
        try:
            result.expanded = await self._expand_query(query)
        except Exception as e:
            logger.warning(f"Query expansion failed: {e}")
            result.expanded = []

        # Step 2: Clarification (if needed)
        try:
            result.clarified = await self._clarify_query(query, history)
        except Exception as e:
            logger.warning(f"Query clarification failed: {e}")
            result.clarified = query

        # Step 3: Query decomposition (for complex queries)
        try:
            result.sub_queries = await self._decompose_query(query)
        except Exception as e:
            logger.warning(f"Query decomposition failed: {e}")
            result.sub_queries = []

        return result

    async def _expand_query(self, query: str) -> list[str]:
        """Generate query variations."""
        prompt = f"""你是一个查询扩展专家。针对用户的查询，生成2个语义相关但表述不同的查询变体。

原查询：{query}

要求：
1. 保持原查询的核心意图
2. 使用不同的表达方式或同义词
3. 每行一个变体，不要编号
4. 只输出变体，不要其他解释

查询变体："""

        response = await self._call_llm(prompt)
        variations = [
            line.strip()
            for line in response.strip().split('\n')
            if line.strip() and not line.strip().startswith('#')
        ]
        return variations[:3]  # Limit to 3 variations

    async def _clarify_query(
        self,
        query: str,
        history: list | None = None
    ) -> str:
        """Clarify ambiguous query."""
        # Check if query has ambiguity indicators
        ambiguity_patterns = [
            r'它[是为]',
            r'这个',
            r'那个',
            r'上面',
            r'刚才'
        ]

        has_ambiguity = any(
            re.search(p, query)
            for p in ambiguity_patterns
        )

        if not has_ambiguity or not history:
            return query

        # Use history to clarify
        history_context = ""
        if history:
            recent = history[-3:] if len(history) > 3 else history
            for turn in recent:
                history_context += f"问：{turn.question}\n答：{turn.sql}\n"

        prompt = f"""根据对话历史，澄清用户当前问题中的模糊指代。

对话历史：
{history_context}

当前问题：{query}

请输出澄清后的问题，不要其他解释。如果问题不需要澄清，直接输出原问题。

澄清后的问题："""

        response = await self._call_llm(prompt)
        return response.strip()

    async def _decompose_query(self, query: str) -> list[str]:
        """Decompose complex query into sub-queries."""
        prompt = f"""判断以下查询是否需要分解为多个独立子查询。如果查询包含多个独立问题，将其分解。

查询：{query}

规则：
1. 只有当问题明显包含多个独立子问题时才分解
2. 如果是单一问题，输出 SINGLE
3. 如果需要分解，每行一个子问题，不要编号

输出："""

        response = await self._call_llm(prompt)

        if "SINGLE" in response.upper():
            return []

        sub_queries = [
            line.strip()
            for line in response.strip().split('\n')
            if line.strip() and not line.strip().startswith('#')
        ]
        return sub_queries[:3]  # Limit to 3 sub-queries

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt."""
        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )
        return response.choices[0].message.content or ""
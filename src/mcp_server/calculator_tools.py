"""Calculator tools for MCP Server."""

import re
from typing import Any


class CalculatorTools:
    """计算器工具集"""

    def calculate(self, expression: str) -> dict[str, Any]:
        """执行数学计算

        Args:
            expression: 数学表达式，如 "100 + 50 * 2"

        Returns:
            {"success": True, "result": 200, "expression": "100 + 50 * 2"}
            或 {"success": False, "error": "错误信息"}
        """
        # 仅允许安全字符：数字、运算符、括号、空格
        if not expression or not expression.strip():
            return {"success": False, "error": "表达式不能为空"}

        # 验证字符集
        if not re.match(r'^[\d\s\+\-\*/%\.\(\)]+$', expression):
            return {"success": False, "error": "包含非法字符，仅允许数字和基础运算符"}

        try:
            # 处理百分比：将 % 替换为 /100
            # 例如：100 + 20% → 100 + 20/100
            expr = expression.replace('%', '/100')

            # 安全执行（限制内置函数）
            result = eval(expr, {"__builtins__": {}}, {})

            return {
                "success": True,
                "result": result,
                "expression": expression
            }
        except ZeroDivisionError:
            return {"success": False, "error": "除零错误"}
        except SyntaxError:
            return {"success": False, "error": "表达式语法错误"}
        except Exception as e:
            return {"success": False, "error": f"计算错误: {str(e)}"}
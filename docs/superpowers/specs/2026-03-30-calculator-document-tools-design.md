# 计算器和文档工具设计文档

## 概述

添加两个新的 MCP 工具支持通用操作：
- **计算器**：基础数学运算
- **文档**：文件读写编辑操作

## 需求

### 计算器工具
- 支持基础四则运算：`+`、`-`、`*`、`/`
- 支持百分比运算
- 支持括号分组
- 安全执行（禁止任意代码）

### 文档工具
- 读取文件内容及元数据
- 写入/追加文件（自动创建目录）
- 编辑文件（文本替换）
- 允许任意路径操作（无限制）

## 架构

### 新增组件

```
src/mcp_server/
├── tools.py              # SQLExecutorTools（现有）
├── calculator_tools.py   # CalculatorTools（新增）
├── document_tools.py     # DocumentTools（新增）
└── server.py             # 注册新工具（修改）
```

### 工具定义

#### CalculatorTools

| 方法 | 参数 | 返回值 |
|------|------|--------|
| `calculate` | `expression: str` | `{success, result, expression}` |

输入验证：
- 允许：数字、`.`、`+`、`-`、`*`、`/`、`%`、`(`、`)`、空格
- 拒绝：字母、下划线、其他特殊字符

#### DocumentTools

| 方法 | 参数 | 返回值 |
|------|------|--------|
| `read_file` | `path: str` | `{success, content, lines, size}` |
| `write_file` | `path: str, content: str, mode: str` | `{success, message, path}` |
| `edit_file` | `path: str, old_text: str, new_text: str, replace_all: bool` | `{success, message, changes}` |

- `mode`：`"write"`（覆盖）或 `"append"`（追加）
- `replace_all`：替换所有匹配项（默认 false）

## 实现细节

### 计算器（安全执行）

```python
import re

def calculate(self, expression: str) -> dict:
    # 仅允许安全字符
    if not re.match(r'^[\d\s\+\-\*/%\.\(\)]+$', expression):
        return {"success": False, "error": "包含非法字符"}

    try:
        # 将 % 替换为 /100 处理百分比
        expr = expression.replace('%', '/100')
        result = eval(expr, {"__builtins__": {}}, {})
        return {"success": True, "result": result, "expression": expression}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### 文档操作

```python
async def read_file(self, path: str) -> dict:
    try:
        p = Path(path)
        content = p.read_text()
        return {
            "success": True,
            "content": content,
            "lines": len(content.splitlines()),
            "size": p.stat().st_size
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

async def write_file(self, path: str, content: str, mode: str = "write") -> dict:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        if mode == "append":
            with open(p, 'a') as f:
                f.write(content)
        else:
            p.write_text(content)

        return {"success": True, "message": f"文件已写入: {path}", "path": str(p)}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def edit_file(self, path: str, old_text: str, new_text: str, replace_all: bool = False) -> dict:
    try:
        p = Path(path)
        content = p.read_text()

        if replace_all:
            count = content.count(old_text)
            content = content.replace(old_text, new_text)
        else:
            count = 1
            content = content.replace(old_text, new_text, 1)

        p.write_text(content)
        return {"success": True, "message": f"已替换 {count} 处", "changes": count}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### Server 注册（server.py）

在 `list_tools()` 中添加：
- `calculate` - 参数：expression
- `read_file` - 参数：path
- `write_file` - 参数：path、content、mode
- `edit_file` - 参数：path、old_text、new_text、replace_all

在 `dispatch_tool()` 中添加：
- 创建 `CalculatorTools` 和 `DocumentTools` 实例
- 分发工具调用到对应方法

## 错误处理

所有方法返回统一错误格式：
```json
{
  "success": false,
  "error": "错误描述"
}
```

## 测试方式

通过 CLI 手动测试：
```bash
# 计算器
text2sql exec-tool calculate --expression "100 * 5 + 20%"

# 文档
text2sql exec-tool read_file --path "/tmp/test.txt"
text2sql exec-tool write_file --path "/tmp/test.txt" --content "Hello"
text2sql exec-tool edit_file --path "/tmp/test.txt" --old "Hello" --new "World"
```

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `src/mcp_server/calculator_tools.py` | 新建文件 |
| `src/mcp_server/document_tools.py` | 新建文件 |
| `src/mcp_server/server.py` | 注册新工具、添加分发逻辑 |
| `src/mcp_server/__init__.py` | 导出新类（可选） |
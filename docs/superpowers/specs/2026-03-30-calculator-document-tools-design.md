# Calculator and Document Tools Design

## Overview

Add two new MCP tools to support general-purpose operations:
- **Calculator**: Basic mathematical calculations
- **Document**: File read/write/edit operations

## Requirements

### Calculator Tool
- Support basic arithmetic: `+`, `-`, `*`, `/`
- Support percentage calculations
- Support parentheses for grouping
- Safe execution (no arbitrary code)

### Document Tool
- Read file content with metadata
- Write/append to files (auto-create directories)
- Edit files (text replacement)
- Allow operations on any path (no restrictions)

## Architecture

### New Components

```
src/mcp_server/
├── tools.py              # SQLExecutorTools (existing)
├── calculator_tools.py   # CalculatorTools (new)
├── document_tools.py     # DocumentTools (new)
└── server.py             # Register new tools (modified)
```

### Tool Definitions

#### CalculatorTools

| Method | Parameters | Returns |
|--------|------------|---------|
| `calculate` | `expression: str` | `{success, result, expression}` |

Input validation:
- Allow: digits, `.`, `+`, `-`, `*`, `/`, `%`, `(`, `)`, spaces
- Reject: letters, underscores, special characters

#### DocumentTools

| Method | Parameters | Returns |
|--------|------------|---------|
| `read_file` | `path: str` | `{success, content, lines, size}` |
| `write_file` | `path: str, content: str, mode: str` | `{success, message, path}` |
| `edit_file` | `path: str, old_text: str, new_text: str, replace_all: bool` | `{success, message, changes}` |

- `mode`: `"write"` (overwrite) or `"append"` (append)
- `replace_all`: replace all occurrences (default: false)

## Implementation Details

### Calculator (Safe Evaluation)

```python
import re

def calculate(self, expression: str) -> dict:
    # Sanitize: only allow safe characters
    if not re.match(r'^[\d\s\+\-\*/%\.\(\)]+$', expression):
        return {"success": False, "error": "Invalid characters"}

    try:
        # Replace % with /100 for percentage
        expr = expression.replace('%', '/100')
        result = eval(expr, {"__builtins__": {}}, {})
        return {"success": True, "result": result, "expression": expression}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### Document Operations

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

        return {"success": True, "message": f"File written: {path}", "path": str(p)}
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
        return {"success": True, "message": f"Replaced {count} occurrences", "changes": count}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### Server Registration (server.py)

Add to `list_tools()`:
- `calculate` - with expression parameter
- `read_file` - with path parameter
- `write_file` - with path, content, mode parameters
- `edit_file` - with path, old_text, new_text, replace_all parameters

Add to `dispatch_tool()`:
- Create instances of `CalculatorTools` and `DocumentTools`
- Route tool calls to appropriate methods

## Error Handling

All methods return consistent error format:
```json
{
  "success": false,
  "error": "Error description"
}
```

## Testing

Manual testing via CLI:
```bash
# Calculator
text2sql exec-tool calculate --expression "100 * 5 + 20%"

# Document
text2sql exec-tool read_file --path "/tmp/test.txt"
text2sql exec-tool write_file --path "/tmp/test.txt" --content "Hello"
text2sql exec-tool edit_file --path "/tmp/test.txt" --old "Hello" --new "World"
```

## Files to Modify

| File | Changes |
|------|---------|
| `src/mcp_server/calculator_tools.py` | New file |
| `src/mcp_server/document_tools.py` | New file |
| `src/mcp_server/server.py` | Register new tools, add dispatch |
| `src/mcp_server/__init__.py` | Export new classes (optional) |
"""Document tools for MCP Server."""

import aiofiles
from pathlib import Path
from typing import Any


class DocumentTools:
    """文档工具集"""

    async def read_file(self, path: str) -> dict[str, Any]:
        """读取文件内容

        Args:
            path: 文件路径（绝对路径或相对路径）

        Returns:
            {"success": True, "content": "...", "lines": 10, "size": 500}
            或 {"success": False, "error": "错误信息"}
        """
        try:
            p = Path(path)

            if not p.exists():
                return {"success": False, "error": f"文件不存在: {path}"}

            if not p.is_file():
                return {"success": False, "error": f"路径不是文件: {path}"}

            async with aiofiles.open(p, mode='r', encoding='utf-8') as f:
                content = await f.read()

            lines = len(content.splitlines())
            size = p.stat().st_size

            return {
                "success": True,
                "content": content,
                "lines": lines,
                "size": size,
                "path": str(p.absolute())
            }
        except PermissionError:
            return {"success": False, "error": f"无权限读取文件: {path}"}
        except UnicodeDecodeError:
            return {"success": False, "error": f"文件编码错误（仅支持 UTF-8）: {path}"}
        except Exception as e:
            return {"success": False, "error": f"读取失败: {str(e)}"}

    async def write_file(
        self,
        path: str,
        content: str,
        mode: str = "write"
    ) -> dict[str, Any]:
        """写入文件

        Args:
            path: 文件路径
            content: 写入内容
            mode: "write"（覆盖）或 "append"（追加）

        Returns:
            {"success": True, "message": "...", "path": "..."}
            或 {"success": False, "error": "错误信息"}
        """
        if mode not in ("write", "append"):
            return {"success": False, "error": f"无效模式: {mode}，支持 'write' 或 'append'"}

        try:
            p = Path(path)

            # 自动创建父目录
            if not p.parent.exists():
                p.parent.mkdir(parents=True, exist_ok=True)

            if mode == "append":
                async with aiofiles.open(p, mode='a', encoding='utf-8') as f:
                    await f.write(content)
                message = f"已追加内容到文件: {path}"
            else:
                async with aiofiles.open(p, mode='w', encoding='utf-8') as f:
                    await f.write(content)
                message = f"已写入文件: {path}"

            return {
                "success": True,
                "message": message,
                "path": str(p.absolute()),
                "mode": mode
            }
        except PermissionError:
            return {"success": False, "error": f"无权限写入文件: {path}"}
        except Exception as e:
            return {"success": False, "error": f"写入失败: {str(e)}"}

    async def edit_file(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False
    ) -> dict[str, Any]:
        """编辑文件（替换文本）

        Args:
            path: 文件路径
            old_text: 要替换的文本
            new_text: 替换后的文本
            replace_all: 是否替换所有匹配项（默认 False）

        Returns:
            {"success": True, "message": "...", "changes": 2}
            或 {"success": False, "error": "错误信息"}
        """
        try:
            p = Path(path)

            if not p.exists():
                return {"success": False, "error": f"文件不存在: {path}"}

            async with aiofiles.open(p, mode='r', encoding='utf-8') as f:
                content = await f.read()

            # 检查是否存在匹配文本
            if old_text not in content:
                return {
                    "success": False,
                    "error": f"未找到匹配文本: '{old_text[:50]}...' (显示前50字符)"
                }

            if replace_all:
                count = content.count(old_text)
                content = content.replace(old_text, new_text)
            else:
                # 只替换第一个匹配
                count = 1
                content = content.replace(old_text, new_text, 1)

            async with aiofiles.open(p, mode='w', encoding='utf-8') as f:
                await f.write(content)

            return {
                "success": True,
                "message": f"已替换 {count} 处匹配",
                "changes": count,
                "path": str(p.absolute())
            }
        except PermissionError:
            return {"success": False, "error": f"无权限编辑文件: {path}"}
        except Exception as e:
            return {"success": False, "error": f"编辑失败: {str(e)}"}
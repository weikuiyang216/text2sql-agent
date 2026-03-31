"""CLI interface for Text-to-SQL Agent."""

import asyncio
import logging
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Prompt

from ..config import config
from ..logging_config import setup_logging, get_logger
from ..agent.core import Text2SQLAgent


console = Console()
logger = get_logger(__name__)


def run_async(coro):
    """运行异步函数"""
    # Initialize logging before running
    setup_logging(
        level=config.LOG_LEVEL,
        log_file=config.LOG_FILE,
        rich_output=config.LOG_RICH_OUTPUT
    )
    return asyncio.run(coro)


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Text-to-SQL Agent - 自然语言转 SQL 查询工具"""
    pass


@cli.command()
@click.option('--db', default=None, help='数据库名称')
@click.option('--verbose', '-v', is_flag=True, help='启用详细日志输出')
def chat(db: Optional[str], verbose: bool):
    """启动交互式对话"""
    # Setup logging with appropriate level
    level = "DEBUG" if verbose else config.LOG_LEVEL
    setup_logging(
        level=level,
        log_file=config.LOG_FILE,
        rich_output=config.LOG_RICH_OUTPUT
    )
    logger.info(f"Starting chat with database: {db or config.DEFAULT_DATABASE}")
    run_async(_chat_async(db))


async def _chat_async(db: Optional[str]):
    """交互式对话实现"""
    db_name = db or config.DEFAULT_DATABASE
    logger.debug(f"Initializing agent with database: {db_name}")

    console.print(Panel.fit(
        "[bold blue]Text-to-SQL Agent[/bold blue]\n"
        f"数据库: [green]{db_name}[/green]\n"
        "输入问题进行查询，输入 help 查看命令，quit 退出",
        title="欢迎使用"
    ))

    agent = Text2SQLAgent()
    logger.debug("Agent initialized")

    try:
        # 切换数据库
        if db_name != config.DEFAULT_DATABASE:
            result = await agent.switch_database(db_name)
            if not result.get("success"):
                logger.error(f"Failed to switch database: {result.get('error')}")
                console.print(f"[red]切换数据库失败: {result.get('error')}[/red]")
                return
            logger.info(f"Switched to database: {db_name}")

        while True:
            try:
                question = Prompt.ask("\n[cyan]问题[/cyan]")

                if not question.strip():
                    continue

                # 处理命令（支持 :help 或 help 两种格式）
                cmd_raw = question.strip().lower()
                cmd = cmd_raw if cmd_raw.startswith(':') else f':{cmd_raw}'

                # 命令列表
                if cmd in (':quit', ':q', ':exit'):
                    console.print("[yellow]再见！[/yellow]")
                    break
                elif cmd == ':help':
                    _show_help()
                    continue
                elif cmd in (':dbs', ':db', ':databases'):
                    await _list_databases(agent)
                    continue
                elif cmd.startswith(':use ') or cmd.startswith('use '):
                    # 支持两种格式
                    if question.lower().startswith('use '):
                        new_db = question[4:].strip()
                    else:
                        new_db = question[5:].strip()
                    result = await agent.switch_database(new_db)
                    if result.get("success"):
                        db_name = new_db
                        console.print(f"[green]已切换到数据库: {new_db}[/green]")
                    else:
                        console.print(f"[red]{result.get('error')}[/red]")
                    continue
                elif cmd == ':schema':
                    schema = await agent.get_schema_text()
                    console.print(Panel(schema, title="数据库 Schema"))
                    continue
                elif cmd == ':clear':
                    agent.history.clear()
                    console.print("[green]对话历史已清空[/green]")
                    continue
                elif cmd.startswith(':'):
                    console.print(f"[red]未知命令: {question}[/red]")
                    console.print("[dim]输入 :help 查看可用命令[/dim]")
                    continue

                # 处理问题
                logger.debug(f"Processing question: {question}")
                with console.status("[bold green]生成 SQL...[/bold green]"):
                    result = await agent.chat(question, auto_fix=True, explain=True)

                logger.debug(f"SQL generated: {result.get('sql', '')}")
                logger.debug(f"Result success: {result.get('success', False)}")

                # 显示 SQL
                sql = result.get("sql", "")
                if sql:
                    console.print("\n[bold]SQL:[/bold]")
                    syntax = Syntax(sql, "sql", theme="monokai", line_numbers=False)
                    console.print(syntax)

                # 显示结果
                data = result.get("result", {})
                if data.get("success"):
                    _display_result(data)
                else:
                    console.print(f"[red]执行失败: {data.get('error')}[/red]")

                # 显示解释
                if result.get("explanation"):
                    console.print(f"\n[dim]解释: {result['explanation']}[/dim]")

            except KeyboardInterrupt:
                console.print("\n[yellow]按 Ctrl+C 再次退出，或继续输入问题[/yellow]")
            except Exception as e:
                console.print(f"[red]错误: {e}[/red]")

    finally:
        await agent.close()


def _show_help():
    """显示帮助信息"""
    help_text = """
[bold]命令列表:[/bold]
  help       显示帮助信息
  quit       退出程序
  dbs        列出所有数据库
  use <db>   切换数据库
  schema     显示当前数据库结构
  clear      清空对话历史

[bold]注意:[/bold] 命令支持带或不带 : 前缀
  help 和 :help 效果相同

[bold]使用示例:[/bold]
  找出所有价格低于5元的商品
  统计每个客户的消费总额
  查询最近7天的销售记录
"""
    console.print(Panel(help_text, title="帮助"))


async def _list_databases(agent: Text2SQLAgent):
    """列出数据库"""
    dbs = await agent.list_databases()
    table = Table(title="可用数据库")
    table.add_column("序号", style="cyan")
    table.add_column("数据库名", style="green")
    for i, db in enumerate(dbs[:20], 1):  # 只显示前20个
        table.add_row(str(i), db)
    if len(dbs) > 20:
        table.add_row("...", f"还有 {len(dbs) - 20} 个")
    console.print(table)


def _display_result(data: dict):
    """显示查询结果"""
    columns = data.get("columns", [])
    rows = data.get("rows", [])
    row_count = data.get("row_count", 0)

    if not columns:
        console.print(f"[green]{data.get('message', '执行成功')}[/green]")
        return

    table = Table(title=f"查询结果 ({row_count} 行)")
    for col in columns:
        table.add_column(col, style="cyan")

    # 只显示前20行
    for row in rows[:20]:
        table.add_row(*[str(v) if v is not None else "NULL" for v in row])

    if len(rows) > 20:
        table.add_row(*["..." for _ in columns])

    console.print(table)


@cli.command()
def list_db():
    """列出所有可用数据库"""
    dbs = config.list_databases()
    table = Table(title="可用数据库")
    table.add_column("序号", style="cyan")
    table.add_column("数据库名", style="green")
    table.add_column("状态", style="yellow")

    for i, db in enumerate(dbs[:20], 1):
        db_path = config.get_db_path(db)
        status = "✓" if db_path.exists() else "✗"
        table.add_row(str(i), db, status)

    console.print(table)
    console.print(f"\n共 {len(dbs)} 个数据库")


@cli.command()
@click.argument('sql')
@click.option('--db', default=None, help='数据库名称')
def exec(sql: str, db: Optional[str]):
    """直接执行 SQL"""
    run_async(_exec_async(sql, db))


async def _exec_async(sql: str, db: Optional[str]):
    """执行 SQL 实现"""
    db_name = db or config.DEFAULT_DATABASE
    agent = Text2SQLAgent()

    try:
        if db_name != config.DEFAULT_DATABASE:
            await agent.switch_database(db_name)

        result = await agent.execute_sql(sql)

        if result.get("success"):
            _display_result(result)
        else:
            console.print(f"[red]执行失败: {result.get('error')}[/red]")

    finally:
        await agent.close()


@cli.command()
@click.option('--db', default=None, help='数据库名称')
def schema(db: Optional[str]):
    """显示数据库结构"""
    run_async(_schema_async(db))


async def _schema_async(db: Optional[str]):
    """显示 Schema 实现"""
    db_name = db or config.DEFAULT_DATABASE
    agent = Text2SQLAgent()

    try:
        if db_name != config.DEFAULT_DATABASE:
            await agent.switch_database(db_name)

        schema_text = await agent.get_schema_text()
        console.print(Panel(schema_text, title=f"数据库: {db_name}"))

    finally:
        await agent.close()


if __name__ == '__main__':
    cli()
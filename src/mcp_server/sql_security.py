"""SQL security validation and execution with safety limits."""

import re
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import aiosqlite
from pathlib import Path

logger = logging.getLogger(__name__)


class SQLStatementType(Enum):
    """SQL statement types."""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    OTHER = "OTHER"


def _default_allowed_types() -> set[SQLStatementType]:
    """Default factory for allowed_types field."""
    return {SQLStatementType.SELECT}


def _read_write_allowed_types() -> set[SQLStatementType]:
    """Factory for read-write allowed types."""
    return {SQLStatementType.SELECT, SQLStatementType.INSERT, SQLStatementType.UPDATE, SQLStatementType.DELETE}


@dataclass
class SQLSecurityConfig:
    """Configuration for SQL security."""
    # Allowed statement types (default: only SELECT)
    allowed_types: set[SQLStatementType] = field(default_factory=_default_allowed_types)
    # Maximum rows to return
    max_rows: int = 1000
    # Execution timeout in seconds
    timeout_seconds: float = 30.0
    # Whether to allow multiple statements (separated by ;)
    allow_multiple: bool = False
    # Maximum SQL length
    max_sql_length: int = 10000


# Default read-only config
READ_ONLY_CONFIG = SQLSecurityConfig()

# Config allowing write operations
READ_WRITE_CONFIG = SQLSecurityConfig(
    allowed_types=_read_write_allowed_types()
)


# Dangerous SQL patterns that should always be blocked
DANGEROUS_PATTERNS = [
    # Schema modifications
    r'\bDROP\b',
    r'\bALTER\b',
    r'\bCREATE\b',
    r'\bTRUNCATE\b',
    r'\bGRANT\b',
    r'\bREVOKE\b',
    # System tables
    r'\bsqlite_master\b',
    r'\bsqlite_sequence\b',
    r'\bsqlite_temp_master\b',
    # SQL injection patterns
    r';.*;',  # Multiple statements
    r'--',   # SQL comment
    r'/\*',  # Block comment start
    r'\*/',  # Block comment end
    r'\bEXEC\b',
    r'\bEXECUTE\b',
    r'\bCALL\b',
]

# Statement type detection patterns
STATEMENT_PATTERNS = {
    SQLStatementType.SELECT: r'^\s*SELECT\b',
    SQLStatementType.INSERT: r'^\s*INSERT\b',
    SQLStatementType.UPDATE: r'^\s*UPDATE\b',
    SQLStatementType.DELETE: r'^\s*DELETE\b',
}


@dataclass
class ValidationResult:
    """Result of SQL validation."""
    valid: bool
    statement_type: SQLStatementType = SQLStatementType.OTHER
    error: str | None = None
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def detect_statement_type(sql: str) -> SQLStatementType:
    """Detect the type of SQL statement."""
    normalized = sql.strip().upper()
    for stmt_type, pattern in STATEMENT_PATTERNS.items():
        if re.match(pattern, normalized, re.IGNORECASE):
            return stmt_type
    return SQLStatementType.OTHER


def validate_sql(sql: str, config: SQLSecurityConfig) -> ValidationResult:
    """Validate SQL for security issues.

    Args:
        sql: SQL statement to validate
        config: Security configuration

    Returns:
        ValidationResult with validation status and details
    """
    warnings = []

    # Check SQL length
    if len(sql) > config.max_sql_length:
        return ValidationResult(
            valid=False,
            error=f"SQL 太长（{len(sql)} 字符），最大允许 {config.max_sql_length} 字符"
        )

    # Check for empty SQL
    if not sql.strip():
        return ValidationResult(
            valid=False,
            error="SQL 语句为空"
        )

    # Detect statement type
    stmt_type = detect_statement_type(sql)

    # Check if statement type is allowed
    if stmt_type not in config.allowed_types:
        allowed_names = [t.value for t in config.allowed_types]
        return ValidationResult(
            valid=False,
            statement_type=stmt_type,
            error=f"不允许执行 {stmt_type.value} 语句，只允许: {', '.join(allowed_names)}"
        )

    # Check for dangerous patterns
    normalized = sql.upper()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return ValidationResult(
                valid=False,
                statement_type=stmt_type,
                error=f"SQL 包含禁止的操作模式: {pattern}"
            )

    # Check for multiple statements
    if config.allow_multiple:
        if ';' in sql.strip() and not sql.strip().endswith(';'):
            statements = sql.split(';')
            if len(statements) > 1:
                for stmt in statements:
                    if stmt.strip():
                        stmt_type_check = detect_statement_type(stmt)
                        if stmt_type_check not in config.allowed_types:
                            return ValidationResult(
                                valid=False,
                                statement_type=stmt_type,
                                error=f"多语句中包含不允许的类型: {stmt_type_check.value}"
                            )
    else:
        # Single statement mode - check for semicolon in middle
        stripped = sql.strip()
        if ';' in stripped and not stripped.endswith(';'):
            return ValidationResult(
                valid=False,
                statement_type=stmt_type,
                error="禁止执行多条 SQL 语句"
            )

    # Add informational warnings
    if stmt_type == SQLStatementType.DELETE:
        warnings.append("DELETE 语句将删除数据")
    elif stmt_type == SQLStatementType.UPDATE:
        warnings.append("UPDATE 语句将修改数据")
    elif stmt_type == SQLStatementType.INSERT:
        warnings.append("INSERT 语句将插入数据")

    return ValidationResult(
        valid=True,
        statement_type=stmt_type,
        warnings=warnings
    )


async def execute_sql_safe(
    db_path: Path,
    sql: str,
    config: SQLSecurityConfig = READ_ONLY_CONFIG
) -> dict[str, Any]:
    """Execute SQL with security validation and limits.

    Args:
        db_path: Path to SQLite database
        sql: SQL statement to execute
        config: Security configuration

    Returns:
        Execution result with success status and data
    """
    # Validate SQL
    validation = validate_sql(sql, config)
    if not validation.valid:
        logger.warning(f"SQL validation failed: {validation.error}")
        return {
            "success": False,
            "error": validation.error,
            "statement_type": validation.statement_type.value,
            "sql": sql[:200] + "..." if len(sql) > 200 else sql
        }

    if validation.warnings:
        for warning in validation.warnings:
            logger.info(f"SQL warning: {warning}")

    if not db_path.exists():
        return {
            "success": False,
            "error": f"数据库文件不存在: {db_path}"
        }

    try:
        # Execute with timeout
        async with aiosqlite.connect(db_path) as db:
            # Set timeout
            db.timeout = config.timeout_seconds

            # Execute SQL
            async with db.execute(sql) as cursor:
                # Check if statement returns data (SELECT)
                if cursor.description:
                    columns = [d[0] for d in cursor.description]

                    # Fetch all rows
                    all_rows = await cursor.fetchall()
                    actual_count = len(all_rows)

                    # Truncate if exceeds limit
                    if actual_count > config.max_rows:
                        logger.warning(f"Result truncated: {actual_count} -> {config.max_rows} rows")
                        rows = [list(row) for row in all_rows[:config.max_rows]]
                        truncated = True
                    else:
                        rows = [list(row) for row in all_rows]
                        truncated = False

                    return {
                        "success": True,
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(rows),
                        "total_rows": actual_count,
                        "truncated": truncated,
                        "statement_type": validation.statement_type.value
                    }
                else:
                    # INSERT/UPDATE/DELETE - commit and return affected rows
                    await db.commit()
                    return {
                        "success": True,
                        "message": f"执行成功，影响 {cursor.rowcount} 行",
                        "row_count": cursor.rowcount,
                        "statement_type": validation.statement_type.value
                    }

    except asyncio.TimeoutError:
        logger.error(f"SQL execution timeout after {config.timeout_seconds}s")
        return {
            "success": False,
            "error": f"执行超时（{config.timeout_seconds}秒）",
            "sql": sql[:200] + "..." if len(sql) > 200 else sql
        }
    except aiosqlite.Error as e:
        logger.error(f"SQL execution error: {e}")
        return {
            "success": False,
            "error": str(e),
            "sql": sql[:200] + "..." if len(sql) > 200 else sql
        }
    except Exception as e:
        logger.error(f"Unexpected error during SQL execution: {e}")
        return {
            "success": False,
            "error": f"执行失败: {str(e)}",
            "sql": sql[:200] + "..." if len(sql) > 200 else sql
        }
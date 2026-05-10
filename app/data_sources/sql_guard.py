# app/data_sources/sql_guard.py

from __future__ import annotations

import re


ALLOWED_FIRST = {"SELECT", "SHOW", "EXPLAIN", "WITH"}

BLOCKED_KEYWORDS = {
    "ALTER", "ANALYZE", "BEGIN", "CALL", "CLUSTER", "COMMENT", "COMMIT", "COPY",
    "CREATE", "DEALLOCATE", "DELETE", "DISCARD", "DO", "DROP", "EXECUTE", "GRANT",
    "INSERT", "LOCK", "MERGE", "PREPARE", "REFRESH", "REINDEX", "RELEASE", "RESET",
    "REVOKE", "ROLLBACK", "SAVEPOINT", "SET", "TRUNCATE", "UPDATE", "VACUUM",
}


def strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*[\s\S]*?\*/", " ", sql)
    sql = re.sub(r"--.*$", " ", sql, flags=re.MULTILINE)
    return sql.strip()


def mask_sql_strings(sql: str) -> str:
    sql = re.sub(r"\$[^$]*\$[\s\S]*?\$[^$]*\$", " ", sql)
    sql = re.sub(r"'(?:''|[^'])*'", " ", sql)
    sql = re.sub(r'"(?:""|[^"])*"', " ", sql)
    return sql


def validate_readonly_sql(sql: str) -> str:
    stripped = strip_sql_comments(sql)

    if not stripped:
        raise ValueError("SQL is empty.")

    body = re.sub(r";+\s*$", "", stripped).strip()

    if ";" in body:
        raise ValueError("Only a single SQL statement is allowed.")

    masked = mask_sql_strings(body)
    tokens = [item.upper() for item in re.findall(r"[A-Za-z_]+", masked)]

    if not tokens:
        raise ValueError("Unable to detect SQL keywords.")

    if tokens[0] not in ALLOWED_FIRST:
        raise ValueError("Only SELECT, SHOW, EXPLAIN, or WITH statements are allowed.")

    bad = next((token for token in tokens if token in BLOCKED_KEYWORDS), None)
    if bad:
        raise ValueError(f"Blocked keyword detected: {bad}")

    return body
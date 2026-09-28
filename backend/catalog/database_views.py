from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView


SENSITIVE_COLUMN_MARKERS = ("password", "secret", "token", "session_data", "credential", "cookie")
MAX_CELL_LENGTH = 4000


def _table_inventory():
    with connection.cursor() as cursor:
        return [table for table in connection.introspection.get_table_list(cursor) if table.type in {"t", "v"}]


def _get_table(table_name: str):
    table = next((item for item in _table_inventory() if item.name == table_name), None)
    if table is None:
        raise NotFound("数据表不存在。")
    return table


def _row_count(cursor, table_name: str) -> int:
    cursor.execute(f"SELECT COUNT(*) FROM {connection.ops.quote_name(table_name)}")
    return int(cursor.fetchone()[0])


def _is_sensitive(column_name: str) -> bool:
    normalized = column_name.casefold()
    return any(marker in normalized for marker in SENSITIVE_COLUMN_MARKERS)


def _safe_value(column_name: str, value):
    if value is None:
        return None
    if _is_sensitive(column_name):
        return "[已隐藏]"
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return f"[二进制数据 · {len(value)} bytes]"
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, cls=DjangoJSONEncoder)
    elif not isinstance(value, (str, int, float, bool, Decimal, date, datetime, time)):
        value = str(value)
    if isinstance(value, str) and len(value) > MAX_CELL_LENGTH:
        return value[:MAX_CELL_LENGTH] + f"…（已截断，共 {len(value)} 字符）"
    return value


def _column_metadata(cursor, table_name: str):
    description = connection.introspection.get_table_description(cursor, table_name)
    constraints = connection.introspection.get_constraints(cursor, table_name)
    primary_columns = {
        column
        for constraint in constraints.values()
        if constraint.get("primary_key")
        for column in constraint.get("columns", [])
    }
    foreign_keys = {
        column: f"{constraint['foreign_key'][0]}.{constraint['foreign_key'][1]}"
        for constraint in constraints.values()
        if constraint.get("foreign_key")
        for column in constraint.get("columns", [])
    }
    columns = []
    for field in description:
        try:
            data_type = connection.introspection.get_field_type(field.type_code, field)
        except (KeyError, TypeError):
            data_type = str(field.type_code)
        columns.append({
            "name": field.name,
            "data_type": data_type,
            "nullable": bool(field.null_ok),
            "primary_key": field.name in primary_columns,
            "foreign_key": foreign_keys.get(field.name),
            "default": _safe_value(field.name, field.default),
            "sensitive": _is_sensitive(field.name),
        })
    return columns


class DatabaseTablesView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        tables = []
        with connection.cursor() as cursor:
            for table in _table_inventory():
                tables.append({
                    "name": table.name,
                    "table_type": "view" if table.type == "v" else "table",
                    "row_count": _row_count(cursor, table.name),
                })
        return Response({"vendor": connection.vendor, "tables": tables})


class DatabaseTableRowsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, table_name: str):
        table = _get_table(table_name)
        page = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("page", 1))
        page_size = serializers.IntegerField(min_value=10, max_value=100).run_validation(request.query_params.get("page_size", 25))
        offset = (page - 1) * page_size
        quoted_table = connection.ops.quote_name(table.name)

        with connection.cursor() as cursor:
            columns = _column_metadata(cursor, table.name)
            total_rows = _row_count(cursor, table.name)
            order_columns = [column["name"] for column in columns if column["primary_key"]]
            order_sql = ""
            if order_columns:
                order_sql = " ORDER BY " + ", ".join(connection.ops.quote_name(name) for name in order_columns)
            cursor.execute(f"SELECT * FROM {quoted_table}{order_sql} LIMIT %s OFFSET %s", [page_size, offset])
            names = [column[0] for column in cursor.description]
            rows = [
                {name: _safe_value(name, value) for name, value in zip(names, values)}
                for values in cursor.fetchall()
            ]

        return Response({
            "vendor": connection.vendor,
            "table": table.name,
            "table_type": "view" if table.type == "v" else "table",
            "page": page,
            "page_size": page_size,
            "total_rows": total_rows,
            "total_pages": max(1, (total_rows + page_size - 1) // page_size),
            "columns": columns,
            "rows": rows,
        })

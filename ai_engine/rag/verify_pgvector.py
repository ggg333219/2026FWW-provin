#!/usr/bin/env python3
"""
PGVector 环境验证脚本 (verify_pgvector.py)

快速检查 PostgreSQL + pgvector 是否就绪：
    python ai_engine/rag/verify_pgvector.py

通过: 退出码 0
跳过/失败: 退出码 1
"""

from __future__ import annotations

import os
import sys


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not ok else ""))
    return ok


def main() -> int:
    all_ok = True

    print("PGVector 环境验证")
    print("=" * 50)

    # 1. psycopg2
    try:
        import psycopg2
        all_ok &= check("psycopg2-binary 已安装", True)
    except ImportError:
        check("psycopg2-binary 已安装", False, "pip install psycopg2-binary pgvector")
        return 1

    # 2. pgvector Python 包
    try:
        import pgvector  # noqa
        all_ok &= check("pgvector Python 包已安装", True)
    except ImportError:
        check("pgvector Python 包已安装", False, "pip install pgvector")
        all_ok = False

    # 3. PostgreSQL 连接
    conn_string = (
        f"postgresql://"
        f"{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '123456')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
        f"/{os.getenv('DB_NAME', 'teaching')}"
    )

    try:
        conn = psycopg2.connect(conn_string, connect_timeout=5)
        all_ok &= check("PostgreSQL 可连接", True)
        conn.close()
    except Exception as e:
        check("PostgreSQL 可连接", False, str(e))
        return 1

    # 4. pgvector 扩展
    try:
        conn = psycopg2.connect(conn_string, connect_timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        has_ext = cur.fetchone() is not None
        all_ok &= check("pgvector 扩展已安装", has_ext,
                        "运行: CREATE EXTENSION IF NOT EXISTS vector;")
        cur.close()
        conn.close()
    except Exception as e:
        check("pgvector 扩展检查", False, str(e))
        all_ok = False

    # 5. halfvec 类型支持
    try:
        conn = psycopg2.connect(conn_string, connect_timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT '[0.1,0.2]'::halfvec(2)")
        result = cur.fetchone()
        all_ok &= check("halfvec 类型可用", result is not None)
        cur.close()
        conn.close()
    except Exception as e:
        check("halfvec 类型可用", False, str(e))
        all_ok = False

    print("=" * 50)
    if all_ok:
        print("全部就绪！可以运行: python ai_engine/tests/test_pgvector_live.py")
        return 0
    else:
        print("环境未就绪，请根据上述 FAIL 项修复")
        return 1


if __name__ == "__main__":
    sys.exit(main())

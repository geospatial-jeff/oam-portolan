"""Run every SQL recipe in the catalog's AGENTS.md files against the built catalog.

Usage: python -m oam_mirror.verify_docs catalog/

A recipe fails when DuckDB errors or returns no rows. The bootstrap rule is
that a documented query that fails is fixed or deleted, never published.
"""

import argparse
import glob
import os
import re
import subprocess
import sys

SQL_BLOCK = re.compile(r"```sql\n(.*?)```", re.S)


def sql_blocks(markdown):
    return [block.strip() for block in SQL_BLOCK.findall(markdown)]


def localize(sql, public_url, catalog_root):
    """Point published URLs in a recipe at the local tree, to test before a push."""
    return sql.replace(public_url, os.path.abspath(catalog_root) + "/")


def run_sql(catalog_root, sql):
    """Return (ok, output). ok means DuckDB succeeded and printed at least one data row."""
    result = subprocess.run(["duckdb", "-csv", "-c", sql], cwd=catalog_root, capture_output=True, text=True)
    if result.returncode != 0:
        return False, result.stderr.strip()
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # -csv prints a header per statement; INSTALL/LOAD print nothing.
    return len(lines) >= 2, result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("catalog")
    parser.add_argument("--local", metavar="PUBLIC_URL", help="read PUBLIC_URL from the local catalog instead of the network")
    args = parser.parse_args()
    paths = [os.path.join(args.catalog, "AGENTS.md")] + sorted(glob.glob(os.path.join(args.catalog, "*", "AGENTS.md")))
    failures = 0
    for path in paths:
        with open(path) as f:
            blocks = sql_blocks(f.read())
        for index, sql in enumerate(blocks, 1):
            if args.local:
                sql = localize(sql, args.local, args.catalog)
            ok, output = run_sql(args.catalog, sql)
            status = "ok" if ok else "FAIL"
            first = output.splitlines()[1] if ok and len(output.splitlines()) > 1 else output[:300]
            print(f"{status} {os.path.relpath(path, args.catalog)} recipe {index}: {first}")
            failures += not ok
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

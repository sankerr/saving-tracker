#!/usr/bin/env python3
"""Import existing JSON portfolio files into Neon PostgreSQL."""

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from repo root or scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import auth
import db
from saving_tracker import default_cache, default_data


def main():
    parser = argparse.ArgumentParser(description="Migrate saving-tracker JSON files to PostgreSQL")
    parser.add_argument("--data", required=True, help="Path to saving-tracker-data.json")
    parser.add_argument("--cache", required=True, help="Path to saving-tracker-cache.json")
    parser.add_argument("--username", default=os.environ.get("ADMIN_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD", ""))
    args = parser.parse_args()

    if not db.DATABASE_URL:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)
    if not args.username or not args.password:
        print("ERROR: set --username/--password or ADMIN_USERNAME/ADMIN_PASSWORD", file=sys.stderr)
        sys.exit(1)

    data_path = Path(args.data)
    cache_path = Path(args.cache)
    if not data_path.exists():
        print(f"ERROR: data file not found: {data_path}", file=sys.stderr)
        sys.exit(1)
    if not cache_path.exists():
        print(f"ERROR: cache file not found: {cache_path}", file=sys.stderr)
        sys.exit(1)

    with data_path.open(encoding="utf-8") as f:
        data = json.load(f)
    with cache_path.open(encoding="utf-8") as f:
        cache = json.load(f)

    if not isinstance(data, dict) or "version" not in data:
        print("ERROR: invalid data JSON", file=sys.stderr)
        sys.exit(1)
    if not isinstance(cache, dict):
        print("ERROR: invalid cache JSON", file=sys.stderr)
        sys.exit(1)

    db.init_schema()
    existing = db.get_user_by_username(args.username)
    if existing:
        user_id = existing["id"]
        print(f"User exists: {args.username} (id={user_id})")
    else:
        user_id = db.create_user(args.username, auth.hash_password(args.password))
        print(f"Created user: {args.username} (id={user_id})")

    db.upsert_state(user_id, data, cache)
    print("Migration complete.")
    print(f"  fund_holdings: {len(data.get('fund_holdings', []))}")
    print(f"  rsu_grants:    {len(data.get('rsu_grants', []))}")
    print(f"  espp_plans:    {len(data.get('espp_plans', []))}")
    print(f"  cash_holdings: {len(data.get('cash_holdings', []))}")


if __name__ == "__main__":
    main()

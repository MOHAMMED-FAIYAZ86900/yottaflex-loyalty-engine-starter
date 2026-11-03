import csv
import json
import hashlib
import sqlite3
from pathlib import Path

DB = Path("data/loyalty_phase4.db")
OUT = Path("exports/dataset")
OUT.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

manifest = {
    "database": str(DB),
    "tables": {},
    "exports": {},
}

try:
    tables = [
        row[0] for row in conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
    ]

    for table in tables:
        rows = [
            dict(row) for row in conn.execute(
                f'SELECT * FROM "{table}"'
            )
        ]

        csv_path = OUT / f"{table}.csv"
        json_path = OUT / f"{table}.json"

        if rows:
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
        else:
            csv_path.write_text("", encoding="utf-8")

        with json_path.open("w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False, default=str)

        manifest["tables"][table] = {
            "row_count": len(rows),
            "columns": list(rows[0].keys()) if rows else [],
        }

        for path in (csv_path, json_path):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest["exports"][str(path)] = {
                "sha256": digest,
                "bytes": path.stat().st_size,
            }

    sql_path = OUT / "loyalty_dataset.sql"
    with sql_path.open("w", encoding="utf-8") as f:
        for line in conn.iterdump():
            f.write(line + "\n")

    manifest["exports"][str(sql_path)] = {
        "sha256": hashlib.sha256(sql_path.read_bytes()).hexdigest(),
        "bytes": sql_path.stat().st_size,
    }

    manifest_path = OUT / "source_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("PHASE 6 EXPORT COMPLETE")
    print("-----------------------")
    print("Tables exported:", len(tables))
    print("Output directory:", OUT)
    for table, details in manifest["tables"].items():
        print(f"{table}: {details['row_count']} rows")
    print("SQL dump:", sql_path)
    print("Manifest:", manifest_path)

finally:
    conn.close()

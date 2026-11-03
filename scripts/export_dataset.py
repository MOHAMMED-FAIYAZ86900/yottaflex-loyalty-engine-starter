import csv
import gzip
import hashlib
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "loyalty_phase4.db"
OUT = ROOT / "exports" / "dataset"
MANIFEST_PATH = OUT / "source_manifest.json"

OUT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------
# Utility functions
# ---------------------------------------------------------

def sha256_file(path: Path) -> str:
    """Calculate SHA-256 without loading the entire file."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def relative_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def get_git_index_files() -> set[str]:
    """Return paths currently staged or tracked in Git's index."""
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--cached", "-z"],
            capture_output=True,
            check=True,
        )

        return {
            item.decode("utf-8").replace("\\", "/")
            for item in result.stdout.split(b"\0")
            if item
        }

    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()


def compress_file(source: Path, destination: Path) -> None:
    """Create deterministic gzip output with no source filename or timestamp."""
    with source.open("rb") as source_file:
        with destination.open("wb") as raw_output:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_output,
                compresslevel=9,
                mtime=0,
            ) as compressed:
                shutil.copyfileobj(source_file, compressed)


def verify_gzip_matches_source(
    source: Path,
    compressed_path: Path,
) -> bool:
    """Verify decompressed gzip content matches the source byte-for-byte."""
    with source.open("rb") as original:
        with gzip.open(compressed_path, "rb") as decompressed:
            while True:
                original_chunk = original.read(1024 * 1024)
                decompressed_chunk = decompressed.read(1024 * 1024)

                if original_chunk != decompressed_chunk:
                    return False

                if not original_chunk:
                    return True


def export_format(path: Path) -> str:
    name = path.name.lower()

    if name.endswith(".sql.gz"):
        return "SQL_GZIP"

    if name.endswith(".csv.gz"):
        return "CSV_GZIP"

    return path.suffix.lstrip(".").upper()


def export_metadata(path: Path, git_files: set[str]) -> dict:
    relative = relative_path(path)
    tracked = relative in git_files

    if path.name == "loyalty_dataset.sql.gz":
        publication_intent = "public_compressed_sql_export"
    elif path.name == "loyalty_dataset.sql":
        publication_intent = "local_uncompressed_sql_source"
    else:
        publication_intent = "dataset_export"

    return {
        "path": relative,
        "format": export_format(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "repository_status": (
            "tracked_in_git_index"
            if tracked
            else "local_only_not_tracked"
        ),
        "publication_intent": publication_intent,
    }


# ---------------------------------------------------------
# Validate database
# ---------------------------------------------------------

if not DB.exists():
    raise FileNotFoundError(
        f"Database not found: {DB}\n"
        "Generate the dataset before exporting."
    )

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

try:
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

    if integrity != "ok":
        raise RuntimeError(
            f"Database integrity check failed: {integrity}"
        )

    foreign_key_errors = conn.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if foreign_key_errors:
        raise RuntimeError(
            f"Database contains {len(foreign_key_errors)} "
            "foreign-key violations."
        )

    tables = [
        row[0]
        for row in conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
    ]

    if not tables:
        raise RuntimeError("No application tables found.")

    manifest = {
        "manifest_version": "3.0",
        "project": "YottaFlex Loyalty Engine",
        "database": relative_path(DB),
        "database_integrity": integrity,
        "foreign_key_violations": len(foreign_key_errors),
        "random_seed": 20261022,
        "table_count": len(tables),
        "tables": {},
        "exports": {},
        "publication_summary": {
            "tracked_in_git_index": [],
            "local_only_not_tracked": [],
            "important_note": (
                "tracked_in_git_index means a file is staged or "
                "tracked locally by Git. It does not independently "
                "prove that the latest version has been pushed to "
                "GitHub. Verify the remote repository after pushing."
            ),
        },
        "sql_export": {
            "uncompressed_path": (
                "exports/dataset/loyalty_dataset.sql"
            ),
            "compressed_path": (
                "exports/dataset/loyalty_dataset.sql.gz"
            ),
            "compression": "gzip",
            "compression_level": 9,
            "deterministic_timestamp": 0,
            "decompression_verified": False,
        },
        "manifest_note": (
            "The manifest itself is excluded from its own exports "
            "hash list to avoid recursive self-hashing."
        ),
    }

    generated_paths = []

    # -----------------------------------------------------
    # Export each table as CSV and JSON
    # -----------------------------------------------------

    print("Starting dataset export...")
    print("------------------------------------")

    for table in tables:
        cursor = conn.execute(f'SELECT * FROM "{table}"')
        columns = [
            description[0]
            for description in cursor.description
        ]
        rows = [dict(row) for row in cursor.fetchall()]

        csv_path = OUT / f"{table}.csv"
        json_path = OUT / f"{table}.json"

        with csv_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            if columns:
                writer = csv.DictWriter(
                    file,
                    fieldnames=columns,
                )
                writer.writeheader()
                writer.writerows(rows)

        with json_path.open("w", encoding="utf-8") as file:
            json.dump(
                rows,
                file,
                indent=2,
                ensure_ascii=False,
                default=str,
            )

        manifest["tables"][table] = {
            "row_count": len(rows),
            "columns": columns,
        }

        generated_paths.extend([csv_path, json_path])

        print(f"{table}: {len(rows):,} rows")

    # -----------------------------------------------------
    # Compress points transaction CSV
    # -----------------------------------------------------

    transaction_csv = OUT / "points_transaction.csv"
    transaction_gzip = OUT / "points_transaction.csv.gz"

    if transaction_csv.exists():
        compress_file(transaction_csv, transaction_gzip)

        if not verify_gzip_matches_source(
            transaction_csv,
            transaction_gzip,
        ):
            raise RuntimeError(
                "Points transaction CSV gzip verification failed."
            )

        generated_paths.append(transaction_gzip)
        print("Verified compressed transaction CSV.")

    # -----------------------------------------------------
    # Generate SQL dump
    # -----------------------------------------------------

    sql_path = OUT / "loyalty_dataset.sql"

    print("Generating SQL dump...")

    with sql_path.open("w", encoding="utf-8", newline="\n") as file:
        for line in conn.iterdump():
            file.write(line + "\n")

    generated_paths.append(sql_path)

    print("SQL dump generated:", sql_path.name)

    # -----------------------------------------------------
    # Compress SQL dump
    # -----------------------------------------------------

    sql_gzip_path = OUT / "loyalty_dataset.sql.gz"

    print("Compressing SQL dump...")

    compress_file(sql_path, sql_gzip_path)

    if not verify_gzip_matches_source(sql_path, sql_gzip_path):
        raise RuntimeError(
            "SQL gzip verification failed: decompressed content "
            "does not match the original SQL dump."
        )

    generated_paths.append(sql_gzip_path)

    manifest["sql_export"]["decompression_verified"] = True
    manifest["sql_export"]["original_bytes"] = sql_path.stat().st_size
    manifest["sql_export"]["compressed_bytes"] = (
        sql_gzip_path.stat().st_size
    )
    manifest["sql_export"]["original_sha256"] = sha256_file(sql_path)
    manifest["sql_export"]["compressed_sha256"] = (
        sha256_file(sql_gzip_path)
    )

    print("SQL compression verified.")
    print("Original SQL bytes:", sql_path.stat().st_size)
    print("Compressed SQL bytes:", sql_gzip_path.stat().st_size)

    # -----------------------------------------------------
    # Build export metadata
    # -----------------------------------------------------

    git_files = get_git_index_files()

    for path in generated_paths:
        metadata = export_metadata(path, git_files)
        key = metadata["path"]

        manifest["exports"][key] = metadata

        if metadata["repository_status"] == "tracked_in_git_index":
            manifest["publication_summary"][
                "tracked_in_git_index"
            ].append(key)
        else:
            manifest["publication_summary"][
                "local_only_not_tracked"
            ].append(key)

    # -----------------------------------------------------
    # Save manifest
    # -----------------------------------------------------

    with MANIFEST_PATH.open("w", encoding="utf-8") as file:
        json.dump(
            manifest,
            file,
            indent=2,
            ensure_ascii=False,
        )

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    print("------------------------------------")
    print("DATASET EXPORT COMPLETE")
    print("------------------------------------")
    print("Database:", DB)
    print("Tables exported:", len(tables))
    print("Export files:", len(generated_paths))
    print(
        "Tracked in Git index:",
        len(manifest["publication_summary"]["tracked_in_git_index"]),
    )
    print(
        "Local-only files:",
        len(manifest["publication_summary"]["local_only_not_tracked"]),
    )
    print("Manifest:", MANIFEST_PATH)

    print("\nLOCAL-ONLY FILES:")
    for path in manifest["publication_summary"]["local_only_not_tracked"]:
        print(" -", path)

    print("\nTRACKED FILES:")
    for path in manifest["publication_summary"]["tracked_in_git_index"]:
        print(" -", path)

    print(
        "\nIMPORTANT: Verify GitHub publication after committing "
        "and pushing."
    )

finally:
    conn.close()
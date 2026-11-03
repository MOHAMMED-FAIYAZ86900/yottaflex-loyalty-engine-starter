
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
    """Calculate SHA-256 without loading the entire file into memory."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def get_git_index_files() -> set[str]:
    """
    Return repository-relative paths staged or tracked in Git's index.

    A file in this set is not automatically guaranteed to have been
    pushed to GitHub. The final push must still be verified.
    """
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


def relative_path(path: Path) -> str:
    """Return a repository-relative POSIX path."""
    return path.relative_to(ROOT).as_posix()


def compress_csv(source: Path, destination: Path) -> None:
    """Create a deterministic gzip file with a fixed modification time."""
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


def export_metadata(path: Path, git_files: set[str]) -> dict:
    """Return size, hash, format, and Git-index status for one export."""
    relative = relative_path(path)

    tracked = relative in git_files

    if path.suffix == ".gz":
        file_format = "CSV_GZIP"
    else:
        file_format = path.suffix.lstrip(".").upper()

    return {
        "path": relative,
        "format": file_format,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "repository_status": (
            "tracked_in_git_index"
            if tracked
            else "local_only_not_tracked"
        ),
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

    # -----------------------------------------------------
    # Identify tables
    # -----------------------------------------------------

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

    git_files = get_git_index_files()

    manifest = {
        "manifest_version": "2.0",
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
        "manifest_note": (
            "The manifest itself is excluded from its own exports "
            "hash list to avoid recursive self-hashing."
        ),
    }

    # -----------------------------------------------------
    # Export each table
    # -----------------------------------------------------

    print("Starting dataset export...")
    print("------------------------------------")

    generated_paths = []

    for table in tables:
        cursor = conn.execute(f'SELECT * FROM "{table}"')
        columns = [description[0] for description in cursor.description]

        rows = [dict(row) for row in cursor.fetchall()]

        csv_path = OUT / f"{table}.csv"
        json_path = OUT / f"{table}.json"

        # CSV export
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

        # JSON export
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
    # Compress large points transaction CSV
    # -----------------------------------------------------

    transaction_csv = OUT / "points_transaction.csv"
    transaction_gzip = OUT / "points_transaction.csv.gz"

    if transaction_csv.exists():
        compress_csv(transaction_csv, transaction_gzip)
        generated_paths.append(transaction_gzip)

        print(
            "Compressed points transaction CSV:",
            transaction_gzip.name,
        )

    # -----------------------------------------------------
    # SQL dump
    # -----------------------------------------------------

    sql_path = OUT / "loyalty_dataset.sql"

    with sql_path.open("w", encoding="utf-8") as file:
        for line in conn.iterdump():
            file.write(line + "\n")

    generated_paths.append(sql_path)

    print("SQL dump generated:", sql_path.name)

    # -----------------------------------------------------
    # Build export metadata
    # -----------------------------------------------------

    # Refresh Git index information after all file generation.
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
        "\nIMPORTANT: GitHub publication must be verified after "
        "the commit and push."
    )

finally:
    conn.close()

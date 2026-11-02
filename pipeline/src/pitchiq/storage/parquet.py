"""Local storage: one Parquet file per table, written atomically, queryable via DuckDB.

Layout under :func:`pitchiq.config.data_dir`::

    raw/<source>/...           HTTP cache (league pages, CSVs)
    processed/<table>.parquet  tidy, validated tables (the pipeline's source of truth)
    artifacts/                 trained models + metadata
    pitchiq.duckdb             views over processed/*.parquet for ad-hoc SQL
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from pitchiq.config import data_dir


class Store:
    """Read/write processed tables and artefacts."""

    def __init__(self, root: Path | None = None) -> None:
        """Create a store rooted at ``root`` (defaults to the configured data dir)."""
        self.root = root or data_dir()
        self.raw = self.root / "raw"
        self.processed = self.root / "processed"
        self.artifacts = self.root / "artifacts"
        for d in (self.raw, self.processed, self.artifacts):
            d.mkdir(parents=True, exist_ok=True)

    def path(self, table: str) -> Path:
        """Path of a processed table."""
        return self.processed / f"{table}.parquet"

    def exists(self, table: str) -> bool:
        """Whether a processed table exists."""
        return self.path(table).exists()

    def read(self, table: str, columns: list[str] | None = None) -> pd.DataFrame:
        """Read a table; returns an empty frame if it does not exist yet."""
        p = self.path(table)
        if not p.exists():
            return pd.DataFrame(columns=columns) if columns else pd.DataFrame()
        return pd.read_parquet(p, columns=columns)

    def write(self, table: str, df: pd.DataFrame) -> Path:
        """Atomically replace a table (write to a temp file, then rename)."""
        p = self.path(table)
        tmp = p.with_suffix(".parquet.tmp")
        df.reset_index(drop=True).to_parquet(tmp, index=False)
        tmp.replace(p)
        return p

    def upsert(self, table: str, df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        """Merge ``df`` into a table, new rows winning on ``keys``; returns the result."""
        old = self.read(table)
        if old.empty:
            merged = df
        elif df.empty:
            merged = old
        else:
            merged = pd.concat([old, df], ignore_index=True).drop_duplicates(
                subset=keys, keep="last"
            )
        self.write(table, merged)
        return merged

    def write_json(self, name: str, obj: Any) -> Path:
        """Write a JSON artefact."""
        p = self.artifacts / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
        return p

    def read_json(self, name: str, default: Any = None) -> Any:
        """Read a JSON artefact (``default`` if missing)."""
        p = self.artifacts / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    def duckdb(self) -> duckdb.DuckDBPyConnection:
        """Open ``pitchiq.duckdb`` with one view per processed table."""
        con = duckdb.connect(str(self.root / "pitchiq.duckdb"))
        for p in sorted(self.processed.glob("*.parquet")):
            con.execute(
                f"CREATE OR REPLACE VIEW {p.stem} AS SELECT * FROM read_parquet('{p.as_posix()}')"
            )
        return con

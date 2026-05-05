#!/usr/bin/env python3
"""
Downloader for the Bugs4Q dataset from Zenodo (record 8148982).

Fix vs the original `loading.py`: the main Database archive is now
required-by-default (the original had it flagged `required=False`, which
meant a fresh clone of the repo wouldn't even pull the data).

Usage:
    python scripts/download_bugs4q.py            # into ./data/bugs4q/
    python scripts/download_bugs4q.py --dest D   # into custom location
    python scripts/download_bugs4q.py --include_framework
"""
from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

import requests

ZENODO_RECORD = "8148982"

FILES = [
    {
        "name": "Bugs4Q-Database.zip",
        "md5": "8aad45d2682350517ee13215b886d7a7",
        "required": True,
    },
    {
        "name": "Bugs4Q-Framework.zip",
        "md5": "342b05a1ebb630ebb2a986c33037afb3",
        "required": False,
    },
]


def md5sum(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def download(url: str, out: Path) -> None:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        downloaded = 0
        with out.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        print(f"\r  {out.name}: {pct}%", end="")
    print("")


def extract(zip_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest_dir)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", type=Path, default=Path("data/bugs4q"))
    ap.add_argument("--include_framework", action="store_true",
                    help="also download the optional framework CLI")
    args = ap.parse_args()

    args.dest.mkdir(parents=True, exist_ok=True)

    for item in FILES:
        fname = item["name"]
        required = item["required"] or (args.include_framework and "Framework" in fname)
        if not required:
            print(f"[SKIP] optional: {fname}")
            continue
        url = f"https://zenodo.org/records/{ZENODO_RECORD}/files/{fname}?download=1"
        out = args.dest / fname
        if out.exists() and md5sum(out) == item["md5"].lower():
            print(f"[OK] already present: {out}")
        else:
            print(f"[GET] {fname}  <-  {url}")
            download(url, out)
            actual = md5sum(out)
            if actual != item["md5"].lower():
                raise RuntimeError(f"MD5 mismatch: {actual} != {item['md5']}")
            print(f"[OK] MD5 verified: {actual}")
        extract(out, args.dest)
        print(f"[OK] extracted -> {args.dest}")

    # Sanity list
    sample = sorted(args.dest.glob("**/buggy.py"))[:5]
    print(f"\n[OK] Found {len(list(args.dest.glob('**/buggy.py')))} buggy.py files.")
    for p in sample:
        print(f"  e.g., {p.relative_to(args.dest)}")


if __name__ == "__main__":
    main()

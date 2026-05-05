"""
download_bugs4q.py
- Downloads Bugs4Q dataset + (optional) framework from Zenodo
- Verifies MD5 checksums
- Extracts archives to ./data/bugs4q
"""
import hashlib
import os
from pathlib import Path
import zipfile
import requests

# ---- Config ----
ZENODO_RECORD = "8148982"
FILES = [
    {
        "name": "Bugs4Q-Database.zip",
        "md5": "8aad45d2682350517ee13215b886d7a7",  # from Zenodo
        "required": True,
    },
    {
        "name": "Bugs4Q-Framework.zip",
        "md5": "342b05a1ebb630ebb2a986c33037afb3",  # from Zenodo
        "required": False,  # flip to True if you want the CLI helper too
    },
]

DEST = Path("data/bugs4q").resolve()
DEST.mkdir(parents=True, exist_ok=True)

def md5sum(path: Path, chunk=1024 * 1024) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def download(url: str, out: Path):
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
                        print(f"\rDownloading {out.name}: {pct}%", end="")
    print("\nDone:", out)

def extract(zip_path: Path, dest_dir: Path):
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest_dir)
    print("Extracted:", zip_path.name, "->", dest_dir)

def main():
    for item in FILES:
        fname = item["name"]
        url = f"https://zenodo.org/records/{ZENODO_RECORD}/files/{fname}?download=1"
        out = DEST / fname

        if not item["required"]:
            # Skip optional files unless user opted in
            # To force download, set required=True above.
            print(f"Skipping optional file: {fname}")
            continue

        print(f"Fetching: {fname}\nURL: {url}")
        download(url, out)

        # Verify checksum
        actual = md5sum(out)
        expected = item["md5"].lower()
        if actual != expected:
            raise RuntimeError(
                f"MD5 mismatch for {fname}: {actual} != {expected}. "
                "Delete the file and re-run."
            )
        print("MD5 verified:", actual)

        # Extract
        extract(out, DEST)

    # Quick sanity: show a few bug folders/files
    print("\nSample contents:")
    for p in sorted(DEST.glob("**/*bugg*.*"))[:10]:
        print(" -", p.relative_to(DEST))

if __name__ == "__main__":
    main()

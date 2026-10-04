"""Extract the clickstream Parquet files from data/Archive.zip into data/raw/.

Usage:  .venv/bin/python scripts/extract_data.py

Skips the macOS resource-fork entries (__MACOSX/) that ship inside the archive.
Each file is written to a .part file first and renamed only after zipfile has
verified its CRC-32, so a re-run safely skips files that are already complete.
"""
import os
import shutil
import zipfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
ZIP = os.path.join(ROOT, "data", "Archive.zip")
OUT = os.path.join(ROOT, "data", "raw")


def main():
    os.makedirs(OUT, exist_ok=True)
    with zipfile.ZipFile(ZIP) as zf:
        members = [m for m in zf.infolist()
                   if m.filename.endswith(".parquet") and not m.filename.startswith("__MACOSX/")]
        for n, m in enumerate(members, 1):
            dest = os.path.join(OUT, os.path.basename(m.filename))
            if os.path.exists(dest) and os.path.getsize(dest) == m.file_size:
                print(f"[{n}/{len(members)}] skip {m.filename} (already extracted)", flush=True)
                continue
            # zipfile raises BadZipFile on a CRC mismatch once the member is fully read
            with zf.open(m) as src, open(dest + ".part", "wb") as dst:
                shutil.copyfileobj(src, dst, 16 << 20)
            os.replace(dest + ".part", dest)
            print(f"[{n}/{len(members)}] {m.filename}: {m.file_size / 1e6:.1f} MB, CRC ok", flush=True)
    print(f"done: {len(members)} parquet files in {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()

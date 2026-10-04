"""Parallel, resumable download of the assignment dataset via HTTP range requests.

Usage:  .venv/bin/python scripts/download_data.py

Splits the archive into 64MB chunks and fetches them concurrently (a single
CloudFront stream tops out at ~2 MB/s). Completed chunks are recorded in a
sidecar state file, so an interrupted run picks up where it stopped. An
existing partial file from a plain sequential download (e.g. curl) is kept
as an already-downloaded prefix.
"""
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = "https://d2h2pq0ozsvj7l.cloudfront.net/Archive.zip"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "Archive.zip")
STATE = OUT + ".state"
CHUNK = 64 * 1024 * 1024
WORKERS = 12
MAX_RETRIES = 8

lock = threading.Lock()
downloaded = 0


def content_length(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as r:
        return int(r.headers["Content-Length"])


def load_state(total):
    """Return (prefix_bytes, set_of_done_chunk_starts), initialising state on first run."""
    if os.path.exists(STATE):
        with open(STATE) as f:
            lines = f.read().split()
        return int(lines[0]), {int(x) for x in lines[1:]}
    # First run: whatever a sequential downloader already wrote is a valid prefix.
    prefix = os.path.getsize(OUT) if os.path.exists(OUT) else 0
    prefix = min(prefix - prefix % (1 << 20), total)  # round down to 1MB, to be safe
    with open(STATE, "w") as f:
        f.write(f"{prefix}\n")
    return prefix, set()


def fetch(fd, start, end):
    """Fetch bytes [start, end] into fd at the same offset, retrying with backoff."""
    global downloaded
    for attempt in range(MAX_RETRIES):
        written = 0
        try:
            req = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=60) as r:
                if r.status != 206:
                    raise IOError(f"expected 206 Partial Content, got {r.status}")
                pos = start
                while buf := r.read(1 << 20):
                    os.pwrite(fd, buf, pos)
                    pos += len(buf)
                    written += len(buf)
                    with lock:
                        downloaded += len(buf)
            if pos != end + 1:
                raise IOError(f"short read: got {pos - start} of {end - start + 1} bytes")
            with lock, open(STATE, "a") as f:
                f.write(f"{start}\n")
            return start
        except Exception as e:  # noqa: BLE001 - any network error is retried
            with lock:
                downloaded -= written
            print(f"chunk {start}: attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"chunk {start} failed after {MAX_RETRIES} attempts")


def main():
    total = content_length(URL)
    prefix, done = load_state(total)
    chunks = [(s, min(s + CHUNK, total) - 1) for s in range(prefix, total, CHUNK)]
    todo = [c for c in chunks if c[0] not in done]
    remaining = sum(e - s + 1 for s, e in todo)
    print(f"total {total / 1e9:.2f} GB | already have {(total - remaining) / 1e9:.2f} GB "
          f"| {len(todo)} chunks to fetch with {WORKERS} workers", flush=True)

    fd = os.open(OUT, os.O_RDWR | os.O_CREAT)
    os.ftruncate(fd, total)
    t0, last_report = time.time(), 0.0
    try:
        with ThreadPoolExecutor(WORKERS) as pool:
            futures = [pool.submit(fetch, fd, s, e) for s, e in todo]
            pending = set(futures)
            while pending:
                finished = {f for f in pending if f.done()}
                for f in finished:
                    f.result()  # re-raise a chunk that exhausted its retries
                pending -= finished
                if time.time() - last_report >= 15:
                    last_report = time.time()
                    elapsed = last_report - t0
                    rate = downloaded / elapsed if elapsed else 0
                    eta = (remaining - downloaded) / rate if rate else float("inf")
                    print(f"progress {downloaded / remaining:6.1%} | {rate / 1e6:5.1f} MB/s "
                          f"| ETA {eta / 60:4.1f} min", flush=True)
                time.sleep(0.5)
    finally:
        os.fsync(fd)
        os.close(fd)

    size = os.path.getsize(OUT)
    if size != total:
        sys.exit(f"size mismatch: {size} != {total}")
    print(f"DONE: {OUT} ({size} bytes) in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()

# Saatva Affiliate Performance & Attribution Hijacking Analysis

Home assignment for the Senior Data Analyst position at Partnerize.

**Business question:** how does Saatva's affiliate program in the US compare with its main
competitors (Nectar, Helix, DreamCloud, Walmart)? For each brand we estimate US affiliate
clicks and the conversions they produced. We then recommend how Saatva can grow its program
and reduce fraud, focusing on attribution hijacking.

## Repository layout

```
scripts/
  download_data.py   # parallel, resumable download of the dataset archive
  extract_data.py    # extracts the Parquet files from the archive and verifies CRCs
data/                # local only (git-ignored): Archive.zip, raw/, sample/
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/download_data.py   # ~9.5 GB
.venv/bin/python scripts/extract_data.py    # -> data/raw/*.parquet (~12.6 GB)
```

The data is not committed to the repository. It was provided for this assignment only, and it is too large for git.

## Dataset

Anonymized clickstream from a browsing panel. Each row is a single interaction (click).

| Column | Type | Notes |
|---|---|---|
| `USER_ID` | text | hashed panel user |
| `SESSION_ID` | text | one user's interactions on the same day, without a major break |
| `_ID` | text | unique interaction id |
| `CREATED_TIME` | timestamp | UTC |
| `SUBDOMAIN` | text | e.g. `mail.google.com` |
| `URL` | text | full URL, including query string |

The archive holds 33 Snappy-compressed Parquet files, about 9.5 GB zipped and 12.6 GB extracted.
It also contains macOS `__MACOSX/` metadata entries, which the extract script skips.

**Early observations on a 2-file development sample** (3.0M rows). These are preliminary
and will be re-checked on the full data:

- Both sample files cover only 2026-05-01 (UTC). The files appear to be split by time,
  so a single file is not a random sample of the period.
- Mattress brands are rare in the panel. That day had 7 rows on saatva.com, against
  9,972 on walmart.com. Panel counts will therefore need to be scaled up to US-level
  estimates, and every assumption behind that scaling documented.

"""Run the analysis pipeline: execute sql/*.sql in order against a local DuckDB file.

Usage:
    .venv/bin/python scripts/run_pipeline.py              # full dataset (data/raw)
    .venv/bin/python scripts/run_pipeline.py --sample     # 2-file dev sample (data/sample)
    .venv/bin/python scripts/run_pipeline.py --from 4     # resume from sql/04_*

The intermediate tables persist in data/analysis[_sample].duckdb, so later steps
can be re-run alone. After each file, the runner prints the row count of every
table that file created, as a sanity check. Tables listed in EXPORTS are
written to outputs/ as CSV.
"""
import argparse
import glob
import os
import re
import time

import duckdb

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
# Result tables written to outputs/*.csv
EXPORTS = ["dq_profile", "dq_hourly", "scaling", "scaling_validation", "competitor_summary",
           "traffic_mix", "publisher_summary", "brand_funnel", "hijack_sensitivity",
           "signal_summary", "flagged_click_sources", "incrementality",
           "incrementality_summary", "commission_at_risk", "seasonal_scaling",
           "panel_profile", "panel_coverage", "hijack_by_segment", "hijack_reweighted", "category_funnel",
           "brand_funnel_cat", "cross_shopping", "journey_order", "click_funnel_stage"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="run on data/sample instead of data/raw")
    ap.add_argument("--from", dest="start", type=int, default=1, help="first sql file number to run")
    ap.add_argument("--to", dest="end", type=int, default=99, help="last sql file number to run")
    args = ap.parse_args()

    os.chdir(ROOT)
    db = "data/analysis_sample.duckdb" if args.sample else "data/analysis.duckdb"
    con = duckdb.connect(db)

    for path in sorted(glob.glob("sql/[0-9][0-9]_*.sql")):
        num = int(os.path.basename(path)[:2])
        if not args.start <= num <= args.end:
            continue
        sql = open(path).read()
        if args.sample:
            sql = sql.replace("data/raw/", "data/sample/")
        t0 = time.time()
        con.execute(sql)
        print(f"{os.path.basename(path):<28} {time.time() - t0:6.1f}s", flush=True)
        for table in re.findall(r"CREATE OR REPLACE TABLE (\w+)", sql):
            n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"    {table:<26} {n:>12,} rows", flush=True)

    os.makedirs("outputs", exist_ok=True)
    for table in EXPORTS:
        # sorted on every column, so a rerun writes byte-identical files
        con.execute(f"COPY (SELECT * FROM {table} ORDER BY ALL) TO 'outputs/{table}.csv' (HEADER)")
        print(f"exported outputs/{table}.csv")


if __name__ == "__main__":
    main()

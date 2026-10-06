"""Build the Publisher Risk Monitor: a single self-contained HTML page.

Usage:
    .venv/bin/python dashboard/build_dashboard.py   # -> dashboard/publisher_risk_monitor.html

Reads the pipeline's tables from data/analysis.duckdb (run scripts/run_pipeline.py
first), and injects them as JSON into dashboard/template.html. The page needs no
server and no network: open the file in a browser.

What goes into the page, per US affiliate click: brand, network, publisher, time,
outcome, the raw timing of each hijacking indicator (so the page can re-apply any
look-back window), and the user's journey from 30 minutes before the click to
2 minutes after it.
The journey keeps the site visited and, on the brand's own site only, the first
segment of the URL path (/cart, /checkout, /ip …). No user ids, query strings or
full URLs are exported.
"""
import json
import os
import re
import csv

import duckdb

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
DB = os.path.join(ROOT, "data", "analysis.duckdb")
TEMPLATE = os.path.join(ROOT, "dashboard", "template.html")
OUT = os.path.join(ROOT, "dashboard", "publisher_risk_monitor.html")

JOURNEY_STEPS = 6   # sites shown before each click
AFTER_STEPS = 2     # and after it

# Defaults for the commission inputs: public sources, listed in README and sql/11.
ECONOMICS = {
    "Walmart":    {"aov": 112.5, "commission": 2.5},
    "Saatva":     {"aov": 860.0, "commission": 5.0},
    "Nectar":     {"aov": 860.0, "commission": 5.0},
    "Helix":      {"aov": 860.0, "commission": 5.0},
    "DreamCloud": {"aov": 860.0, "commission": 5.0},
}


def rows(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def csv_rows(name):
    with open(os.path.join(ROOT, "outputs", name + ".csv")) as f:
        return list(csv.DictReader(f))


def main():
    con = duckdb.connect(DB, read_only=True)

    clicks = rows(con, """
        SELECT c.brand, c.click_key, c.network, c.publisher,
               strftime(c.click_time, '%H:%M:%S')                       AS t,
               c.converted, date_diff('second', c.click_time, c.conversion_time) AS secs_to_order,
               c.no_landing, c.has_paid_search_click_id                  AS paid_search,
               c.secs_since_checkout, c.secs_since_brand_page,
               c.brand_search_60s, c.coupon_ext_60s, c.multi_brand_burst, c.no_referrer,
               c.prev_host, c.coupon IS NOT NULL                         AS has_coupon,
               c.landing_url, s.stage_at_click
        FROM us_clicks c
        JOIN click_stage s USING (brand, click_key)
        ORDER BY c.brand, c.click_time, c.click_key
    """)

    # The journey: the user's events from 30 min before each click to 2 min after it.
    # Same-second events count as "before" (a redirect chain fires within one second),
    # except the click's own rows (its network hop, its landing). Consecutive repeats
    # of the same site + section are collapsed; the last JOURNEY_STEPS before the
    # click and the first AFTER_STEPS after it are kept.
    journey = rows(con, f"""
        WITH ev AS (
            SELECT c.brand, c.click_key,
                   e.host,
                   CASE WHEN e.brand = c.brand AND e.is_brand_page
                        THEN coalesce(nullif(regexp_extract(e.url, '^[a-z]+://[^/?#]+(/[^/?#]*)', 1), ''), '/')
                   END                                                AS section,
                   date_diff('second', e.created_time, c.click_time)  AS secs_before,
                   e.created_time
            FROM us_clicks c
            JOIN brand_user_events e
              ON e.user_id = c.user_id
             AND e.created_time >= c.click_time - INTERVAL 30 MINUTE
             AND e.created_time <= c.click_time + INTERVAL 2 MINUTE
            WHERE NOT (e.created_time = c.click_time
                       AND coalesce(e.hop_brand = c.brand OR (e.brand = c.brand AND e.is_brand_page), FALSE))
        ),
        changes AS (
            SELECT *, secs_before >= 0 AS before,
                   coalesce(host || coalesce(section, '') <>
                            lag(host || coalesce(section, '')) OVER w, TRUE) AS is_new
            FROM ev
            WINDOW w AS (PARTITION BY brand, click_key, secs_before >= 0 ORDER BY created_time, host, section)
        ),
        steps AS (
            SELECT brand, click_key, host, section, secs_before, before,
                   row_number() OVER (PARTITION BY brand, click_key, before
                                      ORDER BY CASE WHEN before THEN -epoch(created_time) ELSE epoch(created_time) END,
                                               host, section) AS k
            FROM changes WHERE is_new
        )
        SELECT brand, click_key, host, section, secs_before, before
        FROM steps
        WHERE k <= CASE WHEN before THEN {JOURNEY_STEPS} ELSE {AFTER_STEPS} END
        ORDER BY brand, click_key, secs_before DESC
    """)

    # Compact encoding: hosts and publishers as indexes into lookup lists.
    hosts, host_ix = [], {}

    def hid(h):
        if h is None:
            return None
        if h not in host_ix:
            host_ix[h] = len(hosts)
            hosts.append(h)
        return host_ix[h]

    steps, after = {}, {}
    for j in journey:
        target = steps if j["before"] else after
        target.setdefault((j["brand"], j["click_key"]), []).append(
            [hid(j["host"]), j["section"], abs(int(j["secs_before"]))])

    def landing_section(u):
        m = re.match(r"^[a-z]+://[^/?#]+(/[^/?#]*)", u or "")
        return m.group(1) if m and m.group(1) else "/"

    out_clicks = []
    for c in clicks:
        out_clicks.append({
            "b": c["brand"], "n": c["network"], "p": c["publisher"], "t": c["t"],
            "cv": int(bool(c["converted"])), "to": c["secs_to_order"],
            "nl": int(bool(c["no_landing"])), "ps": int(bool(c["paid_search"])),
            "sc": c["secs_since_checkout"], "sb": c["secs_since_brand_page"],
            "bs": int(bool(c["brand_search_60s"])), "cp": int(bool(c["coupon_ext_60s"])),
            "bu": int(bool(c["multi_brand_burst"])), "nr": int(bool(c["no_referrer"])),
            "ph": hid(c["prev_host"]), "cc": int(bool(c["has_coupon"])),
            "ls": None if c["no_landing"] else landing_section(c["landing_url"]),
            "j": steps.get((c["brand"], c["click_key"]), []),
            "a": after.get((c["brand"], c["click_key"]), []),
            "st": int(c["stage_at_click"][0]),
        })

    comp = {r["brand"]: r for r in csv_rows("competitor_summary")}
    brands = []
    for b in ("Walmart", "Saatva", "Nectar", "Helix", "DreamCloud"):
        r = comp[b]
        brands.append({
            "brand": b, "client": r["is_client"] == "true",
            "scale": float(r["scale_factor"]),
            "visits": int(r["panel_visits"]),
            "pct_affiliate": float(r["pct_visits_from_affiliate"]),
            **ECONOMICS[b],
        })

    data = {
        "date": "2026-05-01",
        "hosts": hosts,
        "brands": brands,
        "clicks": out_clicks,
        "incrementality": csv_rows("incrementality"),
        "incrementality_summary": csv_rows("incrementality_summary")[0],
    }
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = open(TEMPLATE).read().replace("/*__DATA__*/null", payload)
    with open(OUT, "w") as f:
        f.write(html)
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(out_clicks):,} clicks, "
          f"{len(journey):,} journey steps, {os.path.getsize(OUT) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

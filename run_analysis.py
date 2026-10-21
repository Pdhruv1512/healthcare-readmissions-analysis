"""
Runs every query in sql/queries.sql against hospitals.db, saves each result
to results/ as a CSV, and draws charts of the key findings into images/.

Usage:
    python3 build_database.py   # creates hospitals.db from data/raw/
    python3 run_analysis.py
"""
import csv
import os
import re
import sqlite3

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DB_PATH = "hospitals.db"
SQL_PATH = os.path.join("sql", "queries.sql")
RESULTS_DIR = "results"
IMAGES_DIR = "images"

BLUE = "#2a78d6"      # better than expected / main series
RED = "#e34948"       # worse than expected
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"

plt.rcParams.update({
    "font.size": 10,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": MUTED,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.titlesize": 13,
    "axes.titlecolor": INK,
})


def load_queries(path):
    """Split queries.sql into (number, title, sql) using the '-- N. TITLE' headers."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    matches = list(re.finditer(r"^-- (\d+)\. (.+)$", text, re.MULTILINE))
    queries = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        queries.append((int(m.group(1)), m.group(2).strip(), text[m.start():end].strip()))
    return queries


def slug(title):
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:50]


def style(ax):
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(IMAGES_DIR, name), dpi=150)
    plt.close(fig)


def chart_conditions(rows):
    # rows: condition, hospitals, avg_predicted, avg_expected, avg_err, n_worse, pct_worse
    rows = sorted(rows, key=lambda r: r[2])
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.barh([r[0] for r in rows], [r[2] for r in rows], color=BLUE, height=0.6)
    for i, r in enumerate(rows):
        ax.text(r[2], i, f" {r[2]:.1f}%", va="center", color=INK, fontsize=9)
    ax.set_title("Average 30-day readmission rate by condition", loc="left")
    ax.set_xlabel("Predicted readmission rate (%)")
    style(ax)
    save(fig, "readmission_rate_by_condition.png")


def chart_star_rating(rows):
    # rows: star_rating, hospitals, rows, avg_err, pct_worse
    rated = [r for r in rows if r[0] != "Not rated"]
    labels = [f"{r[0]} star" + ("" if r[0] == "1" else "s") for r in rated]
    values = [r[4] for r in rated]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(labels, values, color=BLUE, width=0.6)
    for i, v in enumerate(values):
        ax.text(i, v, f"{v:.1f}%", ha="center", va="bottom", color=INK, fontsize=9)
    ax.set_title("Share of results worse than expected, by CMS star rating", loc="left")
    ax.set_ylabel("% of hospital-condition results with ERR > 1")
    ax.set_ylim(0, max(values) * 1.15)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    save(fig, "worse_than_expected_by_star_rating.png")


def chart_states(rows):
    # rows: rank, state, hospitals, avg_err, pct_worse  (sorted best -> worst)
    rows = list(reversed(rows))
    fig, ax = plt.subplots(figsize=(8, 8))
    states = [r[1] for r in rows]
    diffs = [r[3] - 1 for r in rows]
    colors = [RED if d > 0 else BLUE for d in diffs]
    ax.barh(states, diffs, color=colors, height=0.7)
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.set_title("Average excess readmission ratio by state\n(states with 20+ hospitals)", loc="left")
    ax.set_xlabel("Average ERR minus 1  (left = fewer readmissions than expected, right = more)")
    ax.tick_params(axis="y", labelsize=8)
    style(ax)
    save(fig, "err_by_state.png")


def chart_volume(rows):
    # rows: quartile, hospitals, min_d, max_d, avg_err, pct_worse
    labels = [f"Q{r[0]}\n{r[2]}-{r[3]}" for r in rows]
    values = [r[5] for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(labels, values, color=BLUE, width=0.6)
    for i, v in enumerate(values):
        ax.text(i, v, f"{v:.1f}%", ha="center", va="bottom", color=INK, fontsize=9)
    ax.set_title("Heart failure: higher-volume hospitals do better", loc="left")
    ax.set_xlabel("Hospital volume quartile (heart failure discharges)")
    ax.set_ylabel("% of hospitals with ERR > 1")
    ax.set_ylim(0, max(values) * 1.15)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    save(fig, "heart_failure_volume.png")


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    results = {}

    for num, title, sql in load_queries(SQL_PATH):
        cur = conn.execute(sql)
        headers = [d[0] for d in cur.description]
        rows = cur.fetchall()
        results[num] = rows
        out = os.path.join(RESULTS_DIR, f"q{num}_{slug(title)}.csv")
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(headers)
            writer.writerows(rows)
        print(f"Q{num} {title}: {len(rows)} rows -> {out}")
    conn.close()

    chart_conditions(results[2])
    chart_star_rating(results[4])
    chart_states(results[6])
    chart_volume(results[7])
    print(f"Charts saved to {IMAGES_DIR}/")


if __name__ == "__main__":
    main()

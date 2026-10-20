"""
Refreshes the auto-generated parts of this profile with live GitHub data.

Runs daily from .github/workflows/update-stats.yml. You can also run it locally:
    set GITHUB_TOKEN=<a personal access token>     (Windows)
    python scripts/update_readme.py

What it writes
  README.md   the text between  <!-- STATS:START --> ... <!-- STATS:END -->
              and                <!-- REPOS:START --> ... <!-- REPOS:END -->
  assets/contributions-light.svg and -dark.svg   the contribution calendar

Everything else in README.md is left untouched. Without a token it still
fills what the public API allows and skips the calendar and active-day count.

Standard library only, nothing to install.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

USER = "4bhimxnyu"
README = "README.md"
CALENDAR_OUT = "assets/contributions-{theme}.svg"
TOP_N = 8                       # rows in the "most committed repositories" table
TOKEN = os.environ.get("GITHUB_TOKEN", "")

# GitHub's own contribution-graph colours, level 0 (none) to 4 (most).
PALETTES = {
    "light": {"cells": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"], "text": "#57606a"},
    "dark":  {"cells": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"], "text": "#8b949e"},
}
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


# -------------------------------------------------------------------- API ---
def api(url: str, method: str = "GET", data: dict | None = None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-readme-updater"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.headers, json.loads(r.read().decode())


def graphql(query: str, variables: dict):
    _, res = api("https://api.github.com/graphql", "POST", {"query": query, "variables": variables})
    if "errors" in res:
        raise RuntimeError(res["errors"])
    return res["data"]


CALENDAR_QUERY = """
query($login:String!, $from:DateTime, $to:DateTime) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}"""


def calendar(from_: datetime | None = None, to: datetime | None = None) -> dict:
    v = {"login": USER}
    if from_:
        v["from"] = from_.isoformat()
    if to:
        v["to"] = to.isoformat()
    return graphql(CALENDAR_QUERY, v)["user"]["contributionsCollection"]["contributionCalendar"]


# ----------------------------------------------------------------- numbers ---
def account_created() -> datetime:
    _, u = api(f"https://api.github.com/users/{USER}")
    return datetime.fromisoformat(u["created_at"].replace("Z", "+00:00"))


def total_commits() -> int:
    _, res = api(f"https://api.github.com/search/commits?q=author:{USER}&per_page=1")
    return int(res.get("total_count", 0))


def active_days(since: datetime) -> int:
    """Number of days with at least one contribution since the account was created."""
    count, start, now = 0, since, datetime.now(timezone.utc)
    while start < now:
        end = min(start + timedelta(days=364), now)
        for week in calendar(start, end)["weeks"]:
            count += sum(1 for d in week["contributionDays"] if d["contributionCount"] > 0)
        start = end + timedelta(days=1)
    return count


def repos_by_commits() -> list[dict]:
    _, repos = api(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner")
    rows = []
    for r in repos:
        if r["fork"]:
            continue
        try:
            headers, first = api(f"https://api.github.com/repos/{USER}/{r['name']}/commits?per_page=1")
        except urllib.error.HTTPError as e:
            if e.code == 409:                       # empty repository, no commits yet
                continue
            sys.exit(f"could not count commits for {r['name']}: {e} (rate limited? set GITHUB_TOKEN)")
        m = re.search(r'page=(\d+)>; rel="last"', headers.get("Link", "") or "")
        count = int(m.group(1)) if m else len(first)
        rows.append({
            "name": r["name"], "url": r["html_url"], "commits": count,
            "language": r["language"] or "—", "pushed": r["pushed_at"][:10],
        })
    rows.sort(key=lambda x: (-x["commits"], x["pushed"]))
    return rows


# ---------------------------------------------------------------- calendar ---
def calendar_svg(cal: dict, theme: str) -> str:
    """Draws the last year of contributions the way GitHub does: 7 rows, one column per week."""
    p = PALETTES[theme]
    cell, gap, left, top = 10, 3, 28, 20
    weeks = cal["weeks"]
    width = left + len(weeks) * (cell + gap) + 4
    height = top + 7 * (cell + gap) + 28
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', '
           f'\'Noto Sans\', Helvetica, Arial, sans-serif" font-size="10" fill="{p["text"]}">']
    # Day labels, like GitHub: Mon / Wed / Fri.
    for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        out.append(f'<text x="0" y="{top + row * (cell + gap) + cell - 1}">{label}</text>')
    # Month labels where a new month starts in a week's first day.
    last_month = None
    for wi, week in enumerate(weeks):
        first = date.fromisoformat(week["contributionDays"][0]["date"])
        if first.month != last_month:
            if last_month is not None or wi == 0:
                out.append(f'<text x="{left + wi * (cell + gap)}" y="{top - 8}">{first:%b}</text>')
            last_month = first.month
    # Cells.
    for wi, week in enumerate(weeks):
        for d in week["contributionDays"]:
            row = (date.fromisoformat(d["date"]).weekday() + 1) % 7      # Sunday = 0, like GitHub
            x, y = left + wi * (cell + gap), top + row * (cell + gap)
            colour = p["cells"][LEVELS.get(d["contributionLevel"], 0)]
            out.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{colour}">'
                       f'<title>{d["contributionCount"]} contributions on {d["date"]}</title></rect>')
    # Footer: total on the left, legend on the right.
    fy = top + 7 * (cell + gap) + 18
    out.append(f'<text x="{left}" y="{fy}">{cal["totalContributions"]:,} contributions in the last year</text>')
    lx = width - 4 - 5 * (cell + gap) - 34
    out.append(f'<text x="{lx - 26}" y="{fy}">Less</text>')
    for i, colour in enumerate(p["cells"]):
        out.append(f'<rect x="{lx + i * (cell + gap)}" y="{fy - cell + 1}" width="{cell}" height="{cell}" rx="2" fill="{colour}"/>')
    out.append(f'<text x="{lx + 5 * (cell + gap) + 2}" y="{fy}">More</text>')
    out.append("</svg>\n")
    return "\n".join(out)


# ------------------------------------------------------------------ render ---
def replace_block(text: str, tag: str, body: str) -> str:
    start, end = f"<!-- {tag}:START -->", f"<!-- {tag}:END -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        sys.exit(f"markers {start} / {end} not found in {README}")
    return pattern.sub(lambda _: f"{start}\n{body}\n{end}", text)


def main():
    created = account_created()
    now = datetime.now(timezone.utc)
    days_on_github = (now - created).days
    commits = total_commits()
    repos = repos_by_commits()

    active = "—"
    if TOKEN:
        active = f"{active_days(created):,}"
        last_year = calendar()
        os.makedirs("assets", exist_ok=True)
        for theme in PALETTES:
            with open(CALENDAR_OUT.format(theme=theme), "w", encoding="utf-8", newline="\n") as f:
                f.write(calendar_svg(last_year, theme))
    else:
        print("no GITHUB_TOKEN: skipping active-day count and contribution calendar")

    stats = (
        "<!-- Generated daily by scripts/update_readme.py. Edit the script, not this block. -->\n"
        "| On GitHub since | Days with contributions | Total commits | Public repositories |\n"
        "|:--|:--|:--|:--|\n"
        f"| {created:%B %Y} ({days_on_github:,} days) | {active} | {commits:,} | {len(repos)} |\n"
        f"\n<sub>Updated {now:%d %b %Y}.</sub>"
    )

    lines = ["<!-- Generated daily by scripts/update_readme.py from commit counts. Edit the script, not this table. -->",
             "| Repository | Commits | Language | Last push |",
             "|:--|--:|:--|:--|"]
    for r in repos[:TOP_N]:
        lines.append(f"| [{r['name']}]({r['url']}) | {r['commits']} | {r['language']} | {r['pushed']} |")

    text = open(README, encoding="utf-8").read()
    text = replace_block(text, "STATS", stats)
    text = replace_block(text, "REPOS", "\n".join(lines))
    open(README, "w", encoding="utf-8", newline="\n").write(text)
    print(f"updated: {days_on_github} days on GitHub, {active} active days, {commits} commits, {len(repos)} repos")


if __name__ == "__main__":
    main()

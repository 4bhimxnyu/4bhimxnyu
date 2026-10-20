"""
Refreshes the auto-generated blocks in README.md with live GitHub numbers.

Runs daily from .github/workflows/update-stats.yml. You can also run it locally:
    set GITHUB_TOKEN=<a personal access token>     (Windows)
    python scripts/update_readme.py

Without a token it still fills in what the public API allows (days on GitHub,
total commits, repo table) and leaves the streak columns as "—".

It rewrites only the text between these marker pairs:
    <!-- STATS:START --> ... <!-- STATS:END -->
    <!-- REPOS:START --> ... <!-- REPOS:END -->
Everything else in README.md is left untouched.

Standard library only, no packages to install.
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
TOP_N = 8                       # rows in the "most committed repos" table
TOKEN = os.environ.get("GITHUB_TOKEN", "")


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


# ----------------------------------------------------------------- numbers ---
def account_created() -> datetime:
    _, u = api(f"https://api.github.com/users/{USER}")
    return datetime.fromisoformat(u["created_at"].replace("Z", "+00:00"))


def total_commits() -> int:
    _, res = api(f"https://api.github.com/search/commits?q=author:{USER}&per_page=1")
    return int(res.get("total_count", 0))


def contribution_days(since: datetime) -> dict[date, int]:
    """Every day since account creation -> contribution count (GraphQL calendar, one year per call)."""
    q = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        contributionsCollection(from:$from, to:$to) {
          contributionCalendar { weeks { contributionDays { date contributionCount } } }
        }
      }
    }"""
    days: dict[date, int] = {}
    start = since
    now = datetime.now(timezone.utc)
    while start < now:
        end = min(start + timedelta(days=364), now)
        data = graphql(q, {"login": USER, "from": start.isoformat(), "to": end.isoformat()})
        for week in data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for d in week["contributionDays"]:
                days[date.fromisoformat(d["date"])] = d["contributionCount"]
        start = end + timedelta(days=1)
    return days


def streaks(days: dict[date, int]) -> tuple[int, int, int]:
    """(days with contributions, current streak, longest streak)."""
    active = sorted(d for d, n in days.items() if n > 0)
    if not active:
        return 0, 0, 0
    longest = run = 1
    for prev, cur in zip(active, active[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        longest = max(longest, run)
    today = datetime.now(timezone.utc).date()
    current = 0
    if (today - active[-1]).days <= 1:          # still alive if active today or yesterday
        current = 1
        for prev, cur in zip(reversed(active[:-1]), reversed(active)):
            if (cur - prev).days == 1:
                current += 1
            else:
                break
    return len(active), current, longest


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

    if TOKEN:
        active, current, longest = streaks(contribution_days(created))
        active_s, current_s, longest_s = f"**{active:,}**", f"**{current}** days", f"**{longest}** days"
    else:
        active_s = current_s = longest_s = "—"

    stats = (
        "<!-- This block is generated daily. Edit scripts/update_readme.py to change it. -->\n"
        "| Days on GitHub | Days with commits | Current streak | Longest streak | Total commits | Public repos |\n"
        "|:--:|:--:|:--:|:--:|:--:|:--:|\n"
        f"| **{days_on_github:,}** <br><sub>since {created:%b %d, %Y}</sub> "
        f"| {active_s} | {current_s} | {longest_s} | **{commits:,}** | **{len(repos)}** |\n"
        f"\n<sub>Last updated {now:%b %d, %Y} (UTC).</sub>"
    )

    lines = ["<!-- This table is generated daily from commit counts. Edit scripts/update_readme.py to change it. -->",
             "| # | Repository | Commits | Language | Last push |",
             "|:-:|:--|--:|:--|:--|"]
    for i, r in enumerate(repos[:TOP_N], 1):
        lines.append(f"| {i} | [{r['name']}]({r['url']}) | {r['commits']} | {r['language']} | {r['pushed']} |")

    text = open(README, encoding="utf-8").read()
    text = replace_block(text, "STATS", stats)
    text = replace_block(text, "REPOS", "\n".join(lines))
    open(README, "w", encoding="utf-8", newline="\n").write(text)
    print(f"updated: {days_on_github} days on GitHub, streaks {active_s}/{current_s}/{longest_s}, "
          f"{commits} commits, {len(repos)} repos")


if __name__ == "__main__":
    main()

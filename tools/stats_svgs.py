"""Render live GitHub stats as terminal-style SVGs (run in the snake workflow).

usage: GITHUB_TOKEN=... JBM_DIR=<ttf dir> python tools/stats_svgs.py <login> <out dir>
Writes stats.svg (counters + language meters) and activity.svg (streaks + 30-day graph).
Only public data the token can see is used; numbers are whatever the API returns.
"""
import datetime as dt
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_svgs as S  # noqa: E402
from build_svgs import B, P, R, Doc, close, window  # noqa: E402

LOGIN, OUTDIR = sys.argv[1], sys.argv[2]
TOKEN = os.environ["GITHUB_TOKEN"]


def gql(query, **variables):
    req = urllib.request.Request("https://api.github.com/graphql",
                                 data=json.dumps({"query": query, "variables": variables}).encode(),
                                 headers={"Authorization": f"bearer {TOKEN}", "User-Agent": LOGIN})
    data = json.load(urllib.request.urlopen(req, timeout=60))
    if data.get("errors"):
        raise SystemExit(f"GraphQL error: {data['errors']}")
    return data["data"]


def fetch():
    u = gql("""query($l:String!){user(login:$l){createdAt followers{totalCount}
      pullRequests{totalCount} issues{totalCount}
      repositoriesContributedTo(contributionTypes:[COMMIT,PULL_REQUEST,ISSUE,REPOSITORY]){totalCount}
      repositories(ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC,first:100){totalCount nodes{stargazerCount
        languages(first:12,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}
      contributionsCollection{contributionYears}}}""", l=LOGIN)["user"]
    days, commits = {}, 0
    for y in u["contributionsCollection"]["contributionYears"]:
        c = gql("""query($l:String!,$f:DateTime!,$t:DateTime!){user(login:$l){contributionsCollection(from:$f,to:$t){
              totalCommitContributions restrictedContributionsCount
              contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}""",
                l=LOGIN, f=f"{y}-01-01T00:00:00Z", t=f"{y}-12-31T23:59:59Z")["user"]["contributionsCollection"]
        commits += c["totalCommitContributions"]
        for w in c["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
    langs = {}
    for r in u["repositories"]["nodes"]:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, [0, e["node"]["color"] or P["fg2"]])[0] += e["size"]
    return dict(
        commits=commits,
        prs=u["pullRequests"]["totalCount"],
        issues=u["issues"]["totalCount"],
        stars=sum(r["stargazerCount"] for r in u["repositories"]["nodes"]),
        repos=u["repositories"]["totalCount"],
        contributed=u["repositoriesContributedTo"]["totalCount"],
        followers=u["followers"]["totalCount"],
        days=dict(sorted(days.items())),
        langs=sorted(langs.items(), key=lambda kv: -kv[1][0]),
    )


def streaks(days):
    today = dt.date.today().isoformat()
    seq = [(d, n) for d, n in days.items() if d <= today]
    longest = run = 0
    best = (None, None)
    start = None
    for d, n in seq:
        if n > 0:
            run += 1
            start = start or d
            if run > longest:
                longest, best = run, (start, d)
        else:
            run, start = 0, None
    cur = 0
    items = list(reversed(seq))
    if items and items[0][1] == 0:  # today not yet active: streak still alive from yesterday
        items = items[1:]
    for _, n in items:
        if n == 0:
            break
        cur += 1
    return cur, longest, best


def fmt(n):
    return f"{n:,}"


EXTRA_CSS = """
.grow{animation:grow 1.1s cubic-bezier(.2,.7,.2,1) both;transform-box:fill-box;transform-origin:left center}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.draw{animation:draw 2.2s ease-out both}
@keyframes draw{from{stroke-dashoffset:var(--len)}to{stroke-dashoffset:0}}
.fadein{animation:fadein 1.2s ease-out both}
@keyframes fadein{from{opacity:0}to{opacity:1}}
.pop{animation:pop .35s cubic-bezier(.3,1.6,.5,1) both;transform-box:fill-box;transform-origin:center}
@keyframes pop{from{transform:scale(0)}to{transform:scale(1)}}
"""


def stats_svg(st):
    d = Doc(1200, 340, f"GitHub stats for {LOGIN}")
    d.css.append(S.COMMON_CSS + EXTRA_CSS)
    window(d, "gh stats --live")
    total = sum(st["days"].values())
    rows = [("contributions", fmt(total), P["cyan"]), ("commits", fmt(st["commits"]), P["blue"]),
            ("pull requests", fmt(st["prs"]), P["purple"]), ("issues", fmt(st["issues"]), P["orange"]),
            ("stars earned", fmt(st["stars"]), P["yellow"]), ("public repos", fmt(st["repos"]), P["green"]),
            ("contributed to", fmt(st["contributed"]), P["teal"])]
    x, y = 48, 92
    d.body.append(d.text("$ gh api user", x, y - 6, 14, S.P["dim"]))
    y += 24
    for i, (k, v, col) in enumerate(rows):
        line, _ = d.spans([("▸ ", col), (k.ljust(16), P["fg2"]), (v.rjust(6), P["fg"], B)], x, y, 17)
        d.body.append(f'<g class="rise" style="animation-delay:{.2 + i * .08:.2f}s">{line}</g>')
        y += 31
    # language meters
    lx = 520
    d.body.append(f'<rect x="{lx - 34}" y="70" width="1" height="{d.h - 100}" fill="{P["line"]}"/>')
    d.body.append(d.text("$ top languages by bytes (public repos)", lx, 86, 14, S.P["dim"]))
    langs = st["langs"][:7]
    tot = sum(v[0] for _, v in st["langs"]) or 1
    ly = 116
    barx, barw = lx + 150, 380
    for i, (name, (size, color)) in enumerate(langs):
        pct = size / tot * 100
        delay = .35 + i * .1
        d.body.append(f'<g class="rise" style="animation-delay:{delay:.2f}s">'
                      + d.text(name[:12], lx, ly, 16, P["fg"])
                      + d.text(f"{pct:5.1f}%", barx + barw + 14, ly, 15, P["fg2"]) + "</g>")
        d.body.append(f'<rect x="{barx}" y="{ly - 13}" width="{barw}" height="14" rx="3" fill="{P["surf2"]}" stroke="{P["line"]}"/>')
        w = max(barw * pct / 100, 3)
        d.body.append(f'<rect class="grow" style="animation-delay:{delay + .15:.2f}s" x="{barx}" y="{ly - 13}" width="{w:.1f}" height="14" rx="3" fill="{color}"/>')
        ly += 31
    close(d)
    d.save("stats.svg", OUTDIR)


def activity_svg(st):
    d = Doc(1200, 470, f"Contribution activity for {LOGIN}")
    d.css.append(S.COMMON_CSS + EXTRA_CSS)
    window(d, "git log --graph --since=30.days")
    days = st["days"]
    today = dt.date.today().isoformat()
    cur, longest, (bs, be) = streaks(days)
    total = sum(days.values())
    first = next((k for k, v in days.items() if v), None) or today

    def nice(s):
        return dt.date.fromisoformat(s).strftime("%b %d, %Y") if s else "-"

    blocks = [(fmt(total), "total contributions", f"since {nice(first)}", P["cyan"]),
              (f"{cur}d", "current streak", "keep it going" if cur else "start one today", P["orange"]),
              (f"{longest}d", "longest streak", f"{nice(bs)} to {nice(be)}" if bs else "-", P["purple"])]
    bw = 1104 / 3
    for i, (big, label, sub, col) in enumerate(blocks):
        x = 48 + i * bw
        g = (d.text(big, x, 112, 38, col, B) + d.text(label, x, 140, 15, P["fg"])
             + d.text(sub, x, 162, 13, S.P["dim"]))
        d.body.append(f'<g class="rise" style="animation-delay:{.2 + i * .12:.2f}s">{g}</g>')
        if i:
            d.body.append(f'<rect x="{x - 26:.0f}" y="80" width="1" height="88" fill="{P["line"]}"/>')
    # 30-day chart
    last = [(k, v) for k, v in days.items() if k <= today][-30:]
    cx0, cy0, cw_, ch_ = 92, 196, 1060, 200
    mx = max([v for _, v in last] + [1])
    step = max(1, -(-mx // 4))
    top = step * 4
    for gi in range(5):
        gy = cy0 + ch_ - ch_ * gi / 4
        d.body.append(f'<line x1="{cx0}" x2="{cx0 + cw_}" y1="{gy:.1f}" y2="{gy:.1f}" stroke="{P["line"]}" stroke-dasharray="3 6"/>')
        lab = str(step * gi)
        d.body.append(d.text(lab, cx0 - 14 - R.cw(12) * len(lab), gy + 4, 12, S.P["dim"]))
    d.body.append(d.text("contributions per day", cx0, cy0 - 12, 12, S.P["dim"]))
    pts = []
    for i, (k, v) in enumerate(last):
        px = cx0 + cw_ * i / max(len(last) - 1, 1)
        py = cy0 + ch_ - ch_ * v / top
        pts.append((px, py, k, v))
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py, *_ in pts)
    area = f"{cx0},{cy0 + ch_} {line} {cx0 + cw_},{cy0 + ch_}"
    d.defs.append(f'<linearGradient id="ar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{P["blue"]}" stop-opacity=".35"/>'
                  f'<stop offset="1" stop-color="{P["blue"]}" stop-opacity="0"/></linearGradient>'
                  f'<linearGradient id="ln" x1="0" x2="1"><stop offset="0" stop-color="{P["cyan"]}"/><stop offset=".5" stop-color="{P["blue"]}"/>'
                  f'<stop offset="1" stop-color="{P["purple"]}"/></linearGradient>')
    length = sum(((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** .5 for i in range(len(pts) - 1)) + 10
    d.body.append(f'<polygon class="fadein" style="animation-delay:.9s" points="{area}" fill="url(#ar)"/>')
    d.body.append(f'<polyline class="draw" style="--len:{length:.0f};animation-delay:.5s" points="{line}" fill="none" stroke="url(#ln)" '
                  f'stroke-width="3" stroke-linejoin="round" stroke-linecap="round" stroke-dasharray="{length:.0f}"/>')
    for i, (px, py, k, v) in enumerate(pts):
        if v:
            d.body.append(f'<circle class="pop" style="animation-delay:{.5 + 2.2 * i / len(pts):.2f}s" cx="{px:.1f}" cy="{py:.1f}" r="4" '
                          f'fill="{P["bg"]}" stroke="{P["purple"] if v == mx else P["cyan"]}" stroke-width="2"/>')
        if i % 5 == 0 or i == len(pts) - 1:
            lab = dt.date.fromisoformat(k).strftime("%b %d")
            d.body.append(d.text(lab, px - R.cw(12) * len(lab) / 2, cy0 + ch_ + 24, 12, S.P["dim"]))
    d.h = cy0 + ch_ + 48
    close(d)
    d.save("activity.svg", OUTDIR)


if __name__ == "__main__":
    st = fetch()
    print(json.dumps({k: v for k, v in st.items() if k not in ("days", "langs")}),
          "langs:", [(n, v[0]) for n, v in st["langs"][:7]], "days:", len(st["days"]))
    stats_svg(st)
    activity_svg(st)

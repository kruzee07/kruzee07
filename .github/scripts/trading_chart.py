#!/usr/bin/env python3
"""Draw an animated daily candlestick chart from a GitHub contribution calendar.

Each day of the contribution calendar is one candle:
  open   = the previous day's close
  close  = open moved up or down by how that day's contribution count compares
           with the year's daily average
  volume = that day's contribution count
  high   = above the open and close, wider on busier days
  low    = below the open and close, wider on busier days

The chart shows a 90-day window that pans across the year, auto-scaling its
price axis as highs and lows enter and leave the window.

Usage:
  GITHUB_TOKEN=... trading_chart.py --login kruzee07 --out dist
  trading_chart.py --data calendar.json --out dist   (offline, [[date, count], ...])
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import urllib.request
from xml.sax.saxutils import escape

# Price model
START_PRICE = 100.0
DAILY_MOVE = 0.015  # a day at twice the average count moves the price 1.5%

# Animation
WINDOW = 90       # candles visible at once
STEP = 0.15       # seconds per day of panning
HOLD = 4.0        # seconds to rest on the latest candle before looping
ZOOM_TIME = 0.5   # seconds for the price axis to rescale
MA_DAYS = 20

# Layout
WIDTH, HEIGHT = 840, 348
CL = 16                       # chart left
SP = 8.4                      # pixels per candle
BW = 5.6                      # candle body width
CW = WINDOW * SP              # chart width
CR = CL + CW                  # chart right, price axis starts here
CT, CH = 70, 178              # candle area top and height
VT, VH = 256, 44              # volume area top and height
MONTH_Y = 318

THEMES = {
    "dark": dict(bg="#0d1117", border="#30363d", text="#e6edf3", muted="#7d8590",
                 grid="#21262d", up="#3fb950", down="#f85149", ma="#d29922"),
    "light": dict(bg="#ffffff", border="#d0d7de", text="#1f2328", muted="#656d76",
                  grid="#eaeef2", up="#1a7f37", down="#cf222e", ma="#9a6700"),
}

QUERY = """query($login: String!) { user(login: $login) { contributionsCollection {
  contributionCalendar { weeks { contributionDays { date contributionCount } } } } } }"""


def fetch_calendar(login, token):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "trading-chart"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if "errors" in body:
        raise SystemExit(f"GitHub API error: {body['errors']}")
    weeks = body["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    return [(d["date"], d["contributionCount"])
            for w in weeks for d in w["contributionDays"] if d["date"] <= today]


def build_candles(days):
    counts = [count for _, count in days]
    average = sum(counts) / len(counts) if counts else 0
    most = max(counts, default=0) or 1
    price = START_PRICE
    candles = []
    for date, count in days:
        open_ = price
        move = (count - average) / average * DAILY_MOVE if average else 0
        close = open_ * (1 + move)
        seed = hashlib.sha256(date.encode()).digest()
        wick = open_ * (0.002 + 0.006 * count / most)
        high = max(open_, close) + wick * (0.3 + seed[0] / 255)
        low = min(open_, close) - wick * (0.3 + seed[1] / 255)
        candles.append(dict(date=dt.date.fromisoformat(date), o=open_, h=high, l=low,
                            c=close, v=count))
        price = close
    for i, candle in enumerate(candles):
        recent = candles[max(0, i - MA_DAYS + 1):i + 1]
        candle["ma"] = sum(c["c"] for c in recent) / len(recent)
    return candles


def nice_step(span):
    raw = span / 4
    magnitude = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if m * magnitude >= raw:
            return m * magnitude


def fit_range(low, high):
    """Padded range around the prices, plus a round tick step for the labels."""
    pad = (high - low) * 0.12 or 1
    low, high = low - pad, high + pad
    return (round(low, 4), round(high, 4), nice_step(high - low))


def axis_ranges(candles, first):
    """Price range for each right-edge candle. Only rescale when needed."""
    ranges, current = [], None
    for j in range(first, len(candles)):
        window = candles[j - first:j + 1]
        low = min(c["l"] for c in window)
        high = max(c["h"] for c in window)
        if (current is None or low < current[0] or high > current[1]
                or high - low < 0.7 * (current[1] - current[0])):
            current = fit_range(low, high)
        ranges.append(current)
    return ranges


def fmt(value):
    return f"{value:,.2f}"


def render(candles, theme_name):
    t = THEMES[theme_name]
    n = len(candles)
    win = min(WINDOW, n)
    first = win - 1                     # right-edge candle when the loop starts
    moves = n - win
    pan_time = moves * STEP
    total = pan_time + HOLD
    animated = moves > 0

    def pct(seconds):
        return f"{min(seconds, total) / total * 100:.5f}%"

    def time_of(j):
        return (j - first) * STEP

    def x_of(i):
        return CL + i * SP + SP / 2

    def screen_y(price, rng):
        return CT + (rng[1] - price) / (rng[1] - rng[0]) * CH

    def zoom(rng):
        k = CH / (rng[1] - rng[0])
        return f"translate(0px,{CT + rng[1] * k:.3f}px) scale(1,{k:.6f})"

    ranges = axis_ranges(candles, first)
    segments = []  # (start j, end j exclusive, range)
    for offset, rng in enumerate(ranges):
        j = first + offset
        if segments and segments[-1][2] == rng:
            segments[-1][1] = j + 1
        else:
            segments.append([j, j + 1, rng])

    css = [
        f"text{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;fill:{t['muted']};font-size:11px}}",
        ".m{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}",
        f".tx{{fill:{t['text']}}}",
        f".up{{fill:{t['up']}}} .dn{{fill:{t['down']}}}",
        ".z line,.z polyline{vector-effect:non-scaling-stroke}",
        "@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}",
        ".live{animation:pulse 1.6s ease-in-out infinite}",
    ]
    end_x = -moves * SP
    if animated:
        css += [
            f"@keyframes pan{{0%{{transform:translateX(0px)}}{pct(pan_time)}{{transform:translateX({end_x:.2f}px)}}100%{{transform:translateX({end_x:.2f}px)}}}}",
            f".pan{{animation:pan {total:.2f}s linear infinite}}",
        ]
        # Zoom keyframes: hold each range, ease into the next over ZOOM_TIME.
        points = [(0.0, segments[0][2])]
        for k in range(1, len(segments)):
            start = time_of(segments[k][0])
            nxt = time_of(segments[k + 1][0]) if k + 1 < len(segments) else total
            points.append((start, segments[k - 1][2]))
            points.append((min(start + ZOOM_TIME, nxt, total), segments[k][2]))
        points.append((total, segments[-1][2]))
        frames, last_pct = [], -1.0
        for seconds, rng in points:
            p = float(pct(seconds)[:-1])
            if p <= last_pct:
                continue
            frames.append(f"{p:.5f}%{{transform:{zoom(rng)}}}")
            last_pct = p
        css += [
            f"@keyframes zoom{{{''.join(frames)}}}",
            f".z{{transform-origin:0 0;animation:zoom {total:.2f}s ease-in-out infinite}}",
            # Slightly shorter than a day so neighbouring readouts never overlap.
            f"@keyframes slot{{0%{{opacity:1}}{pct(STEP - 0.004)}{{opacity:0}}100%{{opacity:0}}}}",
            f".s{{opacity:0;animation:slot {total:.2f}s step-end infinite}}",
            f"@keyframes last{{0%{{opacity:0}}{pct(pan_time)}{{opacity:1}}100%{{opacity:1}}}}",
            f".s.last{{opacity:1;animation:last {total:.2f}s step-end infinite}}",
        ]
        for k, (start, end, _) in enumerate(segments):
            a, b = time_of(start), (time_of(end) if end < n else total)
            if a == 0 and b >= total:
                continue
            if a == 0:
                kf = f"0%{{opacity:1}}{pct(b)}{{opacity:0}}100%{{opacity:0}}"
            elif b >= total:
                kf = f"0%{{opacity:0}}{pct(a)}{{opacity:1}}100%{{opacity:1}}"
            else:
                kf = f"0%{{opacity:0}}{pct(a)}{{opacity:1}}{pct(b)}{{opacity:0}}100%{{opacity:0}}"
            css.append(f"@keyframes g{k}{{{kf}}}")
            css.append(f".g{k}{{animation:g{k} {total:.2f}s step-end infinite}}")

    out = []
    w = out.append
    w(f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
      f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Animated candlestick chart of daily GitHub contributions">')
    w(f"<style>{''.join(css)}</style>")
    w("<defs>"
      f'<clipPath id="cc"><rect x="{CL}" y="{CT - 6}" width="{CW}" height="{CH + 12}"/></clipPath>'
      f'<clipPath id="cv"><rect x="{CL}" y="{VT}" width="{CW}" height="{VH}"/></clipPath>'
      f'<clipPath id="cx"><rect x="{CL}" y="{CT}" width="{CW}" height="{MONTH_Y + 6 - CT}"/></clipPath>'
      "</defs>")
    w(f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="8" fill="{t["bg"]}" stroke="{t["border"]}"/>')

    # Header: static ticker and yearly stats.
    last = candles[-1]
    year_change = (last["c"] / candles[0]["o"] - 1) * 100
    hi52 = max(c["h"] for c in candles)
    lo52 = min(c["l"] for c in candles)
    yc = "up" if year_change >= 0 else "dn"
    w(f'<circle class="live" cx="{CL + 5}" cy="22" r="4" fill="{t["up"]}"/>')
    w(f'<text x="{CL + 16}" y="27" class="tx" style="font-size:16px;font-weight:600">KRUZEE</text>')
    w(f'<text x="{CL + 88}" y="27">GitHub Contributions · 1D</text>')
    w(f'<text x="{WIDTH - 16}" y="27" text-anchor="end" class="m">1Y <tspan class="{yc}">{year_change:+.2f}%</tspan></text>')
    w(f'<text x="{WIDTH - 16}" y="48" text-anchor="end" class="m">52W H <tspan class="tx">{fmt(hi52)}</tspan> L <tspan class="tx">{fmt(lo52)}</tspan></text>')

    # Price axis gridlines and labels, one set per axis range.
    for k, (_, _, rng) in enumerate(segments):
        cls = f' class="g{k}"' if animated and len(segments) > 1 else ""
        parts = [f"<g{cls}>"]
        v = math.ceil(rng[0] / rng[2]) * rng[2]
        while v <= rng[1]:
            y = screen_y(v, rng)
            if CT - 1 <= y <= CT + CH + 1:
                parts.append(f'<line x1="{CL}" x2="{CR}" y1="{y:.1f}" y2="{y:.1f}" stroke="{t["grid"]}"/>')
                parts.append(f'<text x="{CR + 8}" y="{y + 4:.1f}" class="m">{fmt(v)}</text>')
            v += rng[2]
        parts.append("</g>")
        w("".join(parts))

    # Month separators and labels (pan only).
    months = []
    for i, c in enumerate(candles):
        if c["date"].day == 1:
            x = x_of(i) - SP / 2
            label = c["date"].strftime("%b") if c["date"].month != 1 else str(c["date"].year)
            months.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{CT}" y2="{VT + VH}" stroke="{t["grid"]}" stroke-dasharray="2 3"/>'
                          f'<text x="{x + 3:.1f}" y="{MONTH_Y}">{label}</text>')
    pan_attr = f' transform="translate({end_x:.2f} 0)"' if not animated else ""
    w(f'<g clip-path="url(#cx)"><g class="pan"{pan_attr}>{"".join(months)}</g></g>')

    # Candles and moving average (pan + zoom).
    groups = {"up": ([], []), "dn": ([], [])}
    for i, c in enumerate(candles):
        wicks, bodies = groups["up" if c["c"] >= c["o"] else "dn"]
        x = x_of(i)
        top = max(c["o"], c["c"])
        height = max(abs(c["c"] - c["o"]), c["o"] * 0.0006)
        wicks.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{-c["h"]:.3f}" y2="{-c["l"]:.3f}"/>')
        bodies.append(f'<rect x="{x - BW / 2:.1f}" y="{-top:.3f}" width="{BW}" height="{height:.3f}"/>')
    ma = " ".join(f"{x_of(i):.1f},{-c['ma']:.3f}" for i, c in enumerate(candles))
    final_zoom = segments[-1][2]
    zk = CH / (final_zoom[1] - final_zoom[0])
    zoom_attr = f' transform="translate(0 {CT + final_zoom[1] * zk:.3f}) scale(1 {zk:.6f})"'
    w(f'<g clip-path="url(#cc)"><g class="pan"{pan_attr}><g class="z"{zoom_attr}>')
    w(f'<polyline points="{ma}" fill="none" stroke="{t["ma"]}" stroke-width="1.2" opacity=".85"/>')
    for name in ("up", "dn"):
        color = t["up" if name == "up" else "down"]
        wicks, bodies = groups[name]
        w(f'<g stroke="{color}" stroke-width="1">{"".join(wicks)}</g>')
        w(f'<g fill="{color}">{"".join(bodies)}</g>')
    w("</g></g></g>")

    # Volume bars (pan only).
    most = max(c["v"] for c in candles) or 1
    bars = {"up": [], "dn": []}
    for i, c in enumerate(candles):
        h = c["v"] / most * (VH - 4)
        if h > 0:
            bars["up" if c["c"] >= c["o"] else "dn"].append(
                f'<rect x="{x_of(i) - BW / 2:.1f}" y="{VT + VH - h:.1f}" width="{BW}" height="{h:.1f}"/>')
    w(f'<g clip-path="url(#cv)"><g class="pan"{pan_attr}>'
      f'<g fill="{t["up"]}" opacity=".45">{"".join(bars["up"])}</g>'
      f'<g fill="{t["down"]}" opacity=".45">{"".join(bars["dn"])}</g></g></g>')
    w(f'<text x="{CR + 8}" y="{VT + 12}">Vol</text>')

    # Per-day overlays: OHLC readout and the current-price tag.
    for j in range(first, n):
        c = candles[j]
        rng = ranges[j - first]
        color = t["up"] if c["c"] >= c["o"] else t["down"]
        cls = "up" if c["c"] >= c["o"] else "dn"
        change = (c["c"] / c["o"] - 1) * 100
        y = min(max(screen_y(c["c"], rng), CT), CT + CH)
        if animated:
            is_last = j == n - 1
            delay = 0 if j == first else total - time_of(j)
            attr = ' class="s last"' if is_last else f' class="s" style="animation-delay:-{delay:.4f}s"'
        else:
            attr = ""
        w(f"<g{attr}>"
          f'<text x="{CL}" y="48" class="m">{c["date"].strftime("%a %b %d %Y")}'
          f'  O <tspan class="{cls}">{fmt(c["o"])}</tspan> H <tspan class="{cls}">{fmt(c["h"])}</tspan>'
          f' L <tspan class="{cls}">{fmt(c["l"])}</tspan> C <tspan class="{cls}">{fmt(c["c"])}</tspan>'
          f'  <tspan class="{cls}">{change:+.2f}%</tspan>  Vol <tspan class="tx">{c["v"]}</tspan></text>'
          f'<line x1="{CL}" x2="{CR}" y1="{y:.1f}" y2="{y:.1f}" stroke="{color}" stroke-dasharray="3 3" opacity=".7"/>'
          f'<rect x="{CR + 1}" y="{y - 9:.1f}" width="62" height="18" rx="3" fill="{color}"/>'
          f'<text x="{CR + 32}" y="{y + 4:.1f}" text-anchor="middle" class="m" style="fill:#fff;font-weight:600">{fmt(c["c"])}</text>'
          "</g>")

    w(f'<text x="{CL}" y="{HEIGHT - 10}" style="font-size:10px">'
      f'<tspan style="fill:{t["ma"]}">━ MA{MA_DAYS}</tspan>  Price moves with daily contributions vs. the yearly average</text>')
    w(f'<text x="{WIDTH - 16}" y="{HEIGHT - 10}" text-anchor="end" style="font-size:10px">'
      f'Updated {escape(last["date"].isoformat())}</text>')
    w("</svg>")
    return "".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", default=os.environ.get("GITHUB_REPOSITORY_OWNER"))
    parser.add_argument("--data", help="JSON file of [[date, count], ...] instead of the API")
    parser.add_argument("--out", default="dist")
    args = parser.parse_args()

    if args.data:
        with open(args.data) as f:
            days = [tuple(d) for d in json.load(f)]
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token or not args.login:
            raise SystemExit("Set GITHUB_TOKEN and --login, or pass --data.")
        days = fetch_calendar(args.login, token)

    candles = build_candles(days)
    os.makedirs(args.out, exist_ok=True)
    for theme in THEMES:
        path = os.path.join(args.out, f"trading-chart-{theme}.svg")
        with open(path, "w") as f:
            f.write(render(candles, theme))
        print(f"wrote {path} ({os.path.getsize(path) // 1024} KB, {len(candles)} days)")


if __name__ == "__main__":
    main()

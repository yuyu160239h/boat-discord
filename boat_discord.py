#!/usr/bin/env python3
"""PCを閉じても動く朝通知と、発走10分前通知。Discordウェブフックへ送る。

環境変数 DISCORD_WEBHOOK だけ必要。URLはファイルに書かない。
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
BASE = "https://boatraceopenapi.github.io/api/v1"
STADIUM = {
    1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川", 6: "浜名湖",
    7: "蒲郡", 8: "常滑", 9: "津", 10: "三国", 11: "びわこ", 12: "住之江",
    13: "尼崎", 14: "鳴門", 15: "丸亀", 16: "児島", 17: "宮島", 18: "徳山",
    19: "下関", 20: "若松", 21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村",
}
WATCH = {3783: "瓜生", 3942: "寺田", 4362: "土屋", 4990: "4990"}
TECH = {1: "逃げ"}


def get(url):
    with urllib.request.urlopen(url, timeout=60) as res:
        return json.load(res)


def program(day):
    return get(f"{BASE}/{day[:4]}/{day}.json")


def post(text):
    url = os.environ.get("DISCORD_WEBHOOK", "").strip()
    if not url:
        print(text)
        return
    body = json.dumps({"content": text[:1900]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def daterange(start, end):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def history(today):
    start = datetime(2026, 8, 25).date()
    end = min(datetime(2026, 10, 6).date(), today - timedelta(days=1))
    rc = {}
    stad = {}
    for day in daterange(start, end):
        key = day.strftime("%Y%m%d")
        try:
            data = program(key)
        except Exception:
            continue
        stadiums = (data.get("programs") or {}).get("stadiums") or {}
        for stadium in stadiums.values():
            for race in (stadium.get("races") or {}).values():
                result = race.get("result") or {}
                boats = list((result.get("racers") or {}).values())
                if len(boats) < 6:
                    continue
                by = {b.get("course_number"): b for b in boats}
                if not all(c in by for c in range(1, 7)):
                    continue
                winner = next((b for b in boats if b.get("place_number") == 1), None)
                if not winner:
                    continue
                sn = race.get("stadium_number")
                stad.setdefault(sn, [0, 0])
                stad[sn][0] += 1
                if winner.get("course_number") == 1:
                    stad[sn][1] += 1
                tech = TECH.get(result.get("technique_number"))
                for c, boat in by.items():
                    if not isinstance(boat.get("place_number"), int):
                        continue
                    s = rc.setdefault((boat.get("number"), c), {"n": 0, "win": 0, "nige": 0, "st": 0.0, "stn": 0})
                    s["n"] += 1
                    if boat["place_number"] == 1:
                        s["win"] += 1
                        if c == 1 and tech == "逃げ":
                            s["nige"] += 1
                    st = boat.get("start_timing")
                    if isinstance(st, (int, float)) and 0 <= st < 1:
                        s["st"] += st
                        s["stn"] += 1
    return rc, stad


def races(data):
    stadiums = (data.get("programs") or {}).get("stadiums") or {}
    for sn, stadium in stadiums.items():
        for rn, race in (stadium.get("races") or {}).items():
            racers = race.get("racers") or {}
            yield int(sn), int(rn), race, {b.get("entry_number"): b for b in racers.values()}


def rank(values, target, reverse=False):
    usable = [(i, v) for i, v in values if isinstance(v, (int, float))]
    if target is None or not isinstance(target, (int, float)) or len(usable) < 6:
        return None
    ordered = sorted(usable, key=lambda x: x[1], reverse=reverse)
    for place, (i, v) in enumerate(ordered, 1):
        if v == target:
            return place
    return None


def exhibition(race):
    preview = ((race.get("preview") or {}).get("racers") or {})
    boats = list(preview.values())
    one = next((b for b in boats if b.get("entry_number") == 1), None)
    if not one:
        return None, None
    time_rank = rank([(b.get("entry_number"), b.get("exhibition_time")) for b in boats], one.get("exhibition_time"))
    st_rank = rank([(b.get("entry_number"), b.get("start_timing")) for b in boats], one.get("start_timing"))
    return time_rank, st_rank


def build(today):
    rc, stad = history(today)
    data = program(today.strftime("%Y%m%d"))
    watched, group_a, group_b = [], [], []
    for sn, rn, race, by in races(data):
        one, two, three = by.get(1), by.get(2), by.get(3)
        if not one:
            continue
        closed = race.get("closed_at") or ""
        if one.get("number") in WATCH:
            watched.append(f"{STADIUM.get(sn, sn)} {rn}R {closed[11:16]} {WATCH[one['number']]}")
        if not two:
            continue
        s1 = rc.get((one.get("number"), 1), {"n": 0, "win": 0, "nige": 0, "st": 0.0, "stn": 0})
        s2 = rc.get((two.get("number"), 2), {"n": 0, "win": 0})
        s3 = rc.get((three.get("number"), 3), {"n": 0, "win": 0}) if three else {"n": 0, "win": 0}
        if s1["n"] < 4 or s2["n"] < 3 or s1["stn"] < 3:
            pass
        else:
            c1, stavg, c2 = s1["win"] / s1["n"], s1["st"] / s1["stn"], s2["win"] / s2["n"]
            if c1 >= 0.70 and stavg <= 0.15 and c2 <= 0.16:
                group_a.append((closed, sn, rn, one.get("name"), c1, stavg, c2))
        base = stad.get(sn, [0, 0])
        if base[0] < 40 or s1["n"] < 5 or s2["n"] < 4:
            continue
        c1 = s1["win"] / s1["n"]
        nige = s1["nige"] / s1["n"]
        c2 = s2["win"] / s2["n"]
        c3 = (s3["win"] / s3["n"]) if s3["n"] else 0
        stad_c1 = base[1] / base[0]
        score = 0
        score += 2 if c1 >= 0.55 else (-2 if c1 < 0.40 else 0)
        score += 1 if stad_c1 >= 0.55 else (-1 if stad_c1 < 0.48 else 0)
        score += 2 if c2 <= 0.12 else (-2 if c2 >= 0.22 else 0)
        score += 1 if c3 <= 0.12 else (-1 if c3 >= 0.22 else 0)
        if score >= 3 and (nige < 0.55 or c1 < 0.50):
            why = "逃げ55%未満" if nige < 0.55 else "勝率50%未満"
            group_b.append((closed, sn, rn, one.get("name"), why, c1, nige))
    return data, watched, group_a, group_b


def morning(today):
    _, watched, group_a, group_b = build(today)
    lines = [f"ボート {today.isoformat()}", "指定1号艇: " + (" / ".join(watched) if watched else "該当なし"), "", "A 1-2期待値。展示2位になるまで買わない"]
    lines += [f"{STADIUM.get(sn, sn)} {rn}R {closed[11:16]} {name} 1勝{c1:.0%} ST{st:.3f} 2勝{c2:.0%}" for closed, sn, rn, name, c1, st, c2 in sorted(group_a)] or ["なし"]
    lines += ["", "B ギャップ。単勝1"]
    lines += [f"{STADIUM.get(sn, sn)} {rn}R {closed[11:16]} {name} {why} 1勝{c1:.0%} 逃げ{nige:.0%}" for closed, sn, rn, name, why, c1, nige in sorted(group_b)] or ["なし"]
    post("\n".join(lines))


def before_start(today, now):
    data, _, group_a, _ = build(today)
    lookup = {(sn, rn): race for sn, rn, race, _ in races(data)}
    for closed, sn, rn, name, c1, st, c2 in group_a:
        deadline = datetime.strptime(closed, "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
        minutes = (deadline - now).total_seconds() / 60
        if not 6 <= minutes <= 14:
            continue
        time_rank, st_rank = exhibition(lookup[(sn, rn)])
        place = f"{STADIUM.get(sn, sn)} {rn}R {name}"
        if time_rank == 2 and st_rank == 2:
            post(f"買い: {place}\n2連複1-2を1500円、3連単1-2-3、1-2-4、1-2-5、1-2-6を各400円")
        else:
            post(f"見送り: {place} 展示タイム{time_rank} 展示ST{st_rank}")


if __name__ == "__main__":
    now = datetime.now(JST)
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if mode == "morning":
        morning(now.date())
    elif mode == "before":
        before_start(now.date(), now)
    else:
        if now.hour == 8 and now.minute < 20:
            morning(now.date())
        before_start(now.date(), now)

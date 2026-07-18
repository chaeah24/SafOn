"""계산과 저장 — 화면과 무관한 순수 로직. streamlit을 쓰지 않아 따로 테스트할 수 있다."""

import json
from datetime import datetime

import requests
import networkx as nx
from geopy.distance import distance as geo

from config import (STORE, PHOTOS, W, W_DEFAULT, W_TIME, RADIUS, SERVERS)


# ── 저장 ───────────────────────────────────────────────
def load():
    if STORE.exists():
        try:
            j = json.loads(STORE.read_text(encoding="utf-8"))
            return j.get("data", []), j.get("rebut", [])
        except Exception:
            pass
    return [], []


def save(data, rebut):
    STORE.write_text(json.dumps({"data": data, "rebut": rebut},
                                ensure_ascii=False, indent=2), encoding="utf-8")


def add(data, lat, lng, name, factors, tm, memo, photo=None):
    """130m 안에 기존 지점이 있으면 합친다 → 상습 구간 판정의 근거."""
    near = next((d for d in data
                 if geo((d["lat"], d["lng"]), (lat, lng)).meters < 130), None)
    fn = None
    if photo is not None:
        fn = f"{datetime.now():%Y%m%d_%H%M%S}_{photo.name}"
        (PHOTOS / fn).write_bytes(photo.getbuffer())

    if near:
        near["count"] += 1
        near["factors"] = list(dict.fromkeys(near["factors"] + factors))
        near["photo"] = near.get("photo") or fn
        return f"'{near['name']}'에 합쳐졌습니다 (누적 {near['count']}건)"

    data.append(dict(id=max([d["id"] for d in data], default=0) + 1,
                     name=name or f"지점 {len(data)+1}", lat=lat, lng=lng,
                     count=1, time=tm, factors=factors,
                     memo=memo or "(설명 없음)", photo=fn,
                     at=f"{datetime.now():%Y-%m-%d %H:%M}"))
    return "등록되었습니다."


# ── 판정 ───────────────────────────────────────────────
def assess(d):
    """AI 위험도 판정. 점수, 등급, 근거를 함께 돌려줘 화면에 드러낸다."""
    f = d["factors"]
    s = sum(W.get(k, W_DEFAULT) for k in f) * W_TIME[d["time"]] + min(d["count"], 10) * .35
    lv = "위험 매우 높음" if s >= 12 else "주의 필요" if s >= 7 else "경미"
    return round(s, 1), lv, ", ".join(f"{k} +{W.get(k, W_DEFAULT)}" for k in f)


def danger(pts, rows):
    """경로가 지나는 위험 지점과 합산 점수."""
    hit = [(d["name"], assess(d)[0]) for d in rows
           if any(geo((d["lat"], d["lng"]), p).meters <= RADIUS for p in pts)]
    return sum(s for _, s in hit), hit


# ── 경로: 실제 도로망 ──────────────────────────────────
def ask(base, a, b, alt=True, verify=True):
    """OSRM 한 서버에 요청. (성공여부, 결과 또는 메시지, 주소)"""
    url = f"{base}/{a[1]},{a[0]};{b[1]},{b[0]}"
    p = {"overview": "full", "geometries": "geojson"}
    if alt:
        p["alternatives"] = "true"
    try:
        r = requests.get(url, params=p, verify=verify, timeout=15,
                         headers={"User-Agent": "darkroad/1.0"})
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:120]}", url
    if r.status_code != 200:
        return False, f"HTTP {r.status_code} · {r.text[:120]}", r.url
    j = r.json()
    if j.get("code") != "Ok":
        return False, f"{j.get('code')} · {j.get('message','')}", r.url
    return True, j, r.url


def online(a, b, rows, verify=True):
    """서버를 차례로 시도해 첫 성공을 쓴다."""
    log = []
    for name, base in SERVERS:
        for alt in (True, False):
            ok, res, url = ask(base, a, b, alt, verify)
            tag = f"{name}{' (대안경로)' if alt else ''}"
            if ok:
                out = []
                for rt in res["routes"]:
                    pts = [(la, ln) for ln, la in rt["geometry"]["coordinates"]]
                    dg, hit = danger(pts, rows)
                    out.append(dict(pts=pts, dist=rt["distance"],
                                    dur=rt["duration"], dg=dg, hit=hit))
                return {"ok": True, "sc": out, "server": tag}
            log.append((tag, str(res)))
    return {"ok": False, "log": log}


# ── 경로: 오프라인 ─────────────────────────────────────
def offline(a, b, rows, n=40):
    """인터넷 없이 계산하는 대체 경로.

    격자를 만들고 각 칸의 이동 비용에 위험 지점에 가까울수록 가중치를 더한 뒤
    최단경로를 두 번 푼다. 한 번은 거리만으로, 한 번은 거리+위험으로.
    실제 도로를 따르지는 않지만 경로탐색 자체는 진짜 알고리즘이다.
    """
    pad = 0.006
    la0, la1 = min(a[0], b[0]) - pad, max(a[0], b[0]) + pad
    ln0, ln1 = min(a[1], b[1]) - pad, max(a[1], b[1]) + pad
    lats = [la0 + (la1 - la0) * i / (n - 1) for i in range(n)]
    lngs = [ln0 + (ln1 - ln0) * j / (n - 1) for j in range(n)]

    def risk(la, ln):
        t = 0.0
        for d in rows:
            m = geo((d["lat"], d["lng"]), (la, ln)).meters
            if m < 250:
                t += assess(d)[0] * (1 - m / 250)
        return t

    R = [[risk(lats[i], lngs[j]) for j in range(n)] for i in range(n)]

    G = nx.Graph()
    for i in range(n):
        for j in range(n):
            for di, dj in ((0, 1), (1, 0), (1, 1), (1, -1)):
                i2, j2 = i + di, j + dj
                if 0 <= i2 < n and 0 <= j2 < n:
                    m = geo((lats[i], lngs[j]), (lats[i2], lngs[j2])).meters
                    pen = (R[i][j] + R[i2][j2]) / 2
                    G.add_edge((i, j), (i2, j2), d=m, w=m * (1 + pen * .9))

    def near(pt):
        return (min(range(n), key=lambda i: abs(lats[i] - pt[0])),
                min(range(n), key=lambda j: abs(lngs[j] - pt[1])))

    def solve(key):
        path = nx.shortest_path(G, near(a), near(b), weight=key)
        pts = [(lats[i], lngs[j]) for i, j in path]
        dist = sum(geo(pts[k], pts[k + 1]).meters for k in range(len(pts) - 1))
        dg, hit = danger(pts, rows)
        return dict(pts=pts, dist=dist, dur=dist / 1.25, dg=dg, hit=hit)

    return [solve("d"), solve("w")]


def find(a, b, rows, engine="자동", verify=True):
    """엔진 설정에 따라 경로를 찾는다. 결과와 어떤 방식을 썼는지 함께 돌려준다."""
    if engine != "오프라인 계산":
        r = online(a, b, rows, verify)
        if r["ok"]:
            return dict(sc=r["sc"], src=f"{r['server']} (실제 도로망)", err=None)
        if engine == "실제 도로망만":
            return dict(sc=None, src="", err=r["log"])
    return dict(sc=offline(a, b, rows), src="오프라인 격자 계산 (실제 도로 아님)", err=None)


def report_text(data, rebut):
    """구청 제출용 초안."""
    tops = sorted(data, key=lambda x: -x["count"])[:3]
    L = ["대전광역시 야간 보행 안전 개선 요청서 (초안)",
         f"작성일 {datetime.now():%Y년 %m월 %d일} · "
         f"주민 제보 {sum(d['count'] for d in data)}건 기준",
         "", "1. 요청 개요",
         f"주민이 등록한 야간 보행 위험 지점 {len(data)}개소를 분석한 결과입니다.",
         f"이 중 {sum(d['count'] >= 5 for d in data)}개소는 5건 이상 반복 제보된 "
         "상습 구간입니다.", "", "2. 우선 개선 요청 구간", ""]
    for i, d in enumerate(tops, 1):
        s, lv, _ = assess(d)
        reb = [x for x in rebut if x["id"] == d["id"]]
        L += [f"  {i}) {d['name']}",
              f"     제보 {d['count']}건 · {d['time']}",
              f"     위험 요인: {', '.join(d['factors'])}",
              f"     주민 진술: {d['memo']}",
              f"     분석 판정: {lv} (점수 {s})"]
        if reb:
            L.append(f"     ※ 주민 반박 {len(reb)}건 접수, 재검토 필요")
        L.append("")
    L += ["3. 이 문서의 한계",
          f"자동 생성된 초안이며 주민 반박 {len(rebut)}건이 반영되지 않은 판정이 "
          "포함될 수 있습니다. 제출 전 현장 확인이 필요합니다."]
    return "\n".join(L)

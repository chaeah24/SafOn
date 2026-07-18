"""
SafOn — 안심귀가 안내
대전광역시 야간 보행 안전 지도

2026 전국 청소년 SW·AI 경진대회 · 심채아 (대전동신과학고등학교)

실행:
    pip3 install -r requirements.txt
    streamlit run safon.py

원래 네 개 파일이던 것을 하나로 합쳤습니다.
    1부 설정값     가중치, 격자 크기, 색, 지도 타일
    2부 계산과 저장  안전도 판정, 경로탐색, 제보 저장
    3부 지도       육각형 벌집, 경로, 제보 점
    4부 화면       탭 4개
"""

import base64
import json
from datetime import datetime
from math import radians, cos, sin, sqrt
from pathlib import Path

import folium
import networkx as nx
import numpy as np
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from folium import MacroElement
from folium.plugins import AntPath, Fullscreen, LocateControl, MiniMap
from geopy.geocoders import Nominatim
from jinja2 import Template
from streamlit_folium import st_folium

try:
    from streamlit_geolocation import streamlit_geolocation
    GEO_OK = True
except ImportError:
    GEO_OK = False


# ═══════ 1부. 설정값 ══════════════════════════════════════

BASE = Path(__file__).parent
STORE = BASE / "reports.json"
PHOTOS = BASE / "photos"
DATA = BASE / "data"
PHOTOS.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)

# ── 별점 제보 ──────────────────────────────────────────
STAR_LABEL = {1: "매우 위험", 2: "위험", 3: "보통", 4: "안전", 5: "매우 안전"}
STAR_W = 3.0
COUNT_BOOST = 0.08

TAG_HINTS = ["어두움", "시야 막힘", "인적 없음", "차와 섞임", "가로등 고장",
             "CCTV 없음", "밝음", "사람 많음", "CCTV 많음", "상가 많음"]

# ── 제보 시간대 (늦을수록 가중치가 크다) ──────────────
TIMES = ["전시간"] + [f"{i:02d}~{i+1:02d}시" for i in range(24)]

# 기본적으로 모든 1시간 간격 시간대의 가중치를 주간(0.3)으로 통일
W_TIME = {t: 0.3 for t in TIMES}
W_TIME["전시간"] = 1.0

# 야간/새벽 시간대 가중치만 특별히 높게 덮어쓰기
W_TIME.update({
    "17~18시": 0.4, "18~19시": 0.6, "19~20시": 0.8, "20~21시": 1.0,
    "21~22시": 1.2, "22~23시": 1.4, "23~24시": 1.6, "00~01시": 1.8,
    "01~02시": 2.0, "02~03시": 2.0, "03~04시": 1.9, "04~05시": 1.9
})

TIME_DEFAULT = 0  # 기본 선택값을 '전시간'(인덱스 0번)으로 설정

# 예전에 제보된 데이터들의 가중치 호환을 위해 과거 형식들도 유지
W_TIME.update({"18~20시": 0.7, "20~22시": 1.1, "22~24시": 1.5, 
               "24시 이후": 1.9, "01~03시": 2.0, "03~05시": 1.9, 
               "05~17시 (주간)": 0.3})

# ── 지도·격자 ──────────────────────────────────────────
BBOX = (36.15, 36.55, 127.20, 127.60)
GRID = 0.003
HEX_ZOOM = 16
CLICK_ZOOM = 17
INFRA_R = 200
RADIUS = 90
CENTER = (36.3504, 127.3845)

# ── 0~100 안전도 ───────────────────────────────────────
SCORE = dict(
    base=32,
    cctv_n=10, cctv_w=3.2,
    bell_n=4,  bell_w=5.0,
    store_n=5, store_w=3.0,
    lamp_n=8,  lamp_w=1.5,
    risk_cap=45, risk_w=1.3,
)

# ── 안전시설 (data/ 폴더에 CSV를 넣으면 자동 반영) ─────
INFRA_SPECS = [
    dict(key="cctv", file="cctv.csv", label="CCTV", relief=0.8, cap=3.0),
    dict(key="bell", file="bell.csv", label="안전비상벨", relief=1.0, cap=2.5),
    dict(key="store", file="store.csv", label="24시 편의점", relief=0.5, cap=2.0),
    dict(key="lamp", file="streetlight.csv", label="가로등", relief=0.35, cap=2.5),
]

CRIME_INDEX = {"동구": 1.0, "중구": 1.0, "서구": 1.0,
               "유성구": 1.0, "대덕구": 1.0}

SERVERS = [
    ("보행자 도로망", "https://routing.openstreetmap.de/routed-foot/route/v1/foot"),
]

TILES = {
    "VWorld 일반 (국토부·한국 상세)": dict(
        tiles="https://xdworld.vworld.kr/2d/Base/service/{z}/{x}/{y}.png",
        attr="© VWorld 국토교통부", max_zoom=19),
    "VWorld 위성영상": dict(
        tiles="https://xdworld.vworld.kr/2d/Satellite/service/{z}/{x}/{y}.jpeg",
        attr="© VWorld 국토교통부", max_zoom=19),
    "VWorld 회색": dict(
        tiles="https://xdworld.vworld.kr/2d/gray/service/{z}/{x}/{y}.png",
        attr="© VWorld 국토교통부", max_zoom=19),
    "OpenStreetMap": dict(tiles="OpenStreetMap", attr=None, max_zoom=19),
    "밝은 단색": dict(tiles="CartoDB positron", attr=None, max_zoom=19),
    "어두운 단색": dict(tiles="CartoDB dark_matter", attr=None, max_zoom=19),
}

NAVY, NAVY_HOVER, NAVY_LIGHT = "#1b2a4a", "#27395f", "#41567f"

CSS = f"""
<style>
  .stApp {{ background:#fff; }}
  html, body, [class*="css"], .stMarkdown, label, p, span, div {{ color:#111 !important; }}
  h1,h2,h3,h4 {{ color:{NAVY} !important; }}
  h1 {{ font-size:2.1rem !important; letter-spacing:-1px; }}

  [data-testid="stMetricValue"] {{ color:{NAVY} !important; font-size:2rem !important; }}
  [data-testid="stMetricLabel"] {{ color:#5a6478 !important; }}
  [data-testid="stMetric"] {{
      background:#f4f6fb; border:1px solid #dde3ee; border-left:4px solid {NAVY};
      border-radius:8px; padding:10px 14px; }}

  .block-container {{ padding:1rem 1.4rem 2rem !important; max-width:100% !important; }}
  iframe {{ width:100% !important; border-radius:12px; border:1px solid #dde3ee; }}

  @keyframes slidePanel {{
    from {{ opacity:0; transform:translateY(-8px); }}
    to   {{ opacity:1; transform:none; }}
  }}
  .side-panel {{ animation:slidePanel .28s cubic-bezier(.2,.85,.3,1); }}
  .card {{ background:#f7f9fc; border:1px solid #e6eaf2; border-radius:10px;
           padding:11px 13px; }}

  .stButton > button, .stDownloadButton > button {{
      background:#fff; color:{NAVY} !important; border:1.5px solid {NAVY_LIGHT};
      border-radius:8px; font-weight:600; transition:.15s; }}
  .stButton > button:hover, .stDownloadButton > button:hover {{
      background:{NAVY}; color:#fff !important; border-color:{NAVY}; }}
  .stButton > button:hover p {{ color:#fff !important; }}

  .stButton > button[kind="primary"] {{
      background:{NAVY}; color:#fff !important; border:1.5px solid {NAVY}; }}
  .stButton > button[kind="primary"]:hover {{
      background:{NAVY_HOVER}; border-color:{NAVY_HOVER}; }}
  
  /* Primary 버튼 및 폼 제출 버튼 글자 무조건 흰색 고정 (모든 내부 태그 포함) */
  button[kind="primary"], 
  button[kind="primary"] *,
  div[data-testid="stFormSubmitButton"] button,
  div[data-testid="stFormSubmitButton"] button * {{
      color:#FFFFFF !important; 
  }}

  .starrow + div button {{
      border:none !important; background:transparent !important;
      font-size:30px !important; line-height:1 !important;
      padding:0 !important; min-height:0 !important;
      box-shadow:none !important; }}
  .starrow + div button:hover {{
      background:transparent !important; transform:scale(1.2);
      transition:transform .12s; }}
  .starrow + div button p {{ color:#f5b301 !important; margin:0 !important;
      font-size:30px !important; }}
  .starrow + div [data-testid="stHorizontalBlock"] {{ gap:0 !important; }}

  .stTabs [data-baseweb="tab"] {{ font-size:1rem; font-weight:600; }}
  .stTabs [data-baseweb="tab"][aria-selected="true"],
  .stTabs [data-baseweb="tab"][aria-selected="true"] p {{ color:{NAVY} !important; }}
  .stTabs [data-baseweb="tab-highlight"], div[data-baseweb="tab-highlight"] {{
      background-color:{NAVY} !important; height:3px !important; }}
  .stTabs [data-baseweb="tab-list"] {{ gap:6px; }}

  input:focus, textarea:focus {{ border-color:{NAVY_LIGHT} !important; }}
</style>
"""


# ═══════ 2부. 계산과 저장 ══════════════════════════════════

M_PER_DEG = 111_320.0
CELL = 0.0025
KX = 1 / cos(radians(36.35))
SQ3 = sqrt(3)


def meters(a, b):
    dlat = (a[0] - b[0]) * M_PER_DEG
    dlng = (a[1] - b[1]) * M_PER_DEG * cos(radians((a[0] + b[0]) / 2))
    return sqrt(dlat * dlat + dlng * dlng)


def tw(t):
    return W_TIME.get(t, 1.0)


def stars_of(d):
    """예전 형식(위험 제보만 있던 시절)도 읽히게 한다."""
    return float(d.get("stars", 1))


def tags_of(d):
    return d.get("tags") or d.get("factors") or []


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


def add(data, lat, lng, name, stars, tags, tm, memo, photo=None):
    """130m 안에 기존 지점이 있으면 합친다. 별점은 평균을 낸다."""
    near = next((d for d in data
                 if meters((d["lat"], d["lng"]), (lat, lng)) < 130), None)
    fn = None
    if photo is not None:
        fn = f"{datetime.now():%Y%m%d_%H%M%S}_{photo.name}"
        (PHOTOS / fn).write_bytes(photo.getbuffer())

    if near:
        n = near["count"]
        near["stars"] = round((stars_of(near) * n + stars) / (n + 1), 2)
        near["count"] = n + 1
        near["tags"] = list(dict.fromkeys(tags_of(near) + tags))
        near["photo"] = near.get("photo") or fn
        return (f"'{near['name']}'에 합쳐졌습니다 "
                f"(누적 {near['count']}건 · 평균 {near['stars']}점)")

    data.append(dict(id=max([d["id"] for d in data], default=0) + 1,
                     name=name or f"지점 {len(data)+1}", lat=lat, lng=lng,
                     count=1, stars=float(stars), time=tm, tags=tags,
                     memo=memo or "(설명 없음)", photo=fn,
                     at=f"{datetime.now():%Y-%m-%d %H:%M}"))
    return "등록되었습니다."


# ── 공공데이터 ─────────────────────────────────────────
LAT_KEYS = ["위도", "lat", "latitude", "y", "wgs84위도", "위도(y)", "ycoord"]
LNG_KEYS = ["경도", "lon", "lng", "longitude", "x", "wgs84경도", "경도(x)", "xcoord"]


def load_csv(filename):
    f = DATA / filename
    if not f.exists():
        return []
    df = None
    for enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
        try:
            df = pd.read_csv(f, encoding=enc, low_memory=False)
            break
        except Exception:
            continue
    if df is None or df.empty:
        return []

    low = {str(c).strip().lower().replace(" ", ""): c for c in df.columns}
    la = next((low[k] for k in LAT_KEYS if k in low), None)
    ln = next((low[k] for k in LNG_KEYS if k in low), None)
    if not la or not ln:
        return []

    df = df[[la, ln]].apply(pd.to_numeric, errors="coerce").dropna()
    s, n, w, e = BBOX
    df = df[df[la].between(s, n) & df[ln].between(w, e)]
    return [(round(a, 6), round(b, 6)) for a, b in df.values]


def build_index(pts):
    idx = {}
    for la, ln in pts:
        idx.setdefault((int(la / CELL), int(ln / CELL)), []).append((la, ln))
    return idx


def load_infra():
    out = {}
    for sp in INFRA_SPECS:
        pts = load_csv(sp["file"])
        out[sp["key"]] = pts
        out[sp["key"] + "_idx"] = build_index(pts)
    return out


def near_count(pt, idx, r=INFRA_R):
    if not isinstance(idx, dict):
        return sum(1 for p in idx if meters(pt, p) <= r)
    la, ln = pt
    ci, cj = int(la / CELL), int(ln / CELL)
    span = int(r / (CELL * M_PER_DEG)) + 1
    return sum(1
               for i in range(ci - span, ci + span + 1)
               for j in range(cj - span, cj + span + 1)
               for p in idx.get((i, j), ())
               if meters(pt, p) <= r)


def around(pt, infra, r=INFRA_R):
    return {sp["key"]: near_count(pt, infra.get(sp["key"] + "_idx") or {}, r)
            for sp in INFRA_SPECS}


# ── 제보 판정 ──────────────────────────────────────────
def effect(d):
    """제보 한 지점의 영향. 양수면 위험, 음수면 안전 쪽."""
    e = (3 - stars_of(d)) * STAR_W * tw(d["time"])
    return e * (1 + min(d["count"], 10) * COUNT_BOOST)


def assess(d, infra=None):
    """제보 판정. 점수(영향), 등급, 근거를 돌려준다."""
    st_ = stars_of(d)
    e = effect(d)
    label = STAR_LABEL.get(round(st_), "보통")
    lv = ("위험 매우 높음" if e >= 8 else "주의 필요" if e >= 3
          else "안전 제보" if e <= -3 else "보통")
    why = (f"별점 {st_:g}점({label}) · {d['time']} 가중치 ×{tw(d['time'])} "
           f"· 제보 {d['count']}건")
    if tags_of(d):
        why += " · " + ", ".join(tags_of(d))
    return round(e, 1), lv, why


def danger(pts, rows, infra=None):
    """경로가 지나는 제보 지점. 안전 제보는 위험 합을 낮춘다."""
    step = max(1, len(pts) // 400)
    thin = pts[::step]
    hit = [(d["name"], round(effect(d), 1)) for d in rows
           if any(meters((d["lat"], d["lng"]), c) <= RADIUS for c in thin)]
    return sum(s for _, s in hit), [h for h in hit if h[1] > 0]


# ── 경로가 지나는 구역의 안전도 ────────────────────────
#
# 제보만으로 경로를 고르면 "아무도 제보하지 않은 어두운 골목"이
# 가장 안전한 길로 뽑힌다. 제보가 없다는 것은 안전하다는 뜻이 아니라
# 아직 아무도 걷지 않았다는 뜻이므로, 지도에 쓰는 구역 안전도를
# 경로 계산에도 그대로 반영한다.

ZONE_MID = 50.0   # 이 점수를 기준으로 위/아래를 가른다
ZONE_W = 0.30     # 구역 안전도가 경로 선택에 미치는 정도
ZONE_BAD = 25     # 이 점수 미만이면 '위험 구간'으로 센다


def zone_of(pts, tab):
    """경로가 지나는 육각형 칸들의 안전도를 요약한다.

    돌려주는 값
        avg  지나는 칸들의 평균 안전도
        min  가장 낮은 칸의 안전도
        bad  ZONE_BAD 미만인 칸의 수
        n    지나는 칸의 총 수
    """
    if tab is None or len(tab) == 0 or not pts:
        return None
    step = max(1, len(pts) // 400)
    thin = pts[::step]
    col, row = hex_of_vec([p[0] for p in thin], [p[1] for p in thin])
    key = pd.DataFrame({"col": col, "row": row}).drop_duplicates()
    s = key.merge(tab[["col", "row", "안전도"]], on=["col", "row"],
                  how="left")["안전도"]
    # 표에 없는 칸 = 시설도 제보도 없는 칸. 기본점수로 본다.
    s = s.fillna(SCORE["base"])
    if s.empty:
        return None
    return dict(avg=round(float(s.mean()), 1), min=int(s.min()),
                bad=int((s < ZONE_BAD).sum()), n=int(len(s)))


def zone_cost(z):
    """구역 안전도를 경로 비용으로 바꾼다. 낮을수록 좋은 길."""
    if not z:
        return 0.0
    # 평균이 ZONE_MID보다 낮으면 벌점, 높으면 보너스(음수)
    c = (ZONE_MID - z["avg"]) * ZONE_W
    # 평균이 괜찮아도 중간에 위험 칸이 끼면 따로 벌점을 준다
    return round(c + z["bad"] * 2.0, 2)


# ── 육각형 벌집 ────────────────────────────────────────
def hex_of(lat, lng, R=GRID):
    u, v = lat / R, lng / (R * KX)
    col = round(v / 1.5)
    row = round((u - (col % 2) * (SQ3 / 2)) / SQ3)
    return int(col), int(row)


def hex_of_vec(lat, lng, R=GRID):
    u = np.asarray(lat) / R
    v = np.asarray(lng) / (R * KX)
    col = np.round(v / 1.5)
    row = np.round((u - (col % 2) * (SQ3 / 2)) / SQ3)
    return col.astype(int), row.astype(int)


def hex_center_vec(col, row, R=GRID):
    col, row = np.asarray(col), np.asarray(row)
    return ((row * SQ3 + (col % 2) * (SQ3 / 2)) * R, col * 1.5 * R * KX)


def hex_center(col, row, R=GRID):
    return ((row * SQ3 + (col % 2) * (SQ3 / 2)) * R, col * 1.5 * R * KX)


def hex_ring(lat, lng, R=GRID):
    return [[lng + R * KX * cos(radians(60 * k)),
             lat + R * sin(radians(60 * k))] for k in range(7)]


def level(s):
    if s >= 70:
        return "매우 안전"
    if s >= 55:
        return "안전"
    if s >= 40:
        return "보통"
    if s >= 25:
        return "주의"
    return "위험"


def _cells(pts, kind):
    if not pts:
        return pd.DataFrame(columns=["col", "row", kind])
    a = np.asarray(pts)
    col, row = hex_of_vec(a[:, 0], a[:, 1])
    return (pd.DataFrame({"col": col, "row": row})
            .groupby(["col", "row"]).size().reset_index(name=kind))


def grid(infra, reports, expand=True):
    """칸마다 시설 수와 제보 영향을 모아 0~100 안전도를 낸다."""
    tab = None
    for sp in INFRA_SPECS:
        c = _cells(infra.get(sp["key"]) or [], sp["key"])
        tab = c if tab is None else tab.merge(c, on=["col", "row"], how="outer")

    if reports:
        col, row = hex_of_vec([d["lat"] for d in reports],
                              [d["lng"] for d in reports])
        r = pd.DataFrame({
            "col": col, "row": row,
            "cnt": [d["count"] for d in reports],
            "eff": [effect(d) for d in reports],
            "star": [stars_of(d) * d["count"] for d in reports],
            "name": [d["name"] for d in reports]})
        g = r.groupby(["col", "row"]).agg(
            제보=("cnt", "sum"), 위험=("eff", "sum"), 별점합=("star", "sum"),
            지점=("name", lambda s: " / ".join(s)[:110])).reset_index()
        g["평균별점"] = (g["별점합"] / g["제보"]).round(1)
        g = g.drop(columns=["별점합"])
        tab = g if tab is None else tab.merge(g, on=["col", "row"], how="outer")

    if tab is None or tab.empty:
        return pd.DataFrame()

    if expand:
        c_, r_ = tab.col.values, tab.row.values
        d = np.where(c_ % 2 == 1, 1, -1)
        nb = np.concatenate([
            np.stack([c_, r_ + 1], 1), np.stack([c_, r_ - 1], 1),
            np.stack([c_ + 1, r_], 1), np.stack([c_ + 1, r_ + d], 1),
            np.stack([c_ - 1, r_], 1), np.stack([c_ - 1, r_ + d], 1)])
        nb = pd.DataFrame(np.unique(nb, axis=0), columns=["col", "row"])
        tab = tab.merge(nb, on=["col", "row"], how="outer")

    for sp in INFRA_SPECS:
        if sp["key"] not in tab:
            tab[sp["key"]] = 0
    for c in ("제보", "위험", "평균별점"):
        if c not in tab:
            tab[c] = 0
    if "지점" not in tab:
        tab["지점"] = ""

    tab["지점"] = tab["지점"].fillna("")
    tab = tab.fillna(0)

    S = SCORE
    s = (S["base"]
         + np.minimum(tab["cctv"], S["cctv_n"]) * S["cctv_w"]
         + np.minimum(tab["bell"], S["bell_n"]) * S["bell_w"]
         + np.minimum(tab["store"], S["store_n"]) * S["store_w"]
         + np.minimum(tab["lamp"], S["lamp_n"]) * S["lamp_w"]
         - tab["위험"].clip(-S["risk_cap"], S["risk_cap"]) * S["risk_w"])
    tab["안전도"] = s.clip(0, 100).round().astype(int)
    tab["등급"] = pd.cut(tab["안전도"], [-1, 24, 39, 54, 69, 100],
                       labels=["위험", "주의", "보통", "안전", "매우 안전"]
                       ).astype(str)

    clat, clng = hex_center_vec(tab.col.values, tab.row.values)
    tab["clat"], tab["clng"] = clat, clng

    s0, n0, w0, e0 = BBOX
    return tab[tab.clat.between(s0, n0) & tab.clng.between(w0, e0)]


# ── 주소 검색 ──────────────────────────────────────────
_geocoder = Nominatim(user_agent="safe-returner", timeout=10)


def search_address(q):
    if not q or not q.strip():
        return None
    try:
        r = _geocoder.geocode(q if "대전" in q else f"대전 {q}",
                              country_codes="kr", exactly_one=True)
        return (r.latitude, r.longitude, r.address) if r else None
    except Exception:
        return None


# ── 경로 ───────────────────────────────────────────────
def ask(base, a, b, alt=True):
    url = f"{base}/{a[1]},{a[0]};{b[1]},{b[0]}"
    p = {"overview": "full", "geometries": "geojson"}
    if alt:
        p["alternatives"] = "true"
    try:
        r = requests.get(url, params=p, timeout=15,
                         headers={"User-Agent": "safe-returner/1.0"})
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:120]}"
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    j = r.json()
    if j.get("code") != "Ok":
        return False, str(j.get("code"))
    return True, j


def online(a, b, rows, infra=None, tab=None):
    log = []
    for name, base in SERVERS:
        for alt in (True, False):
            ok, res = ask(base, a, b, alt)
            if ok:
                out = []
                for rt in res["routes"]:
                    pts = [(la, ln) for ln, la in rt["geometry"]["coordinates"]]
                    dg, hit = danger(pts, rows, infra)
                    z = zone_of(pts, tab)
                    out.append(dict(pts=pts, dist=rt["distance"],
                                    dur=rt["duration"], dg=dg, hit=hit,
                                    zone=z, total=round(dg + zone_cost(z), 2)))
                return {"ok": True, "sc": out, "server": name}
            log.append((name, str(res)))
    return {"ok": False, "log": log}


def offline(a, b, rows, infra=None, n=34, tab=None):
    pad = 0.006
    la0, la1 = min(a[0], b[0]) - pad, max(a[0], b[0]) + pad
    ln0, ln1 = min(a[1], b[1]) - pad, max(a[1], b[1]) + pad
    lats = [la0 + (la1 - la0) * i / (n - 1) for i in range(n)]
    lngs = [ln0 + (ln1 - ln0) * j / (n - 1) for j in range(n)]
    sc = [(d, max(effect(d), 0)) for d in rows]      # 위험 제보만 피한다

    # 구역 안전도를 (col,row) → 점수 사전으로 만들어 둔다
    zmap = {}
    if tab is not None and len(tab):
        zmap = {(int(c), int(r)): int(s) for c, r, s
                in zip(tab["col"], tab["row"], tab["안전도"])}

    def zrisk(la, ln):
        """시설이 없어 점수가 낮은 칸일수록 지나가는 비용을 올린다."""
        if not zmap:
            return 0.0
        s = zmap.get(hex_of(la, ln), SCORE["base"])
        return max(0.0, (ZONE_MID - s) / ZONE_MID) * 3.0

    def risk(la, ln):
        r = sum(e * (1 - m / 250) for d, e in sc
                if e > 0 and (m := meters((d["lat"], d["lng"]), (la, ln))) < 250)
        return r + zrisk(la, ln)

    R = [[risk(lats[i], lngs[j]) for j in range(n)] for i in range(n)]

    G = nx.Graph()
    for i in range(n):
        for j in range(n):
            for di, dj in ((0, 1), (1, 0), (1, 1), (1, -1)):
                i2, j2 = i + di, j + dj
                if 0 <= i2 < n and 0 <= j2 < n:
                    m = meters((lats[i], lngs[j]), (lats[i2], lngs[j2]))
                    pen = (R[i][j] + R[i2][j2]) / 2
                    G.add_edge((i, j), (i2, j2), d=m, w=m * (1 + pen * .9))

    def near(pt):
        return (min(range(n), key=lambda i: abs(lats[i] - pt[0])),
                min(range(n), key=lambda j: abs(lngs[j] - pt[1])))

    def solve(key):
        path = nx.shortest_path(G, near(a), near(b), weight=key)
        pts = [(lats[i], lngs[j]) for i, j in path]
        dist = sum(meters(pts[k], pts[k + 1]) for k in range(len(pts) - 1))
        dg, hit = danger(pts, rows, infra)
        z = zone_of(pts, tab)
        return dict(pts=pts, dist=dist, dur=dist / 1.25, dg=dg, hit=hit,
                    zone=z, total=round(dg + zone_cost(z), 2))

    return [solve("d"), solve("w")]


def find(a, b, rows, engine="자동", infra=None, tab=None):
    if engine != "오프라인 계산":
        r = online(a, b, rows, infra, tab)
        if r["ok"]:
            return dict(sc=r["sc"], src=f"{r['server']} (실제 도로망)", err=None)
        if engine == "실제 도로망만":
            return dict(sc=None, src="", err=r["log"])
    return dict(sc=offline(a, b, rows, infra, tab=tab),
                src="오프라인 격자 계산 (실제 도로 아님)", err=None)

def get_reports_df(data):
    if not data:
        return pd.DataFrame()
    
    df = pd.DataFrame(data)
    if "tags" in df.columns:
        df["tags"] = df["tags"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
    return df


# ═══════ 3부. 지도 그리기 ══════════════════════════════════

COLORS = {"매우 안전": "#1a7f4b", "안전": "#5cb85c", "보통": "#f2c14e",
          "주의": "#f0883e", "위험": "#e5484d"}


def star_color(s):
    return ("#e5484d" if s <= 1.5 else "#f0883e" if s <= 2.5
            else "#f2c14e" if s <= 3.5 else "#5cb85c" if s <= 4.5 else "#1a7f4b")


def stars_html(s):
    full = int(round(s))
    return ("<span style='color:#f5b301;letter-spacing:1px'>"
            + "★" * full + "<span style='color:#dde'>" + "★" * (5 - full)
            + "</span></span>")


LEGEND = """
<div style="position:fixed;bottom:24px;left:14px;z-index:9999;
     background:rgba(255,255,255,.97);border:1px solid #dde3ee;border-radius:10px;
     padding:11px 14px;font:12px/1.9 -apple-system,sans-serif;color:#111;
     box-shadow:0 2px 8px rgba(0,0,0,.14)">
  <b style="font-size:12.5px">구역 안전도</b>
  <div style="display:flex;gap:2px;margin:7px 0 5px">
    <div style="width:32px;height:11px;background:#e5484d;border-radius:3px 0 0 3px"></div>
    <div style="width:32px;height:11px;background:#f0883e"></div>
    <div style="width:32px;height:11px;background:#f2c14e"></div>
    <div style="width:32px;height:11px;background:#5cb85c"></div>
    <div style="width:32px;height:11px;background:#1a7f4b;border-radius:0 3px 3px 0"></div>
  </div>
  <div style="display:flex;justify-content:space-between;color:#667;font-size:11px">
    <span>위험</span><span>안전</span></div>
  <div style="color:#888;font-size:11px;margin-top:5px;max-width:165px">
    CCTV·비상벨·편의점 + 주민 별점 종합</div>
</div>
"""


class HexBehavior(MacroElement):
    """칸을 누르면 그 한가운데로 이동. 확대하면 벌집이 옅어진다."""

    _template = Template("""
    {% macro script(this, kwargs) %}
      (function () {
        var map = {{ this._parent.get_name() }};
        var gj  = {{ this.layer.get_name() }};
        gj.eachLayer(function (l) {
          l.on('click', function () {
            var c = l.getBounds().getCenter();
            var z = Math.max(map.getZoom() + 1, {{ this.zoom }} + 1);
            map.flyTo(c, Math.min(z, 18), {duration: 0.6});
          });
        });
        function fade() {
          var far = map.getZoom() >= {{ this.zoom }};
          gj.setStyle({fillOpacity: far ? 0.18 : 0.55,
                       weight: far ? 0.5 : 1,
                       opacity: far ? 0.35 : 0.9});
        }
        map.on('zoomend', fade);
        fade();
      })();
    {% endmacro %}
    """)

    def __init__(self, layer, zoom=HEX_ZOOM):
        super().__init__()
        self._name = "HexBehavior"
        self.layer = layer
        self.zoom = zoom


def blank(center, zoom, tile, locate=True):
    t = TILES.get(tile, TILES["OpenStreetMap"])
    m = folium.Map(center, zoom_start=zoom, tiles=t["tiles"], attr=t["attr"],
                   max_zoom=t["max_zoom"], control_scale=True, prefer_canvas=True)
    Fullscreen(title="전체화면", title_cancel="닫기").add_to(m)
    MiniMap(toggle_display=True, minimized=True).add_to(m)
    if locate:
        LocateControl(auto_start=False, flyTo=True,
                      strings={"title": "현재 위치로 이동"}).add_to(m)
    return m


def _card(r, labels):
    """구역 정보 카드."""
    col = COLORS[r.등급]
    bar = (f'<div style="height:7px;background:#eceff4;border-radius:4px;'
           f'overflow:hidden;margin:6px 0 9px">'
           f'<div style="width:{r.안전도}%;height:100%;background:{col}"></div></div>')
    rows = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:3px 0;'
        f'border-bottom:1px solid #f0f2f6"><span style="color:#667">{lab}</span>'
        f'<b>{int(getattr(r, k))}</b></div>'
        for k, lab in labels.items())

    if r.제보:
        rep = (f'<div style="display:flex;justify-content:space-between;'
               f'align-items:center;padding:3px 0;border-bottom:1px solid #f0f2f6">'
               f'<span style="color:#667">주민 별점</span>'
               f'<span>{stars_html(r.평균별점)} '
               f'<b style="color:{star_color(r.평균별점)}">{r.평균별점:g}</b>'
               f'<span style="color:#889;font-size:11px"> ({int(r.제보)}건)</span>'
               f'</span></div>')
    else:
        rep = (f'<div style="display:flex;justify-content:space-between;padding:3px 0;'
               f'border-bottom:1px solid #f0f2f6"><span style="color:#667">주민 별점'
               f'</span><span style="color:#aab">없음</span></div>')

    spot = (f'<div style="margin-top:8px;padding:7px 9px;background:#f7f9fc;'
            f'border-radius:6px;font-size:11.5px;color:#445;line-height:1.5">'
            f'{r.지점}</div>') if r.지점 else ""

    return (f'<div style="font:13px/1.6 -apple-system,sans-serif;min-width:210px">'
            f'<div style="display:flex;align-items:baseline;gap:7px">'
            f'<span style="font-size:17px;font-weight:800;color:{col}">{r.등급}</span>'
            f'<span style="color:#889;font-size:12px">{int(r.안전도)}점</span></div>'
            f'{bar}{rep}{rows}{spot}</div>')


def build_hex(tab):
    """벌집 GeoJSON을 만든다. 무거운 작업이라 app.py 에서 캐시한다."""
    if tab is None or tab.empty:
        return None
    labels = {sp["key"]: sp["label"] for sp in INFRA_SPECS}
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "properties": {"등급": r.등급, "html": _card(r, labels),
                       "tip": f"{r.등급} · {int(r.안전도)}점"},
        "geometry": {"type": "Polygon",
                     "coordinates": [hex_ring(r.clat, r.clng)]},
    } for r in tab.itertuples()]}


def hexes(m, geo):
    if not geo:
        return m
    gj = folium.GeoJson(
        geo, name="구역 안전도",
        style_function=lambda f: {
            "fillColor": COLORS[f["properties"]["등급"]],
            "color": "#ffffff", "weight": 1, "fillOpacity": .55},
        highlight_function=lambda f: {"weight": 2.5, "color": "#1b2a4a"},
        tooltip=folium.GeoJsonTooltip(fields=["tip"], aliases=[""], sticky=True),
        popup=folium.GeoJsonPopup(fields=["html"], aliases=[""],
                                  max_width=280, labels=False),
    )
    gj.add_to(m)
    m.add_child(HexBehavior(gj))
    m.get_root().html.add_child(folium.Element(LEGEND))
    return m


def _photo(d, w=220):
    f = PHOTOS / d["photo"] if d.get("photo") else None
    if not f or not f.exists() or f.stat().st_size > 3_000_000:
        return ""
    b64 = base64.b64encode(f.read_bytes()).decode()
    return (f'<img src="data:image/jpeg;base64,{b64}" '
            f'style="width:{w}px;border-radius:6px;margin-top:7px">')


def reports_layer(m, rows, infra=None):
    """개별 제보 지점. 별점에 따라 색이 달라진다."""
    g = folium.FeatureGroup(name="제보 지점", show=True)
    for d in rows:
        s = stars_of(d)
        col = star_color(s)
        tags = tags_of(d)
        tag_html = (f'<div style="padding:6px 8px;background:#f7f9fc;'
                    f'border-radius:6px;font-size:11px;color:#667;margin-top:6px">'
                    f'{" · ".join(tags)}</div>') if tags else ""
        folium.CircleMarker(
            (d["lat"], d["lng"]), radius=5.5, color="#fff", weight=2,
            fill=True, fill_color=col, fill_opacity=1,
            tooltip=f"{d['name']} · {s:g}점 · {d['count']}건",
            popup=folium.Popup(
                f'<div style="font:13px/1.6 -apple-system,sans-serif;min-width:195px">'
                f'<b style="font-size:15px">{d["name"]}</b><br>'
                f'{stars_html(s)} <b style="color:{col}">{s:g}점</b> '
                f'<span style="color:#889">{STAR_LABEL.get(round(s), "보통")}</span>'
                f'<span style="color:#889;font-size:11.5px"> · '
                f'{d["count"]}건 · {d["time"]}</span>'
                f'<div style="margin:6px 0;color:#445">{d["memo"]}</div>'
                f'{tag_html}{_photo(d)}</div>', max_width=270),
        ).add_to(g)
    g.add_to(m)
    return m


def pin(m, pt, tip, color="blue", icon="info-sign"):
    folium.Marker(pt, tooltip=tip,
                  icon=folium.Icon(color=color, icon=icon)).add_to(m)
    return m


def here(m, pt):
    folium.CircleMarker(pt, radius=9, color="#1b6ef3", fill=True,
                        fill_color="#1b6ef3", fill_opacity=.9, weight=3,
                        tooltip="현재 위치").add_to(m)
    folium.Circle(pt, radius=60, color="#1b6ef3", fill=True,
                  fill_opacity=.12, weight=1).add_to(m)
    return m


def routes(m, fast, safe, p1, p2, s_name, e_name):
    folium.PolyLine(fast["pts"], color="#e5484d", weight=5, dash_array="9,9",
                    opacity=.9, tooltip="최단 경로").add_to(m)
    if safe is not fast:
        AntPath(safe["pts"], color="#1a7f4b", weight=6, delay=800,
                tooltip="안전 경로").add_to(m)
    pin(m, p1, f"출발 · {s_name}", "blue", "play")
    pin(m, p2, f"도착 · {e_name}", "green", "flag")
    lats = [p[0] for p in fast["pts"]]
    lngs = [p[1] for p in fast["pts"]]
    m.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]])
    return m


def finish(m):
    folium.LayerControl(collapsed=True).add_to(m)
    return m


# ═══════ 4부. 화면 ════════════════════════════════════════

st.set_page_config("SafOn", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

if "data" not in st.session_state:
    st.session_state.data, st.session_state.rebut = load()
for k, v in [("route", None), ("me", None), ("found", None), ("qn", 0),
             ("view", None), ("fn", 0)]:
    st.session_state.setdefault(k, v)

S = st.session_state
FACES = {i: "★" * i + "☆" * (5 - i) for i in range(1, 6)}


@st.cache_data(show_spinner=False)
def get_infra(): return load_infra()


@st.cache_data(show_spinner=False)
def geocode(q): return search_address(q)


@st.cache_data(show_spinner="구역 안전도 계산 중")
def hex_tab(sig): return grid(INFRA, S.data)


@st.cache_data(show_spinner="구역 안전도 계산 중")
def hex_geo(sig): return build_hex(hex_tab(sig))


INFRA = get_infra()
data = S.data


def sig():
    return (len(data), sum(d["count"] for d in data),
            round(sum(stars_of(d) for d in data), 1))


def store():
    save(data, S.rebut)
    hex_geo.clear()
    hex_tab.clear()


def draw(m, key, h, click=True):
    kw = dict(height=h, key=key,
              returned_objects=["last_clicked", "last_object_clicked"] if click else [])
    try: return st_folium(m, use_container_width=True, **kw)
    except TypeError: return st_folium(m, width=1500, **kw)


def clicked(out):
    c = (out or {}).get("last_clicked") or (out or {}).get("last_object_clicked")
    return [round(c["lat"], 6), round(c["lng"], 6)] if c else None


def place_card(lat, lng):
    near = around((lat, lng), INFRA)
    chips = " · ".join(f"{sp['label']} {near[sp['key']]}"
                       for sp in INFRA_SPECS if INFRA.get(sp["key"]))
    st.markdown(f'<div class="card" style="margin:0 0 10px">'
                f'<b style="color:#1b2a4a">📍 {lat:.5f}, {lng:.5f}</b>'
                f'<div style="font-size:12px;color:#667;margin-top:3px">'
                f'반경 {INFRA_R}m — {chips or "공공데이터 없음"}</div></div>',
                unsafe_allow_html=True)


def star_input(key, default=3):
    if hasattr(st, "feedback"):
        i = st.feedback("stars", key=key)
        return (i + 1) if i is not None else default
    return st.radio("별점", [1, 2, 3, 4, 5], index=default - 1, key=key,
                    horizontal=True, label_visibility="collapsed",
                    format_func=lambda i: FACES[i])


# ── 상단 ───────────────────────────────────────────────
st.title("SafOn")
st.caption("안심귀가 안내 · 대전광역시 야간 보행 안전 지도")

if S.get("flash"):
    st.toast(S.pop("flash"), icon="✅")

tot = sum(d["count"] for d in data)
avg = sum(stars_of(d) * d["count"] for d in data) / max(tot, 1)

top = st.columns([1, 1, 1, 2.6, 1.3, .7])
for col, (lab, val) in zip(top, [("총 제보", tot), ("제보 지점", len(data)),
                                 ("평균 별점", f"{avg:.1f}" if data else "—")]):
    col.metric(lab, val)

with top[3]:
    q = st.text_input("주소·장소 검색", key=f"q{S.qn}", placeholder="예: 자양동 205-3, 한남대 후문")
    if q and q != S.get("last_q"):
        S.last_q = q
        with st.spinner("검색 중"):
            S.found = geocode(q)
        if S.found: S.view = (S.found[0], S.found[1], 16)

tile = top[4].selectbox("배경지도", list(TILES))

with top[5]:
    st.caption("내 위치")
    if GEO_OK and (loc := streamlit_geolocation()) and loc.get("latitude"):
        new = [loc["latitude"], loc["longitude"]]
        if new != S.me:
            S.me, S.view = new, (new[0], new[1], 17)
            st.rerun()

if S.found:
    a, b = st.columns([6, 1])
    a.success(f"🔎 {S.found[2][:70]}")
    if b.button("검색 해제", use_container_width=True):
        S.found = S.last_q = None
        S.qn += 1
        st.rerun()

# ── 지도 만들기 ────────────────────────────────────────
GEO = hex_geo(sig())
CTR, ZM = (((S.view[0], S.view[1]), S.view[2]) if S.view else
           ((S.me, 17) if S.me else (CENTER, 12)))


def make_map():
    m = blank(CTR, ZM, tile)
    hexes(m, GEO)
    reports_layer(m, data, INFRA)
    if S.me: here(m, S.me)
    if S.found: pin(m, (S.found[0], S.found[1]), "검색 위치", "purple", "search")
    finish(m)
    return m


t1, t2, t3, t4 = st.tabs(["안전도 지도", "제보하기", "안전 길찾기", "목록 · 관리"])

# ══ 1. 안전도 지도 (보기 전용) ═════════════════════════
with t1:
    look = clicked(draw(make_map(), "look", 620))
    if not look:
        st.caption("칸을 누르면 그 구역의 안전도와 근거가 나옵니다. 제보는 **제보하기** 탭에서 합니다.")
    else:
        place_card(*look)
        near = [d for d in data if meters((d["lat"], d["lng"]), look) < 250]
        if near:
            st.caption(f"250m 안 제보 {len(near)}곳")
            for col, d in zip(st.columns(min(len(near), 4)), near[:4]):
                s = stars_of(d)
                col.markdown(
                    f'<div class="card"><b>{d["name"][:16]}</b>'
                    f'<div style="margin:3px 0">{stars_html(s)} '
                    f'<b style="color:{star_color(s)}">{s:g}</b></div>'
                    f'<div style="font-size:11.5px;color:#667">{d["memo"][:40]}</div>'
                    f'</div>', unsafe_allow_html=True)
        else:
            st.caption("250m 안에 등록된 제보가 없습니다.")

# ══ 2. 제보하기 ════════════════════════════════════════
with t2:
    st.caption("지도에서 제보할 자리를 클릭하면 바로 아래에 제보창이 열립니다.")
    spot = clicked(draw(make_map(), "rep", 540))

    if not spot:
        st.info("아직 자리를 고르지 않았습니다. 지도를 클릭하세요.")
    else:
        lat, lng = spot
        st.markdown('<div class="side-panel">', unsafe_allow_html=True)
        place_card(lat, lng)

        with st.form(f"report{S.fn}", clear_on_submit=True):
            c1, c2 = st.columns([1.4, 1])
            name = c1.text_input("지점 이름", placeholder="예: 자양동 원룸촌 골목")
            tm = c2.selectbox("몇 시쯤", TIMES, index=TIME_DEFAULT)

            st.write("**이 자리는 어땠나요** ·  1:매우위험~ 5점 매우안전")
            stars = star_input(f"star{S.fn}")

            d1, d2 = st.columns([2, 1])
            tags = d1.text_input("사유 — 단어로 (쉼표로 여러 개)", placeholder=", ".join(TAG_HINTS[:4]))
            photo = d2.file_uploader("사진 (선택)", type=["jpg", "jpeg", "png"])
            memo = st.text_area("긴 사유 — 자세한 설명", height=90, placeholder="예: 가로등이 나가서 3미터 앞도 안 보였다")

            if st.form_submit_button("등록", type="primary"):
                S.flash = add(data, lat, lng, name, stars, [t.strip() for t in tags.split(",") if t.strip()], tm, memo, photo)
                store()
                S.fn += 1
                S.force_tab = 1
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    if not any(INFRA.get(sp["key"]) for sp in INFRA_SPECS):
        st.caption(f"안전시설을 반영하려면 {DATA.name}/ 폴더에 cctv.csv, bell.csv, store.csv 를 넣으세요.")

# ══ 3. 안전 길찾기 ═════════════════════════════════════
with t3:
    help_msg = "우측 상단의 '내 위치' 아이콘을 눌러 위치 권한을 허용해야 활성화됩니다." if not S.me else "현재 위치를 출발지로 설정합니다."
    use_me = st.checkbox("현재 위치에서 출발", disabled=not S.me, help=help_msg)
    
    a, b, c = st.columns([2, 2, 1])

    if use_me and S.me:
        a.markdown("**출발**")
        a.success(f"현재 위치 ({S.me[0]:.4f}, {S.me[1]:.4f})")
        start, s_nm = list(S.me), "현재 위치"
    else:
        fq = a.text_input("출발 주소", placeholder="예: 대전역, 자양동 205-3")
        start, s_nm = None, fq
        if fq and (r := geocode(fq)):
            start = [r[0], r[1]]
            a.caption(f"✅ {r[2][:40]}")
        elif fq:
            a.caption("❌ 찾지 못했습니다")

    tq = b.text_input("도착 주소", placeholder="예: 한남대학교, 은행동")
    end, e_nm = None, tq
    if tq and (r := geocode(tq)):
        end = [r[0], r[1]]
        b.caption(f"✅ {r[2][:40]}")
    elif tq:
        b.caption("❌ 찾지 못했습니다")

    c.markdown("<div style='height:1.85rem'></div>", unsafe_allow_html=True)
    if c.button("경로 찾기", type="primary", use_container_width=True):
        if not (start and end):
            st.error("출발지와 도착지를 모두 찾아야 합니다.")
        else:
            with st.spinner("보행자 도로망에서 경로 계산 중"):
                r = find(start, end, data, "자동", INFRA, hex_tab(sig()))
            S.route = dict(r, s=s_nm, e=e_nm, sp=list(start), ep=list(end))

    if S.route is None:
        st.info("출발·도착 주소를 넣고 '경로 찾기'를 누르세요.")
    elif S.route["err"]:
        st.error("경로를 찾지 못했습니다. 잠시 후 다시 시도해주세요.")
    else:
        sc = S.route["sc"]
        fast = min(sc, key=lambda x: x["dist"])
        # 안전 경로는 제보 위험 + 구역 안전도를 합친 점수로 고른다
        safe = min(sc, key=lambda x: (x.get("total", x["dg"]), x["dist"]))

        def zone_line(r):
            z = r.get("zone")
            if not z:
                return ""
            return (f"\n\n구역 평균 안전도 {z['avg']} · "
                    f"최저 {z['min']} · 위험 구간 {z['bad']}칸")

        m3 = blank(CENTER, 14, tile, locate=False)
        routes(m3, fast, safe, S.route["sp"], S.route["ep"],
                  S.route["s"], S.route["e"])
        draw(m3, "nav", 540, click=False)

        x, y = st.columns(2)
        x.error(f"**최단 경로**\n\n{fast['dist']/1000:.2f}km · "
                f"도보 {fast['dur']/60:.0f}분\n\n"
                f"위험 지점 {len(fast['hit'])}곳" + zone_line(fast))
        for n, s in fast["hit"]:
            x.caption(f"· {n} ({s})")
        x.caption("지도 앱이 기본으로 주는 경로입니다. 안전은 계산에 없습니다.")

        better = safe is not fast and \
            safe.get("total", safe["dg"]) < fast.get("total", fast["dg"])
        if not better:
            y.warning("더 안전한 우회 경로가 없습니다.\n\n"
                      "우회로 자체가 없는 구간이라는 뜻입니다.")
        else:
            y.success(f"**안전 경로**\n\n{safe['dist']/1000:.2f}km · "
                      f"도보 {safe['dur']/60:.0f}분\n\n"
                      f"위험 지점 {len(safe['hit'])}곳" + zone_line(safe))
            for n, s in safe["hit"]:
                y.caption(f"· {n} ({s})")
            gain = ""
            zf, zs = fast.get("zone"), safe.get("zone")
            if zf and zs:
                gain = (f"\n\n구역 안전도 {zf['avg']} → {zs['avg']} · "
                        f"위험 구간 {zf['bad']}칸 → {zs['bad']}칸")
            y.info(f"차이: +{safe['dist']-fast['dist']:.0f}m · "
                   f"+{(safe['dur']-fast['dur'])/60:.0f}분" + gain)

        st.caption(
            f"{S.route['src']} · 제보 {len(data)}곳 기준, "
            f"경로에서 {RADIUS}m 안의 제보를 통과로 판정. "
            "여기에 경로가 지나는 구역의 안전도(CCTV·안전비상벨·편의점 반영)를 "
            "합쳐 안전 경로를 고릅니다.")

# ══ 4. 목록 · 관리 ═════════════════════════════════════
with t4:
    a, b = st.columns(2)
    a.download_button("백업 내려받기", json.dumps({"data": data, "rebut": S.rebut}, ensure_ascii=False, indent=2), file_name="reports.json", use_container_width=True)
    if b.button("전체 삭제", use_container_width=True):
        S.data, S.rebut, S.route = [], [], None
        store()
        S.force_tab = 3
        st.rerun()

    counts = " · ".join(f"{sp['label']} {len(INFRA.get(sp['key'], [])):,}개" for sp in INFRA_SPECS if INFRA.get(sp["key"]))
    st.caption(f"제보는 {STORE.name} 에 자동 저장됩니다." + (f" · 공공데이터: {counts}" if counts else ""))

    if not data:
        st.info("등록된 제보가 없습니다. '제보하기' 탭에서 추가하세요.")
    else:
        st.dataframe(get_reports_df(data), hide_index=True)

        st.subheader("제보 수정")
        for d in sorted(data, key=lambda x: -effect(x)):
            e, lv, why = assess(d)
            s0 = int(round(stars_of(d)))
            with st.expander(f"{d['name']} · {FACES[s0]} · {d['count']}건 · {lv}"):
                if d.get("photo") and (PHOTOS / d["photo"]).exists():
                    st.image(str(PHOTOS / d["photo"]), width=300)

                with st.form(f"edit{d['id']}"):
                    c1, c2 = st.columns([2, 1])
                    nm = c1.text_input("이름", d["name"])
                    ct = c2.number_input("제보 수", 1, 99, d["count"])
                    st.write("별점")
                    sv = star_input(f"es{d['id']}", s0)

                    c3, c4 = st.columns(2)
                    tg = c3.text_input("사유 (쉼표로 여러 개)", ", ".join(tags_of(d)))
                    tv = c4.selectbox("시간대", TIMES, index=TIMES.index(d["time"]) if d["time"] in TIMES else TIME_DEFAULT)
                    mm = st.text_area("긴 사유", d["memo"], height=80)

                    if st.form_submit_button("수정 저장", type="primary"):
                        d.update(name=nm, count=int(ct), memo=mm, stars=float(sv), time=tv, tags=[t.strip() for t in tg.split(",") if t.strip()])
                        store()
                        S.flash = f"'{nm}' 수정 완료!"
                        S.force_tab = 3
                        st.rerun()

                g1, g2 = st.columns(2)
                if g1.button("삭제", key=f"x{d['id']}", use_container_width=True):
                    S.data = [q for q in data if q["id"] != d["id"]]
                    store()
                    S.flash = "삭제되었습니다."
                    S.force_tab = 3
                    st.rerun()

                st.divider()
                st.markdown(f"**자동 판정: {lv}** (영향 {e})")
                st.caption(f"근거: {why}")
                st.caption("별점·시간대 가중치·제보 수를 공개된 계산식에 넣어 "
                           "판정합니다. 학습 모델이 아니라 규칙 기반이며, "
                           "위 근거가 계산의 전부입니다.")
                txt = st.text_input("이 판정이 틀렸다면?", key=f"t{d['id']}")
                if st.button("판정이 옳지 않습니다", key=f"b{d['id']}") and txt.strip():
                    S.rebut.append(dict(id=d["id"], text=txt.strip(), at=f"{datetime.now():%Y-%m-%d}"))
                    store()
                    S.force_tab = 3
                    st.rerun()
                for x in [x for x in S.rebut if x["id"] == d["id"]]:
                    st.warning(f"주민 반박 · {x['at']}\n\n{x['text']}")

if S.get("force_tab") is not None:
    tab_idx = S.pop("force_tab")
    components.html(f"""
        <script>
        const tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
        if (tabs.length > {tab_idx}) {{
            tabs[{tab_idx}].click();
        }}
        </script>
    """, height=0)

"""
Safe Returner — 안심귀가 안내
대전광역시 야간 보행 안전 지도 (화면)

실행:
    pip3 install streamlit pandas folium streamlit-folium requests geopy networkx
    streamlit run app.py

파일 구성
    config.py   설정값 (동네 목록, 가중치, 지도 타일, CSS)
    core.py     계산과 저장 (위험도 판정, 경로탐색, JSON 저장)
    mapview.py  지도 그리기
    app.py      화면 ← 지금 파일

주의: st_folium이 화면을 다시 그리면 st.button은 False로 돌아간다.
결과는 session_state에 담고, 그리기는 if 블록 바깥에서 한다.
"""

import json
from datetime import datetime

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import core
import mapview as mv
from config import (CSS, PLACES, TILES, GU, CENTER, FACTORS, TIMES,
                    W_TIME, RADIUS, STORE, PHOTOS)

st.set_page_config("Safe Returner", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

if "data" not in st.session_state:
    st.session_state.data, st.session_state.rebut = core.load()
for k, v in [("pick", None), ("route", None)]:
    st.session_state.setdefault(k, v)


def store():
    core.save(st.session_state.data, st.session_state.rebut)


def draw_map(m, key, height=660):
    try:
        return st_folium(m, height=height, use_container_width=True, key=key)
    except TypeError:                       # 구버전 streamlit-folium
        return st_folium(m, height=height, width=1600, key=key)


def spacer(col, h="1.85rem"):
    """selectbox 라벨 높이만큼 띄워 버튼 높이를 맞춘다."""
    col.markdown(f"<div style='height:{h}'></div>", unsafe_allow_html=True)


# ── 제보 입력 ──────────────────────────────────────────
def clear():
    for k in [f"chk_{f}" for f in FACTORS] + ["f_name", "f_other", "f_memo"]:
        st.session_state.pop(k, None)


def form(lat, lng):
    st.caption(f"선택한 위치: {lat:.5f}, {lng:.5f}")
    name = st.text_input("지점 이름", key="f_name", placeholder="예: 자양동 원룸촌 골목")

    st.write("**왜 위험했나요** (해당하는 것 모두)")
    cols = st.columns(4)
    picked = [f for i, f in enumerate(FACTORS)
              if cols[i % 4].checkbox(f, key=f"chk_{f}")]

    extra = []
    if "기타" in picked:
        other = st.text_input("기타 — 직접 입력 (쉼표로 여러 개)", key="f_other",
                              placeholder="예: 공사 가림막, 개가 튀어나옴")
        extra = [x.strip() for x in other.split(",") if x.strip()]

    tm = st.selectbox("시간대", TIMES, index=1, key="f_time")
    memo = st.text_area("한 줄 설명", key="f_memo",
                        placeholder="예: 가로등이 나가서 3미터 앞도 안 보였다")
    photo = st.file_uploader("사진 (선택)", type=["jpg", "jpeg", "png"])

    a, b = st.columns(2)
    if a.button("등록", type="primary", use_container_width=True):
        factors = [f for f in picked if f != "기타"] + extra
        if not factors:
            st.error("위험 요인을 하나 이상 고르거나 직접 입력하세요.")
        else:
            st.session_state.flash = core.add(st.session_state.data, lat, lng,
                                              name, factors, tm, memo, photo)
            store()
            st.session_state.pick = None
            clear()
            st.rerun()
    if b.button("취소", use_container_width=True):
        st.session_state.pick = None
        clear()
        st.rerun()


_dlg = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
dialog = _dlg("📍 이 지점 제보하기")(form) if _dlg else None


# ── 상단 ───────────────────────────────────────────────
st.title("Safe Returner")
st.caption("안심귀가 안내 · 대전광역시 야간 보행 안전 지도 — "
           "지도에서 지점을 클릭한 뒤 제보 버튼을 누르세요")

if st.session_state.get("flash"):
    st.success(st.session_state.pop("flash"))

data = st.session_state.data
top = st.columns([1, 1, 1, 1.2, 1.2, 1.5])
for col, (label, val) in zip(top, [
        ("총 제보", sum(d["count"] for d in data)),
        ("위험 지점", len(data)),
        ("상습 구간", sum(d["count"] >= 5 for d in data))]):
    col.metric(label, val)

gu = top[3].selectbox("자치구", GU)
# '대전 전체'는 자치구가 '전체'일 때만 고를 수 있게 한다
if gu == "전체":
    opts = ["대전 전체"] + list(PLACES)
else:
    opts = [p for p in PLACES if p.startswith(gu)]
where = top[4].selectbox("지도 이동", opts)
tile = top[5].selectbox("배경지도", list(TILES))

t1, t2, t3 = st.tabs(["제보 지도", "안전 길찾기", "목록 · 관리"])

# ══ 제보 지도 ══════════════════════════════════════════
with t1:
    ctr, zm = (CENTER, 12) if where == "대전 전체" else (PLACES[where], 16)
    m = mv.points(mv.blank(ctr, zm, tile), data, cluster=(where == "대전 전체"))
    if st.session_state.pick:
        mv.pin(m, st.session_state.pick, "선택한 위치", "blue", "plus")

    out = draw_map(m, "map")

    # 지도는 마지막 클릭을 계속 돌려주므로 처리한 클릭을 따로 기억한다
    if out and out.get("last_clicked"):
        sig = (round(out["last_clicked"]["lat"], 7),
               round(out["last_clicked"]["lng"], 7))
        if sig != st.session_state.get("last_click"):
            st.session_state.last_click = sig
            st.session_state.pick = list(sig)
            st.session_state.open_form = False
            st.rerun()

    if st.session_state.pick:
        lat, lng = st.session_state.pick
        a, b = st.columns([3, 1])
        a.success(f"📍 선택한 위치: {lat:.5f}, {lng:.5f}")
        if b.button("이 위치에 제보하기", type="primary", use_container_width=True):
            st.session_state.open_form = True
            if dialog:
                st.rerun()
        if st.session_state.get("open_form"):
            if dialog:
                dialog(lat, lng)
            else:
                st.divider()
                st.subheader("📍 이 지점 제보하기")
                form(lat, lng)
    else:
        st.info("👆 지도에서 위험했던 지점을 클릭하세요. 확대해서 정확한 골목을 찍으면 좋습니다.")

# ══ 안전 길찾기 ════════════════════════════════════════
with t2:
    a, b, c, d = st.columns([1.2, 1.2, 1.3, .9])
    s_nm = a.selectbox("출발", list(PLACES))
    e_nm = b.selectbox("도착", list(PLACES), index=1)
    engine = c.selectbox("계산 방식", ["자동", "실제 도로망만", "오프라인 계산"])
    spacer(d)
    go = d.button("경로 찾기", type="primary", use_container_width=True)

    if go:
        with st.spinner("경로 계산 중"):
            r = core.find(PLACES[s_nm], PLACES[e_nm], data, engine)
        st.session_state.route = dict(r, s=s_nm, e=e_nm)

    saved = st.session_state.route
    if saved is None:
        st.info("출발·도착을 고르고 '경로 찾기'를 누르세요.")
    elif saved["err"]:
        st.error("경로를 찾지 못했습니다. '계산 방식'을 오프라인 계산으로 바꿔보세요.")
        for tag, msg in saved["err"]:
            st.caption(f"· {tag} → {msg}")
    else:
        sc = saved["sc"]
        fast = min(sc, key=lambda x: x["dist"])
        safe = min(sc, key=lambda x: (x["dg"], x["dist"]))
        p1, p2 = PLACES[saved["s"]], PLACES[saved["e"]]

        m2 = mv.routes(mv.points(mv.blank(CENTER, 14, tile), data),
                       fast, safe, p1, p2, saved["s"], saved["e"])
        draw_map(m2, "nav", 620)

        x, y = st.columns(2)
        x.error(f"**최단 경로**\n\n{fast['dist']/1000:.2f}km · "
                f"{fast['dur']/60:.0f}분\n\n위험 지점 {len(fast['hit'])}곳 "
                f"(위험도 합 {fast['dg']:.1f})")
        for n, s in fast["hit"]:
            x.caption(f"· {n} ({s})")
        x.caption("지도 앱이 기본으로 주는 경로입니다. 안전은 계산에 없습니다.")

        if safe is fast or safe["dg"] >= fast["dg"]:
            y.warning("위험을 피하는 더 나은 경로가 없습니다.\n\n"
                      "우회로 자체가 없는 구간이라는 뜻이며 개선 우선순위가 가장 높습니다.")
        else:
            y.success(f"**안전 경로**\n\n{safe['dist']/1000:.2f}km · "
                      f"{safe['dur']/60:.0f}분\n\n위험 지점 {len(safe['hit'])}곳 "
                      f"(위험도 합 {safe['dg']:.1f})")
            for n, s in safe["hit"]:
                y.caption(f"· {n} ({s})")
            y.info(f"차이: +{safe['dist']-fast['dist']:.0f}m · "
                   f"+{(safe['dur']-fast['dur'])/60:.0f}분")

        st.caption(f"계산 방식: {saved['src']} · 주민 제보 {len(data)}곳 기준, "
                   f"경로에서 {RADIUS}m 안의 제보를 통과로 판정")

# ══ 목록 · 관리 ════════════════════════════════════════
with t3:
    a, b = st.columns(2)
    a.download_button("백업 내려받기",
                      json.dumps({"data": data, "rebut": st.session_state.rebut},
                                 ensure_ascii=False, indent=2),
                      file_name="reports.json", use_container_width=True)
    if b.button("전체 삭제", use_container_width=True):
        st.session_state.data, st.session_state.rebut = [], []
        st.session_state.route = None
        store()
        st.rerun()

    st.caption(f"제보는 {STORE.name} 에 자동 저장됩니다. 앱을 껐다 켜도 남습니다.")

    if not data:
        st.info("등록된 제보가 없습니다.")
    else:
        st.dataframe(pd.DataFrame([
            dict(이름=d["name"], 제보수=d["count"], 시간대=d["time"],
                 위험도=core.assess(d)[0], 판정=core.assess(d)[1],
                 위험요인=", ".join(d["factors"]), 설명=d["memo"],
                 등록=d.get("at", ""))
            for d in data]).sort_values("위험도", ascending=False), hide_index=True)

        st.subheader("제보 수정 · AI 판정 검토")
        for d in sorted(data, key=lambda x: -x["count"]):
            s, lv, why = core.assess(d)
            with st.expander(f"{d['name']} · 제보 {d['count']}건 · {lv} (점수 {s})"):
                if d.get("photo") and (PHOTOS / d["photo"]).exists():
                    st.image(str(PHOTOS / d["photo"]), width=320)

                e1, e2 = st.columns([2, 1])
                nm = e1.text_input("이름", d["name"], key=f"n{d['id']}")
                ct = e2.number_input("제보 수", 1, 99, d["count"], key=f"c{d['id']}")
                mm = st.text_area("설명", d["memo"], key=f"m{d['id']}")

                g1, g2 = st.columns(2)
                if g1.button("수정 저장", key=f"s{d['id']}", use_container_width=True):
                    d.update(name=nm, count=int(ct), memo=mm)
                    store()
                    st.rerun()
                if g2.button("🗑 삭제", key=f"x{d['id']}", use_container_width=True):
                    st.session_state.data = [q for q in data if q["id"] != d["id"]]
                    store()
                    st.rerun()

                st.divider()
                st.markdown(f"**AI 판정: {lv}** (점수 {s})")
                st.caption(f"근거: {why} · 시간대 가중치 ×{W_TIME[d['time']]}")
                txt = st.text_input("이 판정이 틀렸다면?", key=f"t{d['id']}")
                if st.button("아닌데요", key=f"b{d['id']}") and txt.strip():
                    st.session_state.rebut.append(
                        dict(id=d["id"], text=txt.strip(),
                             at=f"{datetime.now():%Y-%m-%d}"))
                    store()
                    st.rerun()
                for x in [x for x in st.session_state.rebut if x["id"] == d["id"]]:
                    st.warning(f"주민 반박 · {x['at']}\n\n{x['text']}")

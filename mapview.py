"""지도 그리기 — folium 관련 코드만 모았다."""

import base64

import folium
from folium.plugins import HeatMap, AntPath, Fullscreen, MiniMap, MarkerCluster
from branca.colormap import LinearColormap

from config import TILES, PHOTOS
from core import assess

CMAP = LinearColormap(["#22a06b", "#f2a93c", "#e03131"], vmin=0, vmax=20,
                      caption="위험도 (AI 판정 점수)")


def blank(center, zoom, tile):
    t = TILES.get(tile, TILES["OpenStreetMap"])
    m = folium.Map(center, zoom_start=zoom, tiles=t["tiles"], attr=t["attr"],
                   max_zoom=t["max_zoom"], control_scale=True)
    Fullscreen(title="전체화면", title_cancel="닫기").add_to(m)
    MiniMap(toggle_display=True, minimized=True).add_to(m)
    return m


def _photo(d, w=230):
    f = PHOTOS / d["photo"] if d.get("photo") else None
    if not f or not f.exists() or f.stat().st_size > 3_000_000:
        return ""
    b64 = base64.b64encode(f.read_bytes()).decode()
    return (f'<img src="data:image/jpeg;base64,{b64}" '
            f'style="width:{w}px;border-radius:6px;margin-top:6px">')


def _popup(d):
    s, lv, _ = assess(d)
    return (f'<div style="font:13px/1.6 sans-serif">'
            f'<b style="font-size:15px">{d["name"]}</b><br>'
            f'<span style="color:{CMAP(min(s,20))};font-weight:700">{lv}</span>'
            f' · 점수 {s} · 제보 {d["count"]}건<br>'
            f'<span style="color:#666">{d["time"]} · {" · ".join(d["factors"])}</span><br>'
            f'<span style="color:#333">{d["memo"]}</span>{_photo(d)}</div>')


def points(m, rows, cluster=False):
    """위험도별로 레이어를 나눠 켜고 끌 수 있게 한다."""
    G = {n: folium.FeatureGroup(name=n, show=True)
         for n in ["상습 구간 (5건+)", "주의 (2~4건)", "단일 제보"]}
    heat = []

    for d in rows:
        s, lv, _ = assess(d)
        col = CMAP(min(s, 20))
        g = G["상습 구간 (5건+)"] if d["count"] >= 5 else \
            G["주의 (2~4건)"] if d["count"] >= 2 else G["단일 제보"]
        tgt = MarkerCluster().add_to(g) if cluster else g

        if d["count"] >= 5:      # 상습 구간은 옅은 후광을 둘러 멀리서도 보이게
            folium.CircleMarker((d["lat"], d["lng"]), radius=30, color=col,
                                fill=True, fill_color=col, fill_opacity=.12,
                                weight=0).add_to(tgt)

        sz = 26 + min(d["count"], 10) * 2.4
        folium.Marker(
            (d["lat"], d["lng"]),
            tooltip=f"{d['name']} · 제보 {d['count']}건 · {lv}",
            popup=folium.Popup(_popup(d), max_width=280),
            icon=folium.DivIcon(
                icon_size=(sz, sz), icon_anchor=(sz / 2, sz / 2),
                html=f'<div style="width:{sz}px;height:{sz}px;background:{col};'
                     f'border:2.5px solid #fff;border-radius:50%;color:#fff;'
                     f'box-shadow:0 1px 6px rgba(0,0,0,.4);'
                     f'font:700 {11 + min(d["count"], 6)}px sans-serif;'
                     f'display:flex;align-items:center;justify-content:center">'
                     f'{d["count"]}</div>'),
        ).add_to(tgt)
        heat.append([d["lat"], d["lng"], s])

    if heat:
        HeatMap(heat, name="위험도 히트맵", radius=32, blur=24, show=False).add_to(m)
    for g in G.values():
        g.add_to(m)
    CMAP.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m


def pin(m, pt, tip, color="blue", icon="info-sign"):
    folium.Marker(pt, tooltip=tip,
                  icon=folium.Icon(color=color, icon=icon)).add_to(m)
    return m


def routes(m, fast, safe, p1, p2, s_name, e_name):
    folium.PolyLine(fast["pts"], color="#e03131", weight=5, dash_array="9,9",
                    opacity=.9, tooltip="최단 경로").add_to(m)
    if safe is not fast:
        AntPath(safe["pts"], color="#0f9d58", weight=6, delay=800,
                tooltip="안전 경로").add_to(m)
    pin(m, p1, f"출발 · {s_name}", "blue", "play")
    pin(m, p2, f"도착 · {e_name}", "green", "flag")
    lats = [p[0] for p in fast["pts"]]
    lngs = [p[1] for p in fast["pts"]]
    m.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]])
    return m

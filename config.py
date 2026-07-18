"""설정값 모음 — 숫자와 목록만 있는 파일. 여기만 고치면 동작이 바뀐다."""

from pathlib import Path

BASE = Path(__file__).parent
STORE = BASE / "reports.json"
PHOTOS = BASE / "photos"
PHOTOS.mkdir(exist_ok=True)

# 위험 요인과 가중치. 값의 근거를 발표에서 설명할 수 있어야 한다.
W = {"어두움": 2.2, "시야 막힘": 1.9, "인적 없음": 1.6, "차와 섞임": 2.4,
     "가로등 고장": 2.0, "CCTV 없음": 1.5, "소음·개 짖음": 1.2}
FACTORS = list(W) + ["기타"]
W_DEFAULT = 1.5                      # 직접 입력한 요인의 기본 가중치

TIMES = ["18~20시", "20~22시", "22~24시", "24시 이후"]
W_TIME = dict(zip(TIMES, [0.6, 1.0, 1.5, 1.8]))

RADIUS = 90                          # 경로가 이 거리(m) 안이면 그 지점을 지난 것으로 본다

SERVERS = [
    ("OSRM 보행자", "https://routing.openstreetmap.de/routed-foot/route/v1/foot"),
    ("OSRM 자전거", "https://routing.openstreetmap.de/routed-bike/route/v1/bike"),
    ("OSRM 기본", "https://router.project-osrm.org/route/v1/driving"),
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

CENTER = (36.3504, 127.3845)         # 대전시청
GU = ["전체", "동구", "중구", "서구", "유성구", "대덕구"]

# 지도를 빠르게 옮기기 위한 동네 목록. 필요한 곳을 추가해서 쓸 것.
PLACES = {
    "동구 · 대전역": (36.3320, 127.4343), "동구 · 자양동": (36.3541, 127.4197),
    "동구 · 용전동": (36.3496, 127.4335), "동구 · 소제동": (36.3352, 127.4372),
    "동구 · 가양동": (36.3452, 127.4446), "동구 · 판암동": (36.3151, 127.4577),
    "중구 · 은행동": (36.3283, 127.4270), "중구 · 대흥동": (36.3268, 127.4213),
    "중구 · 태평동": (36.3243, 127.4008), "중구 · 오류동": (36.3305, 127.4090),
    "중구 · 부사동": (36.3178, 127.4285), "중구 · 문화동": (36.3140, 127.4155),
    "서구 · 둔산동": (36.3512, 127.3845), "서구 · 탄방동": (36.3462, 127.3921),
    "서구 · 월평동": (36.3593, 127.3702), "서구 · 갈마동": (36.3538, 127.3728),
    "서구 · 도마동": (36.3227, 127.3813), "서구 · 관저동": (36.2967, 127.3406),
    "서구 · 도안동": (36.3113, 127.3486),
    "유성구 · 봉명동": (36.3541, 127.3441), "유성구 · 궁동": (36.3625, 127.3480),
    "유성구 · 어은동": (36.3661, 127.3560), "유성구 · 노은동": (36.3849, 127.3221),
    "유성구 · 반석동": (36.3925, 127.3160), "유성구 · 전민동": (36.3878, 127.3928),
    "대덕구 · 오정동": (36.3574, 127.4110), "대덕구 · 중리동": (36.3648, 127.4166),
    "대덕구 · 법동": (36.3711, 127.4180), "대덕구 · 송촌동": (36.3689, 127.4285),
    "대덕구 · 회덕동": (36.3838, 127.4269), "대덕구 · 신탄진동": (36.4488, 127.4302),
}

# 밤골목 색. 짙은 남색 계열로 통일했다.
NAVY = "#1b2a4a"
NAVY_HOVER = "#27395f"
NAVY_LIGHT = "#41567f"

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

  /* 기본 버튼 — 남색 테두리 */
  .stButton > button, .stDownloadButton > button {{
      background:#fff; color:{NAVY} !important; border:1.5px solid {NAVY_LIGHT};
      border-radius:8px; font-weight:600; transition:.15s; }}
  .stButton > button:hover, .stDownloadButton > button:hover {{
      background:{NAVY}; color:#fff !important; border-color:{NAVY}; }}
  .stButton > button:hover p {{ color:#fff !important; }}

  /* 주요 버튼 — 짙은 남색 채움 */
  .stButton > button[kind="primary"],
  .stFormSubmitButton > button[kind="primary"] {{
      background:{NAVY}; color:#fff !important; border:1.5px solid {NAVY}; }}
  .stButton > button[kind="primary"]:hover,
  .stFormSubmitButton > button[kind="primary"]:hover {{
      background:{NAVY_HOVER}; border-color:{NAVY_HOVER}; }}
  .stButton > button[kind="primary"] p {{ color:#fff !important; }}

  /* 탭 — Streamlit 기본 강조색(빨강)을 남색으로 덮는다.
     버전마다 선택자가 달라 여러 개를 함께 지정한다. */
  .stTabs [data-baseweb="tab"] {{ font-size:1rem; font-weight:600; }}
  .stTabs [data-baseweb="tab"][aria-selected="true"],
  .stTabs [data-baseweb="tab"][aria-selected="true"] p,
  .stTabs button[aria-selected="true"] {{ color:{NAVY} !important; }}
  .stTabs [data-baseweb="tab-highlight"],
  div[data-baseweb="tab-highlight"] {{
      background-color:{NAVY} !important; height:3px !important; }}
  .stTabs [data-baseweb="tab-list"] button:hover {{ color:{NAVY_HOVER} !important; }}
  .stTabs [data-baseweb="tab-list"] {{ gap:6px; }}

  /* 입력칸·체크박스 포커스 */
  input:focus, textarea:focus {{ border-color:{NAVY_LIGHT} !important; }}
  [data-baseweb="checkbox"] span[data-checked="true"],
  [data-testid="stCheckbox"] [data-checked="true"] {{
      background-color:{NAVY} !important; border-color:{NAVY} !important; }}
</style>
"""

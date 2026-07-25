# -*- coding: utf-8 -*-
"""
make_pdf.py
===========
run_saju.py가 출력하는 JSON 결과를 받아서 60페이지 이상 분량의 프리미엄
사주풀이 결과지 PDF를 생성한다.

구현 방식: HTML을 생성한 뒤 LibreOffice(soffice --headless --convert-to pdf)로
변환한다. LibreOffice의 HTML→PDF 변환 필터는 CSS 막대그래프나 SVG 도형을
렌더링하지 못하므로(사전 테스트로 확인됨), 오행 막대그래프 등 시각 자료는
matplotlib으로 PNG 이미지를 미리 만들어 <img> 태그로 삽입한다.

사용법:
  echo '<run_saju.py의 JSON 출력>' | python3 make_pdf.py /output/path.pdf
"""
import sys
import os
import json
import html
import tempfile
import shutil
from pathlib import Path

# ---------------------------------------------------------------
# 임시 폴더/HOME을 안전한 위치로 강제 지정 (Windows/Linux 공용)
# ---------------------------------------------------------------
if os.name == "nt":
    _SAFE_TMP = tempfile.gettempdir()
else:
    _SAFE_TMP = "/tmp"
    os.environ["TMPDIR"] = _SAFE_TMP
tempfile.tempdir = _SAFE_TMP
_safe_home = os.path.join(_SAFE_TMP, "saju_pdf_home")
os.makedirs(_safe_home, exist_ok=True)
if os.name != "nt":
    os.environ["HOME"] = _safe_home
os.environ.setdefault("MPLCONFIGDIR", os.path.join(_SAFE_TMP, "mplconfig"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

sys.path.insert(0, os.path.dirname(__file__))
from office.soffice import run_soffice
from ai_interpreter import generate_ai_interpretation
from glossary import build_footnote_html, UNSEONG_DESC

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")

# 붓글씨체(장제목용)와 본문용 한글 폰트 후보. 파일이 실제로 존재하는 것만 등록한다.
_BRUSH_FONT_CANDIDATES = ["수성혜정체_Regular.ttf", "SuseongHyejeong-Regular.ttf"]
_BRUSH_FONT_FAMILY = None
_BODY_FONT_FAMILY = "Noto Sans CJK KR"

if os.path.isdir(FONTS_DIR):
    for fname in _BRUSH_FONT_CANDIDATES:
        fpath = os.path.join(FONTS_DIR, fname)
        if os.path.exists(fpath):
            try:
                fm.fontManager.addfont(fpath)
                _BRUSH_FONT_FAMILY = fm.FontProperties(fname=fpath).get_name()
            except Exception:
                pass
            break


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def file_uri(path: str) -> str:
    """OS에 상관없이 올바른 file:// URI를 만든다.
    Windows에서 os.path.join()으로 만든 경로(백슬래시 포함)를 그냥
    f"file://{path}" 로 이어붙이면 LibreOffice가 이미지를 인식하지
    못해 <img> 태그가 통째로 무시되는 문제가 있었다 (실제 발생 확인됨)."""
    return Path(path).resolve().as_uri()


# ---------------------------------------------------------------
# matplotlib 차트 생성 (오행 막대그래프 / 오각형 상생상극 다이어그램)
# ---------------------------------------------------------------
OHENG_COLORS = {"목": "#4C9A5B", "화": "#D9534F", "토": "#B8925A", "금": "#B8B8B8", "수": "#4472A8"}
OHENG_ORDER = ["목", "화", "토", "금", "수"]


_MPL_KR_FONT_CANDIDATES_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "C:\\Windows\\Fonts\\malgun.ttf",
]
_mpl_kr_font_ready = False


def _set_korean_font_for_mpl():
    global _mpl_kr_font_ready
    plt.rcParams["axes.unicode_minus"] = False
    if _mpl_kr_font_ready:
        return
    # 1) 이미 이름으로 등록된 한글 폰트가 있는지 먼저 확인
    for candidate in ["Noto Sans CJK KR", "NanumGothic", "Malgun Gothic", "AppleGothic"]:
        try:
            if any(candidate.lower() == f.name.lower() for f in fm.fontManager.ttflist):
                plt.rcParams["font.family"] = candidate
                _mpl_kr_font_ready = True
                return
        except Exception:
            continue
    # 2) 이름으로 못 찾으면(.ttc 컬렉션이라 자동 등록이 안 된 경우 등) 파일 경로로 직접 등록
    for fpath in _MPL_KR_FONT_CANDIDATES_PATHS:
        if os.path.exists(fpath):
            try:
                fm.fontManager.addfont(fpath)
                font_name = fm.FontProperties(fname=fpath).get_name()
                plt.rcParams["font.family"] = font_name
                _mpl_kr_font_ready = True
                return
            except Exception:
                continue
    plt.rcParams["font.family"] = "sans-serif"


def make_oheng_dashboard(oheng_dist: dict, out_path: str):
    """오행 분포를 하나의 통합 대시보드 이미지로 시각화한다.
    (막대그래프 + 상생 오각형 + 비율 도넛을 한 figure 안에 배치해
    조각난 이미지 여러 개를 늘어놓던 기존 방식을 대체한다.)
    """
    import math
    _set_korean_font_for_mpl()

    values = [oheng_dist.get(o, 0) for o in OHENG_ORDER]
    total = sum(values) or 1
    colors = [OHENG_COLORS[o] for o in OHENG_ORDER]

    fig = plt.figure(figsize=(9.0, 5.6), dpi=150)
    fig.patch.set_alpha(0)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.05, 1], height_ratios=[1, 1],
                            hspace=0.38, wspace=0.28,
                            left=0.06, right=0.97, top=0.93, bottom=0.08)

    # ---- (좌상) 막대그래프 ----
    ax_bar = fig.add_subplot(gs[0, 0])
    bars = ax_bar.bar(OHENG_ORDER, values, color=colors, width=0.6, zorder=3)
    for rect, v in zip(bars, values):
        ax_bar.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + 0.08, str(v),
                     ha="center", va="bottom", fontsize=12, fontweight="bold", color="#3A2410")
    ax_bar.set_ylim(0, max(values + [1]) + 1.2)
    ax_bar.set_title("오행 개수 분포", fontsize=12.5, fontweight="bold", color="#8B4513", pad=10)
    ax_bar.spines[["top", "right", "left"]].set_visible(False)
    ax_bar.set_yticks([])
    ax_bar.tick_params(axis="x", labelsize=13)
    ax_bar.set_axisbelow(True)
    ax_bar.grid(axis="y", color="#E8DCC8", linewidth=0.6, zorder=0)

    # ---- (우상) 비율 도넛 ----
    ax_ring = fig.add_subplot(gs[0, 1])
    non_zero = [(o, v, c) for o, v, c in zip(OHENG_ORDER, values, colors) if v > 0]
    if not non_zero:
        non_zero = [(o, 1, c) for o, c in zip(OHENG_ORDER, colors)]
    ax_ring.pie(
        [v for _, v, _ in non_zero], colors=[c for _, _, c in non_zero],
        startangle=90, counterclock=False,
        wedgeprops=dict(width=0.40, edgecolor="white", linewidth=2),
        radius=1.05,
    )
    ax_ring.set_title("오행 비율", fontsize=12.5, fontweight="bold", color="#8B4513", pad=10)
    legend_labels = [f"{o} {v}개 ({v/total*100:.0f}%)" for o, v, _ in non_zero]
    ax_ring.legend(legend_labels, loc="upper center", bbox_to_anchor=(0.5, -0.02),
                    ncol=2, fontsize=9, frameon=False,
                    handlelength=0.9, handletextpad=0.5, columnspacing=1.0,
                    labelcolor=[c for _, _, c in non_zero])
    ax_ring.set_aspect("equal")

    # ---- (하단, 전체 너비) 상생 오각형 다이어그램 ----
    ax_pent = fig.add_subplot(gs[1, :])
    ax_pent.set_xlim(-1.55, 1.55)
    ax_pent.set_ylim(-1.3, 1.35)
    ax_pent.set_aspect("equal")
    ax_pent.axis("off")
    ax_pent.set_title("오행 상생(相生) 순환 구조", fontsize=12.5, fontweight="bold", color="#8B4513", pad=6)

    n = 5
    angle_offset = math.pi / 2
    positions = {}
    for i, o in enumerate(OHENG_ORDER):
        angle = angle_offset - 2 * math.pi * i / n
        positions[o] = (math.cos(angle) * 1.05, math.sin(angle) * 1.05)

    for i in range(n):
        o1 = OHENG_ORDER[i]
        o2 = OHENG_ORDER[(i + 1) % n]
        x1, y1 = positions[o1]
        x2, y2 = positions[o2]
        ax_pent.annotate(
            "", xy=(x2 * 0.76, y2 * 0.76), xytext=(x1 * 0.76, y1 * 0.76),
            arrowprops=dict(arrowstyle="-|>", color="#B8925A", lw=1.8,
                             connectionstyle="arc3,rad=0.22"),
        )

    for o in OHENG_ORDER:
        x, y = positions[o]
        count = oheng_dist.get(o, 0)
        circle = plt.Circle((x, y), 0.30, color=OHENG_COLORS[o], ec="white", lw=2.2, zorder=3)
        ax_pent.add_patch(circle)
        ax_pent.text(x, y, f"{o}\n{count}", ha="center", va="center", fontsize=11.5,
                      fontweight="bold", color="white", zorder=4)

    fig.savefig(out_path, transparent=True)
    plt.close(fig)


def make_sipseong_bar_chart(sipseong: dict, out_path: str):
    """연/월/일/시 십성 배치를 카드형 원으로 시각화."""
    _set_korean_font_for_mpl()
    order = ["연간", "월간", "일간", "시간"]
    labels = ["연주", "월주", "일주", "시주"]
    fig, ax = plt.subplots(figsize=(8.6, 2.6), dpi=150)
    fig.patch.set_alpha(0)
    ax.set_xlim(0, 4)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")
    for i, key in enumerate(order):
        val = sipseong.get(key, "")
        short_val = val.split("(")[0].strip() if "(" in val else val
        x = i + 0.5
        fontsize = 10.5 if len(short_val) <= 3 else 8.5
        circle = plt.Circle((x, 0.55), 0.32, color="#8B4513", alpha=0.88, zorder=2,
                              ec="#5C2E0C", lw=1.4)
        ax.add_patch(circle)
        ax.text(x, 0.55, short_val, ha="center", va="center", fontsize=fontsize,
                 fontweight="bold", color="white", zorder=3)
        ax.text(x, 0.06, labels[i], ha="center", va="center", fontsize=10.5,
                 fontweight="bold", color="#8B4513")
    fig.tight_layout(pad=0.8)
    fig.savefig(out_path, transparent=True)
    plt.close(fig)


def make_daeun_timeline_chart(daeun: dict, out_path: str):
    """대운 흐름을 타임라인 카드로 시각화 (나이순)."""
    _set_korean_font_for_mpl()
    ages = daeun.get("startAges", [])
    pillars = daeun.get("pillars", [])
    n = len(ages)
    if n == 0:
        return
    fig, ax = plt.subplots(figsize=(8.6, 1.9), dpi=150)
    fig.patch.set_alpha(0)
    ax.set_xlim(-0.5, n - 0.5)
    ax.set_ylim(0, 1)
    ax.axis("off")
    if n > 1:
        ax.plot([0, n - 1], [0.51, 0.51], color="#D0B8A0", lw=2, zorder=1)
    for i in range(n):
        x = i
        rect = plt.Rectangle((x - 0.42, 0.28), 0.84, 0.46, facecolor="#EADFCF",
                               edgecolor="#8B4513", lw=1.4, zorder=2)
        ax.add_patch(rect)
        ax.text(x, 0.51, pillars[i] if i < len(pillars) else "", ha="center", va="center",
                 fontsize=10.5, fontweight="bold", color="#3A2410", zorder=3)
        ax.text(x, 0.10, f"{ages[i]}세", ha="center", va="center", fontsize=9.5,
                 fontweight="bold", color="#8B4513")
    fig.tight_layout(pad=0.8)
    fig.savefig(out_path, transparent=True)
    plt.close(fig)


def make_gunghap_score_gauge(score: int, grade: str, out_path: str):
    """궁합 점수를 반원형 게이지로 시각화."""
    import math
    _set_korean_font_for_mpl()
    fig, ax = plt.subplots(figsize=(4.4, 2.7), dpi=150)
    fig.patch.set_alpha(0)
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-0.15, 1.2)
    ax.axis("off")

    theta = [math.pi * (1 - t / 100) for t in range(0, 101)]
    bg_x = [math.cos(t) for t in theta]
    bg_y = [math.sin(t) for t in theta]
    ax.plot(bg_x, bg_y, color="#EADFCF", lw=14, solid_capstyle="round")

    score = max(0, min(100, score))
    theta2 = [math.pi * (1 - t / 100) for t in range(0, score + 1)]
    fg_x = [math.cos(t) for t in theta2]
    fg_y = [math.sin(t) for t in theta2]
    color = "#C0392B" if score >= 80 else ("#B8925A" if score >= 60 else "#7A7A7A")
    ax.plot(fg_x, fg_y, color=color, lw=14, solid_capstyle="round")

    ax.text(0, 0.42, f"{score}점", ha="center", va="center", fontsize=22, fontweight="bold", color=color)
    ax.text(0, 0.14, f"{grade}급 궁합", ha="center", va="center", fontsize=12, fontweight="bold", color="#555")
    fig.tight_layout()
    fig.savefig(out_path, transparent=True)
    plt.close(fig)


def make_monthly_calendar_chart(wolun_list: list, out_path: str):
    """12개월 월운을 3x4 캘린더 형태 카드로 시각화."""
    _set_korean_font_for_mpl()
    fig, axes = plt.subplots(3, 4, figsize=(8.4, 5.8), dpi=150)
    fig.patch.set_alpha(0)
    for idx, item in enumerate(wolun_list):
        r, c = divmod(idx, 4)
        ax = axes[r][c]
        oheng = item.get("oheng", "토")
        color = OHENG_COLORS.get(oheng, "#B8925A")
        ax.set_facecolor("#FFFFFF")
        rect = plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, facecolor=color, alpha=0.16, zorder=0)
        ax.add_patch(rect)
        ax.text(0.5, 0.74, f"{item['month']}월", ha="center", va="center",
                fontsize=13, fontweight="bold", color="#3A2410", transform=ax.transAxes)
        ax.text(0.5, 0.44, item.get("ganji", ""), ha="center", va="center",
                fontsize=11.5, color=color, fontweight="bold", transform=ax.transAxes)
        ax.text(0.5, 0.16, item.get("sipseong", ""), ha="center", va="center",
                fontsize=9.5, color="#555", transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_edgecolor("#D0B8A0")
            spine.set_linewidth(1.2)
    fig.tight_layout(pad=0.8)
    fig.savefig(out_path, transparent=True)
    plt.close(fig)


# ---------------------------------------------------------------
# HTML 조립
# ---------------------------------------------------------------
CSS_TEMPLATE = """
@page {{ size: A4; margin: 14mm 16mm; }}
* {{ box-sizing: border-box; }}
body {{
  font-family: "{body_font}", "Noto Sans KR", sans-serif;
  color: #262220; line-height: 1.9; font-size: 10.8pt;
  letter-spacing: 0.015em; word-break: keep-all; -webkit-hyphens: none; hyphens: none;
}}
.brush {{ font-family: "{brush_font}", "{body_font}", serif; }}

.cover {{ text-align: center; padding-top: 70mm; }}
.cover .brand {{ font-size: 15pt; font-weight: bold; color: #8B4513; margin-bottom: 8mm; letter-spacing: 0.06em; }}
.cover .main-title {{ font-size: 30pt; margin-bottom: 6mm; line-height: 1.5; }}
.cover .sub-title {{ font-size: 13pt; color: #555; margin-bottom: 14mm; letter-spacing: 0.04em; }}
.cover .birth-info {{ font-size: 11.5pt; color: #444; }}
.cover .stamp {{ margin-top: 20mm; font-size: 10pt; color: #B8925A; letter-spacing: 0.02em; }}

.toc-page {{ padding-top: 6mm; }}
.toc-title-pb {{ font-size: 20pt; margin-bottom: 8mm; text-align: center; page-break-before: always; font-family: "{brush_font}", "{body_font}", serif; }}
.toc-page h1 {{ font-size: 20pt; margin-bottom: 8mm; text-align: center; }}
.toc-entry {{ display: flex; justify-content: space-between; padding: 3.2mm 0; border-bottom: 1px dotted #D0B8A0; font-size: 10.8pt; line-height: 1.5; }}
.toc-part {{ font-weight: bold; font-size: 12.5pt; color: #8B4513; margin-top: 6mm; margin-bottom: 2mm; letter-spacing: 0.02em; }}

.chapter-title {{
  font-size: 23pt; color: #8B4513; margin: 0 0 7mm 0; padding-bottom: 3mm;
  border-bottom: 3px solid #C9A24B; font-family: "{brush_font}", "{body_font}", serif;
  letter-spacing: 0.03em;
}}
.chapter-title-pb {{
  font-size: 23pt; color: #8B4513; margin: 0 0 7mm 0; padding-bottom: 3mm;
  border-bottom: 3px solid #C9A24B; font-family: "{brush_font}", "{body_font}", serif;
  page-break-before: always; letter-spacing: 0.03em;
}}
.section-title {{ font-size: 14pt; font-weight: bold; color: #8B4513; margin: 5mm 0 3.5mm 0; letter-spacing: 0.02em; }}
.section-title-pb {{ font-size: 14pt; font-weight: bold; color: #8B4513; margin: 5mm 0 3.5mm 0; page-break-before: always; letter-spacing: 0.02em; }}
.body-text {{ font-size: 10.8pt; text-align: justify; margin: 0 0 3.2mm 0; line-height: 1.9; letter-spacing: 0.015em; }}
.body-text + .body-text {{ margin-top: 3.2mm; }}

table {{ border-collapse: collapse; width: 100%; margin: 3.5mm 0; }}
th, td {{ border: 1px solid #D0B8A0; text-align: center; padding: 2.6mm; font-size: 10pt; line-height: 1.5; }}
th {{ background: #F5E6D3; font-weight: bold; letter-spacing: 0.02em; }}
.pillars-table td {{ font-size: 13pt; font-weight: bold; }}

.oheng-badge-row {{ display: flex; flex-wrap: wrap; gap: 2mm; margin: 2mm 0 4mm 0; }}
.oheng-badge {{ display: inline-block; background: #F5E6D3; border-radius: 3.5mm; padding: 1.8mm 4.5mm; font-size: 10.5pt; letter-spacing: 0.02em; }}
.dashboard-img {{ display: block; margin: 2mm auto; }}
.insight-table {{ width: 100%; border-collapse: separate; border-spacing: 3mm 0; margin: 5mm 0 3mm 0; table-layout: fixed; }}
.insight-card {{ background: #FBF6EC; border: 1px solid #E3D3B8; border-radius: 3mm; padding: 4mm 2mm; text-align: center; width: 33.3%; }}
.insight-label {{ font-size: 9pt; color: #8B7355; margin-bottom: 1.5mm; letter-spacing: 0.02em; }}
.insight-value {{ font-size: 13pt; font-weight: bold; color: #3A2410; }}
.chart-img {{ display: block; margin: 3mm auto; max-width: 100%; }}
.chart-row {{ display: flex; justify-content: space-around; align-items: center; margin: 3mm 0; }}
.chart-row img {{ max-width: 48%; }}

.full-page-section {{ min-height: 250mm; }}
.compact-section {{ margin-top: 4mm; }}
.footnote-box {{ margin-top: 5mm; padding-top: 2.5mm; border-top: 1px solid #E3D9C0; }}
.footnote-item {{ font-size: 8.2pt; color: #7A7A7A; margin: 1mm 0; line-height: 1.6; }}

.page-break {{ page-break-before: always; }}
.two-col {{ display: flex; gap: 6mm; }}
.two-col > div {{ flex: 1; }}

.gunghap-score-box {{ text-align: center; padding: 5mm; background: #F5E6D3; border-radius: 3mm; margin: 4mm 0; }}
.gunghap-score-box .score {{ font-size: 26pt; font-weight: bold; color: #8B4513; }}
.gunghap-score-box .grade {{ font-size: 13pt; color: #555; letter-spacing: 0.02em; }}

.footer-note {{ font-size: 8pt; color: #999; margin-top: 7mm; line-height: 1.6; }}
.footer-note-pb {{ font-size: 8pt; color: #999; margin-top: 7mm; page-break-before: always; line-height: 1.6; }}
"""


def build_html(data: dict, chart_paths: dict) -> str:
    b = data["birth"]
    birth_str = f"{b['year']}년 {b['month']}월 {b['day']}일 {b['hour']:02d}시 {b['minute']:02d}분 (양력)"
    pillars = data["pillars"]
    interp = data.get("interpretation", {})
    ai_extra = data.get("aiExtra", {})  # ai_interpreter.py 그룹 호출 결과 (있으면 우선 사용)
    sipseong = data.get("sipseong", {})
    daeun = data["daeun"]
    unseong = data.get("unseong12", {})
    seun = data["seun"]
    sinsal = data.get("sinsal", {})
    yongsin = data.get("yongsin", {})
    gyeokguk = data.get("gyeokguk", {})
    wolun = data.get("wolun", [])
    gunghap = data.get("gunghap")
    oheng_dist = data["ohengDistribution"]
    most_oheng = data.get("ohengMostCommon", "")
    missing_ohengs = data.get("ohengMissing", []) or []
    _oheng_vals = list(oheng_dist.values())
    _oheng_max, _oheng_min = (max(_oheng_vals), min(_oheng_vals)) if _oheng_vals else (0, 0)
    if _oheng_max - _oheng_min <= 1:
        oheng_balance_label = "고른 편"
    elif _oheng_max - _oheng_min <= 3:
        oheng_balance_label = "다소 치우침"
    else:
        oheng_balance_label = "편중이 뚜렷함"

    def txt(key, fallback=""):
        """AI 그룹 호출 결과(ai_extra)를 우선 사용하고, 없으면 기존 고정문구(interp)로 폴백."""
        return ai_extra.get(key) or interp.get(key) or fallback

    def sec(title, key, fallback_text="", full_page=True, force_break=True):
        body = txt(key, fallback_text)
        footnote = build_footnote_html(body)
        h2_cls = "section-title-pb" if force_break else "section-title"
        div_cls = "full-page-section" if full_page else "compact-section"
        return f"""
        <div class="{div_cls}">
        <h2 class="{h2_cls}">■ {esc(title)}</h2>
        <p class="body-text">{esc(body)}</p>
        {footnote}
        </div>
        """

    ai_note = ("본 리포트의 운세풀이 문장은 AI(Claude)가 계산된 사주 명식을 바탕으로 개인 맞춤 생성했습니다."
               if data.get("aiUsed") else
               "본 리포트의 운세풀이 문장은 사전 정리된 명리학 해석 데이터베이스를 기반으로 생성되었습니다.")

    daeun_headers = "".join(f"<th>{age}세</th>" for age in daeun["startAges"])
    daeun_values = "".join(f"<td>{esc(gj)}</td>" for gj in daeun["pillars"])
    seun_str = " / ".join(f"{y}년: {esc(gj)}" for y, gj in seun.items())

    oheng_rows = " ".join(
        f"<span class='oheng-badge' style=\"background:{OHENG_COLORS.get(k,'#F5E6D3')}22;border:1px solid {OHENG_COLORS.get(k,'#D0B8A0')};\">"
        f"<b style=\"color:{OHENG_COLORS.get(k,'#8B4513')};\">{esc(k)}</b> {v}개</span>"
        for k, v in oheng_dist.items()
    )

    # -------------------- 표지 --------------------
    cover_html = f"""
    <div class="cover">
      <div class="brand brush">易 동네사주카페</div>
      <div class="main-title brush">{esc(data['name'])}님의<br>평생 사주풀이</div>
      <div class="sub-title">정통 사주명리 프리미엄 리포트</div>
      <div class="birth-info">{esc(birth_str)}</div>
      <div class="stamp">- 자평진전 · 삼명통회 · 명리정종 · 적천수 이론 기반 -</div>
    </div>
    <h1 class="chapter-title-pb">리포트 이용 안내</h1>
    <p class="body-text">이 리포트는 정통 사주명리학 고전 이론(자평진전, 삼명통회, 명리정종, 적천수)과 정밀한 절기·만세력 계산을 바탕으로 {esc(data['name'])}님의 사주팔자를 심층 분석한 프리미엄 결과지입니다. 사주 원국 분석부터 오행·십성·용신·격국 분석, 12대 개별 운세, 신년 및 평생운세, 월별 상세 운세까지 총 5부로 구성되어 있으며, 전문 용어가 처음 등장하는 부분마다 하단에 간단한 용어 해설을 각주로 덧붙여 누구나 쉽게 이해할 수 있도록 구성했습니다.</p>
    <p class="body-text">사주명리는 태어난 연월일시에 담긴 우주 자연의 기운을 통해 타고난 기질과 삶의 큰 흐름을 살피는 동양의 전통 학문입니다. 이 리포트에서 제시하는 내용은 절대적인 확정이 아니라, 스스로의 강점을 발견하고 부족한 부분을 보완하며 더 나은 선택을 하기 위한 참고 자료로 활용하시기를 권해드립니다. 특히 대운과 세운, 월운의 흐름을 함께 살펴보시면 시기별 전략을 세우는 데 실질적인 도움이 될 것입니다.</p>
    <p class="body-text">본 리포트에 사용된 용신·희신·격국·궁합 등의 판정은 억부용신론과 월지 지장간 정기를 기준으로 한 표준적인 명리학 이론 체계를 따르고 있습니다. 이는 여러 유파 중 가장 널리 통용되는 방식이며, 유파에 따라 세부 해석에 차이가 있을 수 있음을 참고 부탁드립니다. 그럼 지금부터 {esc(data['name'])}님의 사주팔자 속에 담긴 이야기를 함께 살펴보겠습니다.</p>
    """

    # -------------------- 목차 --------------------
    toc_parts = [
        ("1부. 정통 사주명리 기초분석", [
            "사주팔자 원국 분석", "오행 분석", "십성 분석", "용신·희신 분석", "격국 분석", "대운·세운 분석",
        ]),
        ("2부. 12대 개별 운세", [
            "재물운", "사업운·창업운", "직장운·이직운·승진운", "시험운·합격운", "문서운·계약운", "연애운·인연운",
            "결혼운·배우자운", "자녀운", "가족운", "건강운", "이동운·이사운", "귀인운·인복",
        ]),
        ("3부. 신년 운세 및 평생운세 총론", ["신년 운세", "평생운세 총평", "택일·성명학 안내"]),
        ("4부. 월별 운세 상세", [f"{m}월 운세" for m in range(1, 13)]),
    ]
    if gunghap:
        toc_parts.append(("5부. 궁합 상세분석", ["궁합 종합 총평", "궁합 강점 및 시너지", "궁합 주의점 및 개운법"]))

    toc_html_parts = []
    for part_title, entries in toc_parts:
        toc_html_parts.append(f"<div class='toc-part'>{esc(part_title)}</div>")
        for e in entries:
            toc_html_parts.append(f"<div class='toc-entry'><span>{esc(e)}</span></div>")
    toc_html = f"""
    <div class="toc-page">
      <h1 class="toc-title-pb">목차</h1>
      {''.join(toc_html_parts)}
    </div>
    """

    # -------------------- 1부: 기초분석 --------------------
    unseong_positions = [("연주(초년운)", "연지"), ("월주(청장년운)", "월지"), ("일주(중년·자기자신)", "일지"), ("시주(노년·자녀운)", "시지")]
    unseong_detail_parts = []
    for i, (pos, pos_key) in enumerate(unseong_positions):
        us = unseong.get(pos_key, '')
        desc = UNSEONG_DESC.get(us, '')
        h_cls = "section-title-pb" if i == 0 else "section-title"
        unseong_detail_parts.append(
            f'<h2 class="{h_cls}">■ ' + esc(pos) + ' — ' + esc(us) + '</h2>'
            '<p class="body-text">' + esc(desc) + ' ' + esc(pos) + ' 자리는 각각 초년/청년기(연주), 청장년기(월주), 중년기(일주, 자기자신), 노년기 및 자녀운(시주)과 연결되는 자리로, 이 시기 기운의 흐름을 참고하시면 좋습니다.</p>'
        )
    unseong_detail_html = '<div class="full-page-section">' + "".join(unseong_detail_parts) + '</div>'

    part1_html = f"""
    <h1 class="chapter-title-pb">1부. 정통 사주명리 기초분석</h1>

    <h2 class="section-title">■ 사주팔자 원국표</h2>
    <table class="pillars-table">
      <tr><th>구분</th><th>시주</th><th>일주</th><th>월주</th><th>연주</th></tr>
      <tr><td>천간</td><td>{esc(pillars['시주'][0])}</td><td>{esc(pillars['일주'][0])}</td><td>{esc(pillars['월주'][0])}</td><td>{esc(pillars['연주'][0])}</td></tr>
      <tr><td>지지</td><td>{esc(pillars['시주'][1])}</td><td>{esc(pillars['일주'][1])}</td><td>{esc(pillars['월주'][1])}</td><td>{esc(pillars['연주'][1])}</td></tr>
    </table>
    <p class="body-text">일간(日干, 본인을 의미하는 글자): <b>{esc(data['ilgan'])}</b></p>
    {sec("사주팔자 원국 총평", "사주원국해설", txt('ohengBasic'))}
    <div class="full-page-section" style="min-height:0;">
    <h2 class="section-title-pb">■ 오행 분포</h2>
    <div class="oheng-badge-row">{oheng_rows}</div>
    <img class="chart-img dashboard-img" src="{file_uri(chart_paths['oheng_dashboard'])}" width="700" style="width:92%;max-width:700px;" />
    <table class="insight-table"><tr>
      <td class="insight-card">
        <div class="insight-label">가장 강한 오행</div>
        <div class="insight-value" style="color:{OHENG_COLORS.get(most_oheng,'#8B4513')};">{esc(most_oheng or '-')}</div>
      </td>
      <td class="insight-card">
        <div class="insight-label">부족한 오행</div>
        <div class="insight-value">{esc(', '.join(missing_ohengs) if missing_ohengs else '없음')}</div>
      </td>
      <td class="insight-card">
        <div class="insight-label">오행 균형도</div>
        <div class="insight-value">{esc(oheng_balance_label)}</div>
      </td>
    </tr></table>
    <p class="body-text">위 도표는 사주팔자 여덟 글자에 담긴 오행(목·화·토·금·수)의 분포와, 오행이 서로 낳아주고(상생) 서로 억제하는(상극) 관계, 그리고 전체 대비 비율을 하나의 대시보드로 정리한 것입니다. 특정 오행이 많거나 적은 정도에 따라 타고난 기질과 부족한 기운을 정량적으로 파악할 수 있습니다.</p>
    </div>
    {sec("오행 분석 상세 해설", "오행해설", txt('ohengBasic'), full_page=False, force_break=False)}
    <div class="full-page-section">
    <h2 class="section-title-pb">■ 십성(十星) 배치</h2>
    <table>
      <tr><th>구분</th><th>연주</th><th>월주</th><th>일주</th><th>시주</th></tr>
      <tr><td>십성</td><td>{esc(sipseong.get('연간',''))}</td><td>{esc(sipseong.get('월간',''))}</td><td>{esc(sipseong.get('일간',''))}</td><td>{esc(sipseong.get('시간',''))}</td></tr>
    </table>
    <img class="chart-img" src="{file_uri(chart_paths['sipseong_bar'])}" width="600" style="width:100%;max-width:600px;" />
    <p class="body-text">십성은 일간(나)을 기준으로 다른 글자와의 관계를 비견·겁재·식신·상관·편재·정재·편관·정관·편인·정인 10가지로 분류한 것으로, 성격과 인간관계, 재능의 방향성을 파악하는 핵심 지표입니다. 위 표와 도표는 연주·월주·일주·시주 각 자리에 어떤 십성이 배치되어 있는지를 한눈에 보여줍니다.</p>
    </div>
    {sec("십성 배치 해설", "십성해설", full_page=False, force_break=False)}
    <div class="full-page-section">
    <h2 class="section-title-pb">■ 12운성(十二運星) 흐름</h2>
    <table>
      <tr><th>구분</th><th>연주</th><th>월주</th><th>일주</th><th>시주</th></tr>
      <tr><td>운성</td><td>{esc(unseong.get('연지',''))}</td><td>{esc(unseong.get('월지',''))}</td><td>{esc(unseong.get('일지',''))}</td><td>{esc(unseong.get('시지',''))}</td></tr>
    </table>
    <p class="body-text">12운성은 일간이 각 지지 위에서 태어나 자라고 늙어가는 과정을 장생·목욕·관대·건록·제왕·쇠·병·사·묘·절·태·양 12단계로 표현한 것으로, 각 시기별 기운의 성쇠(盛衰)를 보여줍니다. 기운이 왕성한 자리에서는 활동력과 추진력이 강해지고, 쇠약한 자리에서는 신중함과 내실을 다지는 노력이 필요합니다. 아래에서는 연주·월주·일주·시주 네 자리에 나타난 운성을 하나씩 살펴봅니다.</p>
    </div>
    {unseong_detail_html}
    <div class="full-page-section">
    <h2 class="section-title-pb">■ 용신(用神)·희신(喜神) 분석</h2>
    <table>
      <tr><th>구분</th><th>용신</th><th>희신</th><th>기신</th><th>구신</th><th>한신</th></tr>
      <tr><td>오행</td><td>{esc(yongsin.get('yongsin',''))}</td><td>{esc(yongsin.get('huisin',''))}</td>
          <td>{esc(yongsin.get('gisin',''))}</td><td>{esc(yongsin.get('gusin',''))}</td><td>{esc(yongsin.get('hansin',''))}</td></tr>
    </table>
    <p class="body-text">{esc(yongsin.get('reason',''))}</p>
    </div>
    {sec("용신·희신 분석 해설", "용신해설", full_page=False, force_break=False)}
    <div class="full-page-section">
    <h2 class="section-title-pb">■ 격국(格局) 분석</h2>
    <p class="body-text"><b>{esc(gyeokguk.get('name',''))}</b> — {esc(gyeokguk.get('description',''))}</p>
    <p class="body-text">격국은 사주의 전체적인 틀과 성격 유형을 정하는 분류 체계로, 태어난 달의 지지(월지)에 담긴 지장간의 정기를 기준으로 판정합니다. 격국을 알면 이 사람이 인생에서 어떤 방식으로 성취를 이루어 나가는 유형인지, 어떤 환경에서 능력을 가장 잘 발휘하는지를 가늠할 수 있습니다.</p>
    </div>
    {sec("격국 분석 해설", "격국해설", full_page=False, force_break=False)}
    <div class="full-page-section" style="min-height:0;">
    <h2 class="section-title-pb">■ 대운(大運) — 10년 주기 흐름</h2>
    <p class="body-text">{'순행' if daeun['forward'] else '역행'} · 대운수 {daeun['daeunSu']}세부터 적용됩니다. 대운은 10년 단위로 바뀌는 큰 흐름의 운으로, 아래 표와 타임라인은 앞으로 맞이하게 될 각 대운 시기의 간지를 나이 순으로 정리한 것입니다.</p>
    <table><tr>{daeun_headers}</tr><tr>{daeun_values}</tr></table>
    <img class="chart-img" src="{file_uri(chart_paths['daeun_timeline'])}" width="460" style="width:78%;max-width:460px;" />
    <h2 class="section-title" style="margin-top:6mm;">■ 세운(歲運) — 최근 3개년 흐름</h2>
    <p class="body-text">{seun_str}</p>
    <p class="body-text">세운은 매년 바뀌는 그 해의 운으로, 대운이라는 큰 흐름 안에서 1년 단위의 세부적인 기운 변화를 보여줍니다. 대운과 세운이 만나 이루는 조합에 따라 그 해의 길흉이 달라지므로, 아래 해설과 함께 참고하시기 바랍니다.</p>
    </div>
    {sec("대운·세운 흐름 해설", "대운세운해설", full_page=False, force_break=False)}
    """

    # -------------------- 2부: 12대 개별 운세 --------------------
    life_items = [
        ("재물운", "재물운"), ("사업운·창업운", "사업운창업운"), ("직장운·이직운·승진운", "직장운이직운승진운"),
        ("시험운·합격운", "시험운"), ("문서운·계약운", "문서운"), ("연애운·인연운", "연애운인연운"),
        ("결혼운·배우자운", "결혼운배우자운"), ("자녀운", "자녀운"), ("가족운", "가족운"),
        ("건강운", "건강운"), ("이동운·이사운", "이동운"), ("귀인운·인복", "귀인운"),
    ]
    part2_sections = []
    for i, (title, key) in enumerate(life_items):
        part2_sections.append(f'<h1 class="chapter-title-pb">2부. 12대 개별 운세</h1>' if i == 0 else "")
        part2_sections.append(sec(title, key))
    part2_html = "".join(part2_sections)

    # -------------------- 3부: 신년/평생운세 --------------------
    part3_html = f"""
        <h1 class="chapter-title-pb">3부. 신년 운세 및 평생운세 총론</h1>
    {sec("신년 운세 총평", "신년운세")}
    {sec("평생운세 총평", "평생운세총평")}
    {sec("택일·성명학 안내", "택일성명학안내")}
    """

    # -------------------- 4부: 월별 운세 12개월 --------------------
    monthly_rows = "".join(
        f"<tr><td>{w['month']}월</td><td>{esc(w['ganji'])}</td><td>{esc(w['sipseong'])}</td><td>{esc(w['keyword'])}</td></tr>"
        for w in wolun
    )
    monthly_detail_html = ""
    for idx, w in enumerate(wolun):
        body_key = f"{w['month']}월운세"
        body_text = txt(body_key, w.get('keyword', ''))
        footnote = build_footnote_html(body_text)
        monthly_detail_html += f"""
        <div class="full-page-section">
        <h2 class="section-title-pb">■ {w['month']}월 — {esc(w['ganji'])} ({esc(w['sipseong'])})</h2>
        <p class="body-text">{esc(body_text)}</p>
        {footnote}
        </div>
        """

    part4_html = f"""
        <h1 class="chapter-title-pb">4부. 월별 운세 상세</h1>
    <img class="chart-img" src="{file_uri(chart_paths['monthly'])}" width="600" style="width:100%;max-width:600px;" />
    <table>
      <tr><th>월</th><th>월간지</th><th>십성</th><th>핵심 분위기</th></tr>
      {monthly_rows}
    </table>
    {monthly_detail_html}
    """

    # -------------------- 5부: 궁합 (있을 때만) --------------------
    gunghap_html = ""
    if gunghap:
        gunghap_html = f"""
                <h1 class="chapter-title-pb">5부. 궁합 상세분석</h1>
        <img class="chart-img" src="{file_uri(chart_paths.get('gunghap_gauge','')) if chart_paths.get('gunghap_gauge') else ''}" width="380" style="width:58%;max-width:380px;display:block;margin:0 auto;" />
        <p class="body-text">{esc(gunghap.get('summary',''))}</p>
        <h2 class="section-title">■ 궁합 세부 근거표</h2>
        <table>
          <tr><th>항목</th><th>내용</th></tr>
          <tr><td>일간 관계</td><td>{esc(gunghap.get('ilgan_relation',''))}</td></tr>
          <tr><td>육합</td><td>{esc(', '.join(gunghap.get('yukhap_hits', [])) or '없음')}</td></tr>
          <tr><td>삼합</td><td>{esc(', '.join(gunghap.get('samhap_hits', [])) or '없음')}</td></tr>
          <tr><td>충</td><td>{esc(', '.join(gunghap.get('chung_hits', [])) or '없음')}</td></tr>
          <tr><td>형·해·파</td><td>{esc(', '.join(gunghap.get('hyeong_hae_pa_hits', [])) or '없음')}</td></tr>
        </table>
        <p class="body-text">위 표는 두 사람의 일간(日干) 오행 관계와, 지지(地支)끼리 맺는 합(合)·충(沖)·형(刑)·해(害)·파(破) 관계를 종합적으로 분석한 근거 자료입니다. 육합과 삼합은 관계를 화합시키는 긍정적 작용을, 충·형·해·파는 갈등이나 변화를 유발할 수 있는 작용을 나타냅니다.</p>
        {sec("궁합 종합 총평", "궁합총평", gunghap.get('summary',''), force_break=True)}
        {sec("궁합 강점 및 시너지", "궁합장점", full_page=False, force_break=False)}
        {sec("궁합 주의점 및 개운법", "궁합주의점및개운법", full_page=False, force_break=False)}
        """

    # -------------------- 오행 보완·개운법 부록 --------------------
    gaeunbeop_html = ""
    missing_texts = interp.get("ohengMissingTexts", []) or []
    gaeunbeop_list = interp.get("gaeunbeop", []) or []
    if missing_texts or gaeunbeop_list:
        gb_parts = ['<h1 class="chapter-title-pb">부록. 부족한 오행 보완 및 개운법</h1>']
        gb_parts.append(
            '<p class="body-text">사주팔자에서 상대적으로 부족한 오행의 기운은 일상 속 색상, 방향, 음식, 생활 습관 등을 통해 자연스럽게 보완할 수 있습니다. 아래는 이 사주에서 보완이 필요한 오행에 대한 해설과 구체적인 개운법입니다.</p>'
        )
        for i, txt_item in enumerate(missing_texts):
            gb = gaeunbeop_list[i] if i < len(gaeunbeop_list) else ""
            fn = build_footnote_html(txt_item)
            gb_parts.append(
                '<div class="full-page-section">'
                '<h2 class="section-title-pb">■ 오행 보완 해설 (' + str(i + 1) + ')</h2>'
                '<p class="body-text">' + esc(txt_item) + '</p>'
                '<h2 class="section-title">■ 실천 개운법</h2>'
                '<p class="body-text">' + esc(gb) + '</p>'
                + fn +
                '</div>'
            )
        gaeunbeop_html = "".join(gb_parts)

    # -------------------- 신살 부록 --------------------
    sinsal_html = ""
    if sinsal:
        sinsal_parts = []
        for i, name in enumerate(sinsal.keys()):
            body = interp.get('신살', {}).get(name, '') or f"{name}은(는) 이 사주에 나타나는 특별한 기운으로, 삶의 특정 국면에서 그 영향력이 두드러지게 나타날 수 있습니다."
            footnote = build_footnote_html(body)
            h1_prefix = '<h1 class="chapter-title-pb">부록. 귀인분석 (주요 신살)</h1>\n' if i == 0 else ""
            sinsal_parts.append(f"""
            {h1_prefix}
            <div class="full-page-section">
            <h2 class="section-title-pb">■ {esc(name)}</h2>
            <p class="body-text">{esc(body)}</p>
            {footnote}
            </div>
            """)
        sinsal_html = "".join(sinsal_parts)

    html_doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>{CSS_TEMPLATE.format(body_font=_BODY_FONT_FAMILY, brush_font=(_BRUSH_FONT_FAMILY or _BODY_FONT_FAMILY))}</style>
</head>
<body>
{cover_html}
{toc_html}
{part1_html}
{part2_html}
{part3_html}
{part4_html}
{gunghap_html}
{sinsal_html}
{gaeunbeop_html}
<p class="footer-note-pb">{esc(ai_note)} 본 결과지는 자평진전·삼명통회·명리정종·적천수 등 명리학 고전 이론과 수학적 절기 계산에 기반하여 자동 산출되었습니다.</p>
</body>
</html>
"""
    return html_doc


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "message": "출력 경로가 필요합니다."}, ensure_ascii=False))
        sys.exit(1)

    output_path = sys.argv[1]
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "message": f"입력 JSON 파싱 실패: {e}"}, ensure_ascii=False))
        sys.exit(1)

    tmp_dir = tempfile.mkdtemp(prefix="saju_pdf_")
    try:
        # --- AI 그룹 호출 (실패 시 고정 문구로 자동 폴백) ---
        ai_used = False
        try:
            include_gunghap = bool(data.get("gunghap"))
            ai_extra = generate_ai_interpretation(data, include_gunghap=include_gunghap)
            data["aiExtra"] = ai_extra
            ai_used = True
        except Exception as e:
            print(f"[AI 해석 생성 실패 - 고정 문구로 대체합니다] {e}", file=sys.stderr)
            data["aiExtra"] = {}
        data["aiUsed"] = ai_used

        # --- matplotlib 차트 생성 ---
        chart_paths = {
            "oheng_dashboard": os.path.join(tmp_dir, "oheng_dashboard.png"),
            "monthly": os.path.join(tmp_dir, "monthly.png"),
            "sipseong_bar": os.path.join(tmp_dir, "sipseong_bar.png"),
            "daeun_timeline": os.path.join(tmp_dir, "daeun_timeline.png"),
            "gunghap_gauge": os.path.join(tmp_dir, "gunghap_gauge.png"),
        }
        make_oheng_dashboard(data["ohengDistribution"], chart_paths["oheng_dashboard"])
        make_sipseong_bar_chart(data.get("sipseong", {}), chart_paths["sipseong_bar"])
        make_daeun_timeline_chart(data.get("daeun", {}), chart_paths["daeun_timeline"])
        if data.get("wolun"):
            make_monthly_calendar_chart(data["wolun"], chart_paths["monthly"])
        if data.get("gunghap"):
            make_gunghap_score_gauge(
                data["gunghap"].get("score", 0), data["gunghap"].get("grade", "중"),
                chart_paths["gunghap_gauge"],
            )

        html_content = build_html(data, chart_paths)
        html_path = os.path.join(tmp_dir, "report.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        result = run_soffice(
            ["--headless", "--convert-to", "pdf", "--outdir", tmp_dir, html_path],
            capture_output=True, text=True, timeout=180,
        )

        generated_pdf = os.path.join(tmp_dir, "report.pdf")
        if result.returncode != 0 or not os.path.exists(generated_pdf):
            print(json.dumps({
                "success": False,
                "message": f"PDF 변환 실패: {result.stderr or result.stdout}",
            }, ensure_ascii=False))
            sys.exit(1)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        shutil.move(generated_pdf, output_path)

        print(json.dumps({"success": True, "path": output_path, "aiUsed": ai_used}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"success": False, "message": f"PDF 생성 실패: {e}"}, ensure_ascii=False))
        sys.exit(1)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()

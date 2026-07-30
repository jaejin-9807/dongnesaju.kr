# -*- coding: utf-8 -*-
"""
report_charts.py
================
matplotlib 기반 그래프 생성. 번들 폰트(Noto Sans KR)를 직접 등록해
OS 기본 글꼴에 의존하지 않고, 어떤 환경에서도 한글이 깨지지 않게 한다(섹션 6).
저채도 오행 팔레트 사용. 배경 투명 PNG 로 저장해 HTML <img> 로 삽입한다.
"""
import os
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from report_theme import OHENG_COLORS, OHENG_ORDER, TOKENS

FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_KR_REGULAR = os.path.join(FONTS_DIR, "NotoSansKR-Regular.otf")
_KR_BOLD = os.path.join(FONTS_DIR, "NotoSansKR-Bold.otf")
_font_ready = False


def _ensure_font():
    global _font_ready
    plt.rcParams["axes.unicode_minus"] = False
    if _font_ready:
        return
    fam = None
    for fp in (_KR_REGULAR, _KR_BOLD):
        if os.path.exists(fp):
            try:
                fm.fontManager.addfont(fp)
                fam = fm.FontProperties(fname=fp).get_name()
            except Exception:
                pass
    if fam:
        plt.rcParams["font.family"] = fam
    else:
        # 번들 폰트가 없으면 시스템 한글 폰트라도 시도
        for c in ["Noto Sans CJK KR", "NanumGothic", "Malgun Gothic", "AppleGothic"]:
            if any(c.lower() == f.name.lower() for f in fm.fontManager.ttflist):
                plt.rcParams["font.family"] = c
                break
    _font_ready = True


INK = TOKENS["ink"]
GOLD = TOKENS["gold"]
SEAL = TOKENS["seal"]
LINE = TOKENS["line"]


def make_oheng_dashboard(oheng_dist: dict, out_path: str):
    _ensure_font()
    values = [oheng_dist.get(o, 0) for o in OHENG_ORDER]
    total = sum(values) or 1
    colors = [OHENG_COLORS[o] for o in OHENG_ORDER]

    fig = plt.figure(figsize=(14.4, 5.7), dpi=170)  # 크고 직관적이되 가로형이라 페이지 하단 여백을 줄임
    fig.patch.set_alpha(0)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.05, 1], height_ratios=[1, 1],
                          hspace=0.44, wspace=0.22, left=0.04, right=0.98, top=0.90, bottom=0.08)

    ax_bar = fig.add_subplot(gs[0, 0])
    bars = ax_bar.bar(OHENG_ORDER, values, color=colors, width=0.64, zorder=3)
    for rect, v in zip(bars, values):
        ax_bar.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + 0.08, str(v),
                    ha="center", va="bottom", fontsize=18, fontweight="bold", color=INK)
    ax_bar.set_ylim(0, max(values + [1]) + 1.2)
    ax_bar.set_title("오행 개수 분포", fontsize=19, fontweight="bold", color=SEAL, pad=12)
    ax_bar.spines[["top", "right", "left"]].set_visible(False)
    ax_bar.set_yticks([]); ax_bar.tick_params(axis="x", labelsize=19)
    ax_bar.set_axisbelow(True); ax_bar.grid(axis="y", color=LINE, linewidth=0.6, zorder=0)

    ax_ring = fig.add_subplot(gs[0, 1])
    non_zero = [(o, v, c) for o, v, c in zip(OHENG_ORDER, values, colors) if v > 0] \
        or [(o, 1, c) for o, c in zip(OHENG_ORDER, colors)]
    ax_ring.pie([v for _, v, _ in non_zero], colors=[c for _, _, c in non_zero],
                startangle=90, counterclock=False, autopct="%1.0f%%", pctdistance=0.80,
                textprops=dict(fontsize=13, fontweight="bold", color="white"),
                wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2), radius=1.08)
    ax_ring.set_title("오행 비율", fontsize=19, fontweight="bold", color=SEAL, pad=12)
    ax_ring.legend([f"{o} {v}개" for o, v, _ in non_zero],
                   loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=3, fontsize=13,
                   frameon=False, handlelength=1.0, handletextpad=0.5, columnspacing=1.1,
                   labelcolor=[c for _, _, c in non_zero])
    ax_ring.set_aspect("equal")

    ax_p = fig.add_subplot(gs[1, :])
    ax_p.set_xlim(-1.7, 1.7); ax_p.set_ylim(-1.35, 1.4); ax_p.set_aspect("equal"); ax_p.axis("off")
    ax_p.set_title("오행 상생 순환 구조", fontsize=19, fontweight="bold", color=SEAL, pad=8)
    n = 5; off = math.pi / 2; pos = {}
    for i, o in enumerate(OHENG_ORDER):
        a = off - 2 * math.pi * i / n
        pos[o] = (math.cos(a) * 1.08, math.sin(a) * 1.08)
    for i in range(n):
        x1, y1 = pos[OHENG_ORDER[i]]; x2, y2 = pos[OHENG_ORDER[(i + 1) % n]]
        ax_p.annotate("", xy=(x2 * 0.74, y2 * 0.74), xytext=(x1 * 0.74, y1 * 0.74),
                      arrowprops=dict(arrowstyle="-|>", color=GOLD, lw=2.6, connectionstyle="arc3,rad=0.22"))
    for o in OHENG_ORDER:
        x, y = pos[o]
        ax_p.add_patch(plt.Circle((x, y), 0.34, color=OHENG_COLORS[o], ec="white", lw=2.6, zorder=3))
        ax_p.text(x, y, f"{o}\n{oheng_dist.get(o, 0)}", ha="center", va="center",
                  fontsize=17, fontweight="bold", color="white", zorder=4, linespacing=1.1)
    fig.savefig(out_path, transparent=True); plt.close(fig)


def make_sipseong_chart(sipseong: dict, out_path: str):
    _ensure_font()
    order = ["연간", "월간", "일간", "시간"]; labels = ["연주", "월주", "일주", "시주"]
    # 글자가 잘 보이도록 원과 폰트를 크게 (어르신 가독성)
    fig, ax = plt.subplots(figsize=(9.8, 3.5), dpi=170); fig.patch.set_alpha(0)
    ax.set_xlim(0, 4); ax.set_ylim(0, 1); ax.set_aspect("equal"); ax.axis("off")
    for i, key in enumerate(order):
        val = sipseong.get(key, ""); sv = val.split("(")[0].strip() if "(" in val else val
        x = i + 0.5; fs = 20 if len(sv) <= 2 else (16 if len(sv) == 3 else 13)
        ax.add_patch(plt.Circle((x, 0.58), 0.40, color=SEAL, alpha=0.88, zorder=2, ec="#7A1F19", lw=1.8))
        ax.text(x, 0.58, sv, ha="center", va="center", fontsize=fs, fontweight="bold", color="white", zorder=3)
        ax.text(x, 0.05, labels[i], ha="center", va="center", fontsize=14, fontweight="bold", color=SEAL)
    fig.tight_layout(pad=0.8); fig.savefig(out_path, transparent=True); plt.close(fig)


def make_daeun_timeline(daeun: dict, out_path: str, scores=None, ohengs=None, cur_idx=-1):
    """대운 흐름을 큼직한 카드형 타임라인으로 재디자인.
    - 각 카드: 나이 · 간지 · (오행색 상단 띠) · 운세지수 점
    - 현재 대운은 인장 적색 테두리로 강조
    """
    _ensure_font()
    ages = daeun.get("startAges", []); pillars = daeun.get("pillars", []); n = len(ages)
    if n == 0:
        return
    fig, ax = plt.subplots(figsize=(12.4, 3.0), dpi=170); fig.patch.set_alpha(0)
    ax.set_xlim(-0.6, n - 0.4); ax.set_ylim(0, 1); ax.axis("off")
    if n > 1:
        ax.plot([0, n - 1], [0.30, 0.30], color=TOKENS["gold_soft"], lw=3, zorder=1)
    for i in range(n):
        o = (ohengs[i] if ohengs and i < len(ohengs) else None)
        top = OHENG_COLORS.get(o, GOLD)
        is_cur = (i == cur_idx)
        edge = SEAL if is_cur else GOLD
        lw = 3.0 if is_cur else 1.6
        # 카드 본체
        ax.add_patch(plt.Rectangle((i - 0.44, 0.40), 0.88, 0.46, facecolor="#FBF5E9",
                                   edgecolor=edge, lw=lw, zorder=2))
        # 오행 색 상단 띠
        ax.add_patch(plt.Rectangle((i - 0.44, 0.78), 0.88, 0.08, facecolor=top, zorder=3))
        ax.text(i, 0.60, pillars[i] if i < len(pillars) else "", ha="center", va="center",
                fontsize=18, fontweight="bold", color=INK, zorder=4)
        ax.text(i, 0.20, f"{ages[i]}세~", ha="center", va="center", fontsize=13, fontweight="bold", color=SEAL)
        if is_cur:
            ax.text(i, 0.93, "현재", ha="center", va="center", fontsize=12, fontweight="bold", color=SEAL)
        # 운세지수 점
        if scores and i < len(scores):
            ax.plot(i, 0.30, "o", ms=11, color=_score_color(scores[i]), zorder=5,
                    markeredgecolor="white", markeredgewidth=1.4)
    fig.tight_layout(pad=0.6); fig.savefig(out_path, transparent=True); plt.close(fig)


def _score_color(s):
    return SEAL if s >= 75 else (GOLD if s >= 55 else "#8E9298")


def make_fortune_bars(labels, scores, out_path, title="운세 흐름", highlight_best=True, focus_from=None):
    """정량 '운세 지수' 막대그래프 (10년/12개월 등 공용).
    focus_from(index)이 주어지면: 그 이전(과거) 막대는 흐리게 처리하고,
    '최고' 강조는 focus_from 이후(현재·미래) 구간에서만 표시한다.
    (예: 60대 손님에게 30·40대 과거를 '최고'로 보여주지 않기 위함)"""
    _ensure_font()
    n = len(labels)
    fig, ax = plt.subplots(figsize=(12.4, 4.2), dpi=170); fig.patch.set_alpha(0)
    ff = focus_from if (focus_from is not None and 0 <= focus_from < n) else 0
    bars = []
    for i, s in enumerate(scores):
        past = i < ff
        col = "#C9CCD1" if past else _score_color(s)
        b = ax.bar(i, s, color=col, width=0.66, zorder=3, alpha=(0.55 if past else 1.0))
        bars.append(b)
        ax.text(i, s + 1.5, str(int(s)), ha="center", va="bottom",
                fontsize=13, fontweight="bold", color=("#AAB0B6" if past else INK))
    # '최고'는 현재·미래(focus_from 이후) 구간에서만 표시
    if highlight_best and scores:
        cand = list(range(ff, n)) or list(range(n))
        bi = int(max(cand, key=lambda k: scores[k]))
        ax.text(bi, scores[bi] + 8, "앞으로 최고", ha="center", va="bottom",
                fontsize=13, fontweight="bold", color=SEAL)
    if ff > 0:
        ax.axvline(ff - 0.5, color=SEAL, lw=1.4, ls=":", zorder=1)
        ax.text(ff - 0.5, 103, "지금부터", ha="center", va="bottom", fontsize=11.5, fontweight="bold", color=SEAL)
    ax.set_ylim(0, 108)
    ax.set_xticks(range(n)); ax.set_xticklabels(labels, fontsize=14, fontweight="bold")
    ax.set_yticks([]); ax.set_title(title, fontsize=18, fontweight="bold", color=SEAL, pad=12)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.axhline(60, color=LINE, lw=1.0, ls="--", zorder=0)
    ax.set_axisbelow(True)
    fig.tight_layout(pad=0.8); fig.savefig(out_path, transparent=True); plt.close(fig)


def make_life_curve(ages, scores, out_path, cur_age=None):
    """인생 곡선(대운별 운세지수).
    현재 나이 이전(과거)은 흐리게, 이후(현재·미래)는 선명하게 그려
    '지나온 길'과 '앞으로의 길'을 구분한다. '전성기' 강조는 현재 이후에서만 표시."""
    _ensure_font()
    fig, ax = plt.subplots(figsize=(12.4, 4.0), dpi=170); fig.patch.set_alpha(0)
    ax.plot(ages, scores, "-", color="#C9CCD1", lw=2.4, zorder=2)  # 전체(회색 바탕선)
    # 현재 이후 구간만 금색으로 덧그림
    fut = [i for i in range(len(ages)) if cur_age is None or ages[i] + 9 >= cur_age]
    if len(fut) >= 2:
        ax.plot([ages[i] for i in fut], [scores[i] for i in fut], "-", color=GOLD, lw=3.4, zorder=3)
        ax.fill_between([ages[i] for i in fut], [scores[i] for i in fut], 40, color=GOLD, alpha=0.14, zorder=1)
    for a, s in zip(ages, scores):
        past = (cur_age is not None and a + 9 < cur_age)
        ax.plot(a, s, "o", ms=9, color=("#C9CCD1" if past else _score_color(s)),
                markeredgecolor="white", markeredgewidth=1.4, zorder=4)
    # '앞으로의 전성기'는 현재 이후 구간에서 가장 높은 지점에 표시
    if scores:
        cand = fut if fut else list(range(len(scores)))
        bi = int(max(cand, key=lambda k: scores[k]))
        ax.annotate("앞으로의 전성기", (ages[bi], scores[bi]), textcoords="offset points", xytext=(0, 15),
                    ha="center", fontsize=14, fontweight="bold", color=SEAL)
    if cur_age is not None:
        ax.axvline(cur_age, color=SEAL, lw=1.8, ls=":", zorder=2)
        ax.text(cur_age, 104, "현재", ha="center", fontsize=12.5, fontweight="bold", color=SEAL)
    ax.set_ylim(35, 110); ax.set_yticks([])
    ax.set_xlabel("나이(세)", fontsize=13, fontweight="bold", color=INK)
    ax.tick_params(axis="x", labelsize=13)
    ax.set_title("인생 운세 곡선 (회색=지나온 길 · 금색=앞으로의 길)", fontsize=16, fontweight="bold", color=SEAL, pad=12)
    ax.spines[["top", "right", "left"]].set_visible(False)
    fig.tight_layout(pad=0.8); fig.savefig(out_path, transparent=True); plt.close(fig)


def make_radar(categories, scores, out_path):
    """5대 운세 종합 지수 레이더 차트."""
    _ensure_font()
    n = len(categories)
    angles = [i / n * 2 * math.pi for i in range(n)] + [0.0]
    vals = list(scores) + [scores[0]]
    fig = plt.figure(figsize=(7.6, 7.2), dpi=170); fig.patch.set_alpha(0)
    ax = fig.add_subplot(111, polar=True)
    ax.set_theta_offset(math.pi / 2); ax.set_theta_direction(-1)
    ax.plot(angles, vals, color=SEAL, lw=2.6)
    ax.fill(angles, vals, color=SEAL, alpha=0.16)
    ax.set_xticks(angles[:-1]); ax.set_xticklabels(categories, fontsize=15, fontweight="bold", color=INK)
    ax.set_ylim(0, 100); ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], fontsize=10, color=TOKENS["ink_soft"])
    ax.grid(color=LINE, lw=0.8)
    for ang, v in zip(angles[:-1], scores):
        ax.text(ang, v + 7, str(int(v)), ha="center", fontsize=12, fontweight="bold", color=SEAL)
    fig.tight_layout(pad=1.0); fig.savefig(out_path, transparent=True); plt.close(fig)


def make_monthly_calendar(wolun_list: list, out_path: str):
    _ensure_font()
    fig, axes = plt.subplots(3, 4, figsize=(8.4, 5.8), dpi=150); fig.patch.set_alpha(0)
    for idx, item in enumerate(wolun_list[:12]):
        r, c = divmod(idx, 4); ax = axes[r][c]
        color = OHENG_COLORS.get(item.get("oheng", "토"), GOLD)
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, facecolor=color, alpha=0.16, zorder=0))
        ax.text(0.5, 0.74, f"{item['month']}월", ha="center", va="center", fontsize=13, fontweight="bold", color=INK, transform=ax.transAxes)
        ax.text(0.5, 0.44, item.get("ganji", ""), ha="center", va="center", fontsize=11.5, color=color, fontweight="bold", transform=ax.transAxes)
        ax.text(0.5, 0.16, item.get("sipseong", ""), ha="center", va="center", fontsize=9.5, color=TOKENS["ink_soft"], transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_edgecolor(TOKENS["line"]); sp.set_linewidth(1.1)
    fig.tight_layout(pad=0.8); fig.savefig(out_path, transparent=True); plt.close(fig)


def make_gunghap_gauge(score: int, grade: str, out_path: str):
    _ensure_font()
    fig, ax = plt.subplots(figsize=(4.6, 2.8), dpi=150); fig.patch.set_alpha(0)
    ax.set_xlim(-1.2, 1.2); ax.set_ylim(-0.15, 1.2); ax.axis("off")
    theta = [math.pi * (1 - t / 100) for t in range(0, 101)]
    ax.plot([math.cos(t) for t in theta], [math.sin(t) for t in theta], color=TOKENS["ivory_deep"], lw=14, solid_capstyle="round")
    score = max(0, min(100, int(score)))
    th2 = [math.pi * (1 - t / 100) for t in range(0, score + 1)]
    color = SEAL if score >= 80 else (GOLD if score >= 60 else "#7A7A7A")
    ax.plot([math.cos(t) for t in th2], [math.sin(t) for t in th2], color=color, lw=14, solid_capstyle="round")
    ax.text(0, 0.42, f"{score}점", ha="center", va="center", fontsize=22, fontweight="bold", color=color)
    ax.text(0, 0.12, f"{grade}급 궁합", ha="center", va="center", fontsize=12, fontweight="bold", color=TOKENS["ink_soft"])
    fig.tight_layout(); fig.savefig(out_path, transparent=True); plt.close(fig)


# ------------------------------------------------------------------
# 오행 그래프를 '크게 3개로 분리' (PART 1 가독성 개선)
# ------------------------------------------------------------------
def make_oheng_bar(oheng_dist: dict, out_path: str):
    """오행 개수 막대그래프 — 크고 선명하게."""
    _ensure_font()
    values = [oheng_dist.get(o, 0) for o in OHENG_ORDER]
    colors = [OHENG_COLORS[o] for o in OHENG_ORDER]
    fig, ax = plt.subplots(figsize=(11.5, 5.6), dpi=170); fig.patch.set_alpha(0)
    bars = ax.bar(OHENG_ORDER, values, color=colors, width=0.62, zorder=3)
    for rect, v in zip(bars, values):
        ax.text(rect.get_x()+rect.get_width()/2, rect.get_height()+0.08, str(v),
                ha="center", va="bottom", fontsize=26, fontweight="bold", color=INK)
    ax.set_ylim(0, max(values+[1])+1.3)
    ax.set_title("오행 개수 분포", fontsize=26, fontweight="bold", color=SEAL, pad=16)
    ax.spines[["top","right","left"]].set_visible(False)
    ax.set_yticks([]); ax.tick_params(axis="x", labelsize=27)
    ax.set_axisbelow(True); ax.grid(axis="y", color=LINE, linewidth=0.8, zorder=0)
    fig.tight_layout(pad=1.0); fig.savefig(out_path, transparent=True); plt.close(fig)


def make_oheng_donut(oheng_dist: dict, out_path: str):
    """오행 비율 도넛 — 크고 선명하게."""
    _ensure_font()
    values = [oheng_dist.get(o, 0) for o in OHENG_ORDER]
    total = sum(values) or 1
    colors = [OHENG_COLORS[o] for o in OHENG_ORDER]
    non_zero = [(o, v, c) for o, v, c in zip(OHENG_ORDER, values, colors) if v > 0] \
        or [(o, 1, c) for o, c in zip(OHENG_ORDER, colors)]
    fig, ax = plt.subplots(figsize=(9.6, 6.8), dpi=170); fig.patch.set_alpha(0)
    ax.pie([v for _,v,_ in non_zero], colors=[c for _,_,c in non_zero],
           startangle=90, counterclock=False, autopct="%1.0f%%", pctdistance=0.80,
           textprops=dict(fontsize=20, fontweight="bold", color="white"),
           wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2.4), radius=1.15)
    ax.set_title("오행 비율", fontsize=26, fontweight="bold", color=SEAL, pad=16)
    ax.legend([f"{o} {v}개 ({v/total*100:.0f}%)" for o,v,_ in non_zero],
              loc="center", bbox_to_anchor=(0.5,-0.10), ncol=3, fontsize=17,
              frameon=False, handlelength=1.1, handletextpad=0.5, columnspacing=1.2,
              labelcolor=[c for _,_,c in non_zero])
    ax.set_aspect("equal")
    fig.tight_layout(pad=1.0); fig.savefig(out_path, transparent=True); plt.close(fig)


def make_oheng_pentagon(oheng_dist: dict, out_path: str, ilgan=None):
    """오행 5요소 구성도 — 각 원에 오행·비율·개수, 파란 화살표(상생)·빨간 별(상극)·범례.
    상생: 목→화→토→금→수→목 / 상극: 목→토→수→화→금→목"""
    _ensure_font()
    BLUE = "#3E6FB0"; RED = "#C0504D"
    fig, ax = plt.subplots(figsize=(9.8, 9.4), dpi=170); fig.patch.set_alpha(0)
    ax.set_xlim(-1.85, 1.85); ax.set_ylim(-1.75, 1.85); ax.set_aspect("equal"); ax.axis("off")
    title = ("나의 오행: " + str(ilgan)) if ilgan else "나의 오행 구성"
    ax.text(-1.8, 1.7, title, fontsize=24, fontweight="bold", color=INK, ha="left", va="center")

    total = sum(oheng_dist.get(o, 0) for o in OHENG_ORDER) or 1
    n = 5; off = math.pi / 2; R = 1.16; r_node = 0.42
    pos = {}
    for i, o in enumerate(OHENG_ORDER):
        a = off - 2 * math.pi * i / n
        pos[o] = (math.cos(a) * R, math.sin(a) * R)

    def _trim(p1, p2, t1, t2):
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        return (p1[0] + ux * t1, p1[1] + uy * t1), (p2[0] - ux * t2, p2[1] - uy * t2)

    # 상극(빨강, 안쪽 별): i -> i+2
    for i in range(n):
        p1 = pos[OHENG_ORDER[i]]; p2 = pos[OHENG_ORDER[(i + 2) % n]]
        s, e = _trim(p1, p2, r_node + 0.02, r_node + 0.06)
        ax.annotate("", xy=e, xytext=s, zorder=2,
                    arrowprops=dict(arrowstyle="-|>", color=RED, lw=2.4, alpha=0.9,
                                    shrinkA=0, shrinkB=0))
    # 상생(파랑, 바깥 곡선): i -> i+1
    for i in range(n):
        p1 = pos[OHENG_ORDER[i]]; p2 = pos[OHENG_ORDER[(i + 1) % n]]
        s, e = _trim(p1, p2, r_node + 0.03, r_node + 0.10)
        ax.annotate("", xy=e, xytext=s, zorder=3,
                    arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=3.4,
                                    connectionstyle="arc3,rad=0.28", shrinkA=0, shrinkB=0))
    # 오행 원
    for o in OHENG_ORDER:
        x, y = pos[o]; v = oheng_dist.get(o, 0); pct = round(v / total * 100)
        ax.add_patch(plt.Circle((x, y), r_node, color=OHENG_COLORS[o], ec="white", lw=3.0, zorder=5))
        ax.text(x, y + 0.09, o, ha="center", va="center", fontsize=23, fontweight="bold", color="white", zorder=6)
        ax.text(x, y - 0.17, f"{pct}% · {v}개", ha="center", va="center", fontsize=12.5, fontweight="bold", color="white", zorder=6)
    # 범례
    ax.annotate("", xy=(-1.42, 1.28), xytext=(-1.78, 1.28), arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=3.2))
    ax.text(-1.34, 1.28, "상생 (서로 도와줌)", fontsize=12.5, va="center", color=INK, fontweight="bold")
    ax.annotate("", xy=(-1.42, 1.06), xytext=(-1.78, 1.06), arrowprops=dict(arrowstyle="-|>", color=RED, lw=3.2))
    ax.text(-1.34, 1.06, "상극 (서로 눌러줌)", fontsize=12.5, va="center", color=INK, fontweight="bold")
    fig.tight_layout(pad=0.8); fig.savefig(out_path, transparent=True); plt.close(fig)

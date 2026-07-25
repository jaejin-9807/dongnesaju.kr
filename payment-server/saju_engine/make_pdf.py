# -*- coding: utf-8 -*-
"""
make_pdf.py (v5 — Playwright/Chromium 엔진 + 디자인 시스템)
==========================================================
run_saju.py 가 출력하는 계산 JSON 을 받아 프리미엄 사주풀이 PDF 를 생성한다.

파이프라인(섹션 4):
  사주 계산 JSON
    → (검증된) AI 콘텐츠 JSON
    → HTML/CSS 리포트 템플릿 (report_html.py, 번들 폰트/디자인 시스템)
    → 렌더 엔진 체인 (pdf_render.py: Playwright → WeasyPrint → LibreOffice)
    → 2-pass 렌더로 목차 실제 페이지번호 채움
    → 자동 검수(페이지 수/용량/A4)

입력(JSON, stdin): run_saju 결과. 선택적으로 "meta" 키에 표지/기준연도 정보 포함.
사용법:  echo '<json>' | python3 make_pdf.py /output/path.pdf

※ 기존 LibreOffice 기반 구현은 make_pdf_legacy.py 로 보존했으며,
  LibreOffice 는 pdf_render.py 에서 최후의 비상 폴백으로만 사용된다.
"""
import sys
import os
import re
import json
import tempfile
import shutil
from pathlib import Path

# ---------------------------------------------------------------
# 임시 폴더/HOME 안전 지정 (기존 동작 유지)
# ---------------------------------------------------------------
if os.name == "nt":
    _SAFE_TMP = tempfile.gettempdir()
else:
    _SAFE_TMP = os.environ.get("TMPDIR", "/tmp")
    os.environ.setdefault("TMPDIR", _SAFE_TMP)
tempfile.tempdir = _SAFE_TMP
_safe_home = os.path.join(_SAFE_TMP, "saju_pdf_home")
os.makedirs(_safe_home, exist_ok=True)
if os.name != "nt":
    os.environ.setdefault("HOME", _safe_home)
os.environ.setdefault("MPLCONFIGDIR", os.path.join(_SAFE_TMP, "mplconfig"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

sys.path.insert(0, os.path.dirname(__file__))

from ai_interpreter import generate_ai_interpretation, GROUPS
from report_html import build_report_html, build_teaser_html
import report_charts as charts
import pdf_render

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
COVER_IMAGE = os.path.join(ASSETS_DIR, "cover_source.jpg")


def _sanitize_filename(name: str) -> str:
    """파일명에 사용할 수 없는 문자 제거(섹션 4)."""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "", str(name)).strip()
    name = re.sub(r"\s+", "_", name)
    return name[:80] or "리포트"


def _default_report_type(data, meta):
    if meta.get("teaser"):
        return meta.get("reportType") or "이벤트 무료 사주"
    if meta.get("reportType"):
        return meta["reportType"]
    if data.get("gunghap"):
        return "궁합 분석"
    return "종합 사주 분석"


def _build_charts(data, tmp_dir):
    from report_html import compute_daeun_scores, compute_monthly_scores, compute_radar
    cp = {}

    def _(n):
        return os.path.join(tmp_dir, n)

    def uri(n):
        return Path(_(n)).resolve().as_uri()

    charts.make_oheng_dashboard(data.get("ohengDistribution", {}), _("oheng.png"))
    cp["oheng_dashboard"] = uri("oheng.png")
    # PART1 가독성: 오행 그래프 3종을 크게 분리 생성
    od = data.get("ohengDistribution", {})
    charts.make_oheng_bar(od, _("oheng_bar.png")); cp["oheng_bar"] = uri("oheng_bar.png")
    charts.make_oheng_donut(od, _("oheng_donut.png")); cp["oheng_donut"] = uri("oheng_donut.png")
    charts.make_oheng_pentagon(od, _("oheng_penta.png")); cp["oheng_pentagon"] = uri("oheng_penta.png")
    charts.make_sipseong_chart(data.get("sipseong", {}), _("sipseong.png"))
    cp["sipseong"] = uri("sipseong.png")

    # 대운: 점수/오행/현재 표시가 들어간 카드형 타임라인 + 인생곡선 + 10년 막대
    ds = compute_daeun_scores(data)
    charts.make_daeun_timeline(data.get("daeun", {}), _("daeun.png"),
                               scores=ds["scores"], ohengs=ds["ohengs"], cur_idx=ds["cur_idx"])
    if os.path.exists(_("daeun.png")):
        cp["daeun_timeline"] = uri("daeun.png")
    if ds["ages"]:
        charts.make_life_curve(ds["ages"], ds["scores"], _("life.png"), cur_age=ds["cur_age"])
        cp["life_curve"] = uri("life.png")
        labels10 = [f"{a}세\n{p}" for a, p in zip(ds["ages"], ds["pillars"])]
        charts.make_fortune_bars(labels10, ds["scores"], _("daeun_bars.png"),
                                 title="10년 단위 대운 운세 지수")
        cp["daeun_bars"] = uri("daeun_bars.png")

    if data.get("wolun"):
        charts.make_monthly_calendar(data["wolun"], _("monthly.png"))
        cp["monthly"] = uri("monthly.png")
        ms = compute_monthly_scores(data)
        charts.make_fortune_bars(ms["labels"], ms["scores"], _("monthly_bars.png"),
                                 title=f"{int((data.get('meta') or {}).get('reportYear') or 2026)}년 월별 운세 지수")
        cp["monthly_bars"] = uri("monthly_bars.png")

    rad = compute_radar(data)
    charts.make_radar(rad["categories"], rad["scores"], _("radar.png"))
    cp["radar"] = uri("radar.png")

    if data.get("gunghap"):
        charts.make_gunghap_gauge(data["gunghap"].get("score", 0), data["gunghap"].get("grade", "중"), _("gunghap.png"))
        cp["gunghap_gauge"] = uri("gunghap.png")
    return cp


def _extract_page_map(pdf_path, tokens):
    """1차 PDF 에서 각 CHxxMARK 마커가 몇 페이지에 있는지 찾는다.
    pypdf 가 설치돼 있지 않으면 빈 맵을 돌려주어(목차 페이지번호만 비게 됨) 크래시를 막는다."""
    try:
        from pypdf import PdfReader
    except Exception:
        print("[안내] pypdf 미설치 - 목차 페이지번호 계산을 건너뜁니다. (pip install pypdf 권장)", file=sys.stderr)
        return {}, 0
    reader = PdfReader(pdf_path)
    page_of = {}
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        for tok in tokens:
            if tok not in page_of and (tok + "MARK") in text:
                page_of[tok] = i
    return page_of, len(reader.pages)


def _render_two_pass(html, tmp_dir, output_path):
    """토큰 치환용 2-pass 렌더. 실제 목차 페이지번호를 채운다."""
    tokens = re.findall(r"\{\{PG_(CH\d+)\}\}", html)
    tokens = list(dict.fromkeys(tokens))

    html_p1 = re.sub(r"\{\{PG_CH\d+\}\}", "00", html)
    p1_html_path = os.path.join(tmp_dir, "report_p1.html")
    with open(p1_html_path, "w", encoding="utf-8") as f:
        f.write(html_p1)
    p1_pdf = os.path.join(tmp_dir, "report_p1.pdf")
    info1 = pdf_render.render_pdf(p1_html_path, p1_pdf, debug_dir=tmp_dir)

    page_of, _pages = _extract_page_map(p1_pdf, tokens)

    def repl(m):
        return str(page_of.get(m.group(1), ""))
    html_p2 = re.sub(r"\{\{PG_(CH\d+)\}\}", repl, html)
    p2_html_path = os.path.join(tmp_dir, "report.html")
    with open(p2_html_path, "w", encoding="utf-8") as f:
        f.write(html_p2)
    info2 = pdf_render.render_pdf(p2_html_path, output_path, prefer=info1["engine"], debug_dir=tmp_dir)
    return info2, p2_html_path


def _validate_pdf(pdf_path):
    size = os.path.getsize(pdf_path)
    try:
        from pypdf import PdfReader
    except Exception:
        return {"pages": None, "size": size, "a4_portrait": None,
                "issues": (["파일 용량이 비정상적으로 작습니다."] if size < 20000 else [])}
    reader = PdfReader(pdf_path)
    pages = len(reader.pages)
    box = reader.pages[0].mediabox
    w, h = float(box.width), float(box.height)
    is_a4_portrait = (abs(w - 595) < 8 and abs(h - 842) < 8) or (h > w)
    issues = []
    if pages < 1:
        issues.append("페이지가 없습니다.")
    if size < 20000:
        issues.append("파일 용량이 비정상적으로 작습니다.")
    if not is_a4_portrait:
        issues.append(f"A4 세로형이 아닐 수 있습니다({w:.0f}x{h:.0f}pt).")
    return {"pages": pages, "size": size, "a4_portrait": is_a4_portrait, "issues": issues}


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

    meta = data.get("meta", {}) or {}
    report_type = _default_report_type(data, meta)
    report_year = int(meta.get("reportYear") or 2026)
    customer_name = meta.get("customerName") or data.get("name") or "의뢰인"
    meta.update({
        "reportType": report_type,
        "reportYear": report_year,
        "customerName": customer_name,
        "coverImageUri": Path(COVER_IMAGE).resolve().as_uri() if os.path.exists(COVER_IMAGE) else "",
    })

    tmp_dir = tempfile.mkdtemp(prefix="saju_pdf_")
    try:
        # --- AI 그룹 호출 (검증 포함, 실패 그룹만 폴백) ---
        ai_used = False
        ai_keys = []
        fallback_groups = []
        try:
            include_gunghap = bool(data.get("gunghap"))

            def _progress(gid, ok):
                if not ok:
                    fallback_groups.append(gid)

            ai_extra = generate_ai_interpretation(
                data, include_gunghap=include_gunghap, on_progress=_progress)
            data["aiExtra"] = ai_extra
            ai_keys = list(ai_extra.keys())
            ai_used = len(ai_keys) > 0
        except Exception as e:
            print(f"[AI 해석 생성 실패 - 고정 문구로 대체합니다] {e}", file=sys.stderr)
            data["aiExtra"] = {}
            fallback_groups = [g["id"] for g in GROUPS]
        data["aiUsed"] = ai_used
        data["aiSourceMap"] = {"aiKeys": ai_keys, "fallbackGroups": fallback_groups}

        # --- 차트 생성 ---
        chart_paths = _build_charts(data, tmp_dir)

        # --- HTML 조립 (이벤트 무료 사주는 2장짜리 맛보기) ---
        if meta.get("teaser"):
            html = build_teaser_html(data, chart_paths, meta)
        else:
            html = build_report_html(data, chart_paths, meta)

        # --- 2-pass 렌더 (목차 페이지번호) ---
        render_info, _html_path = _render_two_pass(html, tmp_dir, output_path)

        # --- 검수 ---
        v = _validate_pdf(output_path)

        suggested = _sanitize_filename(f"{customer_name}_{report_type}_{report_year}") + ".pdf"

        print(json.dumps({
            "success": True,
            "path": output_path,
            "engine": render_info["engine"],
            "aiUsed": ai_used,
            "aiSourceMap": data["aiSourceMap"],
            "validation": v,
            "suggestedFilename": suggested,
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"success": False, "message": f"PDF 생성 실패: {e}"}, ensure_ascii=False))
        sys.exit(1)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()

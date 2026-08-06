# -*- coding: utf-8 -*-
"""
report_theme.py
===============
PDF 리포트 전체에 적용되는 디자인 시스템(섹션 6).
- 색상 토큰: 아이보리 배경 / 먹색 본문 / 인장 적색 강조 / 저채도 금색 보조 / 저채도 오행색
- 글꼴: 번들 폰트(@font-face) 고정. OS 기본 글꼴에 의존하지 않음.
  * 제목/장제목: Noto Serif KR (번들)
  * 본문/표/그래프: Noto Sans KR (번들)
  * 중국어용 CJK SC 가 한글에 적용되지 않도록 KR 서브셋만 사용.
- 페이지 공통요소: 상단 머리글(고객/리포트명), 하단 꼬리글(브랜드/주문번호/페이지번호)
- 표/카드가 페이지 중간에서 잘리지 않도록 break-inside: avoid.
- 빈 페이지를 만드는 min-height:250mm 구조 제거.
"""
import os
from pathlib import Path

FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")

# 저채도 오행 색상 (배경/그래프 공용)
OHENG_COLORS = {"목": "#5C7C56", "화": "#B0574B", "토": "#A98B5A", "금": "#8E9298", "수": "#4E6E90"}
OHENG_ORDER = ["목", "화", "토", "금", "수"]

# 디자인 토큰
TOKENS = {
    "ivory": "#F7F0E1",       # 따뜻한 아이보리 배경
    "ivory_deep": "#EFE6D2",  # 카드/플레이트
    "ink": "#2B2620",         # 먹색 본문
    "ink_soft": "#5A5148",    # 보조 텍스트
    "seal": "#A02B23",        # 인장 적색 강조
    "gold": "#B08A3E",        # 저채도 금색
    "gold_soft": "#CBB27C",   # 저채도 금색(선/보더)
    "line": "#D8C9A8",        # 표/구분선
}


def _uri(fname: str) -> str:
    return Path(os.path.join(FONTS_DIR, fname)).resolve().as_uri()


def font_face_css() -> str:
    return f"""
@font-face {{ font-family:'SerifKR'; font-weight:400; font-style:normal;
  src:url('{_uri("NotoSerifKR-Regular.otf")}') format('opentype'); }}
@font-face {{ font-family:'SerifKR'; font-weight:700; font-style:normal;
  src:url('{_uri("NotoSerifKR-Bold.otf")}') format('opentype'); }}
@font-face {{ font-family:'SansKR'; font-weight:400; font-style:normal;
  src:url('{_uri("NotoSansKR-Regular.otf")}') format('opentype'); }}
@font-face {{ font-family:'SansKR'; font-weight:700; font-style:normal;
  src:url('{_uri("NotoSansKR-Bold.otf")}') format('opentype'); }}
@font-face {{ font-family:'BookkMyungjo'; font-weight:400; font-style:normal;
  src:url('{_uri("BookkMyungjo_Light.ttf")}') format('truetype'); }}
"""


def get_css(header_text: str = "", footer_left: str = "") -> str:
    t = TOKENS
    # WeasyPrint 용 머리글/꼬리글은 @page margin-box + string()/counter() 로 처리.
    # Chromium 은 이 margin-box 를 무시하고 page.pdf 의 header/footer 템플릿을 쓴다.
    return font_face_css() + f"""
* {{ box-sizing: border-box; }}
html, body {{ margin:0; padding:0; }}
body {{
  font-family:'SansKR', sans-serif; color:{t['ink']};
  font-size:15.9pt; line-height:1.75; letter-spacing:0.01em;
  word-break:keep-all; -webkit-hyphens:none; hyphens:none;
  background:{t['ivory']};
}}

/* ---------- 페이지 규칙 ---------- */
@page {{
  size: A4;
  margin: 20mm 16mm 18mm 16mm;
  background: {t['ivory']};
  @top-center {{
    content: string(docheader);
    font-family:'SansKR'; font-size:8pt; color:{t['ink_soft']};
    letter-spacing:0.04em; padding-bottom:2mm;
    border-bottom:0.4pt solid {t['line']}; width:100%;
  }}
  @bottom-left  {{ content:"{footer_left}"; font-family:'SansKR'; font-size:7.5pt; color:{t['ink_soft']}; }}
  @bottom-center{{ content:"동네사주카페"; font-family:'SerifKR'; font-size:7.5pt; color:{t['gold']}; }}
  @bottom-right {{ content: counter(page) " / " counter(pages); font-family:'SansKR'; font-size:7.5pt; color:{t['ink_soft']}; }}
}}
/* 표지: 여백 없는 full bleed, 머리/꼬리글 제거 */
@page cover {{
  margin:0;
  @top-center {{ content:none; }}
  @bottom-left {{ content:none; }} @bottom-center {{ content:none; }} @bottom-right {{ content:none; }}
}}
.cover {{ page: cover; }}

/* 장 시작 페이지는 머리글 문자열만 갱신 */
body {{ string-set: docheader "{header_text}"; }}

/* ---------- 표지 (섹션 5) ---------- */
.cover {{
  position:relative; width:210mm; height:297mm; overflow:hidden;
  page-break-after:always; background:{t['ivory']};
}}
.cover .cover-bg {{
  position:absolute; inset:0; width:100%; height:100%;
  object-fit:cover; object-position:center top;
}}
.cover .gold-frame {{
  position:absolute; inset:6mm; border:1.2pt solid {t['gold_soft']};
  box-shadow: inset 0 0 0 2.5pt rgba(176,138,62,0.18); pointer-events:none;
}}
.cover .cartouche {{
  position:absolute; left:50%; transform:translateX(-50%);
  bottom:14mm; width:150mm; height:76mm; padding:0;
  display:flex; align-items:center; justify-content:center; text-align:center;
  /* 불투명 파치먼트 명판 — 자리표시 텍스트를 완전히 가리는 의도된 표지 요소 */
  background:#F5EEDD; border:0.8pt solid {t['gold_soft']}; border-radius:2.5mm;
  box-shadow:0 2mm 9mm rgba(60,45,20,0.16);
}}
.cover .cartouche-inner {{
  width:112mm; padding:5mm 4mm;
  border-top:0.8pt solid {t['gold_soft']}; border-bottom:0.8pt solid {t['gold_soft']};
}}
.cover .c-type {{ font-family:'SerifKR'; font-size:15.5pt; color:{t['seal']}; letter-spacing:0.14em; margin-bottom:5mm; font-weight:700; }}
.cover .c-name {{ font-family:'SerifKR'; font-size:34pt; font-weight:700; color:{t['ink']}; letter-spacing:0.12em; line-height:1.3; margin-bottom:4mm; text-shadow:0 1px 0 rgba(160,43,35,0.10); }}
.cover .c-name .nim {{ font-family:'SerifKR'; font-size:17pt; color:{t['seal']}; font-weight:700; letter-spacing:0.04em; }}
.cover .c-name .amp {{ font-size:24pt; color:{t['seal']}; vertical-align:middle; margin:0 6px; letter-spacing:0; }}
.cover .c-birth {{ font-family:'SansKR'; font-size:10.5pt; color:{t['ink_soft']}; letter-spacing:0.02em; line-height:1.9; }}
.cover .c-birth .cb-nm {{ color:{t['seal']}; font-weight:700; margin-right:3px; }}
.cover .c-year {{ font-family:'SerifKR'; font-size:12.5pt; color:{t['gold']}; letter-spacing:0.1em; margin-top:4mm; font-weight:700; }}
.cover .c-brand {{ display:none; }}

/* ---------- 장 제목 ---------- */
/* 기본적으로 장은 페이지를 강제로 넘기지 않고 자연스럽게 이어져 하단 여백을 줄인다.
   큰 '부(部)'가 시작될 때만 .newpage 로 새 페이지에서 시작한다. */
.chapter {{ page-break-before:auto; margin-top:9mm; }}
.chapter:first-of-type {{ margin-top:0; }}
.chapter.newpage {{ page-break-before:always; margin-top:0; }}
/* 장 구분 간지 페이지: 빈 페이지 중앙에 'N장 + 제목' */
.chapter-divider {{ page-break-before:always; page-break-after:always; height:235mm; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; }}
.cd-badge {{ background:{t['seal']}; color:#fff; font-family:'SerifKR'; font-weight:700; font-size:21pt; padding:4mm 13mm; border-radius:9mm; letter-spacing:0.08em; margin-bottom:13mm; }}
.cd-title {{ font-family:'SerifKR'; font-weight:700; font-size:34pt; color:{t['ink']}; letter-spacing:0.05em; }}
.chapter-head {{
  border-bottom:2pt solid {t['gold']}; padding-bottom:3.5mm; margin-bottom:5mm;
  break-after:avoid; page-break-after:avoid; break-inside:avoid;
}}
.chapter-num {{ font-family:'SerifKR'; font-size:13pt; color:{t['seal']}; letter-spacing:0.26em; font-weight:700; }}
.chapter-title {{ font-family:'SerifKR'; font-size:25pt; font-weight:700; color:{t['ink']}; margin-top:1.5mm; letter-spacing:0.02em; }}
.chapter-sub {{ font-family:'SansKR'; font-size:14.5pt; color:{t['ink_soft']}; margin-top:1.5mm; }}

.section-title {{
  font-family:'SerifKR'; font-size:18pt; font-weight:700; color:{t['seal']};
  margin:6mm 0 3mm; padding-left:3mm; border-left:3.5pt solid {t['gold']};
  break-after:avoid; page-break-after:avoid;
}}
.sub-title {{ font-family:'SansKR'; font-size:16.8pt; font-weight:700; color:{t['ink']}; margin:5mm 0 2mm; break-after:avoid; page-break-after:avoid; }}

p {{ margin:0 0 3mm; }}
.body-text {{ font-family:'BookkMyungjo','SerifKR',serif; font-size:21pt; text-align:left; line-height:1.95; letter-spacing:0.02em; word-break:keep-all; margin:0 0 4.5mm; }}
.callout > div {{ font-family:'BookkMyungjo','SerifKR',serif; }}
.lead {{ font-size:16.5pt; color:{t['ink']}; }}
.muted {{ color:{t['ink_soft']}; }}
strong, b {{ font-weight:700; }}

/* ---------- 카드 / 표 / 강조박스 (break-inside 보호) ---------- */
.card, .kv-table, table, .callout, .summary-grid, .pillars-card, .chart-wrap {{
  break-inside: avoid; page-break-inside: avoid;
}}
.card {{
  background:{t['ivory_deep']}; border:0.6pt solid {t['line']}; border-radius:3mm;
  padding:5mm 6mm; margin:4mm 0;
}}
.callout {{
  background:#FBF3E4; border:0.6pt solid {t['gold_soft']}; border-left:3.5pt solid {t['seal']};
  border-radius:2mm; padding:4.5mm 5.5mm; margin:4mm 0;
}}
.callout .callout-label {{ font-family:'SerifKR'; font-weight:700; color:{t['seal']}; font-size:14.5pt; margin-bottom:1.8mm; }}

table {{ border-collapse:collapse; width:100%; margin:4mm 0; }}
th, td {{ border:0.5pt solid {t['line']}; padding:2.8mm 2mm; font-size:13.5pt; text-align:center; line-height:1.5; }}
th {{ background:{t['ivory_deep']}; font-weight:700; color:{t['ink']}; letter-spacing:0.02em; }}
.pillars-card table td {{ font-size:18pt; font-weight:700; }}
.pillars-card .han {{ font-family:'SerifKR'; }}

/* 핵심요약 그리드 */
.summary-grid {{ display:flex; flex-wrap:wrap; gap:4mm; margin:5mm 0; }}
.summary-grid .cell {{
  flex:1 1 40%; min-width:40%; background:{t['ivory_deep']}; border:0.6pt solid {t['line']};
  border-radius:2.5mm; padding:4mm 4.5mm;
}}
.summary-grid .cell .lbl {{ font-size:11.5pt; color:{t['ink_soft']}; margin-bottom:1.2mm; letter-spacing:0.03em; }}
.summary-grid .cell .val {{ font-family:'SerifKR'; font-size:17pt; font-weight:700; color:{t['ink']}; }}

/* 오행 배지 */
.badge-row {{ display:flex; flex-wrap:wrap; gap:2mm; margin:3mm 0; }}
.badge {{ display:inline-block; padding:1.8mm 4.5mm; border-radius:3mm; font-size:13.5pt; font-weight:700; }}

/* 그래프 */
.chart-wrap {{ text-align:center; margin:5mm 0; }}
.chart-wrap img {{ max-width:100%; }}
.chart-cap {{ font-size:11.5pt; color:{t['ink_soft']}; margin-top:2mm; }}

/* 목차 (실제 페이지번호) */
.toc {{ page-break-before:always; }}
.body-text {{ orphans:2; widows:2; }}
.toc h1 {{ font-family:'SerifKR'; font-size:26pt; color:{t['ink']}; text-align:center; margin:0 0 9mm; font-weight:700; }}
.toc-part {{ font-family:'SerifKR'; font-weight:700; font-size:17.5pt; color:{t['seal']}; margin:6mm 0 2mm; }}
.toc-entry {{ display:flex; align-items:baseline; font-size:16.5pt; margin:3.4mm 0; }}
.toc-entry a {{ color:{t['ink']}; text-decoration:none; }}
.toc-entry .num {{ font-family:'SerifKR'; font-weight:700; color:{t['gold']}; min-width:12mm; }}
.toc-entry .t {{ font-family:'SansKR'; font-weight:700; color:{t['ink']}; }}
.toc-entry .leader {{ flex:1; border-bottom:0.4pt dotted {t['line']}; margin:0 2mm; transform:translateY(-1mm); }}
.toc-entry .pg {{ color:{t['ink_soft']}; font-size:12.5pt; }}
/* WeasyPrint: 목차 페이지번호 자동 채움 */
.toc-entry .pg::after {{ content: target-counter(attr(data-href), page); }}

/* 면책/각주 */
.footnote-box {{ margin-top:5mm; padding-top:2.5mm; border-top:0.5pt solid {t['line']}; }}
.footnote, .footnote-item {{ font-size:12pt; color:{t['ink_soft']}; margin:1.4mm 0; line-height:1.6; }}
.disclaimer {{ font-size:13pt; color:{t['ink_soft']}; line-height:1.7; }}

/* 두 사람 비교(궁합) */
.compare {{ display:flex; gap:4mm; }}
.compare > div {{ flex:1; }}
.avoid-break {{ break-inside:avoid; page-break-inside:avoid; }}
"""

# -*- coding: utf-8 -*-
"""
report_html.py
==============
사주 계산 JSON + 검증된 AI 콘텐츠 JSON -> HTML 리포트 템플릿 (섹션 6·7).

- 표지(섹션 5): 배경 이미지 full-bleed + 고객정보 동적 텍스트 레이어.
- 28단 콘텐츠 구성(섹션 7). 각 페이지에 의미 있는 내용만. 빈 페이지/반복 금지.
- 목차 페이지번호: 본문 챕터마다 보이지 않는 마커(CHMARK..)를 심고, make_pdf.py가
  1차 렌더 후 실제 페이지 번호를 계산해 {{PG_..}} 토큰을 치환한다(엔진 무관, 정확).
- 궁합 리포트는 추가 섹션 포함.
"""
import html as _html
import re as _re
from report_theme import get_css, OHENG_COLORS, OHENG_ORDER, TOKENS
from glossary import GLOSSARY, UNSEONG_DESC, build_footnote_html

# 어려운 한자어를 최대한 덜어 초보자도 읽기 쉽게 만든다.
# (한글 AC00-D7A3 은 포함하지 않도록 CJK 한자 범위만 명시적으로 지정)
_HANJA = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"  # CJK 한자 범위(한글 U+AC00~U+D7A3 미포함)
_PAREN_HANJA = _re.compile("\\s*[\\(（][" + _HANJA + "·\\s]+[\\)）]")
_BARE_HANJA = _re.compile("[" + _HANJA + "]+")


def plain(text):
    """'일간(日干)' -> '일간', '상생(相生)' -> '상생' 처럼 괄호 속·단독 한자를 제거."""
    if text is None:
        return text
    s = str(text)
    s = _PAREN_HANJA.sub("", s)
    s = _BARE_HANJA.sub("", s)
    s = _re.sub(r"\(\s*\)", "", s)
    s = _re.sub(r"[ \t]{2,}", " ", s)
    s = _re.sub(r"\s+([,.·})\]])", r"\1", s)
    return s.strip()


# 어려운 사주용어 → 쉬운 말 자동 치환(본문). 앞 글자가 한글이면 건너뛰어 '개인성향' 같은 오치환을 막는다.
_TERM_MAP = [
    ("역마살", "이동·변화가 많은 기운"), ("도화살", "사람을 끄는 매력의 기운"),
    ("화개살", "예술·정신적인 기운"), ("백호살", "기세가 강한 기운"),
    ("괴강살", "강단 있는 기운"), ("양인살", "강하고 날카로운 기운"),
    ("천을귀인", "큰 도움을 주는 귀인"), ("문창귀인", "공부·시험에 좋은 기운"),
    ("지장간", "속에 숨어 있는 기운"),
    ("편재", "활동적으로 버는 재물 기운"), ("정재", "성실히 모으는 재물 기운"),
    ("겁재", "경쟁하고 나누는 기운"), ("비견", "줏대가 뚜렷한 기운"),
    ("식신", "베풀고 표현하는 기운"), ("상관", "재주와 끼가 많은 기운"),
    ("편관", "강한 추진력의 기운"), ("정관", "책임감과 명예의 기운"),
    ("편인", "직관과 아이디어의 기운"), ("정인", "배우고 도움받는 기운"),
    ("인성", "배우고 도움받는 기운"), ("식상", "표현하고 활동하는 기운"),
    ("관성", "책임·직장과 관련된 기운"), ("재성", "재물과 관련된 기운"),
    ("비겁", "자기 힘·경쟁의 기운"), ("지살", "자주 옮겨다니게 되는 기운"),
    ("용신", "나에게 가장 도움이 되는 기운"), ("희신", "나를 돕는 기운"),
    ("기신", "조심하면 좋은 기운"), ("구신", "방해가 되기 쉬운 기운"),
    ("격국", "타고난 성향의 큰 틀"),
]


# 딱딱한 '~습니다'체를 부드러운 '~해요/~어요'체로. (자주 쓰는 어미만 안전하게 변환)
_SOFTEN = [
    ("있었습니다", "있었어요"), ("없었습니다", "없었어요"),
    ("있습니다", "있어요"), ("없습니다", "없어요"),
    ("좋습니다", "좋아요"), ("많습니다", "많아요"), ("같습니다", "같아요"),
    ("높습니다", "높아요"), ("낮습니다", "낮아요"), ("적습니다", "적어요"),
    ("깊습니다", "깊어요"), ("넓습니다", "넓어요"), ("강합니다", "강해요"), ("약합니다", "약해요"),
    ("쉽습니다", "쉬워요"), ("어렵습니다", "어려워요"),
    ("됐습니다", "됐어요"), ("됩니다", "돼요"),
    ("했습니다", "했어요"), ("합니다", "해요"),
    ("이었습니다", "이었어요"), ("였습니다", "였어요"), ("입니다", "이에요"),
    ("겠습니다", "겠어요"),
    ("드립니다", "드려요"), ("바랍니다", "바라요"),
    ("집니다", "져요"), ("납니다", "나요"),
    ("갑니다", "가요"), ("옵니다", "와요"), ("줍니다", "줘요"),
]


def _soften(text):
    if not text:
        return text
    s = str(text)
    for a, b in _SOFTEN:
        s = s.replace(a, b)
    return s


def _simplify(text):
    """본문에서 어려운 사주 전문용어를 일반인이 이해할 수 있는 말로 바꾼다."""
    if not text:
        return text
    s = str(text)
    for term, repl in _TERM_MAP:
        s = _re.sub(r"(?<![가-힣])" + term, repl, s)
    # 치환된 문구 뒤의 조사를 자연스럽게 보정 (받침 있는 말 뒤 과/을/은/이)
    for base in ("기운", "귀인", "틀"):
        s = (s.replace(base + "와", base + "과")
               .replace(base + "를", base + "을")
               .replace(base + "는", base + "은")
               .replace(base + "가 ", base + "이 "))
    # ㄴ받침(기운/귀인)만 '로'→'으로', ㄹ받침(틀)은 '으로'→'로'
    for base in ("기운", "귀인"):
        s = s.replace(base + "로 ", base + "으로 ")
    s = s.replace("틀으로", "틀로")
    return s


def esc(s):
    return _html.escape(str(s)) if s is not None else ""


# 오행별 개운 요소 (30/90일 가이드·보완법에서 사용)
OHENG_REMEDY = {
    "목": {"color": "초록·청색 계열", "dir": "동쪽", "food": "채소·신맛 음식", "act": "숲·공원 산책과 독서"},
    "화": {"color": "붉은·자주 계열", "dir": "남쪽", "food": "쓴맛 음식·따뜻한 차", "act": "햇볕 쬐기와 활발한 사교"},
    "토": {"color": "노란·갈색 계열", "dir": "중앙", "food": "단맛·곡물류", "act": "규칙적인 생활과 정리정돈"},
    "금": {"color": "흰색·금속색 계열", "dir": "서쪽", "food": "매운맛·견과류", "act": "정돈된 공간과 악기·운동"},
    "수": {"color": "검정·남색 계열", "dir": "북쪽", "food": "짠맛·수분 많은 음식", "act": "충분한 휴식과 명상"},
}


# 천간(한글) -> 오행
CHEONGAN_OHENG = {"갑": "목", "을": "목", "병": "화", "정": "화", "무": "토",
                  "기": "토", "경": "금", "신": "금", "임": "수", "계": "수"}


def fortune_score(oheng, yongsin):
    """용신 기준으로 어떤 오행 시기의 '운세 지수'(0~100 근사)를 매긴다."""
    if not oheng:
        return 60
    if oheng == yongsin.get("yongsin"):
        return 88
    if oheng == yongsin.get("huisin"):
        return 78
    if oheng == yongsin.get("hansin"):
        return 62
    if oheng == yongsin.get("gusin"):
        return 46
    if oheng == yongsin.get("gisin"):
        return 36
    return 60


def compute_daeun_scores(data):
    daeun = data.get("daeun", {}) or {}
    yongsin = data.get("yongsin", {}) or {}
    ages = daeun.get("startAges", []) or []
    pillars = daeun.get("pillars", []) or []
    ohengs = [CHEONGAN_OHENG.get(p[0]) if p else None for p in pillars]
    scores = [fortune_score(o, yongsin) for o in ohengs]
    # 현재 대운 index
    b = data.get("birth", {}) or {}
    report_year = int((data.get("meta") or {}).get("reportYear") or 2026)
    cur_age = report_year - int(b.get("year", report_year))
    cur_idx = -1
    for i, a in enumerate(ages):
        if cur_age >= a:
            cur_idx = i
    return {"ages": ages, "pillars": pillars, "ohengs": ohengs, "scores": scores,
            "cur_idx": cur_idx, "cur_age": cur_age}


def compute_monthly_scores(data):
    yongsin = data.get("yongsin", {}) or {}
    wolun = data.get("wolun", []) or []
    labels = [f"{w['month']}월" for w in wolun]
    scores = [fortune_score(w.get("oheng"), yongsin) for w in wolun]
    return {"labels": labels, "scores": scores}


def compute_radar(data):
    """5대 운세(재물·직업·연애·건강·귀인) 종합 지수(데이터 기반 근사)."""
    sip = " ".join((data.get("sipseong", {}) or {}).values())
    sinsal = data.get("sinsal", {}) or {}
    oheng = data.get("ohengDistribution", {}) or {}
    vals = list(oheng.values())
    spread = (max(vals) - min(vals)) if vals else 4

    def has(*names):
        return any(nm in sip for nm in names)

    def clamp(x):
        return max(42, min(93, int(x)))

    jaemul = clamp(74 if has("정재", "편재") else 58)
    jikeop = clamp(74 if has("정관", "편관") else 58)
    yeonae = clamp(70 if has("정재", "편재", "정관", "편관") else 56)
    health = clamp(84 - spread * 6)
    gwiin = clamp(76 if (has("정인", "편인") or "천을귀인" in sinsal) else 58)
    return {"categories": ["재물", "직업", "연애", "건강", "귀인"],
            "scores": [jaemul, jikeop, yeonae, health, gwiin]}


def _txt_factory(data):
    ai_extra = data.get("aiExtra", {}) or {}
    interp = data.get("interpretation", {}) or {}

    def txt(key, fallback=""):
        return (ai_extra.get(key) or interp.get(key) or fallback)
    return txt


class ChapterRegistry:
    """챕터를 등록하면서 목차(part/title/pgtoken)와 본문을 동시에 구성.
    enabled=False 인 동안의 part/mark 는 무시되어(상품별 섹션 선택), 포함된 '장'만
    1장·2장… 순서로 자동 재번호된다."""
    def __init__(self):
        self.parts = []          # [[chapter_no|None, part_title, [(title, token)...]]]
        self._cur_part = None
        self.counter = 0
        self.chapno = 0          # 순차 장 번호(포함된 PART만 증가)
        self.enabled = True

    def part(self, title, numbered=False):
        if not self.enabled:
            self._cur_part = None
            return None
        no = None
        if numbered:
            self.chapno += 1
            no = self.chapno
        self._cur_part = [no, title, []]
        self.parts.append(self._cur_part)
        return no

    def mark(self, title):
        """새 챕터 시작 마커 HTML 반환 + 목차에 등록."""
        if not self.enabled:
            return ""
        self.counter += 1
        token = f"CH{self.counter:02d}"
        if self._cur_part is None:
            self.part("")
        self._cur_part[2].append((title, token))
        # 보이지 않는 페이지 마커(화면엔 안 보이지만 텍스트 추출은 됨: 배경색과 동일한 아이보리)
        return f"<span class='pgmark' style='font-size:5pt;color:#F7F0E1;line-height:0'>{token}MARK</span>"

    def toc_html(self):
        # 목차는 '1장 한 줄' 형태로 간결하게. (PART 헤더+챕터 제목 중복 제거)
        rows = ["<div class='toc chapter'><h1>차 례</h1>"]
        for no, part_title, entries in self.parts:
            if not entries:
                continue
            pt = plain(part_title or "").strip()
            if no is not None:
                num = f"{no}장"
                title = pt or plain(entries[0][0]).strip()
            elif "부록" in pt:
                num = "부록"
                title = "용어 설명과 안내"
            else:
                # 표지·이용안내·핵심요약 등 번호 없는 페이지는 목차에서 생략
                continue
            token = entries[0][1]
            rows.append(
                f"<div class='toc-entry'><span class='num'>{esc(num)}</span>"
                f"<span class='t'>{esc(title)}</span>"
                f"<span class='leader'></span>"
                f"<span class='pg'>{{{{PG_{token}}}}}</span></div>"
            )
        rows.append("</div>")
        return "".join(rows)


def _p(text):
    # 문서 형식 톤(~합니다)을 유지하고, 어려운 용어만 쉬운 말로 바꾼다. (구어체 어미 변환은 하지 않음)
    s = esc(_simplify(plain(text)))
    # 본문에 의도적으로 넣은 강조 태그(<b>)만 다시 살린다 (esc 로 글자가 되어 노출되는 버그 방지)
    s = s.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    return f"<p class='body-text'>{s}</p>"


def _chapter_head(reg, num_label, title, sub="", new_page=False):
    mark = reg.mark(title)
    sub_html = f"<div class='chapter-sub'>{esc(plain(sub))}</div>" if sub else ""
    cls = "chapter newpage" if new_page else "chapter"
    # PART 챕터 앞에 '장 구분 간지 페이지'(빈 페이지 중앙에 'N장 + 제목')를 넣는다.
    divider = ""
    m = _re.match(r"PART\s*(\d+)", num_label or "")
    if m and new_page:
        divider = (f"<div class='chapter-divider'>"
                   f"<div class='cd-badge'>{int(m.group(1))}장</div>"
                   f"<div class='cd-title'>{esc(plain(title))}</div></div>")
    return (f"{divider}<div class='{cls}'>{mark}"
            f"<div class='chapter-head'><div class='chapter-num'>{esc(num_label)}</div>"
            f"<div class='chapter-title'>{esc(plain(title))}</div>{sub_html}</div>")


def _chapter_head_no(reg, no, title, sub="", new_page=True):
    """상품별 순차 장 번호(no)로 '장 구분 페이지 + 챕터 머리글'을 만든다."""
    mark = reg.mark(title)
    sub_html = f"<div class='chapter-sub'>{esc(plain(sub))}</div>" if sub else ""
    cls = "chapter newpage" if new_page else "chapter"
    divider = ""
    if new_page:
        divider = (f"<div class='chapter-divider'>"
                   f"<div class='cd-badge'>{no}장</div>"
                   f"<div class='cd-title'>{esc(plain(title))}</div></div>")
    return (f"{divider}<div class='{cls}'>{mark}"
            f"<div class='chapter-head'><div class='chapter-num'>{no}장</div>"
            f"<div class='chapter-title'>{esc(plain(title))}</div>{sub_html}</div>")


# 상품명 -> 포함할 본문 모듈(None 이면 프리미엄/궁합처럼 전체 수록)
def _product_modules(name):
    n = _re.sub(r"[\s·・.,]", "", str(name or ""))
    TABLE = {
        "나의사주팔자": {"P1", "P2", "P9", "P10"},        # 종합 요약판(≤40p)
        "재물운": {"P1", "P4"},                            # 단일 주제(≤20p)
        "건강운": {"P1", "P6"},
        "부부가족인연운": {"P1", "P3"},
        "인간관계직장운": {"P1", "P7", "P5"},
        "명예운": {"P1", "P5"},
    }
    for key, mods in TABLE.items():
        if n == key or n.startswith(key):
            return mods
    return None  # 프리미엄 사주풀이 · 궁합사주 · 이벤트 = 전체


class _FilteredBody(list):
    """현재 섹션(cur)이 선택된 모듈에 없으면 append 를 무시하는 본문 리스트."""
    cur = None
    modules = None  # None 이면 전체 수록
    def append(self, x):
        if self.modules is not None and self.cur is not None and self.cur not in self.modules:
            return
        super().append(x)


def _dedup_document(html):
    """공용 fallback 문구 재사용으로 생기는 '동일 문단 중복' 및 빈 문단·고아 소제목을 제거."""
    seen = set()

    def _repl(m):
        key = _re.sub(r"\s+", " ", m.group(1)).strip()
        if not key:
            return ""            # 빈 문단 제거
        if key in seen:
            return ""            # 중복 문단 제거(첫 번째만 유지)
        seen.add(key)
        return m.group(0)

    html = _re.sub(r"<p class='body-text'>(.*?)</p>", _repl, html, flags=_re.S)
    # 문단이 제거돼 남은 '고아 소제목'(뒤에 소제목/장이 바로 오는 경우) 정리
    html = _re.sub(r"<div class='sub-title'>[^<]*</div>\s*(?=<div class='sub-title'>)", "", html)
    html = _re.sub(r"<div class='sub-title'>[^<]*</div>\s*(?=<div class='chapter)", "", html)
    return html


def _section_block(title, body, footnote=True):
    # 긴 해설은 페이지 경계에서 자연스럽게 나뉘어 하단 여백을 채우도록 통짜 avoid-break 를 쓰지 않는다.
    # (제목은 CSS 의 break-after:avoid 로 첫 문장과 함께 붙어 다닌다.)
    body = plain(body)
    fn = plain(build_footnote_html(body)) if footnote else ""
    return (f"<div class='section-title'>{esc(title)}</div>{_p(body)}{fn}")


def _birth_line_str(b, data, calendar_type, time_str):
    """표지에 표시할 생년월일 문구.
    음력 입력이면 '음력 원본 + (양력 변환) 기준'을 함께 보여줘, 날짜가 바뀐 게 아니라
    사주 계산을 위해 양력으로 환산했음을 분명히 한다."""
    lunar = (data or {}).get("birthLunar")
    if lunar:
        leap = "(윤달)" if lunar.get("isLeap") else ""
        return (f"음력 {lunar.get('year','')}년 {lunar.get('month','')}월 {lunar.get('day','')}일{leap}"
                f" · 양력 {b.get('year','')}.{b.get('month','')}.{b.get('day','')} 환산 · {time_str}")
    return f"{b.get('year','')}년 {b.get('month','')}월 {b.get('day','')}일 ({calendar_type}) · {time_str}"


def _life_stage(age):
    """나이대를 20~90대로 구분해, 결과지 문구를 그 시기의 삶에 맞게 조정한다."""
    a = int(age or 40)
    if a < 30:   return {"key": "20", "band": "20대", "senior": False}
    if a < 40:   return {"key": "30", "band": "30대", "senior": False}
    if a < 50:   return {"key": "40", "band": "40대", "senior": False}
    if a < 60:   return {"key": "50", "band": "50대", "senior": False}
    if a < 70:   return {"key": "60", "band": "60대", "senior": True}
    if a < 80:   return {"key": "70", "band": "70대", "senior": True}
    return {"key": "80", "band": "80대 이상", "senior": True}


def build_report_html(data: dict, chart_paths: dict, meta: dict) -> str:
    txt = _txt_factory(data)
    b = data.get("birth", {})
    pillars = data.get("pillars", {})
    sipseong = data.get("sipseong", {})
    unseong = data.get("unseong12", {})
    daeun = data.get("daeun", {})
    seun = data.get("seun", {})
    sinsal = data.get("sinsal", {}) or {}
    yongsin = data.get("yongsin", {}) or {}
    gyeokguk = data.get("gyeokguk", {}) or {}
    wolun = data.get("wolun", []) or []
    gunghap = data.get("gunghap")
    oheng_dist = data.get("ohengDistribution", {}) or {}
    most_oheng = data.get("ohengMostCommon", "")
    missing = data.get("ohengMissing", []) or []
    interp = data.get("interpretation", {}) or {}

    report_year = int(meta.get("reportYear") or 2026)
    customer_name = meta.get("customerName") or data.get("name") or "의뢰인"
    report_type = meta.get("reportType") or "종합 사주 분석"
    order_id = meta.get("orderId") or ""
    brand = meta.get("brand") or "동네사주카페"
    calendar_type = meta.get("calendarType") or "양력"
    time_unknown = bool(meta.get("birthTimeUnknown"))
    cover_img = meta.get("coverImageUri") or ""

    # ---- 오행 균형 라벨 ----
    vals = list(oheng_dist.values())
    spread = (max(vals) - min(vals)) if vals else 0
    balance = "고른 편" if spread <= 1 else ("다소 치우침" if spread <= 3 else "편중이 뚜렷함")

    # ---- 현재 대운 계산 (기준연도 기준) ----
    start_ages = daeun.get("startAges", []) or []
    daeun_pillars = daeun.get("pillars", []) or []
    cur_age = report_year - int(b.get("year", report_year))
    cur_idx = -1
    for i, a in enumerate(start_ages):
        if cur_age >= a:
            cur_idx = i
    cur_daeun_pillar = daeun_pillars[cur_idx] if 0 <= cur_idx < len(daeun_pillars) else "-"
    cur_daeun_age = start_ages[cur_idx] if 0 <= cur_idx < len(start_ages) else None

    # ---- 나이대 프레이밍 (20~90대) : 과거형·부적절 문구 방지 + 그 시기 삶에 맞춤 ----
    _stage = _life_stage(cur_age)
    _sk = _stage["key"]           # "20"~"80"
    is_senior = _stage["senior"]  # 60대 이상
    _is_couple = _sk in ("50", "60", "70", "80")   # 배우자/가정 중심(미혼보다 기혼 가능성)

    # ---- 주의/기회 시기(월) ----
    y = yongsin
    good_set = {y.get("yongsin"), y.get("huisin")}
    bad_set = {y.get("gisin"), y.get("gusin")}
    opp_months = [w for w in wolun if w.get("oheng") in good_set]
    caution_months = [w for w in wolun if w.get("oheng") in bad_set]

    # ---- 생년월일 표기 ----
    if time_unknown:
        time_str = "출생시간 미상"
    else:
        time_str = f"{int(b.get('hour', 0)):02d}시 {int(b.get('minute', 0)):02d}분"
    birth_line = _birth_line_str(b, data, calendar_type, time_str)

    reg = ChapterRegistry()
    # ---- 상품별 수록 모듈 선택 (None = 전체) ----
    MODULES = _product_modules(meta.get("product"))
    body_parts = _FilteredBody()
    body_parts.modules = MODULES
    # 단일 주제 상품(재물/건강/부부/인간관계/명예)은 1장을 '기본요약(명식·오행)'만 담아 20p 이내로.
    # (프리미엄=전체, 나의 사주팔자=P2 포함 → 성격/강점 등 전체 1장 수록)
    p1_lite = (MODULES is not None) and ("P2" not in MODULES)
    compact = (MODULES is not None)   # 프리미엄/궁합 외(단품·요약판)은 분량을 줄여 페이지 상한을 지킨다

    def want(key):
        return MODULES is None or key in MODULES

    def chapter(key, title, sub="", new_page=True):
        """PART 챕터 시작: 선택된 모듈이면 순차 장 번호로 머리글을 넣고, 아니면 건너뛴다."""
        body_parts.cur = key
        on = want(key)
        reg.enabled = on
        if not on:
            return
        no = reg.part(plain(title), numbered=True)
        body_parts.append(_chapter_head_no(reg, no, title, sub, new_page))

    def _reset_always_on():
        """번호 없는 공용 섹션(맺음말·부록·궁합) 앞에서 필터/레지스트리를 원상 복구."""
        body_parts.cur = None
        reg.enabled = True

    # ===================== 1. 표지 =====================
    cover = f"""
    <div class="cover">
      {'<img class="cover-bg" src="'+cover_img+'"/>' if cover_img else ''}
      <div class="gold-frame"></div>
      <div class="c-brand">易 {esc(brand)}</div>
      <div class="cartouche"><div class="cartouche-inner">
        <div class="c-type">{esc(report_type)}</div>
        <div class="c-name">{esc(customer_name)} <span class="nim">님</span></div>
        <div class="c-birth">{esc(birth_line)}</div>
        <div class="c-year">{report_year} {esc('신년운세' if '신년' in report_type else '운세 리포트')}</div>
      </div></div>
    </div>
    """
    body_parts.append(cover)

    # ===================== 2. 이용 안내 및 면책 =====================
    reg.part("")
    body_parts.append(_chapter_head(reg, "안내", "리포트 이용 안내"))
    body_parts.append(_p(
        f"이 리포트는 {customer_name} 님이 태어난 연·월·일·시를 바탕으로 사주를 분석한 자료입니다. "
        f"내 기본 성향부터 오행 균형, 재물·직장·사랑·건강 같은 분야별 운세, {report_year}년 한 해와 달마다의 흐름, "
        f"그리고 바로 실천할 수 있는 조언까지 순서대로 담았습니다."))
    body_parts.append(_p(
        "사주는 태어난 때에 담긴 기운을 읽어 나를 더 잘 이해하도록 돕는 도구입니다. "
        "여기 적힌 내용은 정해진 운명이 아니라, 내 장점을 살리고 부족한 부분을 채워 더 나은 선택을 하는 데 쓰는 참고 자료로 "
        "가볍게 받아들이시면 좋습니다. 어려운 낱말은 문장 아래와 마지막 용어 설명에서 쉽게 풀어 두었습니다."))
    body_parts.append(
        "<div class='callout'><div class='callout-label'>안내</div>"
        "<div class='disclaimer'>이 자료는 참고용 해석이며, 병원 진료나 법률·돈 문제처럼 전문가의 판단이 필요한 일을 대신하지 않습니다. "
        "해석 방식에 따라 세부 내용은 조금씩 달라질 수 있습니다.</div></div>")

    # ===================== 3. 목차 (자리표시 -> make_pdf가 치환) =====================
    body_parts.append("{{TOC}}")

    # ===================== 핵심 요약 =====================
    # 단일 주제 상품은 1장(기본요약)이 곧 요약이므로, 5대 운세 종합요약 페이지는 생략한다.
    if not p1_lite:
        reg.part("한눈에 보는 핵심")
        body_parts.append(_chapter_head(reg, "요약", "한눈에 보는 핵심 운세 요약",
                                        f"{customer_name} 님 사주의 큰 그림을 한 장에 담았습니다.", new_page=True))
        summary_cells = [
            ("나를 상징하는 글자", esc(data.get("ilgan", "-"))),
            ("타고난 성향의 틀", esc(plain(gyeokguk.get("name", "-")))),
            ("나에게 필요한 기운", esc(yongsin.get("yongsin", "-"))),
            ("가장 강한 오행", esc(most_oheng or "-")),
            ("부족한 오행", esc(", ".join(missing) if missing else "없음")),
            ("오행 균형도", esc(balance)),
        ]
        if gunghap:
            summary_cells.append(("궁합 점수", f"{esc(gunghap.get('score','-'))}점 ({esc(gunghap.get('grade','-'))}급)"))
        cells_html = "".join(
            f"<div class='cell'><div class='lbl'>{lbl}</div><div class='val'>{val}</div></div>"
            for lbl, val in summary_cells)
        body_parts.append(f"<div class='summary-grid'>{cells_html}</div>")
        if chart_paths.get("radar"):
            body_parts.append(f"<div class='chart-wrap'><img src='{chart_paths['radar']}' style='width:74%'/>"
                              "<div class='chart-cap'>재물·직업·연애·건강·귀인 — 5대 운세 종합 지수</div></div>")
        body_parts.append(_section_block("총평 한 문장",
            txt("사주원국해설", txt("ohengBasic",
                f"{customer_name} 님은 {plain(gyeokguk.get('name',''))}의 틀 위에서 {most_oheng} 기운이 두드러지는 사주입니다."))))

    # ---- 공용 파생 문구(시기 등) ----
    _ds = compute_daeun_scores(data)
    _best_i = (max(range(len(_ds["scores"])), key=lambda k: _ds["scores"][k]) if _ds["scores"] else -1)
    _worst_i = (min(range(len(_ds["scores"])), key=lambda k: _ds["scores"][k]) if _ds["scores"] else -1)
    _op = ", ".join(f"{w['month']}월" for w in opp_months[:4]) if opp_months else "기운이 오르는 달"
    _ca = ", ".join(f"{w['month']}월" for w in caution_months[:4]) if caution_months else "변화가 큰 달"
    _ci = _ds["cur_idx"]
    _next_change = (_ds["ages"][_ci + 1] if (_ci is not None and 0 <= _ci and _ci + 1 < len(_ds["ages"])) else None)

    def _grid2(l1, v1, l2, v2, hl=True):
        c1 = f"color:{TOKENS['seal']}" if hl else ""
        return ("<div class='summary-grid'>"
                f"<div class='cell'><div class='lbl'>{l1}</div><div class='val' style='{c1}'>{esc(v1)}</div></div>"
                f"<div class='cell'><div class='lbl'>{l2}</div><div class='val'>{esc(v2)}</div></div>"
                "</div>")

    def _pillars_table():
        return (
            "<div class='pillars-card card'><table>"
            "<tr><th>구분</th><th>시주</th><th>일주</th><th>월주</th><th>연주</th></tr>"
            f"<tr><td>천간</td><td class='han'>{esc(pillars.get('시주',['',''])[0])}</td><td class='han'>{esc(pillars.get('일주',['',''])[0])}</td><td class='han'>{esc(pillars.get('월주',['',''])[0])}</td><td class='han'>{esc(pillars.get('연주',['',''])[0])}</td></tr>"
            f"<tr><td>지지</td><td class='han'>{esc(pillars.get('시주',['',''])[1])}</td><td class='han'>{esc(pillars.get('일주',['',''])[1])}</td><td class='han'>{esc(pillars.get('월주',['',''])[1])}</td><td class='han'>{esc(pillars.get('연주',['',''])[1])}</td></tr>"
            "</table></div>")

    def _sub(t):
        body_parts.append(f"<div class='sub-title'>{esc(t)}</div>")

    # ===================== PART 1 =====================
    chapter("P1", "나의 사주팔자 기본 분석",
            "내 사주의 구성과 타고난 성격·기질을 살펴봅니다.")
    _sub("사주 원국과 음양오행 구성")
    body_parts.append(_pillars_table())
    body_parts.append(f"<p class='body-text'>나를 상징하는 글자는 <b>{esc(data.get('ilgan',''))}</b> 입니다. "
                      "아래는 내 사주에 담긴 다섯 기운(오행)의 분포입니다.</p>")
    badges = "".join(
        f"<span class='badge' style='background:{OHENG_COLORS.get(k,'#eee')}22;color:{OHENG_COLORS.get(k,'#333')};border:0.6pt solid {OHENG_COLORS.get(k,'#ccc')}'>{esc(k)} {v}개</span>"
        for k, v in oheng_dist.items())
    body_parts.append(f"<div class='badge-row'>{badges}</div>")
    body_parts.append(
        "<div class='card'><b>오행(五行)이란?</b> 세상의 기운을 "
        "<b>목(木·나무)·화(火·불)·토(土·흙)·금(金·쇠)·수(水·물)</b> 다섯 가지로 나눈 것으로, "
        "내 사주에 이 기운들이 얼마나 담겨 있는지가 성격과 운의 바탕이 됩니다.<br><br>"
        "· <b>상생(相生)</b> — 서로 <b>도와주는</b> 관계예요. 목→화→토→금→수→목 순서로 앞의 기운이 뒤의 기운을 살려줍니다. "
        "(그림의 <b>파란 화살표</b>)<br>"
        "· <b>상극(相剋)</b> — 서로 <b>억누르는</b> 관계예요. 한쪽이 다른 쪽을 눌러 균형을 잡아줍니다. "
        "(그림의 <b>빨간 화살표</b>)<br><br>"
        "상생이 잘 돌면 기운이 순조롭고, 상극이 지나치면 긴장·마찰이 생기기 쉬워요. "
        "그래서 <b>부족한 기운을 채우고 넘치는 기운을 다스려 균형</b>을 맞추는 것이 핵심입니다.</div>")
    _strong = most_oheng or "-"
    _missing_str = ", ".join(missing) if missing else "없음"
    if chart_paths.get('oheng_bar'):
        body_parts.append(
            "<div class='avoid-break' style='margin:4mm 0 2mm;'>"
            f"<div class='chart-wrap' style='margin:2mm 0;'><img src='{chart_paths['oheng_bar']}' style='width:90%'/></div>"
            f"<div class='sub-title' style='text-align:center;border:none;padding:0;color:#8B2E2E;'>■ 오행 개수 분포 — 보는 법</div>"
            f"<p class='body-text'>이 막대그래프는 내 사주 여덟 글자를 목·화·토·금·수 다섯 기운으로 나눠 각각 몇 개인지 센 것입니다. 막대가 높을수록 그 기운이 많다는 뜻이에요. 특정 기운이 유독 높으면 그 성향이 강하게 나타나고, 0개이면 그 기운이 부족합니다. {customer_name} 님은 '{_strong}' 기운이 가장 많고, 부족한 기운은 '{_missing_str}' 입니다. 많은 기운은 장점으로 살리고, 부족한 기운은 생활 속에서 채워 균형을 맞추는 것이 좋습니다.</p>"
            "</div>")
    if (not p1_lite) and chart_paths.get('oheng_donut'):
        body_parts.append(
            "<div class='avoid-break' style='margin:4mm 0 2mm;'>"
            f"<div class='chart-wrap' style='margin:2mm 0;'><img src='{chart_paths['oheng_donut']}' style='width:72%'/></div>"
            f"<div class='sub-title' style='text-align:center;border:none;padding:0;color:#8B2E2E;'>■ 오행 비율 — 보는 법</div>"
            f"<p class='body-text'>이 도넛 그래프는 다섯 기운이 전체에서 차지하는 비율을 %로 보여줍니다. 한 조각이 유독 크면 그 기운으로 치우쳐 있다는 뜻이고, 조각들이 고르게 나뉘면 균형 잡힌 사주입니다. 치우친 기운은 강한 개성이 되지만 과하면 약점이 되기도 하므로, 비어 있는 쪽을 채워 균형을 맞추면 삶이 한결 수월해집니다.</p>"
            "</div>")
    if chart_paths.get('oheng_pentagon'):
        body_parts.append(
            "<div class='avoid-break' style='margin:4mm 0 2mm;'>"
            f"<div class='chart-wrap' style='margin:2mm 0;'><img src='{chart_paths['oheng_pentagon']}' style='width:78%'/></div>"
            f"<div class='sub-title' style='text-align:center;border:none;padding:0;color:#8B2E2E;'>■ 오행 상생 순환 — 보는 법</div>"
            f"<p class='body-text'>이 오각형은 다섯 기운이 서로 낳아주며 이어지는 순서(목→화→토→금→수→목)를 원으로 그린 것입니다. 화살표는 '상생', 즉 앞의 기운이 뒤의 기운을 도와주는 흐름이에요. 각 원 안의 숫자는 내 사주가 가진 그 기운의 개수입니다. 숫자가 많은 자리는 힘이 넘치고, 0인 자리는 흐름이 끊기기 쉬운 곳입니다. 부족한 기운을 채우면 이 순환이 매끄럽게 돌아, 운의 흐름도 함께 좋아집니다.</p>"
            "</div>")
    body_parts.append(_p(txt("p1_구성", txt("사주원국해설", txt("ohengBasic")))))
    # ---- 강한/부족한 기운(오행 강약)은 기본요약에도 포함 ----
    _sub("나에게 부족하거나 강한 기운")
    body_parts.append(_grid2("가장 강한 기운", most_oheng or "-", "부족한 기운", ", ".join(missing) if missing else "없음"))
    body_parts.append(_p(txt("p1_강약", txt("오행해설",
        f"{customer_name} 님은 {most_oheng} 기운이 강하고 {', '.join(missing) if missing else '특정 기운이 부족하지 않은'} 편입니다. 강한 기운은 살리고 부족한 기운은 채우면 좋습니다."))))
    # ---- 성격·행동유형·강점보완 등 심화는 전체풀이/종합요약판에만 (단일 주제 상품은 생략) ----
    if not p1_lite:
        _sub("타고난 성격과 기질")
        if chart_paths.get("sipseong"):
            body_parts.append(f"<div class='chart-wrap'><img src='{chart_paths['sipseong']}' style='width:100%'/></div>")
        body_parts.append(_p(txt("p1_성격", txt("타고난성향", txt("십성해설")))))
        _sub("삶에서 반복되기 쉬운 행동 유형")
        body_parts.append(_p(txt("p1_반복", txt("십성해설",
            "익숙한 방식으로 문제를 풀려는 경향이 반복될 수 있습니다. 중요한 순간에는 평소와 다른 선택지도 함께 살펴보면 도움이 됩니다."))))
        _sub("나의 강점과 보완해야 할 부분")
        body_parts.append(f"<div class='callout'><div class='callout-label'>{esc(plain(gyeokguk.get('name','')))}</div>"
                          f"<div>{esc(plain(gyeokguk.get('description','')))}</div></div>")
        body_parts.append(_p(txt("p1_강점보완", txt("격국해설", txt("타고난성향")))))

    # ===================== PART 2 =====================
    chapter("P2", "인생의 흐름과 전환점",
            "언제 오르고 언제 쉬어가는지, 인생의 결을 살펴봅니다.")
    if chart_paths.get("life_curve"):
        body_parts.append(f"<div class='chart-wrap'><img src='{chart_paths['life_curve']}' style='width:100%'/>"
                          "<div class='chart-cap'>나이에 따른 운세 흐름 — 높을수록 기운이 좋은 시기</div></div>")
    # 현재·앞으로의 대운 중심 (지나온 과거를 '좋았던 때'로 부각하지 않는다)
    _fut_idxs = [i for i in range(len(_ds["ages"])) if _ds["ages"][i] + 9 >= cur_age]
    _bf_i = (max(_fut_idxs, key=lambda k: _ds["scores"][k]) if _fut_idxs else _best_i)
    _bfa = _ds["ages"][_bf_i] if _bf_i >= 0 else None

    _sub("앞으로 기운이 오르는 시기")
    if _bfa is not None:
        if _bfa <= cur_age <= _bfa + 9:
            body_parts.append(_p(f"지금 지나고 계신 <b>{_bfa}세~{_bfa+9}세</b> 흐름이 앞으로 중 기운이 가장 좋은 시기입니다. "
                                 "그동안 쌓아 온 경험과 내공을 바탕으로, 지금이야말로 안정과 보람을 함께 누리기 좋은 때입니다."))
        else:
            body_parts.append(_p(f"앞으로는 <b>{_bfa}세~{_bfa+9}세</b> 무렵에 기운이 한 번 더 오릅니다. "
                                 "그 시기를 향해 지금부터 건강과 관계를 잘 챙겨 두면 좋습니다."))
    body_parts.append(_p(txt("p2_상승정체", txt("대운세운해설"))))
    _sub("앞으로 다가오는 변화의 시기")
    if _next_change is not None and _next_change >= cur_age:
        body_parts.append(_p(f"다음 큰 흐름(대운)은 <b>{_next_change}세</b> 무렵부터 시작됩니다. 이 전후로 환경·마음·관계에 변화가 오기 쉬우니 미리 마음의 준비를 해 두면 한결 편안합니다."))
    else:
        body_parts.append(_p("지금의 큰 흐름이 당분간 이어집니다. 급격한 변화보다는 지금 자리에서 몸과 마음을 편안히 다지는 시기입니다."))
    _sub("올해 흐름 — 좋은 시기와 조심할 시기")
    if chart_paths.get("daeun_bars"):
        body_parts.append(f"<div class='chart-wrap'><img src='{chart_paths['daeun_bars']}' style='width:100%'/>"
                          "<div class='chart-cap'>10년 단위 대운 지수 — 회색은 지나온 시기, 색이 진한 쪽이 지금부터의 흐름입니다</div></div>")
    body_parts.append(_p(f"{report_year}년에는 {_op}에 기운이 밝습니다. 좋은 일·모임·중요한 결정은 이 시기에 맞추면 힘을 받습니다."))
    body_parts.append(_p(f"{report_year}년에는 {_ca}에 변화가 크게 오니, 큰 결정과 무리한 일은 한 박자 늦추고 건강을 특히 살피세요."))
    _sub("지금 나이에 맞는 삶의 방향")
    if _sk in ("20", "30"):
        body_parts.append("<div class='callout'><div class='callout-label'>지금은 '씨앗을 뿌리는' 시기</div>"
                          "<div>지금의 경험과 도전은 훗날 큰 나무가 될 씨앗입니다. 다양한 시도 속에서 나만의 강점을 찾고, 좋은 습관과 사람을 곁에 두면 앞으로의 전성기가 훨씬 든든해집니다.</div></div>")
        if _bfa is not None:
            body_parts.append(_p(f"특히 <b>{_bfa}세~{_bfa+9}세</b> 무렵 기운이 크게 오르니, 그 시기를 향해 지금부터 실력과 관계를 쌓아 두세요."))
    elif _sk in ("40", "50"):
        body_parts.append("<div class='callout'><div class='callout-label'>지금은 '열매를 키우는' 시기</div>"
                          "<div>그동안 쌓아 온 노력이 성과로 무르익는 때입니다. 무리한 확장보다 잘하는 것에 깊이를 더하고, 건강과 가정을 함께 챙기면 안정과 성취를 같이 얻을 수 있습니다.</div></div>")
        if _bfa is not None:
            body_parts.append(_p(f"앞으로 <b>{_bfa}세~{_bfa+9}세</b>에 기운이 오르니, 그 시기에 중요한 결실을 맞출 수 있도록 준비해 두세요."))
    else:
        body_parts.append("<div class='callout'><div class='callout-label'>지금은 '거두고 나누는' 시기</div>"
                          "<div>인생의 큰 산은 이미 여러 번 넘어오셨습니다. 지금부터는 새로 크게 벌이기보다, "
                          "그동안 쌓은 것을 건강하게 지키고 가족·이웃과 나누며 마음의 여유를 누리는 흐름이 잘 맞습니다.</div></div>")
    body_parts.append(_p(txt("p2_황금기", txt("평생운세총평"))))

    # ===================== PART 3 =====================
    if is_senior:
        # 60대 이상: 새 연애보다 부부·동반자·가족 관계 중심
        chapter("P3", "부부 · 가족 · 인연운",
                "배우자·자녀와의 인연, 가족 관계의 결을 살펴봅니다.")
        _sub("관계에서 나타나는 나의 성향")
        body_parts.append(_p(txt("p3_성향", txt("연애운인연운"))))
        _sub("배우자·가족과의 인연의 특징")
        body_parts.append(_p(txt("p3_이상형", txt("결혼운배우자운"))))
        _sub("가정에 화목한 기운이 도는 시기")
        body_parts.append(_p(f"{report_year}년에는 {_op}에 가족의 좋은 소식과 화목한 기운이 따르기 쉽습니다. 이 시기에 가족 모임이나 뜻깊은 행사를 두면 정이 더 깊어집니다."))
        _sub("가족 관계에서 주의할 점")
        body_parts.append(_p(txt("p3_갈등", txt("대인관계운",
            "서운함을 마음에 담아 두기보다, 작은 고마움과 불편을 그때그때 부드럽게 나누면 가족 사이가 더 편안해집니다."))))
        _sub("정을 오래 지키는 방법")
        body_parts.append(_p("자녀·손주·배우자에게 '고맙다', '수고했다'는 말을 자주 건네실수록 관계의 온기가 오래 갑니다. 베풀고 나누는 마음이 곧 노년의 큰 복입니다."))
    elif _is_couple:
        # 40~50대: 배우자·가정운 중심
        chapter("P3", "배우자 · 가정 · 인연운",
                "배우자와의 관계와 가정운의 흐름을 살펴봅니다.")
        _sub("관계에서 나타나는 나의 성향")
        body_parts.append(_p(txt("p3_성향", txt("연애운인연운"))))
        _sub("배우자와 잘 맞는 부분과 보완할 부분")
        body_parts.append(_p(txt("p3_이상형", txt("결혼운배우자운"))))
        _sub("가정운이 좋아지는 시기")
        body_parts.append(_p(f"{report_year}년에는 {_op}에 부부·가정에 화목한 기운이 밝습니다. 함께하는 시간을 늘리면 관계가 더 단단해집니다."))
        _sub("관계에서 주의해야 할 갈등 요소")
        body_parts.append(_p(txt("p3_갈등", txt("대인관계운",
            "서운함을 쌓아 두었다가 한꺼번에 터뜨리면 갈등이 커집니다. 작은 불편은 그때그때 부드럽게 표현하는 편이 좋습니다."))))
        _sub("좋은 관계를 오래 유지하는 방법")
        body_parts.append(_p(txt("p3_유지",
            "상대가 힘을 얻는 부분을 이해하고 배려하는 대화를 나누면 관계가 오래 갑니다. 고마움은 자주, 구체적으로 표현하세요.")))
    else:
        # 20~40대: 연애·결혼운 중심
        chapter("P3", "연애 · 결혼 · 배우자운",
                "나의 연애 성향과 인연의 시기를 살펴봅니다.")
        _sub("연애할 때 나타나는 성향")
        body_parts.append(_p(txt("p3_성향", txt("연애운인연운"))))
        _sub("나와 잘 맞는 상대의 특징")
        body_parts.append(_p(txt("p3_이상형", txt("결혼운배우자운"))))
        _sub("연애와 결혼운이 강해지는 시기")
        body_parts.append(_p(f"{report_year}년에는 {_op}에 인연의 기운이 밝습니다. 소개·모임·새로운 만남에 마음을 열어 보세요."))
        _sub("관계에서 주의해야 할 갈등 요소")
        body_parts.append(_p(txt("p3_갈등", txt("대인관계운",
            "서운함을 쌓아 두었다가 한꺼번에 터뜨리면 갈등이 커집니다. 작은 불편은 그때그때 부드럽게 표현하는 편이 좋습니다."))))
        _sub("좋은 인연을 유지하는 방법")
        body_parts.append(_p(txt("p3_유지",
            "상대가 힘을 얻는 부분을 이해하고 배려하는 대화를 나누면 관계가 오래 갑니다. 고마움은 자주, 구체적으로 표현하세요.")))

    # ===================== PART 4 =====================
    chapter("P4", "재물운과 경제 흐름",
            "돈이 들어오는 때와 지켜야 할 때를 살펴봅니다.")
    _sub("타고난 재물운의 특징")
    body_parts.append(_p(txt("p4_특징", txt("재물운"))))
    _sub("돈을 모으는 방식과 소비 성향")
    body_parts.append(_p(txt("p4_소비", txt("사업운창업운",
        "큰 흐름을 읽고 움직일 때 재물운이 좋아집니다. 충동적인 큰 지출만 조심하면 안정적으로 모을 수 있습니다."))))
    _sub("수입이 증가하기 좋은 시기")
    body_parts.append(_grid2("돈이 불어나기 좋은 달", _op, "지출을 조심할 달", _ca))
    _sub("투자 · 계약 · 지출에 주의할 시기")
    body_parts.append(_p(f"{report_year}년에는 {_ca}에 큰 투자·계약·보증을 특히 신중하게 살피세요. 서두르기보다 한 박자 늦추는 편이 안전합니다."))
    _sub("재물운을 안정적으로 활용하는 방법")
    body_parts.append(_p(txt("p4_활용",
        "수입의 일정 비율을 먼저 떼어 저축·투자로 자동 배분하고, 큰 결정은 기회 달에 몰아서 처리하면 재물운을 안정적으로 살릴 수 있습니다.")))

    # ===================== PART 5 (나이대별 맞춤) =====================
    if _sk == "20":
        chapter("P5", "진로 · 취업 · 성장운",
                "나에게 맞는 길과 첫 도약의 시기를 살펴봅니다.")
        _sub("적성과 강점을 살릴 수 있는 분야")
        body_parts.append(_p(txt("p5_적성", txt("직장운이직운승진운"))))
        _sub("진로 방향과 나에게 유리한 길")
        body_parts.append(_p(txt("p5_방향", txt("사업운창업운"))))
        _sub("취업 · 시험 · 합격운의 흐름")
        body_parts.append(_p(f"{report_year}년에는 {_op}에 합격·발탁의 기운이 오릅니다. 시험·지원·발표는 이 시기에 맞추면 좋고, {_ca}에는 서두르지 말고 실력을 다지세요."))
        _sub("성장 가능성을 높이는 전략")
        body_parts.append(_p("지금은 넓게 경험하며 나만의 강점을 만드는 시기입니다. 한 분야에 깊이를 더해 두면 30대에 크게 도약할 수 있습니다. 조급함보다 방향을 정하는 것이 먼저입니다."))
    elif _sk in ("30", "40"):
        chapter("P5", "직업 · 사업 · 성공운",
                "나에게 맞는 일과 성공의 방향을 살펴봅니다.")
        _sub("적성과 강점을 살릴 수 있는 분야")
        body_parts.append(_p(txt("p5_적성", txt("직장운이직운승진운"))))
        _sub("직장과 사업 중 나에게 유리한 방향")
        body_parts.append(_p(txt("p5_방향", txt("사업운창업운"))))
        _sub("이직 · 승진 · 성취운의 흐름")
        body_parts.append(_p(txt("p5_승진", txt("문서운",
            f"{report_year}년에는 {_op}에 발탁·승진·성취의 기운이 오릅니다. 준비한 것을 이 시기에 제출·발표하면 좋습니다."))))
        _sub("창업 · 확장 · 계약에 유리한 시기")
        body_parts.append(_p(f"창업·확장·중요 계약은 {_op}에 배치하면 힘을 받습니다. 반대로 {_ca}에는 큰 확장을 미루는 편이 안전합니다."))
        _sub("성공 가능성을 높이는 현실적인 전략")
        body_parts.append(_p(txt("p5_전략",
            "한 분야에서 확실한 강점을 만든 뒤, 좋은 시기에 과감히 승부를 거는 전략이 잘 맞습니다. 혼자보다 귀인과 함께할 때 성과가 커집니다.")))
    elif _sk == "50":
        chapter("P5", "직업 · 자산 · 인생 2막",
                "지금의 안정과 다음 인생 2막 준비를 살펴봅니다.")
        _sub("경험과 강점을 살릴 수 있는 분야")
        body_parts.append(_p(txt("p5_적성", txt("직장운이직운승진운"))))
        _sub("자리 지키기와 인생 2막 사이의 방향")
        body_parts.append(_p("지금까지 쌓은 경력과 인맥이 가장 큰 자산인 시기입니다. 무리한 새 도전보다, 잘하시던 일에 깊이를 더하거나 그 경험을 살린 제2의 일(자문·강의·소규모 사업 등)을 천천히 준비하기 좋습니다."))
        _sub("성취 · 자산이 오르는 시기")
        body_parts.append(_p(f"{report_year}년에는 {_op}에 성취와 재물의 기운이 오릅니다. 노후 자산·연금·부동산은 이 시기에 점검하고, {_ca}에는 큰 계약·투자를 서두르지 마세요."))
        _sub("50대의 현명한 전략")
        body_parts.append(_p("건강을 챙기며 자산을 지키고, 다음 20~30년을 내다보며 씀씀이와 관계를 정돈하는 것이 지금의 가장 큰 성공입니다. 조급한 확장보다 안정과 준비가 힘이 됩니다."))
    elif _sk == "60":
        chapter("P5", "사회활동 · 명예 · 자산운",
                "은퇴 이후의 활동과 보람, 자산 관리를 살펴봅니다.")
        _sub("경륜을 살릴 수 있는 활동")
        body_parts.append(_p(txt("p5_적성", txt("직장운이직운승진운"))))
        _sub("보람과 인정을 얻기 좋은 방향")
        body_parts.append(_p("평생 쌓아 온 경험은 그 자체로 큰 자산입니다. 자문·조언·취미·봉사처럼 무리하지 않으면서 인정받는 활동에서 특히 보람이 큽니다. 새로 크게 벌이기보다, 잘하시던 일을 여유 있게 이어가는 편이 잘 맞습니다."))
        _sub("명예와 인정운의 흐름")
        body_parts.append(_p(f"{report_year}년에는 {_op}에 사람들의 인정과 좋은 소식이 따르기 쉽습니다. 가족 경사나 뜻깊은 모임도 이 시기에 잘 어울립니다."))
        _sub("자산 · 문서를 지키고 정리할 시기")
        body_parts.append(_p(f"부동산·상속·보험·계약 같은 문서 일은 {_op}에 차분히 정리하면 좋고, {_ca}에는 큰 계약·보증·투자를 서두르지 마세요. 서류는 꼭 전문가(법무사·세무사) 검토를 받고, 구두 약속보다 문서로 남기세요."))
        _sub("지금 나이에 맞는 현명한 전략")
        body_parts.append(_p("건강을 최우선으로 두고, 가진 것을 지키며 가족·이웃과 나누는 것이 지금 시기의 가장 큰 성공입니다. 무리한 확장보다 마음의 평안과 관계의 온기를 챙기실 때 삶이 더욱 넉넉해집니다."))
    else:  # 70, 80
        chapter("P5", "건강 · 여가 · 나눔운",
                "건강하게 누리고 나누며 보내는 흐름을 살펴봅니다.")
        _sub("무리하지 않고 이어가기 좋은 활동")
        body_parts.append(_p("몸과 마음이 편안한 취미·산책·모임처럼 즐거움을 주는 활동이 가장 잘 맞습니다. 오랜 경험에서 나오는 지혜를 가족과 이웃에게 들려주시는 것만으로도 큰 나눔이 됩니다."))
        _sub("좋은 기운과 좋은 소식이 따르는 시기")
        body_parts.append(_p(f"{report_year}년에는 {_op}에 반가운 소식과 화목한 기운이 따르기 쉽습니다. 가족 경사나 뜻깊은 만남을 이 시기에 두면 더욱 좋습니다."))
        _sub("자산 · 문서를 지키고 물려줄 준비")
        body_parts.append(_p(f"상속·유산·보험·부동산 같은 문서 일은 서두르지 말고 {_op}에 가족과 함께 차분히 정리하세요. 큰 결정은 반드시 전문가(법무사·세무사) 검토를 받고 문서로 남기시는 것이 안전합니다."))
        _sub("지금 시기의 가장 큰 복")
        body_parts.append(_p("건강과 마음의 평안, 그리고 가족·이웃과 나누는 정이 지금 시기의 가장 큰 복입니다. 그동안 잘 걸어오신 삶 자체가 충분히 훌륭하니, 이제는 편안히 누리셔도 됩니다."))

    # ===================== PART 6 =====================
    chapter("P6", "건강과 생활관리",
            "타고난 체질과 건강을 챙길 시기를 살펴봅니다.")
    _sub("사주로 살펴보는 타고난 체질 경향")
    body_parts.append(_p(txt("p6_체질", txt("건강운"))))
    _sub("생활습관에서 보완할 부분")
    _mo = missing[0] if missing else (yongsin.get("yongsin") or "")
    _rm = OHENG_REMEDY.get(_mo, {})
    body_parts.append(_p(txt("p6_생활",
        f"부족하기 쉬운 {_mo} 기운을 채우면 컨디션이 좋아집니다. {(_rm.get('act','규칙적인 생활'))}을 습관으로 삼아 보세요." if _mo else
        "규칙적인 수면과 식사, 가벼운 운동을 꾸준히 지키는 것이 가장 좋은 관리법입니다.")))
    _sub("컨디션 관리가 필요한 시기")
    body_parts.append(_p(f"{report_year}년에는 {_ca}에 특히 무리하지 말고 충분히 쉬어 주세요. 환절기 건강 관리도 함께 신경 쓰면 좋습니다."))
    _sub("오행 균형에 맞춘 생활관리 방향")
    if _rm:
        body_parts.append(f"<div class='card'><b>생활 속 보완 요소</b> — 색상: {esc(_rm.get('color',''))} / 방향: {esc(_rm.get('dir',''))} / 음식: {esc(_rm.get('food',''))} / 활동: {esc(_rm.get('act',''))}</div>")
    body_parts.append("<div class='callout'><div class='callout-label'>참고</div>"
                      "<div class='disclaimer'>건강 관련 내용은 명리학적 참고사항이며, 의료 진단을 대신하지 않습니다.</div></div>")

    # ===================== PART 7 =====================
    chapter("P7", "인간관계와 귀인운",
            "나를 돕는 사람과 관계의 결을 살펴봅니다.")
    _sub("나에게 도움을 주는 귀인의 특징")
    body_parts.append(_p(txt("p7_귀인", txt("귀인운", txt("대인관계운")))))
    if sinsal:
        body_parts.append(f"<div class='card'><b>내 사주에 나타나는 특별한 기운</b><br>{esc(', '.join(list(sinsal.keys())[:5]))}</div>")
    _sub("귀인을 만날 가능성이 높은 환경")
    body_parts.append(_p(f"배움의 자리, 오래된 인연, 진심으로 도운 사람에게서 귀인이 나타나기 쉽습니다. {report_year}년에는 {_op}에 그 기운이 밝습니다."))
    _sub("인간관계에서 반복되는 문제")
    body_parts.append(_p(txt("p7_문제", txt("대인관계운",
        "잘해 주려다 선을 넘거나, 반대로 마음을 닫아 오해가 쌓이는 일이 반복될 수 있습니다. 적당한 거리와 솔직함의 균형이 중요합니다."))))
    _sub("주의해야 할 관계 유형과 대처 방법")
    body_parts.append(_p(txt("p7_주의",
        "에너지를 크게 빼앗는 관계, 돈이 얽힌 관계는 처음에 기준을 분명히 하세요. 어렵더라도 초반에 선을 정하면 뒤탈이 적습니다.")))

    # ===================== PART 8 =====================
    chapter("P8", "운의 흐름을 활용하는 방법",
            "부족한 기운을 채우고 운을 성과로 연결하는 실천법입니다.")
    _sub("부족한 오행을 보완하는 생활방식")
    if missing:
        for i, o in enumerate(missing):
            r = OHENG_REMEDY.get(o, {})
            body_parts.append(f"<div class='card'><b>{esc(o)} 기운 채우기</b> — 색상: {esc(r.get('color',''))} / 방향: {esc(r.get('dir',''))} / 음식: {esc(r.get('food',''))} / 활동: {esc(r.get('act',''))}</div>")
    else:
        body_parts.append(_p(f"나에게 힘이 되는 {esc(yongsin.get('yongsin',''))} 기운을 일상에서 가까이하면 흐름이 매끄러워집니다."))
    _sub("중요한 선택을 앞두고 확인할 기준")
    body_parts.append(_p(txt("p8_기준", txt("용신해설",
        "결정을 앞두고는 ‘이 선택이 내게 필요한 기운을 채워 주는가’를 기준으로 삼아 보세요. 기회 달에 결정을 몰아 처리하면 더 유리합니다."))))
    _sub("좋은 운을 현실의 성과로 연결하는 방법")
    body_parts.append(_p(txt("p8_성과", txt("평생운세총평",
        "운이 좋아도 준비가 없으면 지나갑니다. 미리 실력·인맥·자금을 쌓아 두었다가 기회 달에 실행하면 운을 성과로 바꿀 수 있습니다."))))
    _sub("지금부터 실행할 수 있는 행동전략")
    y_o = yongsin.get("yongsin", ""); r_y = OHENG_REMEDY.get(y_o, {})
    guide = [
        ("이번 주", f"{esc(y_o)} 기운 채우기 — {esc(r_y.get('color','조화로운 색'))} 소품 곁에 두기, {esc(r_y.get('act','가벼운 산책'))} 시작."),
        ("이번 달", f"올해 핵심 목표 1가지를 적어 붙이고, 기회 달({_op})에 할 일을 미리 계획."),
        ("3개월", f"조심할 달({_ca})의 위험을 점검하고, 90일마다 성과를 돌아보기."),
    ]
    rows = "".join(f"<tr><td style='white-space:nowrap'>{w}</td><td style='text-align:left'>{t}</td></tr>" for w, t in guide)
    body_parts.append(f"<div class='card'><table><tr><th>기간</th><th>실행 전략</th></tr>{rows}</table></div>")

    # ===================== PART 9 =====================
    chapter("P9", f"{report_year}년 월별 운세",
            "1월부터 12월까지, 달마다의 흐름을 살펴봅니다.")
    if chart_paths.get("monthly_bars"):
        body_parts.append(f"<div class='chart-wrap'><img src='{chart_paths['monthly_bars']}' style='width:100%'/>"
                          "<div class='chart-cap'>월별 운세 지수 — 높을수록 기운이 좋은 달</div></div>")
    body_parts.append(_grid2("기회가 커지는 달", _op, "계약·재물·관계를 주의할 달", _ca))
    if chart_paths.get("monthly"):
        body_parts.append(f"<div class='chart-wrap'><img src='{chart_paths['monthly']}' style='width:100%'/></div>")
    if not compact:
        _sub("1월부터 12월까지 월별 운의 흐름")
        for w in wolun:
            key = f"{w['month']}월운세"
            body = txt(key, w.get("keyword", ""))
            body_parts.append(f"<div class='sub-title'>{w['month']}월 — {esc(w.get('ganji',''))}</div>{_p(body)}")
    _sub("월별로 집중하면 좋은 행동 방향")
    body_parts.append(_p(f"기회가 커지는 {_op}에는 새로운 시도와 중요한 결정을, {_ca}에는 점검과 마무리에 집중하세요. 매달 초 그 달의 목표 하나를 정해 두면 흐름을 타기 쉽습니다."))

    # ===================== PART 10 =====================
    chapter("P10", "앞으로 10년의 운세 분석",
            "다가올 10년의 큰 흐름과 전환점을 살펴봅니다.")
    if chart_paths.get("daeun_timeline"):
        body_parts.append(f"<div class='chart-wrap'><img src='{chart_paths['daeun_timeline']}' style='width:100%'/>"
                          "<div class='chart-cap'>대운 흐름 — 색 띠는 오행, 붉은 테두리는 현재 대운</div></div>")
    _sub("향후 10년간의 전체적인 운세 흐름")
    if cur_daeun_age is not None:
        body_parts.append(f"<div class='callout'><div class='callout-label'>현재 대운: {esc(cur_daeun_pillar)} ({cur_daeun_age}세~{cur_daeun_age+9}세)</div>"
                          f"<div>{report_year}년 기준 만 {cur_age}세 전후로, 이 대운의 영향 안에 있습니다.</div></div>")
    body_parts.append(_p(txt("p10_흐름", txt("대운세운해설"))))
    _sub("직업 · 사업 · 재물의 변화 가능성")
    body_parts.append(_p(txt("p10_직재", txt("사업운창업운",
        "앞으로 10년은 지금 쌓는 실력과 인맥이 성과로 이어지는 시기입니다. 상승기에는 확장을, 정체기에는 내실을 다지세요."))))
    _sub("연애 · 결혼 · 가정운의 주요 시기")
    body_parts.append(_p(txt("p10_연가", txt("결혼운배우자운",
        "인연과 가정의 큰 변화는 기운이 오르는 대운 시기에 찾아오기 쉽습니다. 그 시기에 맞춰 중요한 결정을 하면 좋습니다."))))
    _sub("인생의 중요한 전환점과 준비 방향")
    if _next_change is not None:
        body_parts.append(_p(f"가장 큰 전환점은 {_next_change}세 무렵 시작되는 대운입니다. 그 전에 실력·자금·관계를 준비해 두면 전환기를 기회로 바꿀 수 있습니다."))
    body_parts.append(_p(txt("p10_전환", txt("평생운세총평"))))

    # ===================== 맺음말 (따뜻한 위로·응원) =====================
    _reset_always_on()   # 상품별 필터 해제(맺음말·부록·궁합은 모든 상품에 공통 수록)
    _gname = esc(plain(gyeokguk.get("name", "")))
    body_parts.append(_chapter_head(reg, "맺음말", "마지막으로 드리는 말", new_page=True))
    body_parts.append(f"<div class='callout' style=\"border-left-color:{TOKENS['seal']};background:#FBEEE6;\">"
                      f"<div class='callout-label' style=\"color:{TOKENS['seal']};\">{esc(customer_name)} 님께</div>"
                      f"<div>{esc(customer_name)} 님은 <b>{_gname}</b>의 좋은 그릇을 타고나셨습니다. "
                      "지나온 길에 힘든 고비도 있었겠지만, 그 시간을 묵묵히 견뎌 오신 것만으로 이미 큰 힘을 지니고 계십니다. "
                      "사주는 정해진 운명을 못 박아 두는 것이 아니라, 나의 결을 이해하고 좋은 시기에 힘을 실어 더 나은 선택을 하도록 돕는 지도와 같습니다.</div></div>")
    body_parts.append(_p("이 리포트의 흐름을 참고하시되, 결국 삶을 만들어 가는 것은 오늘 하루의 마음과 선택입니다. "
                         "좋은 시기에는 용기를 내고, 조심할 시기에는 잠시 숨을 고르며, 곁의 소중한 사람들과 온기를 나누시길 바랍니다. "
                         "이 글이 마음의 갈피를 잡고 한 걸음 내딛는 데 작은 등불이 되었으면 합니다. 앞날에 늘 건강과 평안이 함께하시길 진심으로 응원합니다."))

    # ===================== 26. 용어사전 =====================
    reg.part("부록")
    body_parts.append(_chapter_head(reg, "부록 1", "쉽게 풀어 쓴 용어 설명", new_page=True))
    glo_terms = (["일간", "오행", "십성", "용신", "격국", "대운", "세운", "월운"]
                 if compact else
                 ["일간", "오행", "십성", "용신", "희신", "기신", "격국", "신강", "신약",
                  "대운", "세운", "월운", "지장간", "합", "충", "형", "12운성", "신살", "궁합", "택일"])
    rows = "".join(f"<tr><td style='white-space:nowrap;font-weight:700'>{esc(t)}</td><td style='text-align:left'>{esc(plain(GLOSSARY[t]))}</td></tr>"
                   for t in glo_terms if t in GLOSSARY)
    body_parts.append(f"<div class='card'><table><tr><th style='width:22mm'>용어</th><th>풀이</th></tr>{rows}</table></div>")

    # ===================== 27. 분석 기준 및 면책 =====================
    body_parts.append(_chapter_head(reg, "부록 2", "분석 기준과 안내"))
    body_parts.append(_p("이 리포트는 오래전부터 이어져 온 사주 이론과 정확한 절기 계산을 바탕으로 자동으로 만들어졌습니다. "
                         "나에게 필요한 기운(용신)과 성향의 틀(격국)은 널리 쓰이는 표준 방식으로 판단했습니다."))
    ai_note = ("이 리포트의 해석 문장은 계산된 사주를 바탕으로 AI가 개인 맞춤으로 작성했습니다."
               if data.get("aiUsed") else
               "이 리포트의 해석 문장은 미리 정리해 둔 사주 해석 자료를 바탕으로 작성했습니다.")
    body_parts.append(f"<div class='callout'><div class='callout-label'>작성 방식</div><div class='disclaimer'>{esc(ai_note)}</div></div>")

    # ===================== 궁합 (있을 때만) =====================
    if gunghap:
        _build_gunghap(reg, body_parts, gunghap, chart_paths, txt, customer_name, meta)

    # ===================== 28. 마무리 (전체풀이/궁합에만 — 단품·요약판은 맺음말 1개로 충분) =====================
    if not compact:
        reg.part("")
        body_parts.append(_chapter_head(reg, "맺음말", "마무리하며", new_page=True))
        body_parts.append(_p(f"{customer_name} 님의 사주에는 {most_oheng} 기운이라는 강점과, {esc(yongsin.get('yongsin',''))} 기운이라는 "
                             "가장 중요한 열쇠가 담겨 있습니다. 사주는 정해진 운명이 아니라, 나를 더 잘 이해하고 삶의 흐름을 읽어 "
                             "더 나은 선택을 돕는 지도입니다."))
        body_parts.append(f"<div class='callout' style='text-align:center'><div class='callout-label' style='color:{TOKENS['gold']}'>{esc(brand)}</div>"
                          f"<div>{report_year}년, {customer_name} 님의 앞날에 좋은 기운이 함께하기를 바랍니다.</div></div>")

    # ---- 목차 삽입 + 중복 문단 정리 ----
    toc = reg.toc_html()
    document = "".join(body_parts)
    document = _dedup_document(document)   # 공용 fallback 재사용으로 생긴 중복 문단 제거
    document = document.replace("{{TOC}}", toc)

    header_text = f"{customer_name} 님 · {report_type}"
    footer_left = f"주문번호 {order_id}" if order_id else brand
    css = get_css(header_text=header_text, footer_left=footer_left)

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><style>{css}</style></head>
<body>{document}</body></html>"""


def _build_gunghap(reg, body_parts, gunghap, chart_paths, txt, customer_name, meta):
    reg.part("6부. 궁합 자세히 보기")
    body_parts.append(_chapter_head(reg, "궁합 1", "두 사람의 궁합 총평", new_page=True))
    if chart_paths.get("gunghap_gauge"):
        body_parts.append(f"<div class='chart-wrap'><img src='{chart_paths['gunghap_gauge']}' style='width:58%'/></div>")
    body_parts.append(_p(gunghap.get("summary", "")))
    body_parts.append(
        "<div class='card'><table>"
        "<tr><th>항목</th><th>내용</th></tr>"
        f"<tr><td>일간 관계</td><td>{esc(gunghap.get('ilgan_relation',''))}</td></tr>"
        f"<tr><td>육합</td><td>{esc(', '.join(gunghap.get('yukhap_hits', [])) or '없음')}</td></tr>"
        f"<tr><td>삼합</td><td>{esc(', '.join(gunghap.get('samhap_hits', [])) or '없음')}</td></tr>"
        f"<tr><td>충</td><td>{esc(', '.join(gunghap.get('chung_hits', [])) or '없음')}</td></tr>"
        f"<tr><td>형·해·파</td><td>{esc(', '.join(gunghap.get('hyeong_hae_pa_hits', [])) or '없음')}</td></tr>"
        "</table></div>")
    body_parts.append(_section_block("궁합 종합 총평", txt("궁합총평", gunghap.get("summary", ""))))

    body_parts.append(_chapter_head(reg, "궁합 2", "강점·시너지와 주의점"))
    body_parts.append(_section_block("두 사람의 강점 및 시너지", txt("궁합장점", gunghap.get("강점해설", ""))))
    body_parts.append(_section_block("성향 차이와 갈등 가능 지점", txt("궁합주의점및개운법", gunghap.get("주의점해설", ""))))
    body_parts.append(_section_block("의사소통 방식 제안",
        "서로의 일간 오행 관계를 이해하고, 상대가 힘을 얻는 기운(용신)을 배려하는 대화를 나누면 갈등이 줄어듭니다. "
        "충(沖)에 해당하는 부분은 정면충돌보다 시간차를 두고 조율하는 편이 좋습니다.", footnote=False))

    body_parts.append(_chapter_head(reg, "궁합 3", "관계 개선을 위한 실행 조언"))
    body_parts.append(
        "<div class='card'><b>재물·생활 궁합</b><br>공동의 재무 목표를 문서로 정하고 역할을 나누면 안정적입니다.</div>"
        "<div class='card'><b>결혼·장기 관계 궁합</b><br>서로의 대운 흐름이 좋은 시기에 중요한 결정을 맞추면 시너지가 커집니다.</div>"
        "<div class='card'><b>실행 조언</b><br>월 1회 서로의 계획을 공유하는 시간을 갖고, 기회 월에는 함께 새로운 시도를 해 보세요.</div>")


def _excerpt(text, n=2):
    """긴 해설에서 앞 n문장만 추려 간결하게(무료 리포트용)."""
    t = plain(text or "").strip()
    if not t:
        return t
    import re as _r
    parts = _r.split(r"(?<=다\.)\s+|(?<=요\.)\s+|(?<=\.)\s+", t)
    parts = [x for x in parts if x.strip()]
    return " ".join(parts[:n]).strip()


def build_teaser_html(data: dict, chart_paths: dict, meta: dict) -> str:
    """SNS 무료 이벤트용 3장짜리 무료 사주 리포트.
    '나 위주 + 이달의 흐름운 + 조심할 것' 중심으로 간략하되 신뢰감 있게.
    재물/연애/직업운은 프리미엄에서만 볼 수 있게 잠금 처리하고, 마지막에 결제를 유도한다."""
    import datetime as _dt
    txt = _txt_factory(data)
    b = data.get("birth", {}) or {}
    pillars = data.get("pillars", {}) or {}
    yongsin = data.get("yongsin", {}) or {}
    gyeokguk = data.get("gyeokguk", {}) or {}
    wolun = data.get("wolun", []) or []
    most_oheng = data.get("ohengMostCommon", "")
    missing = data.get("ohengMissing", []) or []

    report_year = int(meta.get("reportYear") or 2026)
    customer_name = meta.get("customerName") or data.get("name") or "고객"
    report_type = meta.get("reportType") or "이달의 운세 · 무료 리포트"
    order_id = meta.get("orderId") or ""
    brand = meta.get("brand") or "동네사주카페"
    calendar_type = meta.get("calendarType") or "양력"
    time_unknown = bool(meta.get("birthTimeUnknown"))
    cover_img = meta.get("coverImageUri") or ""

    if time_unknown:
        time_str = "출생시간 미상"
    else:
        time_str = f"{int(b.get('hour', 0)):02d}시 {int(b.get('minute', 0)):02d}분"
    birth_line = _birth_line_str(b, data, calendar_type, time_str)

    this_month = _dt.datetime.now().month
    wm = next((w for w in wolun if int(w.get("month", 0)) == this_month), (wolun[0] if wolun else None))

    yv = yongsin
    good = {yv.get("yongsin"), yv.get("huisin")}
    bad = {yv.get("gisin"), yv.get("gusin")}
    opp = ", ".join(f"{w['month']}월" for w in wolun if w.get("oheng") in good) or "기운이 오르는 달"
    cau = ", ".join(f"{w['month']}월" for w in wolun if w.get("oheng") in bad) or "변화가 큰 달"
    bad_str = "·".join(x for x in bad if x) or "기운이 약해지는 시기"
    miss_str = ", ".join(missing) if missing else "없음"

    cover = f'''
    <div class="cover">
      {'<img class="cover-bg" src="'+cover_img+'"/>' if cover_img else ''}
      <div class="gold-frame"></div>
      <div class="cartouche"><div class="cartouche-inner">
        <div class="c-type">이달의 운세 · 무료 리포트</div>
        <div class="c-name">{esc(customer_name)} <span class="nim">님</span></div>
        <div class="c-birth">{esc(birth_line)}</div>
        <div class="c-year">{report_year}년 {this_month}월</div>
      </div></div>
    </div>
    '''

    # ---- 텍스트 준비(무료라도 알차게, 문장 3개 내외) ----
    seong = _excerpt(txt("p1_성격", txt("타고난성향", txt("십성해설"))), 3)
    seong2 = _excerpt(txt("타고난성향", txt("십성해설", "")), 2)
    month_flow = _excerpt(txt(f"{wm['month']}월운세", wm.get("keyword", "")), 3) if wm else ""
    ilgan = data.get("ilgan", "")
    gyeok = plain(gyeokguk.get("name", ""))

    # ---- 오행 분포 표(도표) ----
    od = data.get("ohengDistribution", {}) or {}
    _order = ["목", "화", "토", "금", "수"]
    oheng_table = (
        "<div class='card'><table style='width:100%;text-align:center;'>"
        "<tr><th>오행</th>" + "".join(f"<th>{k}</th>" for k in _order) + "</tr>"
        "<tr><td>기운의 개수</td>" + "".join(f"<td><b>{esc(str(od.get(k, 0)))}</b></td>" for k in _order) + "</tr>"
        "</table></div>")

    def chart_img(key, width, cap=""):
        if not chart_paths.get(key):
            return ""
        c = f"<div class='chart-cap'>{esc(cap)}</div>" if cap else ""
        return f"<div class='chart-wrap'><img src='{chart_paths[key]}' style='width:{width}'/>{c}</div>"

    lock = TOKENS['ink_soft']
    def locked(title, teaser):
        return (f"<div class='card' style='border:1px dashed {TOKENS['gold_soft']};background:#FAF4E8;'>"
                f"<b style='color:{TOKENS['seal']}'>{esc(title)}</b> "
                f"<span style='color:{lock};font-size:12.5pt;'>&nbsp;프리미엄 전용 🔒</span><br>"
                f"<span style='color:{lock};font-size:13pt;'>{esc(teaser)}</span></div>")

    # ===================== 1페이지: 사주 원국 + 오행 =====================
    page1 = f'''
    <div class="chapter" style="margin-top:0;">
      <div class="chapter-head"><div class="chapter-num">무료 사주 리포트 · 1</div>
      <div class="chapter-title" style="font-size:21pt;">{esc(customer_name)} 님의 {report_year}년 {this_month}월 운세</div>
      <div class="chapter-sub">이번 달 나의 흐름과 조심할 점을 정통 명리학으로 풀어드립니다.</div></div>

      <div class="section-title">1. 나의 사주 명식(원국)</div>
      <div class="pillars-card card"><table>
        <tr><th>구분</th><th>시주</th><th>일주</th><th>월주</th><th>연주</th></tr>
        <tr><td>천간</td><td class="han">{esc(pillars.get('시주',['',''])[0])}</td><td class="han">{esc(pillars.get('일주',['',''])[0])}</td><td class="han">{esc(pillars.get('월주',['',''])[0])}</td><td class="han">{esc(pillars.get('연주',['',''])[0])}</td></tr>
        <tr><td>지지</td><td class="han">{esc(pillars.get('시주',['',''])[1])}</td><td class="han">{esc(pillars.get('일주',['',''])[1])}</td><td class="han">{esc(pillars.get('월주',['',''])[1])}</td><td class="han">{esc(pillars.get('연주',['',''])[1])}</td></tr>
      </table></div>
      <p class="body-text">태어난 날의 기운으로 나를 상징하는 글자(일간)는 <b>{esc(ilgan)}</b> 이고, 타고난 성향의 큰 틀(격국)은 <b>{esc(gyeok)}</b> 입니다. 이 두 가지가 나의 기본 성격과 인생의 결을 만드는 뿌리예요. 사주 명식은 태어난 연·월·일·시의 기운을 여덟 글자로 나타낸 것으로, 아래 다섯 기운(오행) 분포와 함께 보면 나의 강점과 약점이 또렷하게 드러납니다.</p>

      <div class="section-title">2. 나의 다섯 기운(오행) 분포</div>
      {oheng_table}
      {chart_img('oheng_bar', '92%', '오행별 기운의 많고 적음')}
      <p class="body-text">다섯 기운(목·화·토·금·수) 가운데 <b>{esc(most_oheng or '-')}</b> 기운이 가장 강하고, <b>{esc(miss_str)}</b> 기운은 부족한 편입니다. 강한 기운은 타고난 장점이니 그대로 살리되 지나치지 않게 조절하고, 부족한 기운은 이번 달 생활 속 습관(자주 쓰는 색·다니는 방향·만나는 사람·활동)으로 조금씩 채워주면 운의 균형이 좋아져요.</p>
    </div>
    '''

    # ===================== 2페이지: 성격 · 십성 =====================
    page2 = f'''
    <div class="chapter newpage">
      <div class="chapter-head"><div class="chapter-num">무료 사주 리포트 · 2</div>
      <div class="chapter-title" style="font-size:21pt;">나의 성격과 타고난 기질</div>
      <div class="chapter-sub">사주에 새겨진 나의 본래 성향과 강점입니다.</div></div>

      <div class="section-title">3. 나의 성격과 기질</div>
      <p class="body-text">{esc(seong) or '겉으로 보이는 모습과 속마음이 조금 다른, 자기 색이 분명한 사람입니다. 한번 마음먹으면 끝까지 밀고 나가는 힘이 있고, 사람 사이의 분위기를 잘 읽는 편이에요.'}</p>
      {('<p class="body-text">' + esc(seong2) + '</p>') if seong2 else ''}

      <div class="section-title">4. 십성으로 본 나의 강점</div>
      {chart_img('sipseong', '100%', '십성 분포 — 관계·재물·명예·학문 등 삶의 에너지가 어디에 쏠리는지')}
      <p class="body-text">십성은 나를 둘러싼 사람·일·재물·명예와의 관계를 나타내는 열 가지 기운입니다. 위 분포에서 크게 나타나는 기운이 바로 내가 자연스럽게 힘을 쓰는 영역이에요. 강한 부분은 자신감을 갖고 밀어붙이고, 약한 부분은 사람의 도움을 받거나 준비를 조금 더 하면 좋은 결과로 이어집니다.</p>

      <div class="callout">
        <div class="callout-label">나를 한 문장으로</div>
        <div style="font-size:14pt;">일간 <b>{esc(ilgan)}</b> · 격국 <b>{esc(gyeok)}</b> — 강한 <b>{esc(most_oheng or '-')}</b> 기운을 중심으로, 자기 색이 분명하고 뚝심 있는 사람입니다.</div>
      </div>
    </div>
    '''

    # ============= 3페이지: 이달 흐름 + 조심할 것 + 프리미엄 유도 =============
    page3 = f'''
    <div class="chapter newpage">
      <div class="chapter-head"><div class="chapter-num">무료 사주 리포트 · 3</div>
      <div class="chapter-title" style="font-size:21pt;">{report_year}년 {this_month}월, 나의 흐름운</div>
      <div class="chapter-sub">이번 달 기운의 흐름과 꼭 조심할 점입니다.</div></div>

      <div class="section-title">5. {this_month}월, 나의 흐름운</div>
      <p class="body-text">{esc(month_flow) or '이번 달은 나의 리듬을 지키며 무리하지 않는 것이 좋은 시기입니다. 익숙한 일에서 안정감을 찾고, 새로운 도전은 컨디션이 오르는 시기에 맞추면 한결 수월합니다.'}</p>
      {chart_img('monthly_bars', '100%', f'{report_year}년 월별 운세 흐름 — 막대가 높을수록 기운이 오르는 달')}

      <div class="section-title">6. 이번 달 조심해야 할 것</div>
      <div class="callout"><div class="callout-label">조심하면 좋은 시기</div>
        <div style="font-size:14pt;"><b>{esc(cau)}</b> 은(는) 나와 잘 맞지 않는 <b>{esc(bad_str)}</b> 기운이 강해지는 때예요. 큰 결정·계약·무리한 지출은 한 번 더 신중히 하고, 건강과 감정 관리에 특히 신경 쓰세요. 반대로 <b>{esc(opp)}</b> 에는 기운이 올라가니, 중요한 일은 이 시기에 맞추면 훨씬 수월합니다.</div></div>

      <div class="section-title">7. 더 깊은 내 운세 (프리미엄에서 확인)</div>
      {locked("💰 재물운", "올해 돈이 들어오는 시기와 지켜야 할 지출, 재물을 키우는 방법까지 — 프리미엄 사주풀이에서 자세히 풀어드려요.")}
      {locked("💕 연애·결혼운", "나의 연애 성향과 잘 맞는 상대, 인연이 강해지는 시기 — 프리미엄에서만 확인할 수 있어요.")}
      {locked("💼 직업·성공운", "나에게 맞는 일과 성공의 방향, 이직·승진에 유리한 시기 — 프리미엄에서 만나보세요.")}

      <div class="callout" style="border-left-color:{TOKENS['seal']};background:#FBEEE6;margin-top:5mm;text-align:center;">
        <div class="callout-label" style="color:{TOKENS['seal']};font-size:15.5pt;">지금 내 인생 전체가 궁금하다면?</div>
        <div class="body-text" style="margin-top:1mm;">이 무료 리포트는 <b>이번 달</b> 이야기만 담았어요. <b>프리미엄 사주풀이</b>에서는 재물·연애·직업·건강·귀인과 <b>인생의 황금기</b>, 앞으로 <b>10년의 큰 흐름</b>까지 약 60페이지로 전부 풀어드립니다.</div>
        <div class="body-text" style="margin-top:2mm;font-weight:700;color:{TOKENS['seal']};">▶ 내 인생의 진짜 흐름, 프리미엄 사주풀이로 확인하세요.</div>
      </div>
    </div>
    '''

    content = page1 + page2 + page3

    header_text = f"{customer_name} 님 · {report_type}"
    footer_left = f"주문번호 {order_id}" if order_id else brand
    css = get_css(header_text=header_text, footer_left=footer_left)
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><style>{css}</style></head>
<body>{cover}{content}</body></html>"""

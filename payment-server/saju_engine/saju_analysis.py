# -*- coding: utf-8 -*-
"""
saju_analysis.py
=================
사주 원국(4주 8글자)을 바탕으로:
  - 음양/오행 분포 및 상생상극 관계
  - 십성(十星) 배치
  - 12운성(十二運星) 배치
  - 대운(大運) 산출 (순행/역행, 대운수)
  - 세운(歲運) 산출
  - 주요 신살(神殺): 도화살, 천을귀인, 역마살, 화개살, 문창귀인, 원진살, 백호살
을 계산하는 모듈. 모든 산출은 고정된 수학적 공식/조견표에 기반하며 임의 해석을 하지 않는다.
"""

from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict

from saju_data import (
    CHEONGAN, JIJI, CHEONGAN_OHENG, CHEONGAN_EUMYANG, JIJI_OHENG, JIJI_EUMYANG,
    JIJANGAN, OHENG_LIST, SANGSAENG, SANGGEUK, get_sipseong, get_12unseong,
    GAPJA_60, JIJI_YUKHAP, JIJI_CHUNG, JIJI_SAMHAP, JIJI_HYEONG, JIJI_HAE, JIJI_PA,
)
from saju_core import SajuPillars, get_wolju_ganji, get_yeonju_ganji, MONTH_BRANCH_ORDER
from saju_solar_terms import get_month_jieqi_boundaries, get_lichun_datetime


# ===================================================================
# 1. 오행 분포 및 음양 분포
# ===================================================================
@dataclass
class OhengDistribution:
    counts: Dict[str, int] = field(default_factory=dict)   # {'목':2, '화':1, ...} (천간+지지 본기 기준)
    counts_with_jijanggan: Dict[str, float] = field(default_factory=dict)  # 지장간 비중 포함 가중치
    eumyang_counts: Dict[str, int] = field(default_factory=dict)  # {'양':n, '음':n}

    def most_common(self):
        return max(self.counts, key=lambda k: self.counts[k]) if self.counts else None

    def missing(self):
        return [o for o in OHENG_LIST if self.counts.get(o, 0) == 0]


def calc_oheng_distribution(pillars: SajuPillars) -> OhengDistribution:
    chars = pillars.eight_characters  # [연간,연지,월간,월지,일간,일지,시간,시지]
    counts = {o: 0 for o in OHENG_LIST}
    eumyang_counts = {"양": 0, "음": 0}

    # 천간 4개
    for gan in [chars[0], chars[2], chars[4], chars[6]]:
        counts[CHEONGAN_OHENG[gan]] += 1
        eumyang_counts[CHEONGAN_EUMYANG[gan]] += 1
    # 지지 4개 (본기 오행 기준)
    for ji in [chars[1], chars[3], chars[5], chars[7]]:
        counts[JIJI_OHENG[ji]] += 1
        eumyang_counts[JIJI_EUMYANG[ji]] += 1

    # 지장간까지 포함한 가중치 분포(일수 비중 정규화: 천간 1개=1.0, 지지는 지장간 비중의 합=1.0이 되도록 정규화)
    counts_weighted = {o: 0.0 for o in OHENG_LIST}
    for gan in [chars[0], chars[2], chars[4], chars[6]]:
        counts_weighted[CHEONGAN_OHENG[gan]] += 1.0
    for ji in [chars[1], chars[3], chars[5], chars[7]]:
        hidden = JIJANGAN[ji]
        total_days = sum(d for _, _, d in hidden)
        for gan, _, days in hidden:
            counts_weighted[CHEONGAN_OHENG[gan]] += days / total_days

    return OhengDistribution(counts=counts, counts_with_jijanggan=counts_weighted,
                              eumyang_counts=eumyang_counts)


def analyze_sangsaeng_sanggeuk(pillars: SajuPillars) -> List[str]:
    """4개 천간 사이의 상생상극 관계를 순서대로(연간-월간, 월간-일간, 일간-시간) 분석."""
    chars = pillars.eight_characters
    gans = [chars[0], chars[2], chars[4], chars[6]]
    labels = ["연간-월간", "월간-일간", "일간-시간"]
    results = []
    for i in range(3):
        a, b = gans[i], gans[i + 1]
        oa, ob = CHEONGAN_OHENG[a], CHEONGAN_OHENG[b]
        if oa == ob:
            rel = "비화(比和)"
        elif SANGSAENG[oa] == ob:
            rel = f"{oa}생{ob} 상생"
        elif SANGSAENG[ob] == oa:
            rel = f"{ob}생{oa} 상생(역방향)"
        elif SANGGEUK[oa] == ob:
            rel = f"{oa}극{ob} 상극"
        elif SANGGEUK[ob] == oa:
            rel = f"{ob}극{oa} 상극(역방향)"
        else:
            rel = "무관계"
        results.append(f"{labels[i]}({a}-{b}): {rel}")
    return results


# ===================================================================
# 2. 십성(十星) 배치표
# ===================================================================
def calc_sipseong_table(pillars: SajuPillars) -> Dict[str, str]:
    """일간을 기준으로 연간/월간/시간 및 연지/월지/일지/시지(본기) 십성을 산출."""
    ilgan = pillars.ilgan
    chars = pillars.eight_characters
    yeongan, yeonji, wolgan, wolji, ilgan_, ilji, sigan, siji = chars

    table = {}
    table["연간"] = get_sipseong(ilgan, yeongan)
    table["월간"] = get_sipseong(ilgan, wolgan)
    table["일간"] = "일원(日元, 나 자신)"
    table["시간"] = get_sipseong(ilgan, sigan)

    # 지지는 정기(正氣) 지장간의 천간을 기준으로 십성 판정 (표준 방식)
    def jiji_main_gan(ji):
        hidden = JIJANGAN[ji]
        return [h for h in hidden if h[1] == "정기"][0][0]

    table["연지"] = get_sipseong(ilgan, jiji_main_gan(yeonji))
    table["월지"] = get_sipseong(ilgan, jiji_main_gan(wolji))
    table["일지"] = get_sipseong(ilgan, jiji_main_gan(ilji))
    table["시지"] = get_sipseong(ilgan, jiji_main_gan(siji))
    return table


# ===================================================================
# 3. 12운성(十二運星) 배치표
# ===================================================================
def calc_12unseong_table(pillars: SajuPillars) -> Dict[str, str]:
    ilgan = pillars.ilgan
    chars = pillars.eight_characters
    yeonji, wolji, ilji, siji = chars[1], chars[3], chars[5], chars[7]
    return {
        "연지": get_12unseong(ilgan, yeonji),
        "월지": get_12unseong(ilgan, wolji),
        "일지": get_12unseong(ilgan, ilji),
        "시지": get_12unseong(ilgan, siji),
    }


# ===================================================================
# 4. 대운(大運) 산출
# ===================================================================
YANG_GAN_SET = {"갑", "병", "무", "경", "임"}


def is_forward_daeun(yeongan: str, gender: str) -> bool:
    """
    순행/역행 판정 표준 규칙:
      양남음녀(陽男陰女, 연간이 양간인 남명 또는 연간이 음간인 여명) -> 순행
      음남양녀(陰男陽女, 연간이 음간인 남명 또는 연간이 양간인 여명) -> 역행
    """
    yeongan_is_yang = yeongan in YANG_GAN_SET
    if gender.upper().startswith("M"):
        return yeongan_is_yang
    else:
        return not yeongan_is_yang


@dataclass
class DaeunInfo:
    forward: bool
    daeun_su: int                 # 대운수 (몇 살부터 대운이 바뀌는지)
    pillars: List[str] = field(default_factory=list)   # 각 대운 간지 목록(10년 단위, 8개=80년치)
    start_ages: List[int] = field(default_factory=list)  # 각 대운의 시작 나이


def calc_daeun_su(birth_dt: datetime, forward: bool, tz_offset_hours: float = 9.0) -> int:
    """
    대운수 계산: 출생일로부터 순행이면 다음 절입(節入)까지, 역행이면 직전 절입까지의
    일수를 계산하고, 그 일수를 3으로 나눈 값(소수점 반올림)이 대운수가 된다.
    (전통 공식: 3일 = 1년. 이는 60갑자 1주기=60년과 24절기 주기의 수리적 대응에서 유래)
    """
    jieqi_this = get_month_jieqi_boundaries(birth_dt.year, tz_offset_hours)
    jieqi_prev = get_month_jieqi_boundaries(birth_dt.year - 1, tz_offset_hours)
    jieqi_next = get_month_jieqi_boundaries(birth_dt.year + 1, tz_offset_hours)
    all_jieqi = sorted(jieqi_prev + jieqi_this + jieqi_next, key=lambda x: x[1])

    if forward:
        # 출생일 이후 가장 가까운 절입까지의 일수
        future = [j for j in all_jieqi if j[1] > birth_dt]
        target_dt = future[0][1]
        delta = target_dt - birth_dt
    else:
        # 출생일 이전 가장 가까운 절입까지의 일수
        past = [j for j in all_jieqi if j[1] <= birth_dt]
        target_dt = past[-1][1]
        delta = birth_dt - target_dt

    total_days = delta.total_seconds() / 86400.0
    daeun_su = round(total_days / 3.0)
    return max(daeun_su, 1)  # 최소 1세


def calc_daeun(pillars: SajuPillars, num_periods: int = 8,
                tz_offset_hours: float = 9.0) -> DaeunInfo:
    """대운 목록(기본 8개=80년치, 10년 단위)을 산출."""
    yeongan = pillars.yeonju[0]
    forward = is_forward_daeun(yeongan, pillars.gender)
    daeun_su = calc_daeun_su(pillars.solar_datetime, forward, tz_offset_hours)

    wolgan, wolji = pillars.wolju[0], pillars.wolju[1]
    start_idx = GAPJA_60.index(wolgan + wolji)

    result_pillars = []
    start_ages = []
    for i in range(1, num_periods + 1):
        if forward:
            idx = (start_idx + i) % 60
        else:
            idx = (start_idx - i) % 60
        result_pillars.append(GAPJA_60[idx])
        start_ages.append(daeun_su + (i - 1) * 10)

    return DaeunInfo(forward=forward, daeun_su=daeun_su, pillars=result_pillars,
                      start_ages=start_ages)


# ===================================================================
# 5. 세운(歲運) 산출
# ===================================================================
def calc_seun(target_year: int, tz_offset_hours: float = 9.0) -> str:
    """
    특정 '양력 연도'의 세운 간지를 산출한다.
    절기학상 정확히 하려면 해당 연도의 입춘을 기준으로 절기년을 판정해야 하지만,
    세운은 통상 양력 1/1~12/31 구간의 연간지를 그대로 사용하는 것이 실무 표준이다.
    (입춘 기준 절기년 세운이 필요할 경우 calc_seun_by_ipchun 사용)
    """
    return get_yeonju_ganji(target_year)


def calc_seun_by_ipchun(target_date: datetime, tz_offset_hours: float = 9.0) -> str:
    """입춘 기준으로 정확한 절기년의 세운 간지를 산출."""
    lichun = get_lichun_datetime(target_date.year, tz_offset_hours)
    effective_year = target_date.year if target_date >= lichun else target_date.year - 1
    return get_yeonju_ganji(effective_year)


def calc_seun_list(start_year: int, end_year: int) -> Dict[int, str]:
    return {y: calc_seun(y) for y in range(start_year, end_year + 1)}


# ===================================================================
# 6. 주요 신살(神殺)
# ===================================================================
# 도화살(桃花殺): 삼합의 목욕지(자오묘유)를 기준으로 판정. 연지/일지 삼합국 기준 목욕지.
DOHWA_TABLE = {
    # 삼합국(인오술/신자진/사유축/해묘미) -> 도화지
    frozenset(["인", "오", "술"]): "묘",
    frozenset(["신", "자", "진"]): "유",
    frozenset(["사", "유", "축"]): "오",
    frozenset(["해", "묘", "미"]): "자",
}
SAMHAP_GROUPS = [frozenset(["인", "오", "술"]), frozenset(["신", "자", "진"]),
                  frozenset(["사", "유", "축"]), frozenset(["해", "묘", "미"])]

# 천을귀인(天乙貴人): 일간 기준 조견표 (연해자평/삼명통회 표준)
CHEONEULGWIIN_TABLE = {
    "갑": ["축", "미"], "무": ["축", "미"], "경": ["축", "미"],
    "을": ["자", "신"], "기": ["자", "신"],
    "병": ["해", "유"], "정": ["해", "유"],
    "임": ["묘", "사"], "계": ["묘", "사"],
    "신": ["인", "오"],
}

# 역마살(驛馬殺): 삼합국 기준, 생지(인신사해)의 충 지지
YEOKMA_TABLE = {
    frozenset(["인", "오", "술"]): "신",
    frozenset(["신", "자", "진"]): "인",
    frozenset(["사", "유", "축"]): "해",
    frozenset(["해", "묘", "미"]): "사",
}

# 화개살(華蓋殺): 삼합국 기준 고지(진술축미)
HWAGAE_TABLE = {
    frozenset(["인", "오", "술"]): "술",
    frozenset(["신", "자", "진"]): "진",
    frozenset(["사", "유", "축"]): "축",
    frozenset(["해", "묘", "미"]): "미",
}

# 문창귀인(文昌貴人): 일간 기준 조견표
MUNCHANG_TABLE = {
    "갑": "사", "을": "오", "병": "신", "정": "유", "무": "신",
    "기": "유", "경": "해", "신": "자", "임": "인", "계": "묘",
}

# 원진살(怨嗔殺): 지지 쌍
WONJIN_PAIRS = {
    frozenset(["자", "미"]), frozenset(["축", "오"]), frozenset(["인", "유"]),
    frozenset(["묘", "신"]), frozenset(["진", "해"]), frozenset(["사", "술"]),
}

# 백호살(白虎殺, 백호대살): 특정 60갑자 조합(갑진, 을미, 병술, 정축, 무진, 임술, 계축)
BAEKHO_GANJI = {"갑진", "을미", "병술", "정축", "무진", "임술", "계축"}


def _find_samhap_group(ji: str):
    for grp in SAMHAP_GROUPS:
        if ji in grp:
            return grp
    return None


def calc_sinsal(pillars: SajuPillars) -> Dict[str, List[str]]:
    """
    주요 신살을 산출하여 {신살명: [해당되는 주(柱) 설명]} 형태로 반환.
    기준: 일반적으로 연지(年支) 또는 일지(日支)를 기준지(基準支)로 삼아
    나머지 지지들 중 해당 신살에 해당하는 지지가 있는지 확인한다.
    본 구현은 명리학 실무 표준에 따라 '일지 기준'을 기본으로 하고, '연지 기준'도 함께 표기한다.
    """
    chars = pillars.eight_characters
    yeonji, wolji, ilji, siji = chars[1], chars[3], chars[5], chars[7]
    all_ji = {"연지": yeonji, "월지": wolji, "일지": ilji, "시지": siji}
    ilgan = pillars.ilgan

    result: Dict[str, List[str]] = {}

    # --- 도화살 (일지, 연지 기준 각각) ---
    for base_label, base_ji in [("일지", ilji), ("연지", yeonji)]:
        grp = _find_samhap_group(base_ji)
        if grp:
            dohwa_ji = DOHWA_TABLE[grp]
            hits = [label for label, ji in all_ji.items() if ji == dohwa_ji]
            if hits:
                result.setdefault("도화살(桃花殺)", []).append(
                    f"{base_label}({base_ji}) 기준 도화지={dohwa_ji} → 사주 내 {', '.join(hits)}에 해당"
                )

    # --- 역마살 ---
    for base_label, base_ji in [("일지", ilji), ("연지", yeonji)]:
        grp = _find_samhap_group(base_ji)
        if grp:
            yeokma_ji = YEOKMA_TABLE[grp]
            hits = [label for label, ji in all_ji.items() if ji == yeokma_ji]
            if hits:
                result.setdefault("역마살(驛馬殺)", []).append(
                    f"{base_label}({base_ji}) 기준 역마지={yeokma_ji} → 사주 내 {', '.join(hits)}에 해당"
                )

    # --- 화개살 ---
    for base_label, base_ji in [("일지", ilji), ("연지", yeonji)]:
        grp = _find_samhap_group(base_ji)
        if grp:
            hwagae_ji = HWAGAE_TABLE[grp]
            hits = [label for label, ji in all_ji.items() if ji == hwagae_ji]
            if hits:
                result.setdefault("화개살(華蓋殺)", []).append(
                    f"{base_label}({base_ji}) 기준 화개지={hwagae_ji} → 사주 내 {', '.join(hits)}에 해당"
                )

    # --- 천을귀인 (일간 기준) ---
    gwiin_jis = CHEONEULGWIIN_TABLE.get(ilgan, [])
    hits = [label for label, ji in all_ji.items() if ji in gwiin_jis]
    if hits:
        result["천을귀인(天乙貴人)"] = [f"일간({ilgan}) 기준 귀인지={gwiin_jis} → {', '.join(hits)}에 해당"]

    # --- 문창귀인 (일간 기준) ---
    munchang_ji = MUNCHANG_TABLE.get(ilgan)
    hits = [label for label, ji in all_ji.items() if ji == munchang_ji]
    if hits:
        result["문창귀인(文昌貴人)"] = [f"일간({ilgan}) 기준 문창지={munchang_ji} → {', '.join(hits)}에 해당"]

    # --- 원진살 (지지 쌍 전수 비교) ---
    labels = list(all_ji.keys())
    wonjin_hits = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            pair = frozenset([all_ji[labels[i]], all_ji[labels[j]]])
            if pair in WONJIN_PAIRS and all_ji[labels[i]] != all_ji[labels[j]]:
                wonjin_hits.append(f"{labels[i]}({all_ji[labels[i]]})-{labels[j]}({all_ji[labels[j]]})")
    if wonjin_hits:
        result["원진살(怨嗔殺)"] = wonjin_hits

    # --- 백호살 (연주/월주/일주/시주 60갑자 조합 확인) ---
    baekho_hits = []
    for label, gj in [("연주", pillars.yeonju), ("월주", pillars.wolju),
                       ("일주", pillars.ilju), ("시주", pillars.siju)]:
        if gj in BAEKHO_GANJI:
            baekho_hits.append(f"{label}({gj})")
    if baekho_hits:
        result["백호살(白虎殺)"] = baekho_hits

    return result


# ===================================================================
# 7. 용신(用神)·희신(喜神) 분석 - 표준 억부용신론(抑扶用神論) 기반
# ===================================================================
# 오행별 세력 산정 가중치: 일간 본인은 제외하고, 나머지 7글자(연간/월간/시간의
# 천간 3개 + 연지/월지/일지/시지의 지장간)의 오행을 모두 더해 세력을 계산한다.
# 월지는 월령(月令)을 얻었다고 하여 가중치를 2배로 준다 (명리학 표준 관행).
MONTH_BRANCH_WEIGHT = 2.0


@dataclass
class YongsinResult:
    ilgan_oheng: str                  # 일간의 오행
    is_strong: bool                   # 신강(True)/신약(False)
    strength_score: float             # 일간을 돕는 세력 점수
    weakness_score: float             # 일간을 빼는 세력 점수
    yongsin: str                      # 용신(用神) 오행
    huisin: str                       # 희신(喜神) 오행
    gisin: str                        # 기신(忌神) 오행
    gusin: str                        # 구신(仇神) 오행
    hansin: str                       # 한신(閑神) 오행
    reason: str                       # 판정 근거 요약 문구


def calc_yongsin(pillars: SajuPillars, oheng_dist) -> YongsinResult:
    """
    일간의 신강/신약을 오행 분포(지장간 가중치 포함) 기준으로 판정하고,
    억부법(抑扶法)에 따라 용신/희신/기신/구신/한신 5개 오행을 산출한다.

    신강 -> 일간의 기운을 덜어내는 오행(식상·재성·관성 계열)이 용신이 되어
            기운의 균형을 잡아준다.
    신약 -> 일간을 도와주는 오행(비겁·인성 계열)이 용신이 되어 기운을 보강한다.
    """
    ilgan_oheng = CHEONGAN_OHENG[pillars.ilgan]

    # 지장간까지 포함한 가중치 오행 분포에서, 월지에만 추가 가중치를 부여한다.
    weighted = dict(oheng_dist.counts_with_jijanggan)
    wolji = pillars.wolju[1]
    for gan, _, days in JIJANGAN[wolji]:
        share = (days / sum(d for _, _, d in JIJANGAN[wolji])) * (MONTH_BRANCH_WEIGHT - 1.0)
        weighted[CHEONGAN_OHENG[gan]] = weighted.get(CHEONGAN_OHENG[gan], 0.0) + share

    # 일간을 돕는 오행: 비겁(같은 오행) + 인성(일간을 생하는 오행)
    supporting_ohengs = {ilgan_oheng, [o for o in OHENG_LIST if SANGSAENG[o] == ilgan_oheng][0]}
    # 일간을 빼는 오행: 식상(일간이 생함) + 재성(일간이 극함) + 관성(일간을 극함)
    draining_ohengs = set(OHENG_LIST) - supporting_ohengs

    strength_score = sum(weighted.get(o, 0.0) for o in supporting_ohengs)
    weakness_score = sum(weighted.get(o, 0.0) for o in draining_ohengs)

    is_strong = strength_score >= weakness_score

    def _saeng(o):  # o를 생(生)하는 오행 (인성 방향)
        return [x for x in OHENG_LIST if SANGSAENG[x] == o][0]

    def _geuk(o):  # o를 극(剋)하는 오행
        return [x for x in OHENG_LIST if SANGGEUK[x] == o][0]

    def _piged(o):  # o가 생(生)하는 오행 (식상 방향)
        return SANGSAENG[o]

    def _pigeuk(o):  # o가 극(剋)하는 오행 (재성 방향)
        return SANGGEUK[o]

    if is_strong:
        # 신강: 관성(일간을 극하는 오행)을 용신으로, 재성(일간이 극하는 오행)을 희신으로 우선한다.
        yongsin = _geuk(ilgan_oheng)          # 관성
        huisin = _pigeuk(ilgan_oheng)         # 재성
        gisin = _saeng(ilgan_oheng)           # 인성(신강을 더 강하게 함 -> 기신)
        gusin = ilgan_oheng                   # 비겁(기신을 돕는 오행 -> 구신)
        reason = (
            f"일간 {pillars.ilgan}({ilgan_oheng})을 돕는 세력({strength_score:.1f})이 "
            f"빼내는 세력({weakness_score:.1f})보다 강한 신강(身强) 사주입니다. "
            f"기운을 덜어내는 관성 오행을 용신으로 삼아 균형을 잡습니다."
        )
    else:
        # 신약: 인성(일간을 생하는 오행)을 용신으로, 비겁(같은 오행)을 희신으로 우선한다.
        yongsin = _saeng(ilgan_oheng)         # 인성
        huisin = ilgan_oheng                  # 비겁
        gisin = _pigeuk(ilgan_oheng)          # 재성(신약을 더 약하게 함 -> 기신)
        gusin = _piged(ilgan_oheng)           # 식상(기신을 돕는 오행 -> 구신)
        reason = (
            f"일간 {pillars.ilgan}({ilgan_oheng})을 돕는 세력({strength_score:.1f})이 "
            f"빼내는 세력({weakness_score:.1f})보다 약한 신약(身弱) 사주입니다. "
            f"기운을 보강하는 인성 오행을 용신으로 삼아 균형을 잡습니다."
        )

    used = {yongsin, huisin, gisin, gusin}
    hansin = [o for o in OHENG_LIST if o not in used][0] if len(used) < 5 else yongsin

    return YongsinResult(
        ilgan_oheng=ilgan_oheng, is_strong=is_strong,
        strength_score=round(strength_score, 2), weakness_score=round(weakness_score, 2),
        yongsin=yongsin, huisin=huisin, gisin=gisin, gusin=gusin, hansin=hansin,
        reason=reason,
    )


# ===================================================================
# 8. 격국(格局) 판정 - 월지 지장간 정기(正氣) 기준 표준 8격
# ===================================================================
GYEOKGUK_NAMES = {
    "비견": "건록격(建祿格)", "겁재": "양인격(陽刃格)",
    "식신": "식신격(食神格)", "상관": "상관격(傷官格)",
    "편재": "편재격(偏財格)", "정재": "정재격(正財格)",
    "편관": "편관격(偏官格)", "정관": "정관격(正官格)",
    "편인": "편인격(偏印格)", "정인": "정인격(正印格)",
}

GYEOKGUK_DESC = {
    "건록격(建祿格)": "일간이 월지에서 자신과 같은 비견의 기운을 얻어 자립심과 추진력이 강한 격국입니다.",
    "양인격(陽刃格)": "일간이 월지에서 겁재의 강한 기운을 얻어 승부욕과 결단력이 매우 강한 격국입니다.",
    "식신격(食神格)": "일간의 기운이 월지의 식신으로 흘러, 여유롭고 창의적이며 의식주가 안정된 격국입니다.",
    "상관격(傷官格)": "일간의 기운이 월지의 상관으로 흘러, 재능과 표현력이 뛰어나지만 규범에 얽매이지 않는 격국입니다.",
    "편재격(偏財格)": "일간이 월지의 편재를 극하여 얻는 구조로, 사업 수완과 통 큰 재물운을 지닌 격국입니다.",
    "정재격(正財格)": "일간이 월지의 정재를 극하여 얻는 구조로, 성실하고 계획적인 재물 관리 능력을 지닌 격국입니다.",
    "편관격(偏官格)": "월지의 편관(칠살)이 일간을 극하는 구조로, 강한 책임감과 위기 대응력을 지닌 격국입니다.",
    "정관격(正官格)": "월지의 정관이 일간을 극하는 구조로, 원칙과 명예를 중시하며 조직 생활에 강점을 지닌 격국입니다.",
    "편인격(偏印格)": "월지의 편인이 일간을 생하는 구조로, 독창적 사고와 전문성을 지닌 격국입니다.",
    "정인격(正印格)": "월지의 정인이 일간을 생하는 구조로, 학문과 신뢰를 바탕으로 성장하는 격국입니다.",
}


@dataclass
class GyeokgukResult:
    based_sipseong: str      # 월지 정기가 일간에 대해 갖는 십성
    name: str                # 격국 이름 (예: "정관격(正官格)")
    description: str         # 격국 해설


def calc_gyeokguk(pillars: SajuPillars) -> GyeokgukResult:
    """월지 지장간의 정기(正氣)를 기준으로 일간과의 십성 관계를 판정해 격국을 정한다."""
    wolji = pillars.wolju[1]
    jeonggi_gan = [h for h in JIJANGAN[wolji] if h[1] == "정기"][0][0]
    sipseong = get_sipseong(pillars.ilgan, jeonggi_gan)
    name = GYEOKGUK_NAMES.get(sipseong, "특수격")
    description = GYEOKGUK_DESC.get(name, "특수한 오행 구조를 지닌 격국으로, 일반 격국 이론보다 개별 분석이 필요합니다.")
    return GyeokgukResult(based_sipseong=sipseong, name=name, description=description)


# ===================================================================
# 9. 궁합(宮合) 분석 - 두 사람의 사주 원국 비교
# ===================================================================
@dataclass
class GunghapResult:
    ilgan_a: str                  # 사람A 일간
    ilgan_b: str                  # 사람B 일간
    ilgan_relation: str           # 일간 오행 관계 설명 (상생/상극/비화)
    yukhap_hits: List[str]        # 육합 성립 쌍 목록
    samhap_hits: List[str]        # 삼합 성립 조합 목록
    chung_hits: List[str]         # 충 성립 쌍 목록 (주의 요망)
    hyeong_hae_pa_hits: List[str] # 형/해/파 성립 쌍 목록 (주의 요망)
    score: int                    # 궁합 점수 (0~100)
    grade: str                    # "상" / "중" / "하"
    summary: str                  # 종합 총평 문구


def _oheng_relation(o1: str, o2: str) -> str:
    """오행 o1이 o2에 대해 갖는 관계: 상생(내가 생함)/상생(내가 받음)/상극(내가 극함)/상극(내가 받음)/비화"""
    if o1 == o2:
        return "비화(比和) - 같은 기운으로 서로 잘 통하고 안정적입니다"
    if SANGSAENG[o1] == o2:
        return f"상생(相生) - {o1}이 {o2}를 生하여 도와주는 관계입니다"
    if SANGSAENG[o2] == o1:
        return f"상생(相生) - {o2}이 {o1}를 生하여 도와주는 관계입니다"
    if SANGGEUK[o1] == o2:
        return f"상극(相剋) - {o1}이 {o2}를 剋하여 긴장이 발생할 수 있는 관계입니다"
    if SANGGEUK[o2] == o1:
        return f"상극(相剋) - {o2}이 {o1}를 剋하여 긴장이 발생할 수 있는 관계입니다"
    return "중립"


def calc_gunghap(pillars_a: SajuPillars, pillars_b: SajuPillars) -> GunghapResult:
    """
    두 사람의 사주 원국(4주 8글자)을 비교하여 궁합을 판정한다.
    일간 오행 관계를 기본 축으로 삼고, 두 사람의 지지(연지/월지/일지/시지) 사이에서
    육합/삼합/충/형해파가 몇 건 성립하는지를 가점/감점 요인으로 반영해
    100점 만점 점수와 상/중/하 등급을 산출하는 방식(궁합 판정의 표준적 접근)이다.
    """
    ilgan_a, ilgan_b = pillars_a.ilgan, pillars_b.ilgan
    oheng_a, oheng_b = CHEONGAN_OHENG[ilgan_a], CHEONGAN_OHENG[ilgan_b]
    ilgan_relation = _oheng_relation(oheng_a, oheng_b)

    jiji_a = [pillars_a.yeonju[1], pillars_a.wolju[1], pillars_a.ilju[1], pillars_a.siju[1]]
    jiji_b = [pillars_b.yeonju[1], pillars_b.wolju[1], pillars_b.ilju[1], pillars_b.siju[1]]

    yukhap_hits, samhap_pool, chung_hits, hhp_hits = [], set(), [], []

    for ja in jiji_a:
        for jb in jiji_b:
            pair = tuple(sorted([ja, jb]))
            if pair in JIJI_YUKHAP:
                yukhap_hits.append(f"{ja}-{jb} 육합({JIJI_YUKHAP[pair]})")
            if JIJI_CHUNG.get(ja) == jb:
                chung_hits.append(f"{ja}-{jb} 충(沖)")
            if JIJI_HAE.get(ja) == jb:
                hhp_hits.append(f"{ja}-{jb} 해(害)")
            if JIJI_PA.get(ja) == jb:
                hhp_hits.append(f"{ja}-{jb} 파(破)")

    combined = set(jiji_a) | set(jiji_b)
    for members, result_oheng in JIJI_SAMHAP:
        if set(members).issubset(combined):
            samhap_pool.add(f"{''.join(members)} 삼합({result_oheng})")
    samhap_hits = list(samhap_pool)

    for hyeong_set in JIJI_HYEONG:
        if hyeong_set.issubset(combined) and (hyeong_set & set(jiji_a)) and (hyeong_set & set(jiji_b)):
            hhp_hits.append(f"{''.join(sorted(hyeong_set))} 형(刑)")

    # --- 점수 산출 ---
    score = 60  # 기본 중립 점수
    if "비화" in ilgan_relation or "상생" in ilgan_relation:
        score += 15
    elif "상극" in ilgan_relation:
        score -= 8

    score += min(len(yukhap_hits) * 8, 24)
    score += min(len(samhap_hits) * 10, 20)
    score -= min(len(chung_hits) * 10, 30)
    score -= min(len(hhp_hits) * 6, 18)
    score = max(0, min(100, score))

    if score >= 75:
        grade = "상"
    elif score >= 50:
        grade = "중"
    else:
        grade = "하"

    parts = [f"두 분의 일간 관계는 {ilgan_relation}."]
    if yukhap_hits:
        parts.append(f"지지 육합이 {len(yukhap_hits)}건 성립하여 서로 끌어당기고 조화를 이루는 힘이 있습니다.")
    if samhap_hits:
        parts.append(f"삼합 기운({', '.join(samhap_hits)})이 감지되어 두 사람이 만났을 때 시너지를 내는 구간이 있습니다.")
    if chung_hits:
        parts.append(f"다만 지지 충이 {len(chung_hits)}건 있어 의견 충돌이나 생활 리듬 차이에 유의가 필요합니다.")
    if hhp_hits:
        parts.append(f"형·해·파 관계가 일부 있어 사소한 오해가 쌓이지 않도록 대화가 중요합니다.")
    parts.append(f"종합적으로 이 궁합은 {grade}급({score}점)으로 판단됩니다.")
    summary = " ".join(parts)

    return GunghapResult(
        ilgan_a=ilgan_a, ilgan_b=ilgan_b, ilgan_relation=ilgan_relation,
        yukhap_hits=yukhap_hits, samhap_hits=samhap_hits, chung_hits=chung_hits,
        hyeong_hae_pa_hits=hhp_hits, score=score, grade=grade, summary=summary,
    )


# ===================================================================
# 10. 월별 운세(月運) - 신년 12개월 상세
# ===================================================================
# 양력 1월/2월은 절기상 전년도 12월/입춘 이전에 걸치는 경우가 있으나,
# 프리미엄 리포트의 "1월~12월 캘린더" 형태 안내라는 실용적 목적에 맞춰
# 달력상 1~12월 순서 그대로, 각 월의 절기월지(인월=1이 아니라 양력 월 순서)를
# MONTH_BRANCH_ORDER(인묘진사오미신유술해자축 = 1~12월 근사)에 대응시켜 계산한다.
CALENDAR_MONTH_TO_JIJI = {
    1: "축", 2: "인", 3: "묘", 4: "진", 5: "사", 6: "오",
    7: "미", 8: "신", 9: "유", 10: "술", 11: "해", 12: "자",
}


@dataclass
class WolunItem:
    month: int              # 1~12
    ganji: str               # 월간지 (예: '병인')
    sipseong: str            # 일간 기준 이 달 월간의 십성
    oheng: str                # 월간의 오행
    keyword: str              # 한 줄 요약 키워드


def calc_wolun_list(pillars: SajuPillars, target_year: int) -> List[WolunItem]:
    """
    특정 연도(target_year)의 1월~12월 월운 12개를 산출한다.
    각 달의 월지에 해당 연도 세운 연간을 기준으로 월간을 붙여 월주를 만들고,
    일간과의 십성 관계 및 오행을 함께 반환한다.
    """
    yeonju = calc_seun(target_year)
    yeongan = yeonju[0]

    result = []
    for month in range(1, 13):
        wolji = CALENDAR_MONTH_TO_JIJI[month]
        wolju = get_wolju_ganji(yeongan, wolji)
        wolgan = wolju[0]
        sipseong = get_sipseong(pillars.ilgan, wolgan)
        oheng = CHEONGAN_OHENG[wolgan]
        result.append(WolunItem(
            month=month, ganji=wolju, sipseong=sipseong, oheng=oheng,
            keyword=_wolun_keyword(sipseong),
        ))
    return result


def _wolun_keyword(sipseong: str) -> str:
    """십성별 그 달의 분위기를 한 줄로 요약."""
    table = {
        "비견": "협력과 동료운이 두드러지는 달",
        "겁재": "경쟁과 지출에 유의할 달",
        "식신": "여유와 안정, 미식·취미운이 좋은 달",
        "상관": "표현력이 살아나되 구설을 조심할 달",
        "편재": "활동적인 재물운, 투자·사업 기회의 달",
        "정재": "안정적인 수입과 계획적인 소비의 달",
        "편관": "긴장과 책임이 따르는 도전의 달",
        "정관": "신뢰와 인정, 승진·계약운이 좋은 달",
        "편인": "학습과 통찰, 독립적 사고가 필요한 달",
        "정인": "귀인의 도움과 문서운이 따르는 달",
        "일원(日元, 나 자신)": "본인 중심의 결정이 중요한 달",
    }
    return table.get(sipseong, "무난하게 흘러가는 달")

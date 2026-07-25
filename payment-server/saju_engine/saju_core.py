# -*- coding: utf-8 -*-
"""
saju_core.py
============
만세력 변환 및 사주 원국표(四柱八字) 산출 핵심 로직.

절대 원칙:
  1. 연주(年柱)의 경계는 음력 1월 1일이 아니라 '입춘(立春)' 절입 시각이다.
  2. 월주(月柱)의 경계는 매월 절입(12절: 입춘/경칩/청명/입하/망종/소서/입추/백로/한로/입동/대설/소한)이다.
  3. 일주(日柱)는 60갑자가 하루도 끊기지 않고 순환하는 절대 순환주기이므로,
     기준일(다수의 만세력이 공인하는 날짜)의 간지로부터 날짜 차이(일수)를 정수로 계산하여 구한다.
  4. 시주(時柱)는 일간(日干)에 따라 시지(時支)에 배속되는 천간이 결정되는
     '오호둔시결(五虎遁時訣)' 표준 조견표를 사용한다.
  5. 자시(23:30~01:29 등 자정 전후) 처리는 '조자시/야자시' 논쟁이 있으나,
     본 프로그램은 통용되는 표준(23:30부터 다음날로 간주하는 '자시=하루의 시작' 방식,
     즉 23:30 이후는 다음날 일주를 적용)을 기본값으로 채택하고, 사용자가 옵션으로
     '야자시 미적용(23:30 이전까지는 당일 유지)' 방식도 선택할 수 있도록 한다.
"""

from datetime import datetime, timedelta
from dataclasses import dataclass

from saju_data import (
    CHEONGAN, JIJI, GAPJA_60, CHEONGAN_OHENG, CHEONGAN_EUMYANG,
    JIJI_OHENG, JIJI_EUMYANG, JIJI_ANIMAL, JIJANGAN,
)
from saju_solar_terms import get_lichun_datetime, get_month_jieqi_boundaries

# -----------------------------------------------------------------
# 일주 계산을 위한 60갑자 기준일.
# 1900-01-31 = 갑진일(甲辰日) 은 다수의 한중일 만세력 자료에서 공인되는 기준점 중 하나이다.
# GAPJA_60 리스트에서 "갑진"의 인덱스를 구해 기준 오프셋으로 사용한다.
# -----------------------------------------------------------------
REFERENCE_DATE = datetime(1900, 1, 31)
REFERENCE_GANJI = "갑진"
REFERENCE_INDEX = GAPJA_60.index(REFERENCE_GANJI)  # 갑자 순환에서의 위치(0~59)


def get_ilju_ganji(date_only: datetime) -> str:
    """
    date_only: 시각을 무시한 '역일(曆日, 그날의 자정 기준 날짜)'.
    기준일로부터의 날짜 차이를 60으로 나눈 나머지로 60갑자 인덱스를 구한다.
    """
    d0 = datetime(date_only.year, date_only.month, date_only.day)
    diff_days = (d0 - REFERENCE_DATE).days
    idx = (REFERENCE_INDEX + diff_days) % 60
    return GAPJA_60[idx]


# -----------------------------------------------------------------
# 시주(時柱) 지지 배속: 23:30~01:29=자시, 01:30~03:29=축시 ... (2시간 단위, 30분 오프셋)
# 표준 명리학 시각 구간(태양시 기준 근사, 한국 표준시 KST 사용)
# -----------------------------------------------------------------
SIJI_TABLE = [
    ("자", 23 * 60 + 30, 24 * 60 + 60 + 30),  # 23:30 ~ 01:30 (익일로 넘어가는 특수구간, 별도 처리)
    ("축", 1 * 60 + 30, 3 * 60 + 30),
    ("인", 3 * 60 + 30, 5 * 60 + 30),
    ("묘", 5 * 60 + 30, 7 * 60 + 30),
    ("진", 7 * 60 + 30, 9 * 60 + 30),
    ("사", 9 * 60 + 30, 11 * 60 + 30),
    ("오", 11 * 60 + 30, 13 * 60 + 30),
    ("미", 13 * 60 + 30, 15 * 60 + 30),
    ("신", 15 * 60 + 30, 17 * 60 + 30),
    ("유", 17 * 60 + 30, 19 * 60 + 30),
    ("술", 19 * 60 + 30, 21 * 60 + 30),
    ("해", 21 * 60 + 30, 23 * 60 + 30),
]


def get_siji(hour: int, minute: int) -> str:
    """시/분(0~23,0~59) -> 시지(자축인묘...) 산출. 23:30~01:29 구간은 '자'시."""
    total = hour * 60 + minute
    if total >= 23 * 60 + 30 or total < 1 * 60 + 30:
        return "자"
    for name, start, end in SIJI_TABLE[1:]:
        if start <= total < end:
            return name
    return "자"  # fallback


# -----------------------------------------------------------------
# 오호둔시결(五虎遁時訣) - 일간에 따른 시간 천간 시작점(자시의 천간) 조견표.
# 표준: 갑기일 -> 갑자시부터, 을경일 -> 병자시부터, 병신일 -> 무자시부터,
#       정임일 -> 경자시부터, 무계일 -> 임자시부터.
# -----------------------------------------------------------------
SIGAN_START = {
    "갑": "갑", "기": "갑",
    "을": "병", "경": "병",
    "병": "무", "신": "무",
    "정": "경", "임": "경",
    "무": "임", "계": "임",
}


def get_sigan(ilgan: str, siji: str) -> str:
    """일간과 시지로부터 시간(時干)을 산출."""
    start_gan = SIGAN_START[ilgan]
    start_idx = CHEONGAN.index(start_gan)
    siji_idx = JIJI.index(siji)  # 자=0
    gan_idx = (start_idx + siji_idx) % 10
    return CHEONGAN[gan_idx]


# -----------------------------------------------------------------
# 연주(年柱) 계산: 입춘 이전 출생이면 전년도 간지를 사용.
# 연간지는 60갑자 순환이며, 기준: 1984년=갑자년(甲子年) (표준 공인 값)
# -----------------------------------------------------------------
YEAR_REFERENCE = 1984  # 갑자년
YEAR_REFERENCE_GANJI_INDEX = GAPJA_60.index("갑자")


def get_yeonju_ganji(effective_year: int) -> str:
    diff = effective_year - YEAR_REFERENCE
    idx = (YEAR_REFERENCE_GANJI_INDEX + diff) % 60
    return GAPJA_60[idx]


# -----------------------------------------------------------------
# 월주(月柱) 계산: 연간(年干)에 따라 정월(인월)의 월간이 결정되는
# '오호둔월결(五虎遁月訣)' 표준 조견표를 사용.
#   갑기년 -> 병인월부터, 을경년 -> 무인월부터, 병신년 -> 경인월부터,
#   정임년 -> 임인월부터, 무계년 -> 갑인월부터.
# -----------------------------------------------------------------
WOLGAN_START = {
    "갑": "병", "기": "병",
    "을": "무", "경": "무",
    "병": "경", "신": "경",
    "정": "임", "임": "임",
    "무": "갑", "계": "갑",
}

# 월지 순서(인월부터 시작하여 축월까지 12개월)
MONTH_BRANCH_ORDER = ["인", "묘", "진", "사", "오", "미", "신", "유", "술", "해", "자", "축"]


def get_wolju_ganji(yeongan: str, wolji: str) -> str:
    """연간과 월지로부터 월간지를 산출."""
    start_gan = WOLGAN_START[yeongan]
    start_idx = CHEONGAN.index(start_gan)
    month_offset = MONTH_BRANCH_ORDER.index(wolji)  # 인=0
    gan_idx = (start_idx + month_offset) % 10
    return CHEONGAN[gan_idx] + wolji


@dataclass
class SajuPillars:
    """사주 원국표 결과."""
    solar_datetime: datetime          # 입력된 양력 생년월일시
    effective_year: int                # 입춘 기준 절기년(연주 산출에 사용된 연도)
    yeonju: str                        # 연주 (예: '갑자')
    wolju: str                         # 월주
    ilju: str                          # 일주
    siju: str                          # 시주
    gender: str                        # 'M' / 'F'
    is_yaja_boundary_applied: bool = True  # 야자시/조자시 경계 적용 여부

    @property
    def eight_characters(self):
        """8글자를 순서대로 리스트로 반환: [연간,연지,월간,월지,일간,일지,시간,시지]"""
        return [
            self.yeonju[0], self.yeonju[1],
            self.wolju[0], self.wolju[1],
            self.ilju[0], self.ilju[1],
            self.siju[0], self.siju[1],
        ]

    @property
    def ilgan(self):
        """일간(日干) - 사주 해석의 기준(나 자신)."""
        return self.ilju[0]

    def as_table(self):
        """연/월/일/시 순서의 (천간,지지) 표."""
        return {
            "년주": (self.yeonju[0], self.yeonju[1]),
            "월주": (self.wolju[0], self.wolju[1]),
            "일주": (self.ilju[0], self.ilju[1]),
            "시주": (self.siju[0], self.siju[1]),
        }


def calculate_saju(birth_dt: datetime, gender: str, tz_offset_hours: float = 9.0,
                    apply_yaja_boundary: bool = True) -> SajuPillars:
    """
    양력 생년월일시(KST 기준 datetime)로부터 사주 원국표(4주 8글자)를 산출한다.

    birth_dt: 양력 출생 datetime (naive, KST로 간주)
    gender: 'M' 또는 'F' (대운 순행/역행 판정에 사용)
    apply_yaja_boundary: True면 23:30 이후 출생을 다음날로 간주하는 표준 자시 규칙 적용.
                         False면 자정(00:00) 기준으로만 날짜를 바꾸는 방식(일부 유파) 적용.
    """
    # ---- 1. 일주 계산에 사용할 '역일(曆日)' 결정 (자시 경계 처리) ----
    if apply_yaja_boundary and birth_dt.hour == 23 and birth_dt.minute >= 30:
        date_for_ilju = birth_dt + timedelta(days=1)
    else:
        date_for_ilju = birth_dt

    ilju = get_ilju_ganji(date_for_ilju)
    ilgan = ilju[0]

    # ---- 2. 연주 계산 (입춘 기준) ----
    lichun_this_year = get_lichun_datetime(birth_dt.year, tz_offset_hours)
    if birth_dt < lichun_this_year:
        effective_year = birth_dt.year - 1
    else:
        effective_year = birth_dt.year
    yeonju = get_yeonju_ganji(effective_year)
    yeongan = yeonju[0]

    # ---- 3. 월주 계산 (절입 기준) ----
    jieqi_list = get_month_jieqi_boundaries(birth_dt.year, tz_offset_hours)
    # 입력 시각 직전에 발생한 절입을 찾는다.
    prior = [j for j in jieqi_list if j[1] <= birth_dt]
    if prior:
        _, _, wolji = prior[-1]
    else:
        # 해당 연도 목록에 없으면(연초 소한 이전) 전년도 12월 대설~소한 구간
        earlier = get_month_jieqi_boundaries(birth_dt.year - 1, tz_offset_hours)
        prior_earlier = [j for j in earlier if j[1] <= birth_dt]
        wolji = prior_earlier[-1][2] if prior_earlier else "축"
    wolju = get_wolju_ganji(yeongan, wolji)

    # ---- 4. 시주 계산 ----
    siji = get_siji(birth_dt.hour, birth_dt.minute)
    sigan = get_sigan(ilgan, siji)
    siju = sigan + siji

    return SajuPillars(
        solar_datetime=birth_dt,
        effective_year=effective_year,
        yeonju=yeonju,
        wolju=wolju,
        ilju=ilju,
        siju=siju,
        gender=gender,
        is_yaja_boundary_applied=apply_yaja_boundary,
    )


def format_pillars_table(pillars: SajuPillars) -> str:
    """사주 원국표를 사람이 읽기 좋은 텍스트 표 형태로 출력."""
    t = pillars.as_table()
    lines = []
    lines.append(f"{'구분':<6}{'시주':^8}{'일주':^8}{'월주':^8}{'년주':^8}")
    lines.append(f"{'천간':<6}{t['시주'][0]:^8}{t['일주'][0]:^8}{t['월주'][0]:^8}{t['년주'][0]:^8}")
    lines.append(f"{'지지':<6}{t['시주'][1]:^8}{t['일주'][1]:^8}{t['월주'][1]:^8}{t['년주'][1]:^8}")
    return "\n".join(lines)

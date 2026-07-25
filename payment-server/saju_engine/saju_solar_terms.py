# -*- coding: utf-8 -*-
"""
saju_solar_terms.py
====================
24절기(입춘, 경칩, 청명 ... ) 발생 시각을 태양의 겉보기 황경(apparent ecliptic longitude)을
기준으로 계산하는 모듈.

명리학(사주학)에서 연주(年柱)의 경계는 '입춘(立春)', 월주(月柱)의 경계는 매 절입(節入)
시각(입춘/경칩/청명/입하/망종/소서/입추/백로/한로/입동/대설/소한)이다.
음력 1월 1일(설날)이 아니라 반드시 태양의 위치(황경)로 정해지는 절기를 기준으로 해야
정확한 사주 원국표가 나온다는 것이 자평진전(子平眞詮)/삼명통회(三命通會) 이래의 정론이다.

본 모듈은 Jean Meeus, "Astronomical Algorithms" (2nd ed.) 에 기술된
'낮은 정밀도(low precision)' 태양 겉보기 황경 계산식을 구현한다.
이 공식은 오차가 대략 ±0.01도(=시간으로 환산 시 수 분 이내) 수준으로,
명리학적 절입시각 계산(분 단위 정밀도면 충분)에는 실용상 충분한 정밀도를 제공한다.

참고: 실제 상용 만세력 프로그램들(예: 고전 만세력 서적, 국내 유명 만세력 소프트웨어)도
동일한 저정밀도 태양 황경 공식 계열을 사용하여 절입 시각을 계산한다.
"""

import math
from datetime import datetime, timedelta

# -----------------------------------------------------------------
# 24절기 이름과, 태양 황경(0~360도) 상의 위치.
# 황경 315도 = 입춘. 이후 15도씩 증가할 때마다 다음 절기.
# 명리학에서는 이 중 '절(節)'만 월주 경계로 사용한다 (12절).
# 기(氣, 중기)는 절기 이름표에는 포함하되 월주 경계로는 쓰지 않는다.
# -----------------------------------------------------------------
SOLAR_TERMS = [
    ("소한", 285), ("대한", 300), ("입춘", 315), ("우수", 330),
    ("경칩", 345), ("춘분", 0),   ("청명", 15),  ("곡우", 30),
    ("입하", 45),  ("소만", 60),  ("망종", 75),  ("하지", 90),
    ("소서", 105), ("대서", 120), ("입추", 135), ("처서", 150),
    ("백로", 165), ("추분", 180), ("한로", 195), ("상강", 210),
    ("입동", 225), ("소설", 240), ("대설", 255), ("동지", 270),
]

# 월주(月柱) 경계를 정하는 '절입(節入)' 12절. (절기 이름, 황경, 해당 지지)
# 인월(寅月)은 입춘부터 시작 - 명리학 표준.
JIEQI_TO_MONTH_BRANCH = [
    ("입춘", 315, "인"),
    ("경칩", 345, "묘"),
    ("청명", 15, "진"),
    ("입하", 45, "사"),
    ("망종", 75, "오"),
    ("소서", 105, "미"),
    ("입추", 135, "신"),
    ("백로", 165, "유"),
    ("한로", 195, "술"),
    ("입동", 225, "해"),
    ("대설", 255, "자"),
    ("소한", 285, "축"),
]


def _julian_day(dt_utc: datetime) -> float:
    """UTC datetime -> Julian Day (JD)"""
    y = dt_utc.year
    m = dt_utc.month
    d = (dt_utc.day + dt_utc.hour / 24 + dt_utc.minute / 1440
         + dt_utc.second / 86400)
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5
    return jd


def _julian_day_to_datetime(jd: float) -> datetime:
    """Julian Day -> UTC datetime"""
    jd += 0.5
    z = int(jd)
    f = jd - z
    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - alpha // 4
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day = b - d - int(30.6001 * e) + f
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715

    day_int = int(day)
    frac = day - day_int
    hours = frac * 24
    hour = int(hours)
    minutes = (hours - hour) * 60
    minute = int(minutes)
    second = int(round((minutes - minute) * 60))
    result = datetime(year, month, day_int, hour, minute, 0) + timedelta(seconds=second)
    return result


def _solar_apparent_longitude(jd: float) -> float:
    """
    Jean Meeus 저정밀도 공식에 따른 태양의 겉보기 황경(도, 0~360)을 계산.
    jd: Julian Day (Dynamical Time 기준. 저정밀도 용도이므로 UT와의 차이(ΔT)는
        절기 계산 정밀도(수 분)에 비해 영향이 작으므로 근사적으로 무시 가능하나,
        본 구현에서는 ΔT 보정도 함께 적용하여 정밀도를 높인다.)
    """
    t = (jd - 2451545.0) / 36525.0  # 2000.0 기준 율리우스 세기

    # 태양의 평균 황경 (도)
    l0 = 280.46646 + t * (36000.76983 + t * 0.0003032)
    l0 %= 360.0

    # 태양의 평균 근점이각
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    m_rad = math.radians(m % 360.0)

    # 이심률
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)

    # 중심차(equation of center)
    c = ((1.914602 - t * (0.004817 + 0.000014 * t)) * math.sin(m_rad)
         + (0.019993 - 0.000101 * t) * math.sin(2 * m_rad)
         + 0.000289 * math.sin(3 * m_rad))

    true_long = l0 + c  # 실제(진) 황경

    # 겉보기 황경 보정 (장동 + 광행차)
    omega = 125.04 - 1934.136 * t
    apparent_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    return apparent_long % 360.0


def _delta_t_seconds(year: float) -> float:
    """
    ΔT(TT-UT) 근사 계산 (NASA/Espenak 다항식, 2005~2050년 구간 근사).
    사주 계산에 사용되는 근현대 범위(1900~2100)에 대해 적절한 근사값을 제공한다.
    """
    if 2005 <= year <= 2050:
        t = year - 2000
        return 62.92 + 0.32217 * t + 0.005589 * t**2
    elif 1986 <= year < 2005:
        t = year - 2000
        return 63.86 + 0.3345 * t - 0.060374 * t**2 + 0.0017275 * t**3 \
            + 0.000651814 * t**4 + 0.00002373599 * t**5
    elif 1961 <= year < 1986:
        t = year - 1975
        return 45.45 + 1.067 * t - t**2 / 260 - t**3 / 718
    elif 1900 <= year < 1961:
        t = year - 1920
        return 21.20 + 0.84493 * t - 0.076100 * t**2 + 0.0020936 * t**3
    else:
        t = year - 2000
        return 62.92 + 0.32217 * t + 0.005589 * t**2


def solar_longitude_at(dt_local: datetime, tz_offset_hours: float = 9.0) -> float:
    """주어진 현지시각(기본 KST, UTC+9)의 태양 겉보기 황경을 반환."""
    dt_utc = dt_local - timedelta(hours=tz_offset_hours)
    jd_ut = _julian_day(dt_utc)
    dt_val = _delta_t_seconds(dt_local.year)
    jd_tt = jd_ut + dt_val / 86400.0
    return _solar_apparent_longitude(jd_tt)


def find_solar_term_datetime(target_longitude: float, year: int, month_hint: int,
                              tz_offset_hours: float = 9.0) -> datetime:
    """
    특정 황경(target_longitude, 0~360)에 태양이 도달하는 정확한 시각(KST)을
    이분법(bisection)으로 탐색한다.

    year, month_hint: 탐색 시작 구간을 좁히기 위한 대략적 힌트(해당 절기가 속할 것으로
                       예상되는 연/월). 탐색은 그 앞뒤로 45일 범위에서 수행한다.
    """
    center = datetime(year, month_hint, 15, 12, 0, 0)
    lo = center - timedelta(days=20)
    hi = center + timedelta(days=20)

    def angle_diff(dt):
        lon = solar_longitude_at(dt, tz_offset_hours)
        diff = (lon - target_longitude + 180) % 360 - 180
        return diff

    d_lo = angle_diff(lo)
    d_hi = angle_diff(hi)

    # 구간 내에 부호가 바뀌는 지점이 없으면 탐색 범위를 확장
    expand = 0
    while d_lo * d_hi > 0 and expand < 6:
        lo -= timedelta(days=15)
        hi += timedelta(days=15)
        d_lo = angle_diff(lo)
        d_hi = angle_diff(hi)
        expand += 1

    for _ in range(60):
        mid = lo + (hi - lo) / 2
        d_mid = angle_diff(mid)
        if abs(d_mid) < 1e-7:
            break
        if d_lo * d_mid <= 0:
            hi = mid
            d_hi = d_mid
        else:
            lo = mid
            d_lo = d_mid

    result = lo + (hi - lo) / 2
    # 초 단위 반올림
    result = result.replace(microsecond=0)
    if result.second >= 30:
        result = result.replace(second=0) + timedelta(minutes=1)
    else:
        result = result.replace(second=0)
    return result


_solar_term_cache = {}


def get_year_solar_terms(year: int, tz_offset_hours: float = 9.0):
    """
    해당 '양력 연도'를 전후로 걸친 24절기 발생시각을 모두 계산하여
    [(절기명, 황경, datetime), ...] 리스트로 반환 (시간순 정렬).
    전년도 12월 하순 ~ 익년 1월 초순까지 포함하여 연/월주 경계 판정에 문제가 없도록 한다.
    """
    if year in _solar_term_cache:
        return _solar_term_cache[year]

    results = []
    # 절기가 대략 어느 양력월에 속하는지의 힌트 테이블
    month_hint_map = {
        "소한": 1, "대한": 1, "입춘": 2, "우수": 2, "경칩": 3, "춘분": 3,
        "청명": 4, "곡우": 4, "입하": 5, "소만": 5, "망종": 6, "하지": 6,
        "소서": 7, "대서": 7, "입추": 8, "처서": 8, "백로": 9, "추분": 9,
        "한로": 10, "상강": 10, "입동": 11, "소설": 11, "대설": 12, "동지": 12,
    }

    for y in (year - 1, year, year + 1):
        for name, lon in SOLAR_TERMS:
            hint_month = month_hint_map[name]
            dt = find_solar_term_datetime(lon, y, hint_month, tz_offset_hours)
            results.append((name, lon, dt))

    results.sort(key=lambda x: x[2])
    _solar_term_cache[year] = results
    return results


def get_month_jieqi_boundaries(year: int, tz_offset_hours: float = 9.0):
    """
    해당 연도 부근의 '절입(12절)' 경계만 추출하여 [(절기명, datetime, 지지), ...] 반환.
    월주 산출 시 이 리스트에서 입력 시각 직전의 절입을 찾아 월지를 정한다.
    """
    all_terms = get_year_solar_terms(year, tz_offset_hours)
    jie_names = {name for name, _, _ in JIEQI_TO_MONTH_BRANCH}
    branch_map = {name: branch for name, _, branch in JIEQI_TO_MONTH_BRANCH}
    out = []
    for name, lon, dt in all_terms:
        if name in jie_names:
            out.append((name, dt, branch_map[name]))
    out.sort(key=lambda x: x[1])
    return out


def get_lichun_datetime(year: int, tz_offset_hours: float = 9.0) -> datetime:
    """해당 연도의 입춘(立春) 시각 반환 (연주 경계 판정용)."""
    terms = get_year_solar_terms(year, tz_offset_hours)
    for name, lon, dt in terms:
        if name == "입춘" and dt.year == year:
            return dt
    # fallback
    return find_solar_term_datetime(315, year, 2, tz_offset_hours)
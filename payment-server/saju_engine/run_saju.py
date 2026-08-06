# -*- coding: utf-8 -*-
"""
run_saju.py
===========
Node.js 결제 서버가 child_process로 호출하는 CLI 인터페이스.
표준입력(stdin)으로 JSON 형태의 의뢰인 정보를 받아서 사주 계산을 수행하고,
결과를 표준출력(stdout)으로 JSON 형태로 반환한다.

사용법:
  echo '{...}' | python3 run_saju.py
"""
import sys
import json
from datetime import datetime

from saju_core import calculate_saju
from saju_analysis import (
    calc_oheng_distribution, analyze_sangsaeng_sanggeuk, calc_sipseong_table,
    calc_12unseong_table, calc_daeun, calc_seun_list, calc_sinsal,
    calc_yongsin, calc_gyeokguk, calc_wolun_list, calc_gunghap,
)
from saju_interpretation_db import (
    get_oheng_basic, get_oheng_missing, get_category_text, get_sinsal_text,
    get_gaeunbeop, get_category_text_extended, get_oheng_basic_extended,
    get_sinsal_text_extended, get_daeun_quality_text_extended,
    get_saju_origin_text, get_gyeokguk_text_extended, get_daeun_seun_flow_text,
    get_sinnyeon_unse_text, get_pyeongsaeng_unse_text, get_taekil_seongmyeonghak_text,
    get_wolun_text_extended, get_oheng_analysis_detail_text, get_sipseong_layout_text,
    get_yongsin_analysis_text, get_gunghap_summary_extended, get_gunghap_strength_text,
    get_gunghap_caution_text, get_oheng_missing_extended,
)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "message": f"입력 JSON 파싱 실패: {e}"}, ensure_ascii=False))
        sys.exit(1)

    try:
        name = payload.get("name", "의뢰인")
        gender = payload.get("gender", "M")
        calendar_type = payload.get("calendarType", "양력")
        year = int(payload["year"])
        month = int(payload["month"])
        day = int(payload["day"])
        hour = int(payload.get("hour", 0) or 0)
        minute = int(payload.get("minute", 0) or 0)

        # 음력 입력이면 양력으로 변환한다(윤달 지원). 어르신 사용자는 음력 생일이 많다.
        # 변환 전 '음력 원본'을 따로 보관해, 결과지에 '음력 원본 + 양력 변환'을 함께 표시한다.
        birth_lunar = None
        if calendar_type == "음력":
            is_leap = bool(payload.get("isLeapMonth", False))
            birth_lunar = {"year": year, "month": month, "day": day, "isLeap": is_leap}
            try:
                from korean_lunar_calendar import KoreanLunarCalendar
                cal = KoreanLunarCalendar()
                cal.setLunarDate(year, month, day, is_leap)
                if not cal.solarYear:
                    raise ValueError("해당 음력 날짜를 변환할 수 없습니다.")
                year, month, day = cal.solarYear, cal.solarMonth, cal.solarDay
            except Exception as e:
                print(json.dumps({
                    "success": False,
                    "message": f"음력 생년월일 변환에 실패했습니다: {e}. 날짜(특히 윤달 여부)를 확인해 주세요."
                }, ensure_ascii=False))
                sys.exit(1)

        birth_dt = datetime(year, month, day, hour, minute)
        pillars = calculate_saju(birth_dt, gender)

        oheng_dist = calc_oheng_distribution(pillars)
        sangsaeng = analyze_sangsaeng_sanggeuk(pillars)
        sipseong = calc_sipseong_table(pillars)
        unseong = calc_12unseong_table(pillars)
        daeun = calc_daeun(pillars)
        this_year = datetime.now().year
        seun = calc_seun_list(this_year, this_year + 2)
        sinsal = calc_sinsal(pillars)
        yongsin = calc_yongsin(pillars, oheng_dist)
        gyeokguk = calc_gyeokguk(pillars)
        wolun_list = calc_wolun_list(pillars, this_year)

        most_oheng = oheng_dist.most_common()
        missing_ohengs = oheng_dist.missing()
        representative_sipseong = sipseong.get("월지", "비견")

        # 궁합 상품(2인 사주)인 경우, 상대방 생년월일이 payload에 함께 들어온다.
        gunghap_result = None
        person2 = payload.get("person2")
        if person2 and person2.get("year") and person2.get("month") and person2.get("day"):
            try:
                p2_gender = person2.get("gender", "F")
                p2_dt = datetime(
                    int(person2["year"]), int(person2["month"]), int(person2["day"]),
                    int(person2.get("hour", 0) or 0), int(person2.get("minute", 0) or 0),
                )
                pillars2 = calculate_saju(p2_dt, p2_gender)
                gh = calc_gunghap(pillars, pillars2)
                # --- 상대방(배우자) 사주 분석 : '상대가 어떤 사람인지' 결과지에 담기 위함 ---
                oheng_dist2 = calc_oheng_distribution(pillars2)
                gyeokguk2 = calc_gyeokguk(pillars2)
                yongsin2 = calc_yongsin(pillars2, oheng_dist2)
                sipseong2 = calc_sipseong_table(pillars2)
                unseong2 = calc_12unseong_table(pillars2)
                sinsal2 = calc_sinsal(pillars2)
                daeun2 = calc_daeun(pillars2)
                most_oheng2 = oheng_dist2.most_common()
                missing_ohengs2 = oheng_dist2.missing()
                partner = {
                    "name": person2.get("name") or "배우자",
                    "gender": p2_gender,
                    "birth": {"year": int(person2["year"]), "month": int(person2["month"]),
                              "day": int(person2["day"]),
                              "hour": int(person2.get("hour", 0) or 0),
                              "minute": int(person2.get("minute", 0) or 0),
                              "calendarType": person2.get("calendarType", "양력"),
                              "timeUnknown": (person2.get("hour") is None)},
                    "pillars": {
                        "연주": list(pillars2.yeonju), "월주": list(pillars2.wolju),
                        "일주": list(pillars2.ilju), "시주": list(pillars2.siju),
                    },
                    "ilgan": pillars2.ilgan,
                    "ohengDistribution": oheng_dist2.counts,
                    "ohengMostCommon": most_oheng2,
                    "ohengMissing": missing_ohengs2,
                    "sipseong": sipseong2,
                    "unseong12": unseong2,
                    "sinsal": sinsal2,
                    "gyeokguk": {"name": gyeokguk2.name, "description": gyeokguk2.description},
                    "yongsin": {"yongsin": yongsin2.yongsin, "huisin": yongsin2.huisin,
                                "gisin": yongsin2.gisin, "gusin": yongsin2.gusin,
                                "is_strong": yongsin2.is_strong},
                    "daeun": {"pillars": daeun2.pillars, "startAges": daeun2.start_ages},
                    "personality": get_saju_origin_text(most_oheng2, pillars2.ilgan) if most_oheng2 else "",
                }
                gunghap_result = {
                    "ilgan_a": gh.ilgan_a, "ilgan_b": gh.ilgan_b,
                    "ilgan_relation": gh.ilgan_relation,
                    "yukhap_hits": gh.yukhap_hits, "samhap_hits": gh.samhap_hits,
                    "chung_hits": gh.chung_hits, "hyeong_hae_pa_hits": gh.hyeong_hae_pa_hits,
                    "score": gh.score, "grade": gh.grade, "summary": gh.summary,
                    "partner": partner,
                    "총평해설": get_gunghap_summary_extended(gh.summary, gh.score, gh.grade, gh.ilgan_relation),
                    "강점해설": get_gunghap_strength_text(gh.yukhap_hits, gh.samhap_hits, gh.ilgan_relation),
                    "주의점해설": get_gunghap_caution_text(gh.chung_hits, gh.hyeong_hae_pa_hits),
                }
            except Exception:
                gunghap_result = None

        result = {
            "success": True,
            "name": name,
            "gender": gender,
            "birth": {"year": year, "month": month, "day": day, "hour": hour, "minute": minute},
            "birthCalendarType": calendar_type,
            "birthLunar": birth_lunar,
            "pillars": {
                "연주": list(pillars.yeonju),
                "월주": list(pillars.wolju),
                "일주": list(pillars.ilju),
                "시주": list(pillars.siju),
            },
            "ilgan": pillars.ilgan,
            "ohengDistribution": oheng_dist.counts,
            "ohengMostCommon": most_oheng,
            "ohengMissing": missing_ohengs,
            "sangsaeng": sangsaeng,
            "sipseong": sipseong,
            "unseong12": unseong,
            "daeun": {
                "forward": daeun.forward,
                "daeunSu": daeun.daeun_su,
                "pillars": daeun.pillars,
                "startAges": daeun.start_ages,
            },
            "seun": seun,
            "sinsal": sinsal,
            "yongsin": {
                "ilgan_oheng": yongsin.ilgan_oheng, "is_strong": yongsin.is_strong,
                "strength_score": yongsin.strength_score, "weakness_score": yongsin.weakness_score,
                "yongsin": yongsin.yongsin, "huisin": yongsin.huisin, "gisin": yongsin.gisin,
                "gusin": yongsin.gusin, "hansin": yongsin.hansin, "reason": yongsin.reason,
            },
            "gyeokguk": {
                "based_sipseong": gyeokguk.based_sipseong, "name": gyeokguk.name,
                "description": gyeokguk.description,
            },
            "wolun": [
                {"month": w.month, "ganji": w.ganji, "sipseong": w.sipseong,
                 "oheng": w.oheng, "keyword": w.keyword}
                for w in wolun_list
            ],
            "gunghap": gunghap_result,
            "interpretation": {
                "ohengBasic": get_oheng_basic_extended(most_oheng) if most_oheng else "",
                "ohengMissingTexts": [get_oheng_missing_extended(o) for o in missing_ohengs],
                "gaeunbeop": [get_gaeunbeop(o) for o in missing_ohengs],
                "사주원국해설": get_saju_origin_text(most_oheng, pillars.ilgan) if most_oheng else "",
                "오행해설": get_oheng_analysis_detail_text(oheng_dist.counts, most_oheng, missing_ohengs) if most_oheng else "",
                "십성해설": get_sipseong_layout_text(sipseong, representative_sipseong),
                "용신해설": get_yongsin_analysis_text({
                    "is_strong": yongsin.is_strong, "yongsin": yongsin.yongsin,
                    "huisin": yongsin.huisin, "gisin": yongsin.gisin,
                }),
                "격국해설": get_gyeokguk_text_extended(gyeokguk.name, gyeokguk.description, gyeokguk.based_sipseong),
                "대운세운해설": get_daeun_seun_flow_text(daeun.forward, daeun.daeun_su),
                "타고난성향": get_category_text_extended("타고난성향", representative_sipseong),
                "직장운이직운승진운": get_category_text_extended("직장운이직운승진운", representative_sipseong),
                "사업운창업운": get_category_text_extended("사업운창업운", representative_sipseong),
                "재물운": get_category_text_extended("재물운", representative_sipseong),
                "시험운": get_category_text_extended("시험운", representative_sipseong),
                "문서운": get_category_text_extended("문서운", representative_sipseong),
                "연애운인연운": get_category_text_extended("연애운인연운", representative_sipseong),
                "결혼운배우자운": get_category_text_extended("결혼운배우자운", representative_sipseong),
                "자녀운": get_category_text_extended("자녀운", representative_sipseong),
                "가족운": get_category_text_extended("가족운자녀운", representative_sipseong),
                "대인관계운": get_category_text_extended("대인관계운", representative_sipseong),
                "건강운": get_category_text_extended("건강운", representative_sipseong),
                "이동운": get_category_text_extended("이동운", representative_sipseong),
                "귀인운": get_category_text_extended("귀인운", representative_sipseong),
                "신년운세": get_sinnyeon_unse_text(name, most_oheng, representative_sipseong) if most_oheng else "",
                "평생운세총평": get_pyeongsaeng_unse_text(name, gyeokguk.name, yongsin.yongsin),
                "택일성명학안내": get_taekil_seongmyeonghak_text(most_oheng, missing_ohengs) if most_oheng else "",
                "신살": {k: get_sinsal_text_extended(k) for k in sinsal.keys()},
                **{
                    f"{w.month}월운세": get_wolun_text_extended(w.month, w.sipseong, w.oheng, w.keyword, w.ganji)
                    for w in wolun_list
                },
                **({
                    "궁합총평": gunghap_result["총평해설"],
                    "궁합장점": gunghap_result["강점해설"],
                    "궁합주의점및개운법": gunghap_result["주의점해설"],
                } if gunghap_result else {}),
            },
        }

        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"success": False, "message": f"사주 계산 중 오류: {e}"}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

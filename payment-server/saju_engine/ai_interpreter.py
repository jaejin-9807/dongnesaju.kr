# -*- coding: utf-8 -*-
"""
ai_interpreter.py
==================
계산된 사주 원국(오행/십성/12운성/대운/세운/신살/용신/격국/궁합/월운 등
수학적 산출 결과) 전체를 Claude API에 넘겨서, 그 사람만의 실제 운세풀이
문장을 생성한다. 60페이지 이상 프리미엄 리포트를 위해, 한 번의 호출로
전부 받으면 응답이 너무 길어져 잘리거나 타임아웃이 나기 쉬우므로
목차 파트별로 6개 그룹으로 나누어 순차 호출한다.

★ 중요 원칙
  - 이 모듈은 saju_analysis.py / saju_core.py가 산출한 '계산 결과'만 AI에게
    전달한다. AI가 사주 명식 자체를 새로 지어내지 않고, 이미 정확하게 계산된
    값을 바탕으로 "해석 문장"만 작성하도록 프롬프트를 설계한다.
  - .env의 ANTHROPIC_API_KEY가 없거나 호출이 실패하면 예외를 그대로 올려서,
    호출부(make_pdf.py)가 기존 고정 문구 DB로 자동 폴백할 수 있게 한다.
  - 관리자가 "운세풀이 시작하기" 또는 "샘플 PDF 생성" 버튼을 눌렀을 때만
    호출되는 지점(make_pdf.py)에서만 사용하므로, 고객이 주문만 넣는 단계에서는
    이 모듈이 호출되지 않는다 (= API 비용이 발생하지 않는다).
  - 그룹 하나가 실패해도 전체를 포기하지 않고, 해당 그룹만 폴백 문구로
    대체한 뒤 나머지 그룹은 계속 진행한다(부분 실패 허용).
"""
import json
import os
import time
import urllib.request
import urllib.error

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_TIMEOUT = 180  # 항목이 많아 응답이 길어지므로 60초 -> 180초로 상향

# ---------------------------------------------------------------
# 1부(기초분석 6장) + 2부(12대 운세) + 3부(확장운세 3장) + 5부(궁합 3장)
# + 6부(총론/부록 2장)에서 AI가 문장을 채워야 하는 항목들을 그룹으로 분류.
# 4부(월별운세 12개월)는 항목 수가 많아 별도 그룹 2개로 다시 나눈다.
# ---------------------------------------------------------------
GROUPS = [
    {
        "id": "basic",
        "title": "1부. 정통 사주명리 기초분석",
        "keys": [
            ("사주원국해설", "사주팔자 원국 총평"),
            ("오행해설", "오행 분석 상세 해설"),
            ("십성해설", "십성(十星) 배치 해설"),
            ("용신해설", "용신·희신 분석 해설"),
            ("격국해설", "격국 분석 해설"),
            ("대운세운해설", "대운·세운 흐름 해설"),
        ],
    },
    {
        "id": "life1",
        "title": "2부. 12대 개별 운세 (1/2)",
        "keys": [
            ("재물운", "재물운·금전운"),
            ("사업운창업운", "사업운·창업운"),
            ("직장운이직운승진운", "직장운·이직운·승진운"),
            ("시험운", "시험운·합격운"),
            ("문서운", "문서운·계약운"),
            ("연애운인연운", "연애운·인연운"),
        ],
    },
    {
        "id": "life2",
        "title": "2부. 12대 개별 운세 (2/2)",
        "keys": [
            ("결혼운배우자운", "결혼운·배우자운"),
            ("자녀운", "자녀운"),
            ("가족운", "가족운"),
            ("건강운", "건강운"),
            ("이동운", "이동운·이사운"),
            ("귀인운", "귀인운·인복"),
        ],
    },
    {
        "id": "yearly",
        "title": "3부. 신년 운세 및 6부. 평생운세 총론",
        "keys": [
            ("신년운세", "올해 신년 운세 총평"),
            ("평생운세총평", "평생운세 총평"),
            ("택일성명학안내", "택일·성명학 안내"),
        ],
    },
    {
        "id": "monthly1",
        "title": "4부. 월별 운세 상세 (1~6월)",
        "keys": [(f"{m}월운세", f"{m}월 상세 운세") for m in range(1, 7)],
    },
    {
        "id": "monthly2",
        "title": "4부. 월별 운세 상세 (7~12월)",
        "keys": [(f"{m}월운세", f"{m}월 상세 운세") for m in range(7, 13)],
    },
    {
        "id": "gunghap",
        "title": "5부. 궁합 상세분석",
        "keys": [
            ("궁합총평", "궁합 종합 총평"),
            ("궁합장점", "궁합 강점 및 시너지"),
            ("궁합주의점및개운법", "궁합 주의점 및 개운법"),
        ],
        "optional": True,  # 궁합 상품이 아니거나 person2가 없으면 건너뜀
    },
]

# 하위 호환: 기존 8개 항목 키 목록 (make_pdf.py 등에서 참조할 수 있음)
INTERPRETATION_KEYS = [
    ("타고난성향", "타고난 성향과 기질"),
    ("직장운이직운승진운", "직장운·이직운·승진운"),
    ("사업운창업운", "사업운·창업운"),
    ("재물운", "재물운·금전운"),
    ("연애운인연운", "연애운·인연운"),
    ("결혼운배우자운", "결혼운·배우자운"),
    ("가족운자녀운", "가족운·자녀운"),
    ("대인관계운", "대인관계·인간관계운"),
]


def _fact_lines(data: dict) -> list:
    """계산된 사주 데이터를 프롬프트용 사실(fact) 목록 문자열로 정리한다. 모든 그룹이 공유."""
    pillars = data["pillars"]
    oheng = data["ohengDistribution"]
    sipseong = data["sipseong"]
    unseong = data.get("unseong12", {})
    daeun = data["daeun"]
    seun = data["seun"]
    sinsal = data.get("sinsal", {})
    sangsaeng = data.get("sangsaeng", [])
    yongsin = data.get("yongsin")
    gyeokguk = data.get("gyeokguk")

    lines = [
        f"이름: {data.get('name', '의뢰인')} / 성별: {'남성' if data.get('gender') == 'M' else '여성'}",
        f"생년월일시: {data['birth']['year']}년 {data['birth']['month']}월 {data['birth']['day']}일 "
        f"{data['birth']['hour']}시 {data['birth']['minute']}분 (양력)",
        f"사주 원국 (연주/월주/일주/시주): "
        f"{''.join(pillars['연주'])} {''.join(pillars['월주'])} {''.join(pillars['일주'])} {''.join(pillars['시주'])}",
        f"일간(본인을 상징하는 글자): {data['ilgan']}",
        f"오행 분포: " + ", ".join(f"{k} {v}개" for k, v in oheng.items()),
        f"부족한 오행: {', '.join(data.get('ohengMissing', [])) or '없음'}",
        f"천간 상생상극 관계: {', '.join(sangsaeng)}",
        f"십성 배치: " + ", ".join(f"{k}={v}" for k, v in sipseong.items()),
        f"12운성 배치: " + ", ".join(f"{k}={v}" for k, v in unseong.items()),
        f"대운: {'순행' if daeun['forward'] else '역행'}, 대운수 {daeun['daeunSu']}세부터 적용, "
        f"흐름: " + ", ".join(f"{age}세={gj}" for age, gj in zip(daeun["startAges"], daeun["pillars"])),
        f"최근 세운: " + ", ".join(f"{y}년={gj}" for y, gj in seun.items()),
    ]
    if yongsin:
        lines.append(
            f"용신 분석: {'신강' if yongsin.get('is_strong') else '신약'} 사주, "
            f"용신={yongsin.get('yongsin')} 희신={yongsin.get('huisin')} "
            f"기신={yongsin.get('gisin')} 구신={yongsin.get('gusin')} 한신={yongsin.get('hansin')}, "
            f"근거: {yongsin.get('reason')}"
        )
    if gyeokguk:
        lines.append(f"격국: {gyeokguk.get('name')} ({gyeokguk.get('description')})")
    if sinsal:
        lines.append("주요 신살: " + ", ".join(sinsal.keys()))
    return lines


def _wolun_fact_lines(data: dict) -> list:
    """월별 운세(월운) 12개월 데이터가 있으면 프롬프트용 텍스트로 정리."""
    wolun = data.get("wolun")
    if not wolun:
        return []
    lines = ["신년 12개월 월운(月運) 흐름:"]
    for item in wolun:
        lines.append(
            f"- {item['month']}월: {item['ganji']} (십성={item['sipseong']}, 오행={item['oheng']}) "
            f"핵심분위기: {item['keyword']}"
        )
    return lines


def _gunghap_fact_lines(data: dict) -> list:
    """궁합 데이터가 있으면(2인 상품) 프롬프트용 텍스트로 정리. 없으면 빈 리스트."""
    g = data.get("gunghap")
    if not g:
        return []
    lines = [
        f"두 사람 궁합 계산 결과: 일간관계={g.get('ilgan_relation')}",
        f"육합 성립: {', '.join(g.get('yukhap_hits', [])) or '없음'}",
        f"삼합 성립: {', '.join(g.get('samhap_hits', [])) or '없음'}",
        f"충 성립(주의요망): {', '.join(g.get('chung_hits', [])) or '없음'}",
        f"형·해·파 성립(주의요망): {', '.join(g.get('hyeong_hae_pa_hits', [])) or '없음'}",
        f"궁합 점수/등급: {g.get('score')}점 / {g.get('grade')}급",
    ]
    return lines


def _build_group_prompt(data: dict, group: dict) -> str:
    fact_lines = _fact_lines(data)
    extra_lines = []
    if group["id"] in ("monthly1", "monthly2"):
        extra_lines = _wolun_fact_lines(data)
    if group["id"] == "gunghap":
        extra_lines = _gunghap_fact_lines(data)

    keys_desc = "\n".join(f"- {key}: {label}" for key, label in group["keys"])

    # ---- 개인화 신호: 분 단위 출생 시각 · 이름(발음오행/한자 뜻·획수) ----
    # 같은 명식이라도 이 신호가 달라 해석의 결이 겹치지 않게 한다.
    pz_lines = []
    try:
        from personalize import build_context
        _meta = data.get("meta", {}) or {}
        _pz = build_context(data, _meta)
        tp = _pz.get("time_phase") or {}
        if tp:
            pz_lines.append(
                f"- 출생 시각의 결: {tp['siji']}시({tp['animal']})의 '{tp['phase']}'"
                f"(해당 시가 시작된 뒤 {tp['passed']}분 경과). "
                f"앞 시각 {tp['prev']}시({tp['prev_oheng']}), 뒤 시각 {tp['next']}시({tp['next_oheng']})의 영향 참고."
            )
        prof = _pz.get("name_profile") or {}
        if prof.get("sound_ohengs"):
            pairs = ", ".join(f"{c}({o})" for c, o in prof.get("sound", []) if o)
            pz_lines.append(f"- 이름 발음오행: {pairs}")
        if prof.get("chars"):
            cs = ", ".join(
                f"{c['char']}({c.get('meaning') or '뜻 미상'}"
                + (f", {c['strokes']}획" if c.get("strokes") else "")
                + (f", 자원오행 {c['oheng']}" if c.get("oheng") else "") + ")"
                for c in prof["chars"])
            if cs:
                pz_lines.append(f"- 이름 한자: {cs}")
        if prof.get("total_strokes"):
            pz_lines.append(f"- 이름 총획: {prof['total_strokes']}획 (수리오행 {prof['stroke_oheng']})")
        if _pz.get("V"):
            mt = _pz["V"].metaphor()
            pz_lines.append(
                f"- 이 리포트에서 사용할 비유 소재: '{mt['subject']}'"
                f"(성장={mt['grow']}, 절정={mt['peak']}, 휴식={mt['rest']}). "
                "이 소재를 자연스럽게 활용해 다른 사람의 글과 표현이 겹치지 않게 하세요."
            )
    except Exception:
        pass

    all_lines = fact_lines + ([""] + extra_lines if extra_lines else [])
    if pz_lines:
        all_lines = all_lines + ["", "[이 사람만의 개인화 정보]"] + pz_lines

    prompt = f"""당신은 명리학(사주팔자)에 정통한 전문 상담가입니다.
아래는 한 의뢰인의 사주를 자평진전·삼명통회·명리정종·적천수 등 고전 이론에 기반해
정확하게 수학적으로 계산한 결과입니다. 이 계산 결과에 근거해서, 실제로 이 사람에게
해당하는 구체적이고 개인화된 운세풀이를 작성해 주세요.

이번 요청은 전체 리포트 중 "{group['title']}" 파트입니다.

[계산된 사주 정보]
{chr(10).join(all_lines)}

[작성 지침 — 아주 중요]
1. 반드시 위 계산 결과(오행 분포, 십성, 용신/격국, 대운/세운, 신살, 월운, 궁합 등)를
   근거로 해석하세요. 근거 없는 뻔한 덕담은 쓰지 마세요.
2. **읽는 사람은 사주를 처음 접하는 일반인입니다. 초등학교 고학년도 이해할 만큼
   쉽고 친근하게 쓰세요.**
   - **한자(漢字)는 절대 쓰지 마세요.** 한글로만 쓰고, 한자 병기(예: '용신(用神)')도 하지 마세요.
   - 어려운 전문용어(비겁·식상·관성·인성·충·형 등)는 가급적 피하고, 꼭 필요하면
     '나에게 힘이 되는 기운', '경쟁을 뜻하는 기운'처럼 쉬운 말로 풀어서 설명하세요.
   - 한 문장은 짧고 명료하게(대략 40자 이내), 어려운 한자어 대신 쉬운 우리말을 쓰세요.
   - 상담사가 옆에서 다정하게 이야기해 주듯 따뜻하고 구체적인 조언을 담으세요.
3. 각 항목은 300~450자 정도로, 구체적인 상황·시기·행동 제안을 포함해 실질적으로
   도움이 되게 쓰세요.
4. 정중한 존댓말("~해요", "~합니다", "~하면 좋아요")로 편안하게 쓰세요.
5. **[이 사람만의 개인화 정보]가 주어졌다면 반드시 해석에 녹여 쓰세요.**
   - 같은 날 같은 시에 태어난 사람이라도 '초입·중간·끝자락'에 따라 기운이 다릅니다.
     이 차이를 해석의 방향에 실제로 반영하세요(예: 초입=시작하는 힘·예민한 감각,
     중간=중심이 단단함·한 우물, 끝자락=변화 적응·전환에 강함).
   - 이름의 발음오행·한자 뜻·획수가 사주의 부족한 기운을 보완하는지, 이미 강한 기운을
     더 키우는지 짚어 주세요.
   - 지정된 비유 소재를 활용하고, 문장 구조와 도입부를 매번 다르게 구성해
     **다른 의뢰인의 결과지와 표현이 겹치지 않게** 쓰세요. 정형화된 상투구는 피하세요.
6. 아래 항목 전부를 빠짐없이 작성하세요:
{keys_desc}

[출력 형식]
다른 설명 없이, 아래와 같은 JSON 객체 하나만 출력하세요 (키는 정확히 아래 영문/한글 키 이름을 그대로 사용):
{{
{chr(10).join(f'  "{key}": "...",' for key, _ in group["keys"])}
}}
"""
    return prompt


def _call_claude(prompt: str, api_key: str, model: str, timeout: int, max_tokens: int = 4000) -> str:
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Claude API 호출 실패 (HTTP {e.code}): {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Claude API 연결 실패: {e.reason}") from e

    try:
        return resp_data["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Claude API 응답 형식이 예상과 다릅니다: {resp_data}") from e


def _parse_json_block(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(f"Claude API 응답에서 JSON을 찾을 수 없습니다: {text[:300]}")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude API 응답 JSON 파싱 실패: {e} / 원문: {text[:300]}") from e


def generate_ai_interpretation(data: dict, timeout: int = DEFAULT_TIMEOUT,
                                include_gunghap: bool = False,
                                on_progress=None) -> dict:
    """
    사주 계산 결과(data)를 Claude API에 그룹 단위로 순차 전달해 60페이지 분량의
    해석 문장을 생성한다. 각 그룹은 독립적으로 실패할 수 있으며, 실패한 그룹은
    빈 문자열로 채워지고 make_pdf.py 쪽에서 고정 문구로 폴백 처리한다.

    Args:
        data: run_saju.py가 산출한 계산 결과 딕셔너리 (wolun, gunghap 필드 포함 가능)
        timeout: 그룹당 API 타임아웃(초). 항목이 많아 60초보다 넉넉하게 잡아야 한다.
        include_gunghap: True면 궁합 그룹도 함께 호출(2인 상품일 때만 True로 설정)
        on_progress: 그룹 하나가 끝날 때마다 호출되는 콜백(선택). on_progress(group_id, ok: bool)

    Returns:
        모든 그룹의 키-문장을 하나로 합친 딕셔너리. 최소 하나의 그룹이라도
        성공해야 하며, 전체 그룹이 실패하면 RuntimeError를 던진다(완전 폴백 유도).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다.")

    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    combined = {}
    success_count = 0
    errors = []

    for group in GROUPS:
        if group.get("optional") and group["id"] == "gunghap" and not include_gunghap:
            continue

        prompt = _build_group_prompt(data, group)
        try:
            text = _call_claude(prompt, api_key, model, timeout=timeout, max_tokens=4000)
            parsed = _parse_json_block(text)
            missing = [key for key, _ in group["keys"] if key not in parsed or not parsed[key]]
            if missing:
                raise RuntimeError(f"'{group['title']}' 그룹 응답에 누락된 항목: {', '.join(missing)}")
            for key, _ in group["keys"]:
                combined[key] = str(parsed[key])
            success_count += 1
            if on_progress:
                on_progress(group["id"], True)
        except Exception as e:
            print(f"[AI 그룹 호출 실패 - '{group['title']}' 그룹만 고정 문구로 대체] {e}")
            errors.append(f"{group['title']}: {e}")
            if on_progress:
                on_progress(group["id"], False)
            # 이 그룹은 실패했으므로 combined에 아무 것도 넣지 않는다.
            # 호출부(make_pdf.py)가 빈 키를 감지해 고정 문구 DB로 채운다.

        # 그룹 사이에 짧게 쉬어 API 레이트리밋을 완화한다.
        time.sleep(0.5)

    if success_count == 0:
        raise RuntimeError("모든 AI 그룹 호출이 실패했습니다: " + " | ".join(errors))

    return combined

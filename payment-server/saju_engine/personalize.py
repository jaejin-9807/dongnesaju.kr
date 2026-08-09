# -*- coding: utf-8 -*-
"""
===================================================================
personalize.py — 결과지 개인화 엔진
===================================================================
같은 사주 원국(명식)이 나오더라도 결과지가 서로 겹치지 않도록,
아래 세 축으로 해석의 결을 미세하게 틀어 준다.

 1) 출생 시각의 분(分) 단위 — 같은 진시라도 초입/중간/끝자락의 기운이 다르다.
 2) 이름(한글 발음오행 + 한자 뜻·획수) — 사주의 부족한 기운을 보완하는지 본다.
 3) 문장 변형 시드 — 같은 논지라도 문장 구조와 비유를 매번 다르게 고른다.

※ 시드는 '생년월일시 + 이름'에서 결정론적으로 만든다.
   같은 사람은 다시 뽑아도 같은 결과지가 나오고, 다른 사람은 달라진다.
===================================================================
"""
import hashlib
import re

# ------------------------------------------------------------------
# 1. 출생 시각 — 12지지 시(時)와 분 단위 위상
# ------------------------------------------------------------------
# 자시(23~01) 축시(01~03) 인시(03~05) 묘시(05~07) 진시(07~09) 사시(09~11)
# 오시(11~13) 미시(13~15) 신시(15~17) 유시(17~19) 술시(19~21) 해시(21~23)
_SIJI = [
    ("자", 23, "쥐"), ("축", 1, "소"), ("인", 3, "범"), ("묘", 5, "토끼"),
    ("진", 7, "용"), ("사", 9, "뱀"), ("오", 11, "말"), ("미", 13, "양"),
    ("신", 15, "원숭이"), ("유", 17, "닭"), ("술", 19, "개"), ("해", 21, "돼지"),
]
_SIJI_OHENG = {
    "자": "수", "축": "토", "인": "목", "묘": "목", "진": "토", "사": "화",
    "오": "화", "미": "토", "신": "금", "유": "금", "술": "토", "해": "수",
}
# 각 시(時)의 앞뒤에 맞닿은 시
_PREV = {"자": "해", "축": "자", "인": "축", "묘": "인", "진": "묘", "사": "진",
         "오": "사", "미": "오", "신": "미", "유": "신", "술": "유", "해": "술"}
_NEXT = {v: k for k, v in _PREV.items()}


def time_phase(hour, minute):
    """출생 시각을 12지 시(時)와 '초입/중간/끝자락' 위상으로 나눈다."""
    if hour is None:
        return None
    h = int(hour) % 24
    m = int(minute or 0)
    # 자시는 23시부터 다음날 01시까지 걸쳐 있다
    idx = None
    for i, (name, start, _) in enumerate(_SIJI):
        end = (start + 2) % 24
        if start < end:
            if start <= h < end:
                idx = i
                break
        else:  # 자시(23~1)
            if h >= start or h < end:
                idx = i
                break
    if idx is None:
        idx = 0
    name, start, animal = _SIJI[idx]
    # 시작점으로부터 몇 분이 지났는가 (0~119)
    passed = ((h - start) % 24) * 60 + m
    if passed < 40:
        phase, label = "초입", "이제 막 문을 연"
    elif passed < 80:
        phase, label = "중간", "한가운데 무르익은"
    else:
        phase, label = "끝자락", "다음 기운으로 넘어가려는"
    return {
        "siji": name, "animal": animal, "oheng": _SIJI_OHENG.get(name, ""),
        "phase": phase, "label": label, "passed": passed,
        "prev": _PREV.get(name, ""), "next": _NEXT.get(name, ""),
        "prev_oheng": _SIJI_OHENG.get(_PREV.get(name, ""), ""),
        "next_oheng": _SIJI_OHENG.get(_NEXT.get(name, ""), ""),
    }


def time_phase_text(tp, name):
    """분 단위 위상을 해석 문장으로."""
    if not tp:
        return ""
    s, ph = tp["siji"], tp["phase"]
    if ph == "초입":
        return (f"{name} 님은 {s}시({tp['animal']})의 {tp['label']} 자리에서 태어나셨습니다. "
                f"앞 시각인 {tp['prev']}시의 {tp['prev_oheng']} 기운이 아직 옅게 남아 있어, "
                f"{s}시 본래의 {tp['oheng']} 기운에 더해 시작을 여는 힘과 예민한 감각이 함께 실립니다. "
                "판단이 빠르고 낌새를 먼저 알아채지만, 그만큼 서두르다 지치기 쉬우니 속도 조절이 관건입니다.")
    if ph == "중간":
        return (f"{name} 님은 {s}시({tp['animal']})의 {tp['label']} 한복판에서 태어나셨습니다. "
                f"{tp['oheng']} 기운이 흔들림 없이 가장 순수하게 자리 잡은 때라, "
                "타고난 기질이 또렷하고 중심이 단단합니다. 방향을 정하면 끝까지 밀고 가는 힘이 여기서 나옵니다. "
                "다만 자기 색이 뚜렷한 만큼, 다른 결의 사람과는 조율하는 연습이 필요합니다.")
    return (f"{name} 님은 {s}시({tp['animal']})의 {tp['label']} 끝자락에서 태어나셨습니다. "
            f"뒤따라오는 {tp['next']}시의 {tp['next_oheng']} 기운이 미리 스며들어, "
            f"{s}시의 {tp['oheng']} 기운에 변화를 받아들이는 유연함이 더해집니다. "
            "한 자리에 머물기보다 흐름을 갈아타며 길을 넓히는 편이 잘 맞습니다.")


# ------------------------------------------------------------------
# 2. 이름 — 한글 발음오행 + 한자 뜻(자원오행) + 획수
# ------------------------------------------------------------------
# 한글 초성 자음 → 오행 (전통 성명학의 발음오행)
_CHOSUNG = ["ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ", "ㅆ",
            "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
_SOUND_OHENG = {
    "ㄱ": "목", "ㄲ": "목", "ㅋ": "목",
    "ㄴ": "화", "ㄷ": "화", "ㄸ": "화", "ㄹ": "화", "ㅌ": "화",
    "ㅇ": "토", "ㅎ": "토",
    "ㅅ": "금", "ㅆ": "금", "ㅈ": "금", "ㅉ": "금", "ㅊ": "금",
    "ㅁ": "수", "ㅂ": "수", "ㅃ": "수", "ㅍ": "수",
}


def sound_oheng(korean_name):
    """한글 이름의 글자별 발음오행 목록."""
    out = []
    for ch in str(korean_name or ""):
        code = ord(ch) - 0xAC00
        if 0 <= code <= 11171:
            cho = _CHOSUNG[code // 588]
            out.append((ch, _SOUND_OHENG.get(cho, "")))
    return out


# 한자 뜻(훈)에 담긴 자연물 → 자원오행
_MEANING_OHENG = [
    ("목", ["나무", "수풀", "숲", "풀", "꽃", "잎", "뿌리", "가지", "대나무", "소나무", "동녘", "봄"]),
    ("화", ["불", "빛", "밝", "빛날", "해", "햇", "여름", "붉", "타오", "덥", "환할", "비칠"]),
    ("토", ["흙", "땅", "산", "뫼", "언덕", "들", "터", "성", "누를", "가운데", "두터"]),
    ("금", ["쇠", "금", "구슬", "옥", "보배", "칼", "돌", "굳", "단단", "가을", "흰", "종"]),
    ("수", ["물", "바다", "강", "내", "비", "샘", "이슬", "겨울", "검", "북녘", "흐를", "깊"]),
]


def meaning_oheng(meaning_text):
    """'보배 진', '넓을 홍' 같은 훈음에서 자원오행을 추정."""
    t = str(meaning_text or "")
    # '성 김'(성씨)처럼 뜻이 아닌 표기는 제외해 오탐을 막는다
    t = re.sub(r"성\s*[가-힣]\s*·?", " ", t)
    for oh, keys in _MEANING_OHENG:
        for k in keys:
            if k in t:
                return oh
    return ""


# 이름에 자주 쓰이는 한자의 획수(정자 기준). 없는 글자는 건너뛴다.
_STROKES = {
    "洪": 9, "吉": 6, "童": 12, "金": 8, "李": 7, "朴": 6, "崔": 11, "鄭": 15,
    "姜": 9, "趙": 14, "尹": 4, "張": 11, "林": 8, "吳": 7, "韓": 17, "申": 5,
    "徐": 10, "權": 22, "黃": 12, "安": 6, "宋": 7, "柳": 9, "全": 6, "高": 10,
    "文": 4, "孫": 10, "白": 5, "許": 11, "南": 9, "沈": 7, "盧": 16, "河": 8,
    "民": 5, "俊": 9, "秀": 7, "英": 9, "美": 9, "喜": 12, "善": 12, "仁": 4,
    "義": 13, "禮": 18, "智": 12, "信": 9, "誠": 14, "孝": 7, "忠": 8, "德": 15,
    "明": 8, "光": 6, "星": 9, "月": 4, "日": 4, "天": 4, "地": 6, "山": 3,
    "水": 4, "木": 4, "火": 4, "土": 3, "石": 5, "玉": 5, "珍": 9, "珠": 10,
    "花": 8, "松": 8, "竹": 6, "梅": 11, "蘭": 21, "菊": 12, "春": 9, "夏": 10,
    "秋": 9, "冬": 5, "東": 8, "西": 6, "南": 9, "北": 5, "中": 4, "大": 3,
    "小": 3, "長": 8, "永": 5, "元": 4, "宇": 6, "宙": 8, "海": 10, "江": 6,
    "泉": 9, "淸": 11, "洙": 9, "泰": 10, "浩": 10, "淳": 11, "潤": 15, "澤": 16,
    "成": 6, "宰": 10, "載": 13, "在": 6, "才": 3, "材": 7, "植": 12, "根": 10,
    "銀": 14, "鐵": 21, "鎭": 18, "錫": 16, "鍾": 17, "鏞": 19, "鎬": 18,
    "熙": 13, "炫": 9, "炡": 9, "煥": 13, "燦": 17, "煐": 13, "烈": 10,
    "培": 11, "基": 11, "垣": 9, "均": 7, "坤": 8, "圭": 6, "堂": 11,
    "書": 10, "文": 4, "學": 16, "敎": 11, "訓": 10, "詩": 13, "語": 14,
    "宗": 8, "祐": 10, "福": 14, "祥": 11, "禧": 17, "禎": 14,
    "雨": 8, "雲": 12, "雪": 11, "霞": 17, "電": 13,
    "眞": 10, "眞": 10, "正": 5, "直": 8, "貞": 9, "淑": 12, "靜": 16,
    "娟": 10, "娥": 10, "妍": 7, "婉": 11, "媛": 12, "嬉": 15,
}
# 획수 → 오행 (수리오행: 1·2목, 3·4화, 5·6토, 7·8금, 9·0수)
_NUM_OHENG = {1: "목", 2: "목", 3: "화", 4: "화", 5: "토", 6: "토",
              7: "금", 8: "금", 9: "수", 0: "수"}


def hanja_profile(korean_name, hanja_name):
    """이름의 발음오행·자원오행·획수(수리오행)를 종합한 프로필."""
    snd = sound_oheng(korean_name)
    prof = {
        "korean": korean_name or "",
        "hanja": hanja_name or "",
        "sound": snd,
        "sound_ohengs": [o for _, o in snd if o],
        "chars": [],
        "total_strokes": None,
        "stroke_oheng": "",
    }
    if not hanja_name:
        return prof
    total = 0
    known = 0
    try:
        from hanja_meaning import HANJA_MEANING  # 선택적: 있으면 뜻 사용
    except Exception:
        HANJA_MEANING = {}
    for ch in str(hanja_name):
        if not re.match(r"[一-鿿]", ch):
            continue
        st = _STROKES.get(ch)
        mean = HANJA_MEANING.get(ch, "")
        prof["chars"].append({
            "char": ch, "strokes": st, "meaning": mean,
            "oheng": meaning_oheng(mean),
        })
        if st:
            total += st
            known += 1
    if known and known == len(prof["chars"]):
        prof["total_strokes"] = total
        prof["stroke_oheng"] = _NUM_OHENG.get(total % 10, "")
    return prof


def name_effect_text(prof, missing, yongsin, name):
    """이름이 사주의 부족한 기운을 어떻게 보완하는지 서술."""
    if not prof:
        return ""
    parts = []
    snd = [o for o in prof["sound_ohengs"] if o]
    if snd:
        uniq = []
        for o in snd:
            if o not in uniq:
                uniq.append(o)
        chain = "·".join(uniq)
        helps = [o for o in uniq if o in (missing or []) or o == yongsin]
        if helps:
            parts.append(
                f"이름 '{prof['korean']}'을 소리 내어 부를 때 흐르는 기운은 {chain}입니다. "
                f"그중 {'·'.join(helps)} 기운이 사주에서 부족하거나 꼭 필요한 자리를 메워 주니, "
                "이름이 평생 곁에서 부족한 곳을 채워 주는 셈입니다. 이름이 자주 불릴수록 그 기운이 두터워집니다.")
        else:
            parts.append(
                f"이름 '{prof['korean']}'의 소리에는 {chain} 기운이 흐릅니다. "
                "사주에 이미 있는 기운을 한 번 더 실어 주는 구조라, 타고난 색이 더욱 또렷해집니다. "
                "강점이 선명해지는 대신 치우침도 함께 커지니, 부족한 기운은 생활 습관으로 보완하시면 좋습니다.")
    # 한자 뜻 — 자원오행을 못 찾더라도 글자 뜻은 반드시 소개한다.
    if prof["chars"]:
        names = ", ".join(f"{c['char']}({c['meaning']})" for c in prof["chars"] if c.get("meaning"))
        ch_ohengs = [c["oheng"] for c in prof["chars"] if c.get("oheng")]
        fill = [o for o in ch_ohengs if o in (missing or []) or o == yongsin]
        if names:
            if fill:
                tail = (f"글자에 깃든 {'·'.join(sorted(set(fill)))} 기운이 사주의 빈 곳을 직접 채워 주어, "
                        "이름과 사주가 서로 맞물려 돌아가는 좋은 짜임입니다.")
            elif ch_ohengs:
                tail = (f"글자에는 {'·'.join(sorted(set(ch_ohengs)))} 기운이 담겨 있어, "
                        "타고난 성정을 곧게 세우고 스스로를 지키는 힘이 됩니다.")
            else:
                tail = ("글자에 담긴 뜻이 살아온 태도와 인상을 만들어, "
                        "이름을 부르는 사람들에게 그 결이 그대로 전해집니다.")
            parts.append(f"한자 {prof['hanja']}는 {names}의 뜻을 담고 있습니다. " + tail)
    if prof.get("total_strokes"):
        so = prof["stroke_oheng"]
        parts.append(
            f"한자 획수를 모두 더하면 {prof['total_strokes']}획으로 수리상 {so} 기운에 해당합니다. "
            + ("이 역시 사주에 필요한 기운과 맞닿아 있어, 이름이 뒤에서 밀어 주는 형국입니다."
               if (so == yongsin or so in (missing or [])) else
               "이름의 획수 기운은 타고난 흐름을 안정시키는 쪽으로 작용합니다."))
    return " ".join(parts)


# ------------------------------------------------------------------
# 3. 문장 변형 — 같은 논지도 매번 다른 구조·비유로
# ------------------------------------------------------------------
class Variator:
    """생년월일시+이름에서 만든 고정 시드로, 문장 후보 중 하나를 골라 준다.
    같은 사람은 항상 같은 선택 → 결과지 재생성 시에도 일관성 유지."""

    def __init__(self, seed_source):
        h = hashlib.sha256(str(seed_source).encode("utf-8")).hexdigest()
        self.seed = int(h[:12], 16)
        self._i = 0

    def pick(self, options):
        """후보 중 하나를 고른다. 호출 순서마다 다른 자리를 집는다."""
        if not options:
            return ""
        self._i += 1
        idx = (self.seed // (7 ** self._i) + self._i * 31) % len(options)
        return options[idx]

    def metaphor(self):
        """해석에 쓸 비유 소재(사람마다 다르게)."""
        return self.pick([
            {"subject": "나무", "grow": "뿌리를 넓히고", "peak": "열매를 맺는", "rest": "잎을 떨구고 쉬는"},
            {"subject": "물길", "grow": "물길을 트고", "peak": "너른 강으로 흐르는", "rest": "잠시 고여 맑아지는"},
            {"subject": "쇠", "grow": "담금질을 거듭하고", "peak": "날을 세우는", "rest": "불을 식히는"},
            {"subject": "밭", "grow": "땅을 고르고", "peak": "곡식을 거두는", "rest": "땅을 묵히는"},
            {"subject": "등불", "grow": "심지를 돋우고", "peak": "환히 밝히는", "rest": "기름을 채우는"},
            {"subject": "길", "grow": "길을 내고", "peak": "먼 곳에 닿는", "rest": "숨을 고르는"},
        ])

    def opener(self, name):
        """문단 첫 문장 형태를 바꿔 복사한 느낌을 없앤다."""
        return self.pick([
            f"{name} 님의 사주를 펼쳐 보면,",
            f"여덟 글자를 하나씩 짚어 보면 {name} 님은,",
            f"{name} 님의 명식이 말해 주는 것은,",
            f"타고난 기운의 짜임을 보면 {name} 님은,",
            f"{name} 님 사주의 중심을 들여다보면,",
        ])

    def connector(self):
        return self.pick(["다만", "한편", "그런가 하면", "여기서 중요한 것은", "눈여겨볼 점은"])


def closing_line(V, topic, ctx):
    """섹션마다 붙는 '나에게만 해당하는' 마무리 한 문장.
    시드 + 개인 데이터(일간·용신·시각 위상·이름 기운)를 엮어 매번 다르게 만든다."""
    if not V:
        return ""
    name = ctx.get("name", "의뢰인")
    ilgan = ctx.get("ilgan", "")
    yong = ctx.get("yongsin", "")
    strong = ctx.get("strong", "")
    miss = ctx.get("missing") or []
    tp = ctx.get("time_phase") or {}
    ph = tp.get("phase", "")
    nm_oh = (ctx.get("name_ohengs") or [])
    mt = V.metaphor()
    miss_s = miss[0] if miss else ""
    phase_hint = {
        "초입": "먼저 움직여 자리를 잡는 방식",
        "중간": "한 가지를 깊게 밀고 가는 방식",
        "끝자락": "흐름이 바뀔 때 갈아타는 방식",
    }.get(ph, "자기 속도를 지키는 방식")

    POOL = {
        "재물": [
            f"{name} 님의 일간 {ilgan}에게 재물은 {mt['subject']}처럼 다뤄야 합니다. {mt['grow']} 시기를 건너뛰면 {mt['peak']} 때가 오지 않습니다.",
            f"{yong} 기운이 살아날 때 재물의 문이 함께 열립니다. {phase_hint}이 {name} 님께는 가장 수익률이 좋은 방법입니다.",
            (f"부족한 {miss_s} 기운이 재물 관리의 빈틈으로 나타나기 쉽습니다. 그 자리를 사람이나 시스템으로 메우면 손실이 크게 줄어듭니다."
             if miss_s else f"{strong} 기운이 넉넉한 만큼 기회는 자주 옵니다. 다만 모두 잡으려 하면 새어 나가니 두세 개만 고르세요."),
        ],
        "직업": [
            f"{ilgan} 일간에게 맞는 자리는 이름이 알려진 곳보다 {phase_hint}이 통하는 곳입니다.",
            f"{name} 님은 {mt['subject']} 같은 사람이라, 조직이 {mt['grow']} 시간을 허락할 때 제 몫을 냅니다. 급하게 성과를 요구하는 곳은 맞지 않습니다.",
            f"{yong} 기운을 채워 주는 분야·사람과 함께할 때 실력이 배로 드러납니다. 일을 고를 때 이 기준을 먼저 보세요.",
        ],
        "건강": [
            f"{strong} 기운이 몰린 자리부터 먼저 피로가 옵니다. 신호가 오면 참지 말고 그날 쉬어 주는 것이 {name} 님께는 가장 확실한 관리법입니다.",
            (f"{miss_s} 기운이 부족해 회복이 더딜 수 있습니다. 이 기운을 채우는 생활 습관 하나만 정해 3개월만 지켜 보세요."
             if miss_s else "기운의 균형이 나쁘지 않아 큰 병보다 잔병이 문제입니다. 규칙적인 생활이 곧 최고의 처방입니다."),
            f"{phase_hint}으로 살아온 만큼 특정 부위에 무리가 쌓입니다. 한 달에 하루는 아무 계획 없이 비워 두세요.",
        ],
        "관계": [
            f"{name} 님은 {mt['subject']} 같은 결이라, 결이 다른 사람과는 처음엔 부딪혀도 오래 보면 서로를 채웁니다.",
            f"{yong} 기운을 지닌 사람이 {name} 님께 귀인입니다. 함께 있으면 편안하고 일이 풀리는 사람을 곁에 두세요.",
            f"{phase_hint}을 이해해 주는 사람과 오래갑니다. 속도를 재촉하는 관계는 자연히 멀어집니다.",
        ],
        "흐름": [
            f"{name} 님의 흐름은 {mt['subject']}에 가깝습니다. {mt['peak']} 때를 알아보는 눈이 인생의 크기를 정합니다.",
            f"{yong} 기운이 드는 시기에 결정을 몰아 두는 습관 하나가, 십 년 뒤의 자리를 바꿔 놓습니다.",
            f"{phase_hint}이 {name} 님의 무기입니다. 남의 속도에 맞추려 할 때 오히려 흐름이 끊깁니다.",
        ],
        "성격": [
            f"{ilgan} 일간에 {strong} 기운이 더해져, 겉으로 보이는 모습보다 속이 훨씬 단단합니다.",
            (f"이름의 {'·'.join(nm_oh[:2])} 기운이 타고난 성정을 한 번 더 감싸 줍니다. {name} 님이 스스로를 믿을 때 이 힘이 가장 잘 나옵니다."
             if nm_oh else f"{name} 님의 강점은 {strong} 기운에서 나옵니다. 이 결을 억누르지 않는 환경을 고르세요."),
            f"{phase_hint}이 몸에 배어 있어, 남들이 망설일 때 {name} 님은 이미 답을 알고 있는 경우가 많습니다.",
        ],
    }
    return V.pick(POOL.get(topic, POOL["흐름"]))


def build_context(data, meta):
    """결과지 전체에서 쓸 개인화 컨텍스트를 한 번에 만든다."""
    b = data.get("birth", {}) or {}
    name = meta.get("customerName") or data.get("name") or "의뢰인"
    hanja = meta.get("customerNameHanja") or ""
    tp = time_phase(b.get("hour"), b.get("minute")) if not meta.get("birthTimeUnknown") else None
    prof = hanja_profile(name, hanja)
    seed_src = f"{b.get('year')}-{b.get('month')}-{b.get('day')}-{b.get('hour')}-{b.get('minute')}-{name}-{hanja}"
    return {
        "name": name,
        "ilgan": data.get("ilgan", ""),
        "strong": data.get("ohengMostCommon", ""),
        "missing": data.get("ohengMissing") or [],
        "yongsin": (data.get("yongsin") or {}).get("yongsin", ""),
        "name_ohengs": [o for o in prof.get("sound_ohengs", []) if o],
        "time_phase": tp,
        "time_text": time_phase_text(tp, name) if tp else "",
        "name_profile": prof,
        "name_text": name_effect_text(
            prof, data.get("ohengMissing") or [],
            (data.get("yongsin") or {}).get("yongsin", ""), name),
        "V": Variator(seed_src),
    }

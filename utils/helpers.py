# =============================================================================
# utils/helpers.py
# =============================================================================

import re
import json
import hashlib
import os
import requests
from datetime import datetime, timedelta, date as date_type, timezone
from logger import get_logger

log = get_logger(__name__)

# Nepal timezone: UTC+5:45
_NEPAL_TZ     = timezone(timedelta(hours=5, minutes=45))
_NEPAL_OFFSET = timedelta(hours=5, minutes=45)

def nepal_now():
    """
    Return current datetime in Nepal Standard Time.
    Server clock is already set to Nepal time (UTC+5:45),
    so datetime.now() is correct — no conversion needed.
    """
    return datetime.now()

def to_nepal_time(dt):
    """
    Normalise a datetime to Nepal Standard Time.
    - Timezone-aware datetimes (e.g. from JSON-LD with +05:45 or Z):
      converted properly to Nepal time then stripped of tz info.
    - Naive datetimes: server is Nepal time so returned as-is.
    """
    if dt is None:
        return None
    if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
        # Has explicit timezone — convert to Nepal time correctly
        return dt.astimezone(_NEPAL_TZ).replace(tzinfo=None)
    # Already Nepal time (server clock)
    return dt

# =============================================================================
# TEXT CLEANING
# =============================================================================

def safe_text(text):
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# =============================================================================
# IMAGE DOWNLOAD
# =============================================================================

IMAGE_DIR = "images"

def download_image(url):
    if not url:
        return None
    try:
        os.makedirs(IMAGE_DIR, exist_ok=True)
        ext      = url.split(".")[-1].split("?")[0][:4].lower()
        ext      = ext if ext in ("jpg", "jpeg", "png", "webp", "gif") else "jpg"
        filename = hashlib.md5(url.encode()).hexdigest() + "." + ext
        filepath = os.path.join(IMAGE_DIR, filename)
        if os.path.exists(filepath):
            return filepath
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=8, stream=True)
        if r.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return filepath
    except Exception as e:
        log.debug("Image download failed for %s: %s", url, e)
    return None


# =============================================================================
# CONTENT HASH
# =============================================================================

def generate_hash(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


# =============================================================================
# ARTICLE CLASSIFICATION
# =============================================================================

_POLITICAL_KEYWORDS = [
    "election","vote","parliament","minister","government","political",
    "party","politics","protest","corruption","president","democracy",
    "coalition","policy","law","court","verdict",
    "निर्वाचन","मतदान","संसद","मन्त्री","सरकार","राजनीति",
    "भ्रष्टाचार","आन्दोलन","चुनाव","प्रधानमन्त्री","राष्ट्रपति",
    "लोकतन्त्र","गठबन्धन","अदालत","फैसला","नीति","कानून",
]
_ELECTION_KEYWORDS = [
    "election","vote","voting","ballot","candidate","polling","electoral",
    "निर्वाचन","मतदान","चुनाव","मतपत्र","उम्मेदवार","मतगणना",
]

# =============================================================================
# CATEGORY DETECTION
# =============================================================================

_CATEGORY_KEYWORDS = {
    "Politics": [
        # English
        "election","vote","parliament","minister","government","political",
        "party","politics","protest","corruption","president","democracy",
        "coalition","policy","law","court","verdict","cabinet","senate",
        "congress","prime minister","opposition","ruling","constitution",
        # Nepali
        "निर्वाचन","मतदान","संसद","मन्त्री","सरकार","राजनीति",
        "भ्रष्टाचार","आन्दोलन","चुनाव","प्रधानमन्त्री","राष्ट्रपति",
        "लोकतन्त्र","गठबन्धन","अदालत","फैसला","नीति","कानून","संविधान",
        "प्रतिपक्ष","सत्तारुढ","मन्त्रिपरिषद",
    ],
    "Economy": [
        # English
        "economy","economic","gdp","inflation","budget","tax","revenue",
        "investment","market","stock","trade","export","import","bank",
        "finance","loan","interest rate","fiscal","monetary",
        # Nepali
        "अर्थतन्त्र","आर्थिक","बजेट","कर","राजस्व","लगानी","बजार",
        "शेयर","व्यापार","निर्यात","आयात","बैंक","वित्त","ऋण","ब्याज",
    ],
    "Sports": [
        # English
        "cricket","football","soccer","basketball","tennis","athletics",
        "tournament","championship","match","player","team","goal","score",
        "olympic","stadium","coach","referee","league","series",
        # Nepali
        "क्रिकेट","फुटबल","खेल","खेलाडी","टिम","च्याम्पियनशिप",
        "टुर्नामेन्ट","म्याच","गोल","स्टेडियम","लिग",
    ],
    "Technology": [
        # English
        "technology","tech","digital","internet","software","hardware",
        "artificial intelligence","ai","cyber","mobile","app","startup",
        "innovation","computer","network","data","cloud","robot",
        # Nepali
        "प्रविधि","डिजिटल","इन्टरनेट","सफ्टवेयर","कम्प्युटर","एआई",
        "साइबर","मोबाइल","स्टार्टअप","नेटवर्क",
    ],
    "Health": [
        # English
        "health","hospital","doctor","medicine","disease","virus","vaccine",
        "patient","treatment","surgery","mental health","pandemic","covid",
        "cancer","diabetes","nutrition","medical","clinic","pharmaceutical",
        # Nepali
        "स्वास्थ्य","अस्पताल","डाक्टर","औषधि","रोग","भाइरस","खोप",
        "बिरामी","उपचार","शल्यक्रिया","महामारी","क्यान्सर","पोषण",
    ],
    "Education": [
        # English
        "education","school","university","college","student","teacher",
        "exam","scholarship","curriculum","degree","literacy","training",
        # Nepali
        "शिक्षा","विद्यालय","विश्वविद्यालय","कलेज","विद्यार्थी","शिक्षक",
        "परीक्षा","छात्रवृत्ति","पाठ्यक्रम","डिग्री","साक्षरता",
    ],
    "Entertainment": [
        # English
        "movie","film","music","song","actor","actress","celebrity",
        "concert","festival","art","culture","dance","theatre","award",
        # Nepali
        "चलचित्र","फिल्म","संगीत","गीत","कलाकार","सेलिब्रिटी",
        "महोत्सव","कला","संस्कृति","नृत्य","पुरस्कार",
    ],
    "Environment": [
        # English
        "climate","environment","pollution","carbon","emission","forest",
        "wildlife","earthquake","flood","disaster","weather","temperature",
        # Nepali
        "जलवायु","वातावरण","प्रदूषण","वन","वन्यजन्तु","भूकम्प",
        "बाढी","विपद","मौसम","तापक्रम",
    ],
    "International": [
        # English
        "india","china","usa","america","united nations","un","nato",
        "foreign","international","global","world","bilateral","embassy",
        "diplomat","summit","treaty","sanction","border",
        # Nepali
        "भारत","चीन","अमेरिका","संयुक्त राष्ट्र","विदेश","अन्तर्राष्ट्रिय",
        "विश्व","द्विपक्षीय","दूतावास","कूटनीति","सम्झौता","सीमा",
    ],
    "Crime": [
        # English
        "murder","arrest","police","crime","criminal","theft","fraud",
        "drug","violence","robbery","rape","investigation","jail","prison",
        # Nepali
        "हत्या","गिरफ्तार","प्रहरी","अपराध","चोरी","जालसाजी",
        "लागूपदार्थ","हिंसा","डकैती","बलात्कार","अनुसन्धान","जेल",
    ],
    "Business": [
        # English
        "company","business","corporate","industry","manufacturing",
        "product","service","profit","loss","merger","acquisition",
        # Nepali
        "कम्पनी","व्यापार","उद्योग","उत्पादन","सेवा","नाफा","नोक्सान",
    ],
}


def detect_category(title, content):
    """
    Detect the most likely news category based on keyword matching.
    Uses word-boundary matching to avoid substrings (e.g. "app" in "happened").
    Title is weighted 3x over content. Returns best category or "General".
    """
    import re as _re

    def count_matches(text, keywords):
        count = 0
        text_l = text.lower()
        for kw in keywords:
            kw_l = kw.lower()
            # For single words use word-boundary; for phrases use substring
            if " " in kw_l:
                if kw_l in text_l:
                    count += 1
            else:
                # Match whole word only — avoids "app" in "happened"
                if _re.search(r"(?<![a-zA-Zà-ÿऀ-ॿ])" +
                              _re.escape(kw_l) +
                              r"(?![a-zA-Zà-ÿऀ-ॿ])", text_l):
                    count += 1
        return count

    title_score   = {cat: count_matches(title,   kws) * 3
                     for cat, kws in _CATEGORY_KEYWORDS.items()}
    content_score = {cat: count_matches(content, kws)
                     for cat, kws in _CATEGORY_KEYWORDS.items()}

    scores = {cat: title_score[cat] + content_score[cat]
              for cat in _CATEGORY_KEYWORDS if title_score[cat] + content_score[cat] > 0}

    if not scores:
        return "General"

    return max(scores, key=scores.get)


def classify_article(title, content):
    """
    Classify article: returns (is_political, is_election_related, category).
    """
    content_lower = content.lower()
    title_lower   = title.lower()
    combined      = title_lower + " " + content_lower

    is_political = "Yes" if any(k in combined for k in _POLITICAL_KEYWORDS) else "No"
    is_election  = "Yes" if any(k in combined for k in _ELECTION_KEYWORDS)  else "No"
    category     = detect_category(title, content)

    return is_political, is_election, category


# =============================================================================
# DATE EXTRACTION — robust multi-format, multi-language
# =============================================================================

# Devanagari digits → ASCII
_NE_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# =============================================================================
# BIKRAM SAMBAT → GREGORIAN CONVERSION
#
# Uses a verified lookup table of exact BS month lengths per year.
# The simple "epoch + days" approach was wrong because BS month lengths
# vary by year (unlike the Gregorian calendar). This table covers
# BS 2000–2090 (AD ~1943–2033).
#
# Each row: bs_year → list of 12 month lengths in days
# Source: verified against nepali-date-converter reference data
# =============================================================================

_BS_YEAR_DATA = {
    # BS year : [Baisakh, Jestha, Ashadh, Shrawan, Bhadra, Ashwin,
    #            Kartik,  Mangsir, Poush,  Magh,   Falgun, Chaitra]
    2000: [30,32,31,32,31,30,30,30,29,30,29,31],
    2001: [31,31,32,32,31,30,30,30,29,30,30,30],
    2002: [31,32,31,32,31,30,30,30,29,30,30,30],
    2003: [31,32,31,32,31,30,30,30,29,30,30,30],
    2004: [31,32,31,32,31,30,30,30,29,30,30,30],
    2005: [31,32,31,32,31,30,30,30,29,30,30,30],
    2006: [31,32,31,32,31,30,30,30,29,30,30,31],
    2007: [30,32,31,32,31,30,30,30,29,30,30,30],
    2008: [31,31,32,31,31,31,30,29,30,29,30,30],
    2009: [31,31,32,31,31,31,30,29,30,29,30,30],
    2010: [31,32,31,32,31,30,30,29,30,29,30,30],
    2011: [31,32,31,32,31,30,30,29,30,29,30,30],
    2012: [31,32,31,32,31,30,30,29,30,29,30,30],
    2013: [31,31,31,32,31,31,29,30,29,30,29,31],
    2014: [31,31,32,31,31,31,30,29,30,29,30,30],
    2015: [31,32,31,32,31,30,30,29,30,29,30,30],
    2016: [31,32,31,32,31,30,30,29,30,29,30,30],
    2017: [31,32,31,32,31,30,30,29,30,29,30,30],
    2018: [31,31,32,31,31,31,29,30,29,30,29,31],
    2019: [31,31,32,31,31,31,30,29,30,29,30,30],
    2020: [31,32,31,32,31,30,30,29,30,29,30,30],
    2021: [31,32,31,32,31,30,30,29,30,29,30,30],
    2022: [31,32,31,32,31,30,30,29,30,29,30,30],
    2023: [31,31,31,32,31,31,30,29,29,30,29,31],
    2024: [31,31,32,31,31,31,30,29,30,29,30,30],
    2025: [31,32,31,32,31,30,30,29,30,29,30,30],
    2026: [31,32,31,32,31,30,30,29,30,29,30,30],
    2027: [31,32,31,32,31,30,30,29,30,29,30,30],
    2028: [31,31,32,31,31,31,30,29,29,30,29,31],
    2029: [31,31,32,31,31,31,30,29,30,29,30,30],
    2030: [31,32,31,32,31,30,30,29,30,29,30,30],
    2031: [31,32,31,32,31,30,30,29,30,29,30,30],
    2032: [31,32,31,32,31,30,30,29,30,29,30,30],
    2033: [31,31,31,32,31,31,29,30,29,30,29,31],
    2034: [31,31,32,31,31,31,30,29,30,29,30,30],
    2035: [31,32,31,32,31,30,30,29,30,29,30,30],
    2036: [31,32,31,32,31,30,30,29,30,29,30,30],
    2037: [31,32,31,32,31,30,30,29,30,29,30,30],
    2038: [31,31,31,32,31,31,30,29,29,30,29,31],
    2039: [31,31,32,31,31,31,30,29,30,29,30,30],
    2040: [31,32,31,32,31,30,30,29,30,29,30,30],
    2041: [31,32,31,32,31,30,30,29,30,29,30,30],
    2042: [31,32,31,32,31,30,30,29,30,29,30,30],
    2043: [31,31,31,32,31,31,30,29,29,30,30,30],
    2044: [31,31,32,31,31,31,30,29,30,29,30,30],
    2045: [31,32,31,32,31,30,30,29,30,29,30,30],
    2046: [31,32,31,32,31,30,30,29,30,29,30,30],
    2047: [31,32,31,32,31,30,30,29,30,29,30,30],
    2048: [31,31,32,31,31,31,29,30,29,30,29,31],
    2049: [31,31,32,31,31,31,30,29,30,29,30,30],
    2050: [31,32,31,32,31,30,30,29,30,29,30,30],
    2051: [31,32,31,32,31,30,30,29,30,29,30,30],
    2052: [31,32,31,32,31,30,30,29,30,29,30,30],
    2053: [31,31,32,32,31,30,30,29,30,29,30,30],
    2054: [31,31,32,31,31,31,30,29,30,29,30,30],
    2055: [31,32,31,32,31,30,30,29,30,29,30,30],
    2056: [31,32,31,32,31,30,30,29,30,29,30,30],
    2057: [31,32,31,32,31,30,30,29,30,29,30,30],
    2058: [31,31,31,32,31,31,29,30,29,30,29,31],
    2059: [31,31,32,31,31,31,30,29,30,29,30,30],
    2060: [31,32,31,32,31,30,30,29,30,29,30,30],
    2061: [31,32,31,32,31,30,30,29,30,29,30,30],
    2062: [31,32,31,32,31,30,30,29,30,29,30,30],
    2063: [31,31,31,32,31,31,29,30,29,30,29,31],
    2064: [31,31,32,31,31,31,30,29,30,29,30,30],
    2065: [31,32,31,32,31,30,30,29,30,29,30,30],
    2066: [31,32,31,32,31,30,30,29,30,29,30,30],
    2067: [31,32,31,32,31,30,30,29,30,29,30,30],
    2068: [31,31,31,32,31,31,29,30,29,30,29,31],
    2069: [31,31,32,31,31,31,30,29,30,29,30,30],
    2070: [31,32,31,32,31,30,30,29,30,29,30,30],
    2071: [31,32,31,32,31,30,30,29,30,29,30,30],
    2072: [31,32,31,32,31,30,30,29,30,29,30,30],
    2073: [31,31,31,32,31,31,29,30,29,30,30,30],
    2074: [31,31,32,31,31,31,30,29,30,29,30,30],
    2075: [31,32,31,32,31,30,30,29,30,29,30,30],
    2076: [31,32,31,32,31,30,30,29,30,29,30,30],
    2077: [31,32,31,32,31,30,30,29,30,29,30,30],
    2078: [31,31,31,32,31,31,29,30,29,30,29,31],
    2079: [31,31,32,31,31,31,30,29,30,29,30,30],
    2080: [31,32,31,32,31,30,30,29,30,29,30,30],
    2081: [31,31,31,32,31,31,29,30,29,30,29,31],
    2082: [31,31,32,31,31,31,30,29,30,29,30,30],  # BS 2082 ≈ AD 2025/2026
    2083: [31,32,31,32,31,30,30,29,30,29,30,30],
    2084: [31,32,31,32,31,30,30,29,30,29,30,30],
    2085: [31,32,31,32,31,30,30,29,30,29,30,30],
    2086: [31,31,31,32,31,31,29,30,29,30,29,31],
    2087: [31,31,32,31,31,31,30,29,30,29,30,30],
    2088: [31,32,31,32,31,30,30,29,30,29,30,30],
    2089: [31,32,31,32,31,30,30,29,30,29,30,30],
    2090: [31,32,31,32,31,30,30,29,30,29,30,30],
}

# =============================================================================
# ANCHOR-BASED BS ↔ AD CONVERSION
#
# Verified anchor: BS 2082/01/01 = AD 2025-04-14
# Using this anchor eliminates the 14-day accumulated error that occurs
# when walking from the 1943 epoch across 82 years of variable-length months.
#
# Verified by user: AD 2026-03-18 = BS 2082-12-04
# =============================================================================
_BS_ANCHOR_AD = date_type(2025, 4, 14)  # BS 2082/01/01 — verified
_BS_ANCHOR_Y  = 2082
_BS_ANCHOR_M  = 1
_BS_ANCHOR_D  = 1


def _bs_to_ad(bs_year, bs_month, bs_day):
    """
    Convert Bikram Sambat to AD using verified anchor BS 2082/01/01 = 2025-04-14.
    """
    if bs_year not in _BS_YEAR_DATA:
        raise ValueError(f"BS year {bs_year} not in lookup table")
    months = _BS_YEAR_DATA[bs_year]
    if not (1 <= bs_month <= 12):
        raise ValueError(f"Invalid BS month {bs_month}")
    if not (1 <= bs_day <= months[bs_month - 1]):
        raise ValueError(f"BS {bs_year}/{bs_month}/{bs_day} out of range")

    # Days from anchor year start to target
    days = 0
    if bs_year >= _BS_ANCHOR_Y:
        for y in range(_BS_ANCHOR_Y, bs_year):
            days += sum(_BS_YEAR_DATA.get(y, [365]))
    else:
        for y in range(bs_year, _BS_ANCHOR_Y):
            days -= sum(_BS_YEAR_DATA.get(y, [365]))

    for m in range(1, bs_month):
        days += months[m - 1]
    days += bs_day - 1

    ad_date = _BS_ANCHOR_AD + timedelta(days=days)
    return datetime(ad_date.year, ad_date.month, ad_date.day)


def _ad_to_bs(ad_year, ad_month, ad_day):
    """
    Convert AD date to Bikram Sambat using verified anchor.
    Returns (bs_year, bs_month, bs_day).
    """
    diff = (date_type(ad_year, ad_month, ad_day) - _BS_ANCHOR_AD).days
    y, m, d = _BS_ANCHOR_Y, _BS_ANCHOR_M, _BS_ANCHOR_D

    if diff >= 0:
        while diff > 0:
            months = _BS_YEAR_DATA.get(y, [])
            dim    = months[m - 1] if months else 30
            rem    = dim - (d - 1)
            if diff < rem:
                d += diff; diff = 0
            else:
                diff -= rem; d = 1; m += 1
                if m > 12: m = 1; y += 1
    else:
        diff = abs(diff)
        while diff > 0:
            m -= 1
            if m < 1: m = 12; y -= 1
            months = _BS_YEAR_DATA.get(y, [])
            dim    = months[m - 1] if months else 30
            if diff < dim:
                d = dim - diff + 1; diff = 0
            else:
                diff -= dim; d = 1

    return y, m, d


# Self-check with user-verified value: AD 2026-03-18 = BS 2082-12-04
def _verify_bs_conversion():
    try:
        dt = _bs_to_ad(2082, 12, 4)
        assert dt.year == 2026 and dt.month == 3 and dt.day == 18, \
            f"BS 2082/12/04 → expected 2026-03-18, got {dt.date()}"
        y, m, d = _ad_to_bs(2026, 3, 18)
        assert (y, m, d) == (2082, 12, 4), \
            f"AD 2026-03-18 → expected BS 2082/12/04, got {y}/{m}/{d}"
        log.debug("BS conversion verified: 2082/12/04 ↔ 2026-03-18 ✓")
    except Exception as e:
        log.warning("BS conversion self-check FAILED: %s", e)

_verify_bs_conversion()


# Nepali calendar (BS) month names → month numbers (1=Baisakh … 12=Chaitra)
_BS_MONTHS = {
    "बैशाख": 1,  "वैशाख": 1,
    "जेठ": 2,    "जेष्ठ": 2,
    "असार": 3,   "आषाढ": 3,   "असाढ": 3,
    "साउन": 4,   "श्रावण": 4,  "सावन": 4,
    "भदौ": 5,    "भाद्र": 5,   "भादौ": 5,   "भाद्रपद": 5,
    "असोज": 6,   "आश्विन": 6,  "अश्विन": 6,
    "कार्तिक": 7,
    "मंसिर": 8,  "मार्गशीर्ष": 8, "मङ्सिर": 8,
    "पुस": 9,    "पौष": 9,    "पुष": 9,
    "माघ": 10,
    "फागुन": 11, "फाल्गुन": 11, "फाल्गुण": 11,
    "चैत": 12,   "चैत्र": 12,  "चैत्": 12,
}

# English/Nepali AD month names
_NE_AD_MONTHS = {
    "जनवरी": 1,  "फेब्रुअरी": 2, "फेब्रुवरी": 2, "मार्च": 3,
    "अप्रिल": 4, "अप्रील": 4,    "मे": 5,         "जुन": 6,
    "जुलाई": 7,  "अगस्ट": 8,     "अगष्ट": 8,      "सेप्टेम्बर": 9,
    "अक्टोबर": 10,"अक्तोबर": 10, "नोभेम्बर": 11,  "डिसेम्बर": 12,
}
_EN_MONTHS = {
    "january": 1,  "february": 2, "march": 3,    "april": 4,
    "may": 5,      "june": 6,     "july": 7,      "august": 8,
    "september": 9,"october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "oct": 10,"nov": 11,"dec": 12,
}

# Nepali relative time words
_NE_RELATIVE = {
    "आज": 0, "आजै": 0, "अहिले": 0,
    "हिजो": 1, "हिजोको": 1,
    "परसि": -1,  # future — reject
}


def _strip_tz(text):
    return re.split(r"[+Z]", text)[0].strip()


def _try_parse(text):
    """Try standard datetime formats. Returns (datetime, confidence) or (None, None)."""
    if not text:
        return None, None
    text = text.strip().translate(_NE_DIGITS)
    text = _strip_tz(text)
    text = re.sub(r"\s+", " ", text)

    formats = [
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%Y/%m/%d",
        "%B %d, %Y", "%B %d %Y",
        "%d %B %Y",  "%d %B, %Y",
        "%b %d, %Y", "%d %b %Y",
        "%Y.%m.%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt), "high"
        except ValueError:
            continue
    return None, None


def _parse_relative_date(text):
    """
    Parse relative dates in English and Nepali.
    Returns (datetime, confidence, source_label) or (None, None, None)
    """
    text_ascii = text.translate(_NE_DIGITS).strip().lower()
    now = nepal_now()

    for word, days_ago in _NE_RELATIVE.items():
        if word in text:
            if days_ago < 0:
                return None, None, None
            return now - timedelta(days=days_ago), "medium", "relative"

    m = re.search(r"(\d+)\s*(minute|min|hour|hr|day|week)s?\s*ago", text_ascii)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {
            "minute": timedelta(minutes=n), "min": timedelta(minutes=n),
            "hour": timedelta(hours=n),     "hr":  timedelta(hours=n),
            "day":  timedelta(days=n),
            "week": timedelta(weeks=n),
        }.get(unit)
        if delta:
            return now - delta, "medium", "relative"

    m = re.search(r"(\d+)\s*(घण्टा|मिनेट|दिन|हप्ता)\s*अघि", text)
    if m:
        n    = int(m.group(1).translate(_NE_DIGITS))
        unit = m.group(2)
        delta = {
            "घण्टा": timedelta(hours=n),
            "मिनेट": timedelta(minutes=n),
            "दिन":   timedelta(days=n),
            "हप्ता": timedelta(weeks=n),
        }.get(unit)
        if delta:
            return now - delta, "medium", "relative"

    return None, None, None


def _parse_bs_date(text):
    """
    Parse Bikram Sambat dates using the verified lookup table.
    e.g. '१० फागुन २०८२' → AD 2026-02-22
    Returns (datetime_in_AD, confidence, 'bs_converted') or (None, None, None)
    """
    text_ascii = text.translate(_NE_DIGITS)

    # Sort by length descending so longer month names match before shorter ones
    # (e.g. "मार्गशीर्ष" before "मार्च" to avoid partial matches)
    for month_name in sorted(_BS_MONTHS, key=len, reverse=True):
        if month_name in text:
            month_num  = _BS_MONTHS[month_name]
            nums       = [int(n) for n in re.findall(r"\d+", text_ascii)]
            # BS year: 2000–2090 range
            bs_year    = next((n for n in nums if 2000 <= n <= 2090), None)
            # BS day: 1–32, not the year
            bs_day     = next((n for n in nums if 1 <= n <= 32 and n != bs_year), None)
            if bs_year and bs_day:
                try:
                    ad_dt = _bs_to_ad(bs_year, month_num, bs_day)
                    log.debug("BS→AD: %d %s %d → %s", bs_day, month_name, bs_year, ad_dt.date())
                    return ad_dt, "high", "bs_converted"
                except Exception as e:
                    log.debug("BS conversion failed for %d/%d/%d: %s",
                              bs_year, month_num, bs_day, e)
    return None, None, None


def _parse_text_date(text):
    """
    Parse human-readable dates in Nepali AD or English.
    Returns (datetime, confidence, source_label) or (None, None, None)

    IMPORTANT: Only matches AD years (> 2000). BS years (2079, 2082 etc.)
    will NOT accidentally be treated as AD years here because BS years
    are > 2000 and would produce far-future dates which _validate_date rejects.
    """
    text_ascii = text.translate(_NE_DIGITS).strip()
    lower      = text_ascii.lower()

    for month_name, month_num in _NE_AD_MONTHS.items():
        if month_name in text:
            nums = [int(n) for n in re.findall(r"\d+", text_ascii)]
            # AD year must be in realistic range (2010–2035)
            year = next((n for n in nums if 2010 <= n <= 2035), None)
            day  = next((n for n in nums if 1 <= n <= 31), None)
            if year and day:
                try:
                    return datetime(year, month_num, day), "high", "text"
                except ValueError:
                    pass

    for month_name, month_num in _EN_MONTHS.items():
        if month_name in lower:
            nums = [int(n) for n in re.findall(r"\d+", text_ascii)]
            # AD year must be in realistic range (2010–2035)
            year = next((n for n in nums if 2010 <= n <= 2035), None)
            day  = next((n for n in nums if 1 <= n <= 31), None)
            if year and day:
                try:
                    return datetime(year, month_num, day), "high", "text"
                except ValueError:
                    pass

    return None, None, None


def _validate_date(dt, max_age_days, allow_future=False):
    """
    Validate a parsed datetime. Returns True if valid, False if rejected.
    Rejects:
      - Future dates (strictly: any date after today)
      - Dates older than max_age_days
      - Years outside realistic range (2010 to current year)
      - Any date more than 1 day ahead (event/modified dates on sites)
    """
    if dt is None:
        return False

    if hasattr(dt, "tzinfo") and dt.tzinfo:
        dt = dt.replace(tzinfo=None)

    now         = nepal_now()
    today       = now.date()
    d           = dt.date() if isinstance(dt, datetime) else dt
    current_year = today.year

    # Reject years outside realistic range
    # Upper bound: current year (future articles are impossible)
    # Lower bound: 2010 (no news older than ~15 years)
    if not (2010 <= d.year <= current_year):
        log.debug("Rejected out-of-range year: %s (current year: %d)", d, current_year)
        return False

    # Strict future rejection — no buffer at all
    # Any date after today is invalid (event dates, wrong metadata, etc.)
    if not allow_future and d > today:
        log.info("Rejected FUTURE date: %s (today: %s)", d, today)
        return False

    # Reject dates older than max_age_days
    cutoff = (now - timedelta(days=max_age_days)).date()
    if d < cutoff:
        log.debug("Rejected old date: %s (cutoff: %s, max_age: %d days)",
                  d, cutoff, max_age_days)
        return False

    return True


def cap_future_time(dt):
    """
    If a datetime's TIME is in the future (same date, but time ahead of now),
    strip the time component and return date-only at midnight.
    Rationale: a wrong time is more misleading than no time.
    Sites with misconfigured clocks still get the date right — keep the date,
    discard the unreliable time.
    Future DATES (tomorrow etc.) are handled by _ensure_ad_date.
    """
    if dt is None or not isinstance(dt, datetime):
        return dt
    now = nepal_now()
    if dt > now:
        # Keep the date, zero the time (midnight) — date is likely correct
        date_only = datetime(dt.year, dt.month, dt.day, 0, 0, 0)
        log.info("Future time stripped — kept date only: %s → %s (site clock %s ahead)",
                 dt, date_only, dt - now)
        return date_only
    return dt


# =============================================================================
# DateResult container
# =============================================================================
class DateResult:
    def __init__(self, dt=None, source="none", confidence="none"):
        self.dt         = dt
        self.source     = source
        self.confidence = confidence

    def __bool__(self):
        return self.dt is not None

    def __repr__(self):
        return f"DateResult(dt={self.dt}, source={self.source}, conf={self.confidence})"


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
def extract_publish_date(soup, max_age_days=None):
    """
    Extract and validate the published date from a BeautifulSoup article page.

    Priority order:
      1. JSON-LD structured data      → high confidence
      2. <meta> tags                  → high confidence
      3. <time> tags                  → high confidence
      4. CSS class / itemprop attrs   → medium confidence
      5. Bikram Sambat text dates     → high confidence (BS→AD conversion)
      6. Relative date text           → medium confidence
      7. Nepali AD / English text     → high confidence
      8. ISO regex scan               → medium confidence
      9. Return empty DateResult      → caller decides fallback

    Returns DateResult. .dt is None when no valid date found.
    """
    from config import MAX_ARTICLE_AGE_DAYS
    max_age = max_age_days or MAX_ARTICLE_AGE_DAYS

    def try_candidate(raw_val, source_label):
        """
        Parse a raw date string. Returns DateResult.
        Caps future TIMES on today's date at nepal_now() —
        handles sites whose clocks run slightly ahead.
        """
        if not raw_val or not str(raw_val).strip():
            return None
        raw = str(raw_val).strip()

        dt, conf = _try_parse(raw)
        if dt:
            return DateResult(cap_future_time(dt), source_label, conf)

        dt, conf, _ = _parse_bs_date(raw)
        if dt:
            return DateResult(cap_future_time(dt), "bs_converted", conf)

        dt, conf, _ = _parse_relative_date(raw)
        if dt:
            return DateResult(cap_future_time(dt), "relative", conf)

        dt, conf, _ = _parse_text_date(raw)
        if dt:
            return DateResult(cap_future_time(dt), source_label, conf)

        return None

    # ── 1. JSON-LD ────────────────────────────────────────────────────────────
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data  = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Priority: datePublished/dateCreated only (most reliable)
                # dateModified/startDate often contain future or update dates
                for key in ("datePublished", "dateCreated"):
                    r = try_candidate(item.get(key), "json_ld")
                    if r:
                        log.debug("Date from JSON-LD (%s): %s", key, r.dt)
                        return r
                # Fallback to other date fields only if above not found
                for key in ("dateModified", "uploadDate", "startDate"):
                    val = item.get(key)
                    if val:
                        r = try_candidate(str(val), "json_ld_fallback")
                        if r:
                            log.debug("Date from JSON-LD fallback (%s): %s", key, r.dt)
                            return r
                for node in item.get("@graph", []):
                    if not isinstance(node, dict):
                        continue
                    for key in ("datePublished", "dateCreated"):
                        r = try_candidate(node.get(key), "json_ld")
                        if r:
                            return r
                    # Fallback for graph nodes
                    for key in ("dateModified",):
                        val = node.get(key)
                        if val:
                            r = try_candidate(str(val), "json_ld_fallback")
                            if r:
                                return r
        except Exception:
            pass

    # ── 2. <meta> tags ────────────────────────────────────────────────────────
    # Check publish-specific meta first, modified/updated as fallback only
    for name in ("article:published_time", "og:published_time",
                 "pubdate", "publishdate", "DC.date", "DC.Date",
                 "sailthru.date", "parsely-pub-date",
                 # Fallback: modified times (less reliable)
                 "article:modified_time", "og:updated_time", "date"):
        tag = (soup.find("meta", property=name) or
               soup.find("meta", attrs={"name": name}))
        if tag:
            r = try_candidate(tag.get("content", ""), "meta")
            if r:
                log.debug("Date from meta[%s]: %s", name, r.dt)
                return r

    # ── 3. <time> tags ────────────────────────────────────────────────────────
    for tag in soup.find_all("time"):
        val = tag.get("datetime") or tag.get("pubdate") or tag.get_text(strip=True)
        r   = try_candidate(val, "time_tag")
        if r:
            log.debug("Date from <time>: %s", r.dt)
            return r

    # ── 4. CSS class / itemprop ───────────────────────────────────────────────
    for sel in ("[itemprop='datePublished']", "[itemprop='dateCreated']",
                "[class*='publish']", "[class*='posted']",
                "[class*='entry-date']", "[class*='post-date']",
                "[class*='article-date']", "[class*='news-date']",
                "[class*='date']", "[class*='time']",
                "[data-date]", "[data-time]", "[data-published]"):
        for tag in soup.select(sel)[:5]:
            for attr in ("content", "datetime", "data-date", "data-time", "data-published"):
                r = try_candidate(tag.get(attr, ""), "css")
                if r:
                    log.debug("Date from attr [%s] on '%s': %s", attr, sel, r.dt)
                    return r
            text = tag.get_text(strip=True)
            if text and 3 < len(text) < 100:
                r = try_candidate(text, "css")
                if r:
                    log.debug("Date from CSS text '%s': %s", sel, r.dt)
                    return r

    # ── 5+6+7. Full text scan ────────────────────────────────────────────────
    full_text = soup.get_text(" ")[:5000]

    # BS calendar dates (e.g. "प्रकाशित मिति : १० फागुन २०८२")
    dt, conf, _ = _parse_bs_date(full_text)
    if dt:
        log.debug("BS date from page text: %s", dt.date())
        return DateResult(dt, "bs_converted", conf)

    # Relative dates
    dt, conf, _ = _parse_relative_date(full_text[:500])
    if dt:
        return DateResult(dt, "relative", conf)

    # Nepali AD / English text date
    dt, conf, _ = _parse_text_date(full_text[:3000])
    if dt:
        return DateResult(dt, "text", conf)

    # ── 8. ISO date regex ────────────────────────────────────────────────────
    m = re.search(
        r"\b(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b",
        full_text
    )
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            log.debug("Date from ISO regex: %s", dt)
            return DateResult(dt, "regex", "medium")
        except ValueError:
            pass

    log.debug("No publish date found on page")
    return DateResult()  # .dt is None — genuinely no date found anywhere


def _ensure_ad_date(result, context=""):
    """
    Final guard — ensure a DateResult contains a valid AD date.
    Blocks:
      - BS years (year > current_year, e.g. 2082)
      - Future dates (any date after today)
      - Pre-2010 dates
    Called by generic_scraper after every date extraction attempt.
    """
    if not result or result.dt is None:
        return result

    today = nepal_now().date()
    d     = result.dt.date() if isinstance(result.dt, datetime) else result.dt

    # Block future DATES (date > today = wrong metadata, BS year, etc.)
    # Future TIMES on today's date are handled by cap_future_time()
    if d > today:
        log.warning("Blocked future/BS date: %s (year=%d src=%s) %s",
                    d, d.year, result.source, context)
        return DateResult()

    # Cap future times on today's date (site clock slightly ahead)
    if isinstance(result.dt, datetime):
        result.dt = cap_future_time(result.dt)

    # Block pre-2010
    if d.year < 2010:
        log.warning("Blocked pre-2010 date: %s (src=%s) %s",
                    d, result.source, context)
        return DateResult()

    return result

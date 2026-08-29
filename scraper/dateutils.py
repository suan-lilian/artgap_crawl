"""날짜 파싱 유틸.

두 가지 상황을 처리한다:
1. parse_column_date: 행 안에 별도 날짜 컬럼이 있는 경우 ("2026-09-10 16:00",
   "2026.08.14 - 2026.10.18" 같은 범위는 끝 날짜를 반환, "-"/빈 문자열은 None)
2. extract_deadline_from_title: 마감일이 제목 문자열 안에 "(~8.24.(월) 17:00까지)"
   식으로 섞여 있는 경우, 등록일(reference_date)을 기준으로 연도를 추정해서 추출
"""
import re
from datetime import date, timedelta
from typing import Optional

_FULL_DATE_RE = re.compile(r"(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})")
_MD_RE = re.compile(r"(\d{1,2})\s*[./]\s*(\d{1,2})")


def parse_column_date(text: Optional[str]) -> Optional[date]:
    """행 안의 날짜 컬럼 텍스트를 파싱. 범위("A - B")면 끝 날짜(B)를 반환."""
    if not text:
        return None
    text = text.strip()
    if not text or text in ("-", "–", "—", "−"):
        return None

    matches = _FULL_DATE_RE.findall(text)
    if not matches:
        return None

    y, m, d = matches[-1]
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def _resolve_year(month: int, day: int, reference_date: date) -> Optional[date]:
    try:
        candidate = date(reference_date.year, month, day)
    except ValueError:
        return None
    # 등록일보다 훨씬 과거로 보이면(예: 12월에 등록, 마감 1월) 다음 해로 보정
    if (candidate - reference_date) < timedelta(days=-180):
        try:
            candidate = date(reference_date.year + 1, month, day)
        except ValueError:
            return None
    return candidate


def extract_deadline_from_title(title: str, reference_date: date) -> Optional[date]:
    """제목 문자열 안에서 마감일을 추출한다.

    우선순위:
    1. 마지막 '~' 뒤에 나오는 날짜 (범위든 단일 마감이든 끝/마감 쪽 날짜)
    2. '까지' 앞에 나오는 날짜
    3. 그 외에는 마감일을 알 수 없다고 보고 None 반환 (거짓 양성 방지를 위해
       제목 전체를 무작정 뒤지지 않음)
    """
    if not title:
        return None

    anchor_idx = None
    tilde_idx = title.rfind("~")
    if tilde_idx != -1:
        anchor_idx = tilde_idx + 1
    else:
        until_idx = title.find("까지")
        if until_idx != -1:
            anchor_idx = max(0, until_idx - 20)

    if anchor_idx is None:
        return None

    tail = title[anchor_idx : anchor_idx + 40]

    full_match = _FULL_DATE_RE.search(tail)
    if full_match:
        y, m, d = full_match.groups()
        try:
            return date(int(y), int(m), int(d))
        except ValueError:
            pass

    md_match = _MD_RE.search(tail)
    if md_match:
        m, d = (int(x) for x in md_match.groups())
        if 1 <= m <= 12 and 1 <= d <= 31:
            return _resolve_year(m, d, reference_date)

    return None

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


def _date_from_anchor(title: str, anchor_idx: int, reference_date: date) -> Optional[date]:
    tail = title[anchor_idx : anchor_idx + 40]

    full_match = _FULL_DATE_RE.search(tail)
    if full_match:
        y, m, d = full_match.groups()
        try:
            return date(int(y), int(m), int(d))
        except ValueError:
            return None

    md_match = _MD_RE.search(tail)
    if md_match:
        m, d = (int(x) for x in md_match.groups())
        if 1 <= m <= 12 and 1 <= d <= 31:
            return _resolve_year(m, d, reference_date)

    return None


def extract_deadline_from_title(title: str, reference_date: date) -> Optional[date]:
    """제목 문자열 안에서 마감일을 추출한다.

    한 제목에 마감일이 여러 개 섞여 있는 경우(예: "(융자)4차 공모(~8.21),
    (보증)5차 공모(~8.10)")가 있어, '~' 뒤/'까지' 앞 후보를 전부 모아서
    그중 가장 늦은(미래에 가까운) 날짜를 마감일로 사용한다. 마지막 후보만
    쓰면 이미 지난 날짜 때문에 실제로는 아직 열려있는 공모까지 마감 처리되는
    문제가 있었음.

    후보가 하나도 없으면 마감일을 알 수 없다고 보고 None을 반환한다(거짓
    양성 방지를 위해 제목 전체를 무작정 뒤지지 않음).
    """
    if not title:
        return None

    anchor_idxs = [m.start() + 1 for m in re.finditer("~", title)]
    for m in re.finditer("까지", title):
        anchor_idxs.append(max(0, m.start() - 20))

    if not anchor_idxs:
        return None

    candidates = [_date_from_anchor(title, idx, reference_date) for idx in anchor_idxs]
    candidates = [c for c in candidates if c is not None]
    if not candidates:
        return None

    return max(candidates)

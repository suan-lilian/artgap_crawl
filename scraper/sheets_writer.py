"""Google 스프레드시트 기록.

환경변수:
  GOOGLE_SERVICE_ACCOUNT_JSON : 서비스 계정 키 JSON 전체 내용(문자열)
  GOOGLE_SHEET_ID             : 대상 스프레드시트 ID (URL의 /d/와 /edit 사이 값)

서비스 계정 이메일(...@...iam.gserviceaccount.com)을 대상 스프레드시트에
'편집자'로 공유해줘야 쓰기가 성공한다.

시트 구성:
  - "지원사업공고" (메인): 사이트명 / 마감일 / 공고명 / 바로가기 / 지원여부(체크박스)
    현재 진행중인 공고만 표시(마감 지난 건 크롤러 단계에서 이미 제외됨).
    마감일 오름차순 정렬, 마감 7일 이내는 배경 #ff7878 / 글자색 #ffffff로 강조.
    '지원여부' 체크박스는 '바로가기' 링크를 기준으로 이전 실행 값을 그대로 이어받는다
    (매번 시트 전체를 새로 쓰지만 체크 상태는 유지됨).
  - "지난공고" (아카이브): 메인 시트에서 사라진(마감되었거나 원 사이트에서 내려간) 공고를
    '보관일'과 함께 옮겨 쌓아두고, ARCHIVE_RETENTION_DAYS(기본 180일)보다 오래된 행은
    자동으로 삭제한다.
"""
import json
import os
from datetime import date, datetime, timedelta
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

MAIN_HEADER = ["사이트명", "마감일", "공고명", "바로가기", "지원여부"]
ARCHIVE_HEADER = ["사이트명", "마감일", "공고명", "바로가기", "지원여부", "보관일"]
ARCHIVE_WORKSHEET_NAME = "지난공고"
ARCHIVE_RETENTION_DAYS = 180

URGENT_WITHIN_DAYS = 7
URGENT_BG = {"red": 1.0, "green": 0x78 / 255, "blue": 0x78 / 255}
URGENT_FG = {"red": 1.0, "green": 1.0, "blue": 1.0}
DEFAULT_BG = {"red": 1.0, "green": 1.0, "blue": 1.0}
DEFAULT_FG = {"red": 0.0, "green": 0.0, "blue": 0.0}


def _get_client() -> gspread.Client:
    creds_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    creds_info = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_or_create_worksheet(sh: gspread.Spreadsheet, name: str, cols: int) -> gspread.Worksheet:
    try:
        return sh.worksheet(name)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=name, rows="100", cols=str(cols))


def _parse_bool(text: str) -> bool:
    return text.strip().upper() == "TRUE"


def _parse_date_cell(text: str) -> Optional[date]:
    text = text.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y. %m. %d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _read_existing_by_link(ws: gspread.Worksheet, link_col: int, applied_col: Optional[int]) -> dict:
    """기존 시트를 (헤더 제외) link -> {"applied": bool, "row": [...]} 형태로 읽어온다."""
    values = ws.get_all_values()
    result = {}
    for row in values[1:]:
        if len(row) <= link_col or not row[link_col]:
            continue
        link = row[link_col]
        applied = _parse_bool(row[applied_col]) if applied_col is not None and len(row) > applied_col else False
        result[link] = {"applied": applied, "row": row}
    return result


def _cell_format_request(sheet_id: int, start_row: int, end_row: int, n_cols: int, bg: dict, fg: dict) -> dict:
    """start_row/end_row는 0-based, end_row는 배타적(exclusive)."""
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": 0,
                "endColumnIndex": n_cols,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": bg,
                    "textFormat": {"foregroundColor": fg},
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat.foregroundColor)",
        }
    }


def _checkbox_validation_request(sheet_id: int, start_row: int, end_row: int, col: int) -> dict:
    return {
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": col,
                "endColumnIndex": col + 1,
            },
            "rule": {"condition": {"type": "BOOLEAN"}, "strict": True},
        }
    }


def _write_main_sheet(sh: gspread.Spreadsheet, rows: list[dict], worksheet_name: str) -> list[dict]:
    """메인 시트를 새로 쓰고, 지금 목록에서 사라진(마감/삭제된) 기존 행들을 반환한다."""
    ws = _get_or_create_worksheet(sh, worksheet_name, cols=5)

    old_by_link = _read_existing_by_link(ws, link_col=3, applied_col=4)

    def sort_key(r: dict):
        d = r.get("deadline")
        return (d is None, d or date.max)

    sorted_rows = sorted(rows, key=sort_key)
    new_links = {r.get("link", "") for r in sorted_rows}

    values = [MAIN_HEADER]
    for r in sorted_rows:
        deadline = r.get("deadline")
        link = r.get("link", "")
        applied = old_by_link.get(link, {}).get("applied", False)
        values.append(
            [
                r.get("site", ""),
                deadline.isoformat() if deadline else "",
                r.get("title", ""),
                link,
                applied,
            ]
        )

    ws.clear()
    # USER_ENTERED로 써야 "2026-09-10" 문자열이 실제 날짜 값으로 인식되어
    # 마감일 컬럼에 이미 지정해 둔 날짜 서식이 그대로 적용된다.
    ws.update(values=values, range_name="A1", value_input_option="USER_ENTERED")

    today = date.today()
    urgent_row_indexes = [
        i
        for i, r in enumerate(sorted_rows)
        if r.get("deadline") and (r["deadline"] - today) <= timedelta(days=URGENT_WITHIN_DAYS)
    ]

    requests = []
    if sorted_rows:
        requests.append(_cell_format_request(ws.id, 1, 1 + len(sorted_rows), 5, DEFAULT_BG, DEFAULT_FG))
        for i in urgent_row_indexes:
            sheet_row = 1 + i
            requests.append(_cell_format_request(ws.id, sheet_row, sheet_row + 1, 5, URGENT_BG, URGENT_FG))
    requests.append(_checkbox_validation_request(ws.id, 1, max(2, 1 + len(sorted_rows)), 4))

    if requests:
        sh.batch_update({"requests": requests})

    print(
        f"[{worksheet_name}] {len(rows)}건 기록 (마감 {URGENT_WITHIN_DAYS}일 이내 강조 "
        f"{len(urgent_row_indexes)}건)"
    )

    newly_closed = [info["row"] for link, info in old_by_link.items() if link not in new_links]
    return newly_closed


def _write_archive_sheet(sh: gspread.Spreadsheet, newly_closed_rows: list[list[str]]) -> None:
    ws = _get_or_create_worksheet(sh, ARCHIVE_WORKSHEET_NAME, cols=6)
    existing = ws.get_all_values()
    existing_data_rows = existing[1:] if existing else []

    today = date.today()
    cutoff = today - timedelta(days=ARCHIVE_RETENTION_DAYS)

    kept = []
    for row in existing_data_rows:
        archived_on = _parse_date_cell(row[5]) if len(row) > 5 else None
        if archived_on is not None and archived_on < cutoff:
            continue  # 보관 기간(기본 180일) 초과 -> 삭제
        kept.append(row)

    pruned_count = len(existing_data_rows) - len(kept)

    for row in newly_closed_rows:
        padded = list(row) + [""] * (5 - len(row)) if len(row) < 5 else row[:5]
        kept.append(padded + [today.isoformat()])

    def sort_key(row: list[str]):
        return row[5] if len(row) > 5 else ""

    kept.sort(key=sort_key, reverse=True)

    values = [ARCHIVE_HEADER] + kept
    ws.clear()
    ws.update(values=values, range_name="A1", value_input_option="USER_ENTERED")

    if kept:
        request = _checkbox_validation_request(ws.id, 1, 1 + len(kept), 4)
        sh.batch_update({"requests": [request]})

    print(
        f"[{ARCHIVE_WORKSHEET_NAME}] 신규 보관 {len(newly_closed_rows)}건, "
        f"{ARCHIVE_RETENTION_DAYS}일 초과 삭제 {pruned_count}건, 현재 총 {len(kept)}건"
    )


def write_rows(
    rows: list[dict],
    sheet_id: Optional[str] = None,
    worksheet_name: str = "지원사업공고",
) -> None:
    sheet_id = sheet_id or os.environ["GOOGLE_SHEET_ID"]
    client = _get_client()
    sh = client.open_by_key(sheet_id)

    newly_closed = _write_main_sheet(sh, rows, worksheet_name)
    _write_archive_sheet(sh, newly_closed)

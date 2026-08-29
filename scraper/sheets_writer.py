"""Google 스프레드시트 기록.

환경변수:
  GOOGLE_SERVICE_ACCOUNT_JSON : 서비스 계정 키 JSON 전체 내용(문자열)
  GOOGLE_SHEET_ID             : 대상 스프레드시트 ID (URL의 /d/와 /edit 사이 값)

서비스 계정 이메일(...@...iam.gserviceaccount.com)을 대상 스프레드시트에
'편집자'로 공유해줘야 쓰기가 성공한다.

컬럼 순서: 사이트명 / 마감일 / 공고명 / 바로가기 (마감일 오름차순 정렬).
마감이 7일 이내로 임박한 행은 배경 #ff7878 / 글자색 #ffffff 로 강조 표시한다.
"""
import json
import os
from datetime import date, timedelta
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADER = ["사이트명", "마감일", "공고명", "바로가기"]

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


def _cell_format_request(sheet_id: int, start_row: int, end_row: int, bg: dict, fg: dict) -> dict:
    """start_row/end_row는 0-based, end_row는 배타적(exclusive). A~D열(0~3) 대상."""
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": 0,
                "endColumnIndex": 4,
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


def write_rows(
    rows: list[dict],
    sheet_id: Optional[str] = None,
    worksheet_name: str = "지원사업공고",
) -> None:
    sheet_id = sheet_id or os.environ["GOOGLE_SHEET_ID"]
    client = _get_client()
    sh = client.open_by_key(sheet_id)

    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows=str(len(rows) + 10), cols="4")

    def sort_key(r: dict):
        d = r.get("deadline")
        return (d is None, d or date.max)

    sorted_rows = sorted(rows, key=sort_key)

    values = [HEADER]
    for r in sorted_rows:
        deadline = r.get("deadline")
        values.append(
            [
                r.get("site", ""),
                deadline.isoformat() if deadline else "",
                r.get("title", ""),
                r.get("link", ""),
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
        # 이전 실행에서 남은 강조 표시가 있을 수 있으므로 데이터 영역 전체를 먼저 기본 서식으로 초기화
        requests.append(_cell_format_request(ws.id, 1, 1 + len(sorted_rows), DEFAULT_BG, DEFAULT_FG))
        for i in urgent_row_indexes:
            sheet_row = 1 + i  # 0-based, 헤더가 row index 0
            requests.append(_cell_format_request(ws.id, sheet_row, sheet_row + 1, URGENT_BG, URGENT_FG))

    if requests:
        sh.batch_update({"requests": requests})

    print(
        f"구글 시트에 {len(rows)}건 기록 완료 (worksheet: {worksheet_name}, "
        f"마감 {URGENT_WITHIN_DAYS}일 이내 강조 {len(urgent_row_indexes)}건)"
    )

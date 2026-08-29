"""Google 스프레드시트 기록.

환경변수:
  GOOGLE_SERVICE_ACCOUNT_JSON : 서비스 계정 키 JSON 전체 내용(문자열)
  GOOGLE_SHEET_ID             : 대상 스프레드시트 ID (URL의 /d/와 /edit 사이 값)

서비스 계정 이메일(...@...iam.gserviceaccount.com)을 대상 스프레드시트에
'편집자'로 공유해줘야 쓰기가 성공한다.
"""
import json
import os
from datetime import date
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADER = ["사이트명", "공고명", "마감일", "바로가기"]


def _get_client() -> gspread.Client:
    creds_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    creds_info = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return gspread.authorize(creds)


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

    values = [HEADER]
    for r in sorted(rows, key=sort_key):
        deadline = r.get("deadline")
        values.append(
            [
                r.get("site", ""),
                r.get("title", ""),
                deadline.isoformat() if deadline else "",
                r.get("link", ""),
            ]
        )

    ws.clear()
    ws.update(values=values, range_name="A1")
    print(f"구글 시트에 {len(rows)}건 기록 완료 (worksheet: {worksheet_name})")

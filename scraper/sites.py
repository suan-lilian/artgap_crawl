"""
사이트별 크롤링 설정.

각 SiteConfig의 selector는 실제 사이트에 접속해서(2026-08-29 기준) 검증한 값입니다.
사이트 구조는 언제든 바뀔 수 있으므로, 크롤링 결과가 0건이면 가장 먼저 이 파일의
selector가 여전히 유효한지 확인하세요.

selector는 모두 "행(row) 요소 기준 상대경로"입니다 (row_selector로 찾은 각 요소 안에서
title_selector / link_selector / deadline_selector / posted_date_selector / status_selector를 찾습니다).
"""
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class SiteConfig:
    key: str
    name: str
    list_url: str

    row_selector: str

    # None이면 row 자신을 사용
    title_selector: Optional[str] = None
    link_selector: Optional[str] = None

    # "href": <a href> 를 그대로 사용 (상대경로는 자동으로 절대경로로 변환됨)
    # "onclick": onclick 속성을 정규식으로 파싱해서 link_builder로 URL을 재구성
    link_attr: Literal["href", "onclick"] = "href"
    link_builder: Optional[str] = None  # crawler.py의 LINK_BUILDERS 키

    # 마감일이 "column"(행 안의 별도 날짜 필드)에 있는지 "title"(제목 안에 텍스트로 포함)인지
    deadline_source: Literal["column", "title"] = "column"
    deadline_selector: Optional[str] = None  # deadline_source == "column" 일 때 사용
    posted_date_selector: Optional[str] = None  # deadline_source == "title" 일 때 연도 추정용 등록일

    # 접수중/접수마감 등 상태 아이콘으로 필터링하고 싶을 때 사용 (선택)
    status_selector: Optional[str] = None
    status_keep_pattern: Optional[str] = None  # 이 정규식에 매치되는 행만 유지

    # 제목이 이 정규식에 매치되면 해당 행은 스킵 (예: "[결과발표]" 등 공고가 아닌 글 제외)
    title_exclude_pattern: Optional[str] = None

    # JS 렌더링 사이트: row_selector가 나타날 때까지 대기
    wait_selector: Optional[str] = None
    wait_timeout_ms: int = 15000

    enabled: bool = True
    notes: str = ""


SITES: list[SiteConfig] = [
    SiteConfig(
        key="artskorealab",
        name="아트코리아랩",
        list_url="https://www.artskorealab.kr/bbs/list.do?key=2303300002",
        row_selector="ul.notice-list.pc li",
        title_selector="strong.ti",
        link_selector="a.box",
        link_attr="onclick",
        link_builder="artskorealab",
        deadline_source="title",
        posted_date_selector="span.date",
        notes=(
            "'공지사항' 게시판에 지원사업 공고가 함께 올라옴. 마감일은 별도 컬럼이 아니라 "
            "제목 안에 '(~8.24.(월) 17:00까지)' 형태로 포함되어 있어 제목에서 정규식으로 추출."
        ),
    ),
    SiteConfig(
        key="artmore",
        name="아트모아",
        list_url="https://www.artmore.kr/sub/community/notice_list.do",
        row_selector="table.notice_tb tbody tr",
        title_selector="td.ta_l a",
        link_selector="td.ta_l a",
        deadline_source="title",
        posted_date_selector="td:nth-child(3)",
        notes=(
            "artmore.kr은 예술경영지원센터 산하 예술인 일자리 플랫폼. '공지사항' 게시판에 "
            "예술산업 금융지원 등 지원사업 공고가 올라오며, 마감일은 제목 안에 포함됨."
        ),
    ),
    SiteConfig(
        key="arko",
        name="한국문화예술위원회(아르코)",
        list_url="https://thearts.arko.or.kr/thearts/news/contest",
        row_selector="div.output-list li",
        title_selector="h2.title",
        link_selector="a.item",
        deadline_source="column",
        deadline_selector="p.date",
        wait_selector="div.output-list li",
        wait_timeout_ms=20000,
        notes=(
            "arko.or.kr은 포털 성격이라 실제 목록은 아르코 통합플랫폼(thearts.arko.or.kr)의 "
            "'공모' 게시판에 있음. 이 게시판은 '아트누리' 연동으로 전국 모든 기관의 공모를 "
            "통합해서 보여주므로 아르코 자체 공고만 있는 게 아님(기관명 필터 기능 없음). "
            "JS 렌더링 사이트라 wait_selector 필요. 날짜는 'YYYY.MM.DD - YYYY.MM.DD' 범위라 "
            "끝 날짜를 마감일로 사용."
        ),
    ),
    SiteConfig(
        key="sfac",
        name="서울문화재단",
        list_url="https://www.sfac.or.kr/opensquare/notice/support_list.do?cbIdx=992",
        row_selector="ul.board-list--wrap li",
        title_selector="dl.item--col.subject dd",
        link_selector="a",
        link_attr="onclick",
        link_builder="sfac",
        deadline_source="title",
        posted_date_selector="dl.item--col.date dd",
        title_exclude_pattern=r"^\[결과",
        notes=(
            "'공모소식' 게시판. 링크가 <a href='javascript:void(0)' onclick=\"doView('992','bcIdx',...)\">"
            "형태라 onclick에서 cbIdx/bcIdx를 파싱해 URL 재구성. 마감일은 제목 안에 포함. "
            "[결과발표]로 시작하는 선정결과 글은 지원사업 공고가 아니므로 제외."
        ),
    ),
    SiteConfig(
        key="gokams",
        name="예술경영지원센터",
        list_url="https://www.gokams.or.kr/02_apply/introduction.aspx",
        row_selector="table.boardList tbody tr",
        title_selector="td.left a",
        link_selector="td.left a",
        deadline_source="column",
        deadline_selector="td:nth-child(4)",
        status_selector="td:nth-child(2) img",
        status_keep_pattern="접수중",
        notes=(
            "'공모사업 안내' 게시판(지원/신청 메뉴). 접수마감/선정결과 컬럼이 분리되어 있고, "
            "2번째 컬럼 아이콘의 alt 텍스트('접수중'/'접수마감')로 선정결과 글을 걸러냄."
        ),
    ),
    SiteConfig(
        key="momo365",
        name="모모365",
        list_url="https://www.momo365.net/Support?cd=support&ViewType=list",
        row_selector="table.qx_support_content tbody tr",
        title_selector="td:nth-child(3) a",
        link_selector="td:nth-child(3) a",
        deadline_source="column",
        deadline_selector="td:nth-child(8)",
        notes=(
            "'공모사업' 게시판. 시작일/마감일이 각각 별도 컬럼(YYYY-MM-DD)으로 깔끔하게 "
            "분리되어 있어 파싱이 가장 단순함. 이 사이트 자체가 전국 문화예술 공모 통합 "
            "플랫폼이라 여러 기관 공고가 섞여 나오는 것이 정상."
        ),
    ),
    SiteConfig(
        key="wearts",
        name="위아츠",
        list_url="https://wearts.co.kr/ALL",
        row_selector="",
        enabled=False,
        notes=(
            "봇 차단이 아니라 로그인(회원) 필요 구조. '지난 주 지원사업 소식(무료)' 게시글도 "
            "클릭하면 onclick=\"location.href='/login?...'\" 로 강제 리다이렉트됨. 계정 생성/"
            "로그인 자동화는 정책상 수행할 수 없어 비활성화(enabled=False) 처리함. 사용자가 "
            "직접 로그인 세션(쿠키)을 제공하면 그걸로 재도전 가능."
        ),
    ),
]

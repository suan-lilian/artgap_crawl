"""예술 지원사업 공고 스크랩 진입점.

python main.py           -> 크롤링 + 구글 시트 기록
python main.py --dry-run -> 크롤링만 하고 콘솔에만 출력 (시트 연동 없이 검증할 때)
"""
import argparse

from dotenv import load_dotenv

from scraper.crawler import crawl_all

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="구글 시트에 쓰지 않고 콘솔에만 결과를 출력",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Playwright를 headless=False로 실행 (디버깅용)",
    )
    args = parser.parse_args()

    rows = crawl_all(headless=not args.headed)

    print(f"\n총 {len(rows)}건의 진행중인 지원사업 공고를 수집했습니다.\n")
    for r in rows:
        deadline = r["deadline"].isoformat() if r["deadline"] else "미상"
        print(f"[{r['site']}] {r['title']} | 마감: {deadline} | {r['link']}")

    if args.dry_run:
        print("\n--dry-run 옵션으로 실행되어 구글 시트에는 기록하지 않았습니다.")
        return

    from scraper.sheets_writer import write_rows

    write_rows(rows)


if __name__ == "__main__":
    main()

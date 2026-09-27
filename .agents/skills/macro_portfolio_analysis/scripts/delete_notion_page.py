import os
import sys
import json
import logging
import argparse
import re
from pathlib import Path
from dotenv import load_dotenv
from notion_client import Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def normalize_date(date_str: str) -> str:
    """YYYYMMDD 또는 YYYY-MM-DD 문자열을 YYYY-MM-DD로 변환합니다."""
    date_str = str(date_str).strip()
    m = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})$", date_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return date_str

def delete_existing_pages(target_date: str, db_id: str = None, api_key: str = None) -> int:
    load_dotenv()
    
    api_key = api_key or os.getenv("NOTION_API_KEY")
    db_id = db_id or os.getenv("NOTION_DB_ID")
    
    if not api_key or not db_id:
        logger.error("NOTION_API_KEY or NOTION_DB_ID is missing in environment.")
        return 0

    target_date_iso = normalize_date(target_date)
    logger.info(f"[Notion Cleanup] Checking existing pages for date: {target_date_iso}")

    client = Client(auth=api_key)

    # 1. DB 스키마 및 data_source_id 확인
    try:
        db_info = client.databases.retrieve(db_id)
    except Exception as e:
        logger.error(f"Failed to retrieve database ({db_id}): {e}")
        return 0

    db_properties = db_info.get("properties", {})
    ds_id = None
    if db_info.get("data_sources"):
        ds_id = db_info["data_sources"][0]["id"]
        try:
            ds_info = client.data_sources.retrieve(ds_id)
            db_properties = ds_info.get("properties", db_properties)
        except Exception as e:
            logger.warning(f"Failed to retrieve data_source info ({ds_id}): {e}")

    # 2. 날짜 속성 식별
    date_prop = None
    for candidate in ["날짜", "작성일", "Date"]:
        if candidate in db_properties and db_properties[candidate]["type"] == "date":
            date_prop = candidate
            break

    if not date_prop:
        # type이 date인 첫 번째 속성 탐색
        for k, v in db_properties.items():
            if v.get("type") == "date":
                date_prop = k
                break

    if not date_prop:
        logger.warning("No 'date' property found in Notion database. Skipping cleanup.")
        return 0

    # 3. 해당 날짜의 기존 페이지 쿼리
    date_filter = {
        "property": date_prop,
        "date": {
            "equals": target_date_iso
        }
    }

    results = []
    try:
        if ds_id:
            query_res = client.data_sources.query(data_source_id=ds_id, filter=date_filter)
            results = query_res.get("results", [])
        else:
            query_res = client.request(
                path=f"databases/{db_id}/query",
                method="POST",
                body={"filter": date_filter}
            )
            results = query_res.get("results", [])
    except Exception as e:
        logger.error(f"Failed to query Notion pages for date {target_date_iso}: {e}")
        return 0

    if not results:
        logger.info(f"[Notion Cleanup] No existing page found for date {target_date_iso}. Ready for new upload.")
        return 0

    # 4. 발견된 페이지들 아카이브(삭제) 처리
    archived_count = 0
    for page in results:
        page_id = page.get("id")
        title_blocks = page.get("properties", {}).get("이름", {}).get("title", [])
        page_title = title_blocks[0].get("plain_text", "Untitled") if title_blocks else "Untitled"
        
        try:
            client.pages.update(page_id=page_id, archived=True)
            logger.info(f"[Notion Cleanup] Archived existing page: '{page_title}' (ID: {page_id})")
            archived_count += 1
        except Exception as e:
            logger.error(f"[Notion Cleanup] Failed to archive page {page_id}: {e}")

    logger.info(f"[Notion Cleanup] Successfully cleaned up {archived_count} existing page(s) for date {target_date_iso}.")
    return archived_count

def main():
    parser = argparse.ArgumentParser(description="Archive existing Notion pages for a specific date to prevent duplicates")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD or YYYYMMDD format")
    args = parser.parse_args()

    target_date = args.date
    if not target_date:
        # scratch/notion_upload_meta.json 파일에서 fallback 탐색
        meta_path = Path("scratch/notion_upload_meta.json")
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    target_date = meta.get("date")
            except Exception as e:
                logger.warning(f"Could not read scratch/notion_upload_meta.json: {e}")

    if not target_date:
        logger.error("No target date specified. Please pass --date <YYYY-MM-DD> or provide scratch/notion_upload_meta.json")
        sys.exit(1)

    delete_existing_pages(target_date)

if __name__ == "__main__":
    main()

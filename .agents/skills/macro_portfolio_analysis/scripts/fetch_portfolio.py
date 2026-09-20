import os
import json
import logging
import time
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def cleanup_old_files(target_dir, max_days=15):
    """지정된 디렉토리 내 생성/수정된 지 max_days일이 지난 파일들을 정리합니다."""
    if not os.path.exists(target_dir):
        return
    now = time.time()
    cutoff = now - (max_days * 86400)
    
    removed_count = 0
    for root, dirs, files in os.walk(target_dir):
        for f in files:
            file_path = os.path.join(root, f)
            try:
                if os.path.getmtime(file_path) < cutoff:
                    os.remove(file_path)
                    removed_count += 1
            except Exception as e:
                logger.warning(f"Failed to remove old file {file_path}: {e}")
                
    if removed_count > 0:
        logger.info(f"Cleaned up {removed_count} file(s) older than {max_days} days in '{target_dir}'.")

def fetch_portfolio_data(target_date=None):
    load_dotenv()
    
    # 15일 지난 임시 파일들 정리
    cleanup_old_files("scratch", max_days=15)
    cleanup_old_files("archive", max_days=15)
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        logger.error("Missing Supabase credentials in .env file.")
        return []

    max_retries = 3
    for attempt in range(max_retries):
        try:
            import httpx
            
            headers = {
                "apikey": key,
                "Authorization": f"Bearer {key}"
            }
            
            logger.info("Fetching asset_ratio...")
            r_asset = httpx.get(f"{url}/rest/v1/asset_ratio?select=*", headers=headers)
            r_asset.raise_for_status()
            
            logger.info("Fetching holdings...")
            r_holdings = httpx.get(f"{url}/rest/v1/holdings?select=*", headers=headers)
            r_holdings.raise_for_status()
            
            logger.info("Fetching groups...")
            r_groups = httpx.get(f"{url}/rest/v1/groups?select=*", headers=headers)
            r_groups.raise_for_status()
            
            snapshot = {
                "groups": r_groups.json(),
                "asset_ratio": r_asset.json(),
                "holdings": r_holdings.json()
            }
            
            date_str = target_date or datetime.now().strftime("%Y%m%d")
            date_str = date_str.replace("-", "")
            
            os.makedirs("scratch", exist_ok=True)
            output_path = os.path.join("scratch", f"portfolio_snapshot_{date_str}.json")
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
                
            logger.info(f"Successfully saved portfolio snapshot to {output_path}")
            return snapshot
            
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error("All retries failed. Returning empty fallback.")
                date_str = target_date or datetime.now().strftime("%Y%m%d")
                date_str = date_str.replace("-", "")
                os.makedirs("scratch", exist_ok=True)
                output_path = os.path.join("scratch", f"portfolio_snapshot_{date_str}.json")
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
                return []

def main():
    parser = argparse.ArgumentParser(description="Fetch portfolio snapshot from Supabase")
    parser.add_argument("--date", help="Target date (YYYY-MM-DD or YYYYMMDD, defaults to today)")
    args = parser.parse_args()
    fetch_portfolio_data(args.date)

if __name__ == "__main__":
    main()

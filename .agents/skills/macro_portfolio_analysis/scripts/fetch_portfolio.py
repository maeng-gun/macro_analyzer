import os
import json
import logging
import time
from datetime import datetime
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fetch_portfolio_data():
    load_dotenv()
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    
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
            
            today_str = datetime.now().strftime("%Y%m%d")
            os.makedirs("scratch", exist_ok=True)
            output_path = os.path.join("scratch", f"portfolio_snapshot_{today_str}.json")
            
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
                
                # Write empty array as fallback
                today_str = datetime.now().strftime("%Y%m%d")
                os.makedirs("scratch", exist_ok=True)
                output_path = os.path.join("scratch", f"portfolio_snapshot_{today_str}.json")
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
                return []
                
if __name__ == "__main__":
    fetch_portfolio_data()

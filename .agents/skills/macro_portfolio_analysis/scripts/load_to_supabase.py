import os
import json
import argparse
import logging
from datetime import datetime
import httpx
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_json(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def upsert_rows(client, url, table_name, on_conflict_cols, rows, headers, chunk_size=50):
    if not rows:
        logger.info(f"[{table_name}] No rows to insert.")
        return True

    endpoint = f"{url}/rest/v1/{table_name}?on_conflict={on_conflict_cols}"
    req_headers = dict(headers)
    req_headers["Prefer"] = "resolution=merge-duplicates,return=representation"

    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        r = client.post(endpoint, json=chunk, headers=req_headers, timeout=20.0)
        if r.status_code not in [200, 201]:
            logger.error(f"[{table_name}] Upsert failed ({r.status_code}): {r.text}")
            return False
            
    logger.info(f"[{table_name}] Successfully upserted {len(rows)} rows.")
    return True

def load_metrics_to_supabase(metrics_path, fallback_dump_dir="scratch"):
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")

    if not url or not key:
        logger.error("Missing Supabase credentials in .env.")
        return False

    metrics_data = load_json(metrics_path)
    date_str = metrics_data.get("date", datetime.now().strftime("%Y-%m-%d"))

    # 1. Prepare topic shocks
    raw_shocks = metrics_data.get("topic_shocks", [])
    topic_shocks_rows = []
    for s in raw_shocks:
        topic_shocks_rows.append({
            "date": s["date"],
            "topic_id": s["topic_id"],
            "asset_class": s["asset_class"],
            "horizon": s["horizon"],
            "direction": s["direction"],
            "impact": s["impact"],
            "signal": s["signal"],
            "topic_shock": s["topic_shock"],
            "rationale": s.get("rationale", "")
        })

    # 2. Prepare asset scores
    raw_assets = metrics_data.get("asset_scores", [])
    asset_scores_rows = []
    for a in raw_assets:
        asset_scores_rows.append({
            "date": a["date"],
            "asset_class": a["asset_class"],
            "horizon": a["horizon"],
            "asset_macro_score": a["asset_macro_score"],
            "weight": a["weight"],
            "total_wi": a["total_wi"],
            "sma_5": a.get("sma_5"),
            "sma_20": a.get("sma_20"),
            "slope_20": a.get("slope_20")
        })

    # 3. Prepare portfolio scores
    raw_portfolio = metrics_data.get("portfolio_scores", [])
    portfolio_scores_rows = []
    for p in raw_portfolio:
        portfolio_scores_rows.append({
            "date": p["date"],
            "horizon": p["horizon"],
            "portfolio_macro_score": p["portfolio_macro_score"]
        })

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

    success = True
    try:
        with httpx.Client() as client:
            ok1 = upsert_rows(client, url, "macro_topic_shocks", "date,topic_id,asset_class,horizon", topic_shocks_rows, headers)
            ok2 = upsert_rows(client, url, "macro_daily_asset_scores", "date,asset_class,horizon", asset_scores_rows, headers)
            ok3 = upsert_rows(client, url, "macro_daily_portfolio_scores", "date,horizon", portfolio_scores_rows, headers)
            success = ok1 and ok2 and ok3
    except Exception as e:
        logger.error(f"Supabase connection or execution error: {e}")
        success = False

    if not success:
        os.makedirs(fallback_dump_dir, exist_ok=True)
        dump_path = os.path.join(fallback_dump_dir, f"failed_db_payload_{date_str.replace('-', '')}.json")
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump({
                "topic_shocks": topic_shocks_rows,
                "asset_scores": asset_scores_rows,
                "portfolio_scores": portfolio_scores_rows
            }, f, ensure_ascii=False, indent=2)
        logger.warning(f"Dumped failed payload for retry: {dump_path}")

    return success

def main():
    parser = argparse.ArgumentParser(description="Load quant metrics to Supabase time-series tables")
    parser.add_argument("--metrics", help="Path to calculated_metrics_YYYYMMDD.json")
    parser.add_argument("--date", help="Date YYYYMMDD or YYYY-MM-DD")
    args = parser.parse_args()

    date_compact = ""
    if args.date:
        date_compact = args.date.replace("-", "")
    elif args.metrics:
        import re
        m = re.search(r"\d{8}", os.path.basename(args.metrics))
        if m:
            date_compact = m.group(0)

    if not date_compact:
        date_compact = datetime.now().strftime("%Y%m%d")

    metrics_path = args.metrics or f"scratch/calculated_metrics_{date_compact}.json"
    logger.info(f"Loading metrics from {metrics_path} to Supabase...")
    ok = load_metrics_to_supabase(metrics_path)
    if ok:
        print("[Supabase] Data ingestion completed successfully.")
    else:
        print("[Supabase] Data ingestion encountered errors. Check logs and scratch/ dump.")

if __name__ == "__main__":
    main()

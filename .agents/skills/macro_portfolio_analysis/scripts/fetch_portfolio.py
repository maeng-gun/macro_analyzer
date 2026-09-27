import os
import json
import logging
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MACRO_ASSET_CLASSES = [
    "귀금속",
    "원자재",
    "인컴자산",
    "국내주식",
    "해외주식",
    "국내채권",
    "해외채권",
    "만기보유채권 및 현금성"
]

def map_to_macro_asset_class(g, sg, sg2):
    """
    18개 자산 구분을 사용자의 8대 매크로 자산군으로 분류합니다:
    1) 귀금속 : 대체자산 - 실물자산 - 귀금속
    2) 원자재 : 대체자산 - 실물자산 - 원자재
    3) 인컴자산 : 대체자산 - 인컴자산 - (국내+해외 합계)
    4) 국내주식 : 주식 - 국내 - (인덱스/종목/테마 합계)
    5) 해외주식 : 주식 - (선진국 + 신흥국 합계) - (하위 모든 항목 합계)
    6) 국내채권 : 채권 - 시장형 - 국내
    7) 해외채권 : 채권 - 시장형 - 해외
    8) 만기보유채권 및 현금성 : (채권 - 만기보유 전체) + (현금성 전체)
    """
    g = str(g or "").strip()
    sg = str(sg or "").strip()
    sg2 = str(sg2 or "").strip()

    # 1. 귀금속
    if g == "대체자산" and sg == "실물자산" and sg2 == "귀금속":
        return "귀금속"
    # 2. 원자재
    if g == "대체자산" and sg == "실물자산" and sg2 == "원자재":
        return "원자재"
    # 3. 인컴자산
    if g == "대체자산" and sg == "인컴자산":
        return "인컴자산"
    # 4. 국내주식
    if g == "주식" and sg == "국내":
        return "국내주식"
    # 5. 해외주식
    if g == "주식" and sg in ("선진국", "신흥국"):
        return "해외주식"
    # 6. 국내채권 (시장형)
    if g == "채권" and sg == "시장형" and sg2 == "국내":
        return "국내채권"
    # 7. 해외채권 (시장형)
    if g == "채권" and sg == "시장형" and sg2 == "해외":
        return "해외채권"
    # 8. 만기보유채권 및 현금성
    if (g == "채권" and sg == "만기보유") or (g == "현금성"):
        return "만기보유채권 및 현금성"
        
    return "기타"

def aggregate_macro_asset_ratios_from_leaves(leaf_rows, total_eval_amt):
    """
    18개 리프 세부자산군 행의 평가금액을 합산하여 8대 매크로 자산군별 비중(%)과 평가금액을 계산합니다.
    """
    grouped = {c: {"비중": 0.0, "평가금액": 0.0, "sub_assets": []} for c in MACRO_ASSET_CLASSES}
    
    for row in leaf_rows:
        g = row.get("자산군")
        sg = row.get("세부자산군")
        sg2 = row.get("세부자산군2")
        eval_amt = float(row.get("평가금액") or 0.0)
        w = round((eval_amt / total_eval_amt * 100), 2) if total_eval_amt > 0 else 0.0
        
        macro_c = map_to_macro_asset_class(g, sg, sg2)
        if macro_c not in grouped:
            grouped[macro_c] = {"비중": 0.0, "평가금액": 0.0, "sub_assets": []}
            
        grouped[macro_c]["비중"] += w
        grouped[macro_c]["평가금액"] += eval_amt
        grouped[macro_c]["sub_assets"].append({
            "자산군": g,
            "세부자산군": sg,
            "세부자산군2": sg2,
            "비중": round(w, 2),
            "평가금액": round(eval_amt, 0)
        })
        
    result = []
    for c in MACRO_ASSET_CLASSES:
        info = grouped.get(c, {"비중": 0.0, "평가금액": 0.0, "sub_assets": []})
        result.append({
            "macro_asset_class": c,
            "비중": round(info["비중"], 2),
            "평가금액": round(info["평가금액"], 0),
            "sub_assets": info["sub_assets"]
        })
    return result

def cleanup_old_files(target_dir, max_days=15):
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

def normalize_date_str(date_input):
    """문자열 날짜를 YYYY-MM-DD(표준) 및 YYYYMMDD(컴팩트)로 분리 반환합니다."""
    if not date_input:
        dt = datetime.now()
        return dt.strftime("%Y-%m-%d"), dt.strftime("%Y%m%d")
    clean = str(date_input).strip().replace("-", "")
    if len(clean) == 8 and clean.isdigit():
        iso = f"{clean[:4]}-{clean[4:6]}-{clean[6:]}"
        return iso, clean
    return str(date_input).strip(), clean

def fetch_portfolio_data(target_date=None):
    load_dotenv()
    
    cleanup_old_files("scratch", max_days=15)
    cleanup_old_files("archive", max_days=15)
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        logger.error("Missing Supabase credentials in .env file.")
        return []

    target_date_iso, target_date_compact = normalize_date_str(target_date)
    logger.info(f"Target analysis date: {target_date_iso} (compact: {target_date_compact})")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            import httpx
            
            headers = {
                "apikey": key,
                "Authorization": f"Bearer {key}"
            }
            
            # 1. return 테이블에서 가용 기준일 목록 조회 및 최적 기준일(basis_date) 선정
            logger.info("Fetching available basis dates from 'return' table...")
            r_dates = httpx.get(f"{url}/rest/v1/return?select=기준일&order=기준일.desc&limit=5000", headers=headers)
            r_dates.raise_for_status()
            
            distinct_dates = sorted(list(set(d["기준일"] for d in r_dates.json() if d.get("기준일"))), reverse=True)
            if not distinct_dates:
                logger.warning("No basis dates found in 'return' table. Fallback to asset_ratio table.")
                basis_date = None
            else:
                # target_date_iso 이하인 가장 최근 기준일 선택
                candidates = [d for d in distinct_dates if d <= target_date_iso]
                if candidates:
                    basis_date = candidates[0] # 이미 내림차순 정렬됨
                else:
                    # target_date 이전 데이터가 없는 경우 가용한 가장 과거 기준일 선택
                    basis_date = distinct_dates[-1]
                    logger.warning(f"Target date {target_date_iso} is earlier than all basis dates. Using earliest available date: {basis_date}")
            
            logger.info(f"Selected basis_date for return table: {basis_date}")
            
            # 2. 선별된 basis_date의 return 테이블 데이터 조회
            leaf_rows = []
            macro_asset_ratio = []
            if basis_date:
                r_ret = httpx.get(f"{url}/rest/v1/return?기준일=eq.{basis_date}&select=*", headers=headers)
                r_ret.raise_for_status()
                ret_rows = r_ret.json()
                
                # 세부자산군과 세부자산군2가 모두 존재하는 리프 노드(18개 행) 필터링
                leaf_rows = [
                    r for r in ret_rows
                    if r.get("세부자산군") and str(r.get("세부자산군")).strip() != ""
                    and r.get("세부자산군2") and str(r.get("세부자산군2")).strip() != ""
                ]
                
                total_eval_amt = sum(float(r.get("평가금액") or 0.0) for r in leaf_rows)
                logger.info(f"Found {len(leaf_rows)} leaf asset rows for basis date {basis_date}. Total eval: {total_eval_amt:,.0f} KRW")
                macro_asset_ratio = aggregate_macro_asset_ratios_from_leaves(leaf_rows, total_eval_amt)
            
            # Fallback: 만약 return 테이블에서 유의미한 리프 데이터를 얻지 못한 경우 기존 asset_ratio 사용
            if not macro_asset_ratio:
                logger.warning("Fallback: Fetching from 'asset_ratio' table...")
                r_asset = httpx.get(f"{url}/rest/v1/asset_ratio?select=*", headers=headers)
                r_asset.raise_for_status()
                raw_asset_ratio = r_asset.json()
                total_eval_amt = sum(float(r.get("평가금액") or 0.0) for r in raw_asset_ratio)
                macro_asset_ratio = aggregate_macro_asset_ratios_from_leaves(raw_asset_ratio, total_eval_amt)
                basis_date = basis_date or "asset_ratio_latest"
            
            # 3. holdings 조회
            logger.info("Fetching holdings...")
            r_holdings = httpx.get(f"{url}/rest/v1/holdings?select=*", headers=headers)
            r_holdings.raise_for_status()
            raw_holdings = r_holdings.json()
            
            # Enrich holdings with macro_asset_class
            for h in raw_holdings:
                h["macro_asset_class"] = map_to_macro_asset_class(
                    h.get("자산군"), h.get("세부자산군"), h.get("세부자산군2")
                )
            
            # 4. groups 조회
            logger.info("Fetching groups...")
            r_groups = httpx.get(f"{url}/rest/v1/groups?select=*", headers=headers)
            r_groups.raise_for_status()
            raw_groups = r_groups.json()
            
            snapshot = {
                "target_date": target_date_iso,
                "basis_date": basis_date,
                "macro_asset_classes": MACRO_ASSET_CLASSES,
                "macro_asset_ratio": macro_asset_ratio,
                "groups": raw_groups,
                "leaf_asset_ratio": leaf_rows,
                "holdings": raw_holdings
            }
            
            os.makedirs("scratch", exist_ok=True)
            output_path = os.path.join("scratch", f"portfolio_snapshot_{target_date_compact}.json")
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
                
            logger.info(f"Successfully saved portfolio snapshot to {output_path} (Basis Date: {basis_date})")
            return snapshot
            
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                logger.error("All retries failed. Returning empty fallback.")
                os.makedirs("scratch", exist_ok=True)
                output_path = os.path.join("scratch", f"portfolio_snapshot_{target_date_compact}.json")
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
                return []

def main():
    parser = argparse.ArgumentParser(description="Fetch portfolio snapshot from Supabase 'return' table and group into 8 Macro Asset Classes")
    parser.add_argument("--date", help="Target date (YYYY-MM-DD or YYYYMMDD, defaults to today)")
    args = parser.parse_args()
    fetch_portfolio_data(args.date)

if __name__ == "__main__":
    main()


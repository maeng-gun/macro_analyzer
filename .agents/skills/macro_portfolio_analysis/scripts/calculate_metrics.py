import os
import json
import argparse
from collections import defaultdict
from datetime import datetime

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

def load_json(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def calculate_quant_metrics(shocks_payload, portfolio_snapshot):
    date_str = shocks_payload.get("date", datetime.now().strftime("%Y-%m-%d"))
    topics = shocks_payload.get("topics", [])

    # 1. Extract 8 macro asset class weights from portfolio_snapshot
    asset_weights = {c: 0.0 for c in MACRO_ASSET_CLASSES}
    if isinstance(portfolio_snapshot, dict):
        macro_ratios = portfolio_snapshot.get("macro_asset_ratio", [])
        if macro_ratios:
            for row in macro_ratios:
                c = row.get("macro_asset_class")
                w = row.get("비중", 0.0)
                if c:
                    asset_weights[c] = float(w)
        else:
            # Fallback to asset_ratio if macro_asset_ratio not present
            for row in portfolio_snapshot.get("asset_ratio", []):
                c = row.get("세부자산군2")
                w = row.get("비중", 0.0)
                if c in asset_weights:
                    asset_weights[c] += float(w)

    # 2. Process all topic shocks
    flattened_shocks = []
    shocks_by_asset_horizon = defaultdict(list)

    for topic in topics:
        t_id = topic.get("topic_id", "unnamed_topic")
        t_title = topic.get("topic_title", t_id)
        t_shocks = topic.get("shocks", [])
        
        for s in t_shocks:
            asset_class = s.get("asset_class")
            horizon = int(s.get("horizon", 2))
            direction = int(s.get("direction", 0))
            impact = float(s.get("impact", 0.0))
            signal = float(s.get("signal", 0.0))
            rationale = s.get("rationale", "")

            # Direction must be -1, 0, or 1
            if direction not in [-1, 0, 1]:
                direction = 1 if direction > 0 else (-1 if direction < 0 else 0)

            # Impact and Signal between 0.0 and 1.0
            impact = max(0.0, min(1.0, impact))
            signal = max(0.0, min(1.0, signal))

            # Topic_Shock = Direction * Impact * Signal
            topic_shock = round(direction * impact * signal, 3)

            shock_record = {
                "date": date_str,
                "topic_id": t_id,
                "topic_title": t_title,
                "asset_class": asset_class,
                "horizon": horizon,
                "direction": direction,
                "impact": round(impact, 2),
                "signal": round(signal, 2),
                "topic_shock": topic_shock,
                "rationale": rationale
            }
            flattened_shocks.append(shock_record)
            if asset_class:
                shocks_by_asset_horizon[(asset_class, horizon)].append(shock_record)

    # 3. Calculate Macro Asset Scores per horizon
    all_target_assets = list(MACRO_ASSET_CLASSES)
    # Include any shock asset classes that might not be in standard 8
    for (a, _) in shocks_by_asset_horizon.keys():
        if a and a not in all_target_assets:
            all_target_assets.append(a)

    asset_score_records = []
    portfolio_wi_sums = defaultdict(float)

    for horizon in [1, 2, 3]:
        for asset in all_target_assets:
            shock_list = shocks_by_asset_horizon.get((asset, horizon), [])
            weight = asset_weights.get(asset, 0.0)

            if shock_list:
                sum_shocks = sum(s["topic_shock"] for s in shock_list)
                sum_signals = sum(s["signal"] for s in shock_list)

                if sum_signals > 0:
                    raw_score = sum_shocks / sum_signals
                    asset_score = max(-1.0, min(1.0, round(raw_score, 3)))
                else:
                    asset_score = 0.0

                directions = {s["direction"] for s in shock_list if s["direction"] != 0}
                high_uncertainty = len(directions) > 1
                total_wi = round(asset_score * weight, 3)
            else:
                asset_score = None
                high_uncertainty = False
                total_wi = 0.0

            portfolio_wi_sums[horizon] += total_wi

            asset_score_records.append({
                "date": date_str,
                "asset_class": asset,
                "horizon": horizon,
                "asset_macro_score": asset_score,
                "weight": round(weight, 2),
                "total_wi": total_wi,
                "shock_count": len(shock_list),
                "high_uncertainty": high_uncertainty,
                "sma_5": None,
                "sma_20": None,
                "slope_20": None
            })

    # 4. Calculate Portfolio Macro Scores per horizon
    portfolio_score_records = []
    for horizon in [1, 2, 3]:
        p_score = round(portfolio_wi_sums[horizon], 3)
        portfolio_score_records.append({
            "date": date_str,
            "horizon": horizon,
            "portfolio_macro_score": p_score
        })

    # 5. Ranked assets per horizon (by absolute Total_WI descending)
    ranked_assets = {}
    for h in [1, 2, 3]:
        h_records = [r for r in asset_score_records if r["horizon"] == h]
        h_records.sort(key=lambda x: abs(x["total_wi"]), reverse=True)
        ranked_assets[str(h)] = h_records

    output = {
        "date": date_str,
        "asset_scores": asset_score_records,
        "portfolio_scores": portfolio_score_records,
        "topic_shocks": flattened_shocks,
        "ranked_assets": ranked_assets
    }
    return output

def main():
    parser = argparse.ArgumentParser(description="Deterministic Macro-Portfolio Quant Metrics Engine (8 Macro Asset Classes)")
    parser.add_argument("--shocks", help="Path to extracted_shocks_YYYYMMDD.json")
    parser.add_argument("--portfolio", help="Path to portfolio_snapshot_YYYYMMDD.json")
    parser.add_argument("--date", help="Target date YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--output", help="Path to save calculated_metrics_YYYYMMDD.json")
    args = parser.parse_args()

    date_compact = ""
    if args.date:
        date_compact = args.date.replace("-", "")
    else:
        if args.shocks:
            base = os.path.basename(args.shocks)
            import re
            m = re.search(r"\d{8}", base)
            if m:
                date_compact = m.group(0)

    if not date_compact:
        date_compact = datetime.now().strftime("%Y%m%d")

    shocks_path = args.shocks or f"scratch/extracted_shocks_{date_compact}.json"
    portfolio_path = args.portfolio or f"scratch/portfolio_snapshot_{date_compact}.json"
    out_path = args.output or f"scratch/calculated_metrics_{date_compact}.json"

    print(f"[Quant Engine] Loading shocks: {shocks_path}")
    shocks_payload = load_json(shocks_path)
    print(f"[Quant Engine] Loading portfolio snapshot: {portfolio_path}")
    portfolio_snapshot = load_json(portfolio_path)

    print("[Quant Engine] Computing metrics for 8 Macro Asset Classes...")
    metrics = calculate_quant_metrics(shocks_payload, portfolio_snapshot)

    save_json(metrics, out_path)
    print(f"[Quant Engine] Successfully saved calculated metrics to: {out_path}")
    print(f"  - Total topic shocks: {len(metrics['topic_shocks'])}")
    print(f"  - Total asset scores calculated: {len(metrics['asset_scores'])}")
    for p in metrics["portfolio_scores"]:
        print(f"  - Portfolio Score (H={p['horizon']}): {p['portfolio_macro_score']:+.3f}")

if __name__ == "__main__":
    main()

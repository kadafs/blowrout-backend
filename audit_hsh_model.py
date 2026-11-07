import os
import glob
import json
from collections import defaultdict

DATA_DIR = "data/football"

def audit_profiles():
    print("=== 1. AUDITING HSH PROFILE FILES ===")
    team_p = os.path.join(DATA_DIR, "hsh_team_profiles.json")
    league_p = os.path.join(DATA_DIR, "hsh_league_profiles.json")
    
    if os.path.exists(team_p):
        with open(team_p, encoding="utf-8") as f:
            td = json.load(f)
        teams = td.get("teams", {})
        print(f"  Team profiles file: {len(teams)} teams, updated_at: {td.get('updated_at')}")
        # sample stats
        games_list = [t.get("games", 0) for t in teams.values()]
        if games_list:
            print(f"    Games per team: min={min(games_list)}, max={max(games_list)}, avg={sum(games_list)/len(games_list):.1f}")
            print(f"    Teams with >= 5 games: {len([g for g in games_list if g >= 5])} / {len(games_list)}")
    else:
        print("  ❌ Team profiles file NOT FOUND")
        
    if os.path.exists(league_p):
        with open(league_p, encoding="utf-8") as f:
            ld = json.load(f)
        leagues = ld.get("leagues", {})
        print(f"  League profiles file: {len(leagues)} leagues, updated_at: {ld.get('updated_at')}")
        for lid, linfo in list(leagues.items())[:5]:
            print(f"    League {linfo.get('league')}: games={linfo.get('games')}, ht_share={linfo.get('ht_goal_share')}, sh_share={linfo.get('sh_goal_share')}, 2H_rate={linfo.get('rate_2h')}")
    else:
        print("  ❌ League profiles file NOT FOUND")
    print()

def audit_graded_accuracy():
    print("=== 2. AUDITING HISTORICAL HSH PREDICTION PERFORMANCE ===")
    pred_files = sorted(glob.glob(os.path.join(DATA_DIR, "universal_predictions_*.json")))
    print(f"  Total football prediction files found: {len(pred_files)}")
    
    total_preds = 0
    with_hsh_block = 0
    with_ht_score = 0
    graded_hsh = 0
    hsh_wins = 0
    hsh_losses = 0
    
    decision_counts = defaultdict(int)
    decision_results = defaultdict(lambda: {"WIN": 0, "LOSS": 0, "ACTUAL_1H": 0, "ACTUAL_2H": 0, "ACTUAL_TIE": 0})
    confidence_results = defaultdict(lambda: {"WIN": 0, "LOSS": 0})
    source_results = defaultdict(lambda: {"WIN": 0, "LOSS": 0})
    actual_distribution = defaultdict(int)

    for fpath in pred_files:
        try:
            with open(fpath, encoding="utf-8") as f:
                d = json.load(f)
            preds = d.get("predictions", []) if isinstance(d, dict) else d
            for p in preds:
                total_preds += 1
                hsh_info = p.get("hsh") or {}
                decision = p.get("hsh_decision") or hsh_info.get("hsh_decision")
                conf = p.get("hsh_confidence") or hsh_info.get("hsh_confidence")
                source = p.get("hsh_source") or hsh_info.get("hsh_source")
                
                if decision:
                    with_hsh_block += 1
                    decision_counts[decision] += 1
                    
                act_ht_h = p.get("actual_ht_home")
                act_ht_a = p.get("actual_ht_away")
                act_hsh = p.get("actual_hsh_result")
                grade = p.get("hsh_grade")
                
                if act_ht_h is not None and act_ht_a is not None:
                    with_ht_score += 1
                    if act_hsh:
                        actual_distribution[act_hsh] += 1
                        
                if grade in ("WIN", "LOSS"):
                    graded_hsh += 1
                    if grade == "WIN":
                        hsh_wins += 1
                    else:
                        hsh_losses += 1
                    
                    decision_results[decision][grade] += 1
                    if act_hsh:
                        decision_results[decision][f"ACTUAL_{act_hsh}"] += 1
                    if conf:
                        confidence_results[conf][grade] += 1
                    if source:
                        source_results[source][grade] += 1

        except Exception as e:
            continue
            
    print(f"  Total predictions evaluated: {total_preds}")
    print(f"  Predictions with HSH block: {with_hsh_block} ({with_hsh_block/max(total_preds,1)*100:.1f}%)")
    print(f"  Predictions with Halftime Scores: {with_ht_score} ({with_ht_score/max(total_preds,1)*100:.1f}%)")
    print(f"  Graded HSH picks (non-PASS): {graded_hsh}")
    
    if actual_distribution:
        total_act = sum(actual_distribution.values())
        print(f"\n  Actual Real-World Halftime Distribution ({total_act} games):")
        for k in ["1H", "2H", "TIE"]:
            cnt = actual_distribution.get(k, 0)
            print(f"    Actual {k}: {cnt} ({cnt/total_act*100:.2f}%)")
            
    print(f"\n  Decision Distribution:")
    for dec, cnt in sorted(decision_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"    {dec}: {cnt} ({cnt/max(with_hsh_block,1)*100:.1f}%)")
        
    if graded_hsh > 0:
        overall_win_rate = (hsh_wins / graded_hsh) * 100
        print(f"\n  OVERALL HSH PERFORMANCE:")
        print(f"    Total Graded Picks : {graded_hsh}")
        print(f"    Wins               : {hsh_wins}")
        print(f"    Losses             : {hsh_losses}")
        print(f"    Overall Win Rate   : {overall_win_rate:.2f}%")
        
        print(f"\n  Performance by Decision (1H vs 2H):")
        for dec in ["2H", "1H"]:
            res = decision_results[dec]
            w = res["WIN"]
            l = res["LOSS"]
            tot = w + l
            if tot > 0:
                pct = (w / tot) * 100
                print(f"    Decision '{dec}': {w}/{tot} ({pct:.2f}% win rate) | Breakdown: actual 1H={res['ACTUAL_1H']}, 2H={res['ACTUAL_2H']}, TIE={res['ACTUAL_TIE']}")
                
        print(f"\n  Performance by Confidence Tier:")
        for conf in ["HIGH", "MODERATE", "LOW"]:
            res = confidence_results[conf]
            w = res["WIN"]
            l = res["LOSS"]
            tot = w + l
            if tot > 0:
                pct = (w / tot) * 100
                print(f"    Tier '{conf}': {w}/{tot} ({pct:.2f}% win rate)")

        print(f"\n  Performance by Data Source:")
        for src, res in source_results.items():
            w = res["WIN"]
            l = res["LOSS"]
            tot = w + l
            if tot > 0:
                pct = (w / tot) * 100
                print(f"    Source '{src}': {w}/{tot} ({pct:.2f}% win rate)")
    else:
        print("  ⚠️ No graded HSH predictions found.")
    print()

def audit_pipeline():
    print("=== 3. AUDITING CI/CD & PIPELINE INTEGRATION ===")
    workflows = glob.glob(".github/workflows/football_*.yml")
    for wf in workflows:
        with open(wf, encoding="utf-8") as f:
            content = f.read()
        has_aggregate = "aggregate_hsh_stats.py" in content
        has_hsh_engine = "hsh_engine" in content or "compute_hsh" in content
        print(f"  {os.path.basename(wf)}:")
        print(f"    Calls aggregate_hsh_stats.py : {'YES' if has_aggregate else 'NO ⚠️'}")

if __name__ == '__main__':
    audit_profiles()
    audit_graded_accuracy()
    audit_pipeline()


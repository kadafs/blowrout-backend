import os

def patch_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add --force argument
    old_arg = '    parser.add_argument("--regrade", action="store_true",'
    new_arg = '    parser.add_argument("--force",   action="store_true",\n                        help="Re-fetch finished games from API and re-grade all predictions from scratch")\n    parser.add_argument("--regrade", action="store_true",'
    if old_arg in content and '--force' not in content:
        content = content.replace(old_arg, new_arg, 1)

    # 2. Update not ungraded check
    old_ungraded = '    if not ungraded:\n        print("  ✅ Already graded. Run with --regrade to backfill Delta fields.")\n        return'
    new_ungraded = '    if not ungraded and not args.force:\n        print("  ✅ Already graded. Run with --regrade to backfill Delta fields, or --force to re-grade.")\n        return'
    if old_ungraded in content:
        content = content.replace(old_ungraded, new_ungraded, 1)

    # 3. Add NCAA Men inversion fix
    old_scores = '''        ht_home = (h_q1 + h_q2) if (h_scores.get("quarter_1") is not None) else None
        ht_away = (a_q1 + a_q2) if (a_scores.get("quarter_1") is not None) else None
        if h_score is not None and a_score is not None:'''

    new_scores = '''        ht_home = (h_q1 + h_q2) if (h_scores.get("quarter_1") is not None) else None
        ht_away = (a_q1 + a_q2) if (a_scores.get("quarter_1") is not None) else None

        # Upstream API-Basketball Inversion Guard:
        # In NCAA Men (League 116 or 11600-11699), when quarter_1 is None,
        # API-Basketball ingests text feeds formatted as "Visitor Score - Home Score"
        # and naively places the visitor score into scores.home and host into scores.away.
        # Detect this and restore the true home/away scores.
        if (lid == 116 or (11600 <= lid <= 11699)) and h_scores.get("quarter_1") is None:
            if h_score is not None and a_score is not None:
                h_score, a_score = a_score, h_score

        if h_score is not None and a_score is not None:'''
    if old_scores in content:
        content = content.replace(old_scores, new_scores, 1)

    # 4. Update pred loop check for args.force
    old_pred_check = '        if pred.get("actual_result"):'
    new_pred_check = '        if pred.get("actual_result") and not args.force:'
    if old_pred_check in content:
        content = content.replace(old_pred_check, new_pred_check, 1)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Patched {filepath} successfully!")

patch_file('grade_basketball_v2.py')
patch_file('grade_basketball.py')

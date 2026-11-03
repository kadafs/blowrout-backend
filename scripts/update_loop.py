with open('grade_basketball_v2.py', 'r', encoding='utf-8') as f:
    text = f.read()

target = 'for pred in predictions:\n        if pred.get("actual_result"):'
replacement = 'for pred in predictions:\n        if pred.get("actual_result") and not args.force:'

if target in text:
    text = text.replace(target, replacement, 1)
    with open('grade_basketball_v2.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Updated grade_basketball_v2.py")

with open('grade_basketball.py', 'r', encoding='utf-8') as f:
    text2 = f.read()

if target in text2:
    text2 = text2.replace(target, replacement, 1)
    with open('grade_basketball.py', 'w', encoding='utf-8') as f:
        f.write(text2)
    print("Updated grade_basketball.py")

import json
import os

insights_file = 'output/lcil_insights.json'
if os.path.exists(insights_file):
    with open(insights_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    insights = data.get("insights", [])
    print(f'Total insights in file: {len(insights)}')
    
    high_conf = [i for i in insights if i.get("confidence", 0) >= 0.7]
    med_conf = [i for i in insights if 0.4 <= i.get("confidence", 0) < 0.7]
    low_conf = [i for i in insights if 0 < i.get("confidence", 0) < 0.4]
    
    print(f'High confidence (>= 0.7): {len(high_conf)}')
    print(f'Medium confidence (0.4-0.7): {len(med_conf)}')
    print(f'Low confidence (> 0 and < 0.4): {len(low_conf)}')
    
    if high_conf:
        print('\nSample high confidence insight:')
        sample = high_conf[0]
        print(f'  Column: {sample.get("column")}')
        print(f'  Confidence: {sample.get("confidence")}')
        print(f'  Insight: {sample.get("insight", "")[:100]}...')
else:
    print(f'File not found: {insights_file}')

from profiler.lcil import enrich_low_cardinality_intelligence
import json

result = enrich_low_cardinality_intelligence(output_base='output', batch_size=10, provider='nvidia')
print(f'Success: {result["success"]}')
print(f'Total insights with confidence > 0: {result.get("insights_count", 0)}')

if result.get("insights_file"):
    with open(result["insights_file"], 'r', encoding='utf-8') as f:
        insights = json.load(f)
    
    confidence_counts = {}
    for insight in insights.get("insights", []):
        conf = insight.get("confidence", 0)
        if conf > 0:
            conf_range = f'{int(conf*10)/10:.1f}-{int(conf*10)/10 + 0.1:.1f}'
            confidence_counts[conf_range] = confidence_counts.get(conf_range, 0) + 1
    
    print('\nConfidence distribution:')
    for conf_range in sorted(confidence_counts.keys()):
        print(f'  {conf_range}: {confidence_counts[conf_range]} insights')

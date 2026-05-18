from profiler.lcil import enrich_low_cardinality_intelligence
result = enrich_low_cardinality_intelligence(output_base='output', batch_size=10, provider='nvidia')
print(f'Success: {result["success"]}, Insights: {result.get("insights_count", 0)}')

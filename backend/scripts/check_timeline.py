import json

import os
script_dir = os.path.dirname(os.path.abspath(__file__))
timeline_path = os.path.join(script_dir, '..', '..', 'frontend', 'public', 'data', 'timeline.json')
with open(timeline_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

for i, d in enumerate(data):
    has_ai = 'ai_analysis' in d and bool(d.get('ai_analysis'))
    has_original = 'original_content' in d and bool(d.get('original_content'))
    title = d.get('title', 'N/A')[:40]
    print(f"{i:2d}: {d['date']:12s} | ai={has_ai!s:5s} | orig={has_original!s:5s} | {title}")

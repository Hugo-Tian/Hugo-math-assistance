"""Summarize explicit human reviews. Missing reviews remain unknown, never inferred."""
import argparse
import json
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('results');parser.add_argument('--reviews');args=parser.parse_args()
data=json.loads(Path(args.results).read_text(encoding='utf-8'))
template=[{'id':r['id'],'variant':r['variant'],'correctness':None,'citation_support':None,'task_completion':None,'reviewer':'','notes':'',
    'rubric':r.get('rubric',[])} for r in data['results'] if r['status']!='skipped']
path=Path(args.results).with_suffix('.human-review.json')
if not args.reviews:
    path.write_text(json.dumps(template,ensure_ascii=False,indent=2),encoding='utf-8');print(path)
else:
    reviews=json.loads(Path(args.reviews).read_text(encoding='utf-8'));valid={(r['id'],r['variant']) for r in template}
    seen=set()
    for r in reviews:
        pair=(r['id'],r['variant'])
        if pair not in valid or pair in seen:raise ValueError('Unknown or duplicate case/variant')
        seen.add(pair)
        for key in ('correctness','citation_support','task_completion'):
            if r.get(key) not in (None,0,1,2):raise ValueError('Scores must be null or 0/1/2')
            if r.get(key) is not None and not r.get('reviewer'):raise ValueError('Scored rows require an identified reviewer')
    report='# 人工审阅汇总\n\n0=错误/不支持/未完成；1=部分满足；2=完整满足。只统计已审阅行；不把未填写项计为0或满分。\n\n'
    for key in ('correctness','citation_support','task_completion'):
        scores=[r[key] for r in reviews if r.get(key) is not None]
        report+=f'- {key}: '+(f'{sum(scores)/(2*len(scores)):.3f}，已审阅 {len(scores)} 行' if scores else '未知，尚未人工审阅')+'\n'
    Path(args.results).with_suffix('.human-review.md').write_text(report,encoding='utf-8');print(report)

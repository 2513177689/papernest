"""Explainable retrieval: BM25 + optional embeddings/LLM, diversity at selection time."""
import json
import math
import re
from collections import Counter
from datetime import date, timedelta
from . import db, ai

ALIASES={'大模型':['language model','llm','transformer'],'检索增强':['retrieval','rag'],
    '自然语言':['nlp','language'],'机器学习':['machine learning'],'深度学习':['deep learning','neural'],
    '计算机视觉':['computer vision','image'],'强化学习':['reinforcement learning'],
    '推荐系统':['recommendation','recommender'],'数据库':['database'],'分布式':['distributed'],
    '网络安全':['security'],'数学':['mathematics'],'物理':['physics'],'生物':['biology'],'医学':['medical','clinical']}
STOP={'the','a','an','of','and','in','to','for','with','on','is','are','我','的','和','研究','关注'}


def tokens(text):
    words=re.findall(r'[a-z][a-z0-9-]+|[\u4e00-\u9fff]{2,}',text.lower())
    return [w for w in words if w not in STOP]


def terms(direction):
    raw=' '.join([direction.get('name',''),direction.get('description',''),*direction.get('keywords',[])])
    expanded=[v for k,vs in ALIASES.items() if k in raw for v in vs]
    return list(dict.fromkeys(direction.get('keywords',[])+expanded)),tokens(raw+' '+' '.join(expanded))


def doc(p):
    return p['title']+' '+p.get('abstract','')+' '+' '.join(p.get('tags',[]))


def bm25(corpus,query):
    if not corpus:return []
    counts=[Counter(tokens(d)) for d in corpus];n=len(counts)
    lengths=[sum(c.values()) for c in counts];avg=max(sum(lengths)/n,1)
    freq={term:sum(term in c for c in counts) for term in set(query)}
    return [sum(math.log(1+(n-freq[t]+.5)/(freq[t]+.5))*c.get(t,0)*2.5 /
        (c.get(t,0)+1.5*(.25+.75*length/avg)) for t in set(query)) for c,length in zip(counts,lengths)]


def cosine(a,b):
    if len(a)!=len(b): return 0.0
    denom=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return sum(x*y for x,y in zip(a,b))/denom if denom else 0.0


def rank(direction,papers=None):
    papers=papers if papers is not None else db.all_rows('papers')
    phrases,query=terms(direction)
    corpus=[doc(p) for p in papers];raw=bm25(corpus,query);maximum=max(raw,default=1) or 1
    with db.connect() as c:
        stored={r['paper_id']:json.loads(r['data']) for r in c.execute('SELECT paper_id,data FROM recommendations WHERE direction_id=?',(direction['id'],))}
    signature=json.dumps(direction,sort_keys=True,ensure_ascii=False)
    liked=[set(tokens(doc(p))) for p in papers if p.get('feedback')=='helpful']
    results=[]
    for p,text,value in zip(papers,corpus,raw):
        lower=text.lower();matched=[k for k in phrases if k.lower() in lower]
        excluded=[k for k in direction.get('excludes',[]) if k.lower() in lower]
        if p.get('feedback')=='irrelevant':excluded.append('已标记不相关')
        lexical=value/maximum
        explicit=min(len(matched)/max(min(len(phrases),3),1),1)
        score=.65*lexical+.35*explicit
        reasons=['匹配关键词：'+ '、'.join(matched[:5])] if matched else (['主题词与研究需求有交集'] if value else [])
        followed_authors=[a for a in direction.get('authors',[]) if a.lower() in ' '.join(p.get('authors',[])).lower()]
        followed_venues=[v for v in direction.get('venues',[]) if v.lower() in p.get('venue','').lower()]
        if followed_authors:score=min(1,score+.25);reasons.append('关注作者：'+'、'.join(followed_authors))
        if followed_venues:score=min(1,score+.12);reasons.append('关注会议/期刊：'+'、'.join(followed_venues))
        old=stored.get(p['id'],{})
        # Cached judgments must match current direction and paper text, not just its identifier.
        if old.get('profile')!=signature or old.get('document')!=text:old={}
        if 'semantic' in old:
            score=.7*score+.3*max(0,old['semantic']);reasons.append('结合语义相似度')
        if old.get('analysis'):
            score=.65*score+.35*old['analysis']['relevance'];reasons.append(old['analysis']['reason'])
        pt=set(tokens(text))
        similarity=max((len(pt&x)/max(len(pt|x),1) for x in liked),default=0)
        score=min(1,score+.08*similarity+(.04 if p.get('feedback')=='helpful' else 0))
        if similarity>.1:reasons.append('与你标记有帮助的论文内容相近')
        result=p | {'rank_score':round(score,4),'reasons':reasons,'excluded':excluded,
            'analysis':old.get('analysis'),'semantic':old.get('semantic')}
        results.append(result)
    return sorted(results,key=lambda p:(not bool(p['excluded']),p['rank_score'],p.get('published','')),reverse=True)


def classics(direction,mode='personal'):
    """Reading priority, not a scientific quality score; never calls a paid model."""
    personal=mode=='personal' and direction.get('id')!='none'
    rows=rank(direction,[p for p in db.all_rows('papers') if p.get('classic')])
    results=[]
    for p in rows:
        if p['excluded']:continue
        if personal and p['rank_score']<.18:continue
        kinds={e.get('type') for e in p.get('evidence',[]) if e.get('url','').startswith(('https://','http://'))}
        evidence=40 if kinds & {'教材章节','官方技术文档'} else 30 if '教材参考文献' in kinds else 20 if kinds else 0
        try:age=max(0,date.today().year-int(p.get('published','')[:4]))
        except (ValueError,TypeError):age=0
        maturity=min(age*2,20)
        relevance=round(min(1,max(0,p['rank_score']))*40,1) if personal else 0
        score=round(evidence+maturity+relevance,1) if personal else round((evidence+maturity)/60*100,1)
        grade='S' if score>=90 else 'A' if score>=75 else 'B' if score>=60 else 'C'
        results.append(p | {'classic_score':score,'classic_grade':grade,'score_parts':{'evidence':evidence,'maturity':maturity,'relevance':relevance},'score_scope':'personal' if personal else 'all'})
    results.sort(key=lambda p:(-p['classic_score'],p.get('published',''),p['id']))
    return [p | {'classic_rank':i+1} for i,p in enumerate(results)]


def select_diverse(rows,limit):
    chosen=[];remaining=list(rows)
    while remaining and len(chosen)<limit:
        def adjusted(p):
            words=set(tokens(p['title']))
            overlap=max((len(words&set(tokens(c['title'])))/max(len(words|set(tokens(c['title']))),1) for c in chosen),default=0)
            return p['rank_score']-.18*overlap
        item=max(remaining,key=adjusted);chosen.append(item);remaining.remove(item)
    return chosen


def daily(direction,mode='recommended'):
    s=ai.settings();ranked=rank(direction)
    cutoff=(date.fromisoformat(ai.today())-timedelta(days=s['lookback_days'])).isoformat()
    fresh=[p for p in ranked if cutoff<=p.get('published','')<=ai.today() and not p.get('classic')]
    if mode=='all':return fresh
    if mode=='filtered':return [p for p in fresh if p['excluded'] or p['rank_score']<.18]
    return select_diverse([p for p in fresh if not p['excluded'] and p['rank_score']>=.18 and p.get('status')!='已读'],s['daily_limit'])


async def refine(direction,progress=None):
    s=ai.settings();cutoff=(date.fromisoformat(ai.today())-timedelta(days=s['lookback_days'])).isoformat()
    rows=[p for p in rank(direction) if not p['excluded'] and p['rank_score']>.1
          and not p.get('classic') and cutoff<=p.get('published','')<=ai.today()][:s['ai_candidates']]
    warnings=[];qvec=None
    if s['embedding_enabled']:
        try:qvec=await ai.embed(direction['name']+' '+direction.get('description','')+' '+' '.join(direction.get('keywords',[])))
        except ValueError as e:warnings.append(str(e))
    for i,p in enumerate(rows):
        item={'profile':json.dumps(direction,sort_keys=True,ensure_ascii=False),'document':doc(p),'created':db.now()}
        if qvec:
            try:item['semantic']=cosine(qvec,await ai.embed(doc(p)))
            except ValueError as e:warnings.append(str(e));qvec=None
        if s['auto_ai'] and p.get('abstract'):
            try:
                prompt='研究需求：'+json.dumps(direction,ensure_ascii=False)+'\n论文标题与摘要：'+doc(p)[:16000]+'''
仅返回 JSON 对象：{"relevance":0到1的相关性,"reason":"一句话推荐理由","summary":"200字中文概览","uncertain":"摘要无法确认的条件","concepts":["前置知识概念"]}。相关性不是论文质量。不要根据作者名气判定。'''
                answer=await ai.generate(ai.SYSTEM,prompt,'screen')
                match=re.search(r'\{[\s\S]*\}',answer['text'])
                analysis=json.loads(match.group(0) if match else answer['text'])
                analysis['relevance']=min(1,max(0,float(analysis['relevance'])))
                if not isinstance(analysis.get('reason'),str) or not isinstance(analysis.get('summary'),str):raise ValueError('格式错误')
                item['analysis']=analysis
            except Exception:
                warnings.append('部分 AI 精筛未完成，已保留规则结果。')
                # Keep processing no further paid requests after a quota or service error.
                s['auto_ai']=False
        if len(item)>3:
            with db.connect() as c:c.execute('INSERT INTO recommendations VALUES (?,?,?) ON CONFLICT(direction_id,paper_id) DO UPDATE SET data=excluded.data',(direction['id'],p['id'],json.dumps(item,ensure_ascii=False)))
        if progress:progress(f'候选精筛 {i+1}/{len(rows)}')
    return list(dict.fromkeys(warnings))


def courses_for(direction,query='',free_only=True):
    phrases,q=terms(direction)
    query_tokens=set(tokens(query+' '+' '.join(phrases)))
    known=set(db.setting('known_concepts',[]))
    result=[]
    for c in db.all_rows('courses'):
        if free_only and c.get('free') not in {'免费','免费公开材料','免费导航'}:continue
        matched=[t for t in c.get('tags',[]) if t.lower() in (query+' '+' '.join(phrases)).lower() or set(tokens(t))&query_tokens]
        if query:
            search_text=(c['title']+' '+c.get('description','')+' '+' '.join(c.get('tags',[]))).lower()
            search_terms=[query.lower()]+[term for alias,values in ALIASES.items() if alias in query for term in values]
            if not any(term in search_text for term in search_terms):continue
        c=c | {'match':len(matched),'reason':'可补充：'+'、'.join(matched[:4]) if matched else '学科课程资源，可按需浏览',
            'known':bool(matched) and all(t in known for t in matched)}
        result.append(c)
    return sorted(result,key=lambda c:(not c['known'],c['match'],c.get('language')=='中文'),reverse=True)

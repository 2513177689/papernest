import asyncio
import hashlib
import io
import json
import os
import re
import secrets
import zipfile
import httpx
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import db, ai, sources, recommend, zotero
from .catalog import seed, DEFAULT_SETTINGS
from .security import encrypt

db.init();seed()
CSRF=secrets.token_urlsafe(32)
tasks=set()
job_lock=asyncio.Lock()
scheduler=AsyncIOScheduler()


def spawn(coro):
    task=asyncio.create_task(coro);tasks.add(task);task.add_done_callback(tasks.discard)


def configure_schedule():
    if scheduler.get_job('daily'):scheduler.remove_job('daily')
    s=ai.settings()
    if s['schedule_enabled']:
        scheduler.add_job(scheduled,'cron',id='daily',hour=s['schedule_hour'],minute=0,
            timezone=s['timezone'],misfire_grace_time=3600,coalesce=True,max_instances=1)


async def scheduled():
    if not db.all_rows('directions') or job_lock.locked():return
    await run_job(new_job('每日更新'))


@asynccontextmanager
async def lifespan(app):
    for job in db.all_rows('jobs'):
        if job['status'] in {'running','queued'}:
            job.update(status='interrupted',message='上次运行被中断，可以重新获取。');db.put('jobs',job['id'],job)
    scheduler.start();configure_schedule()
    if ai.settings()['schedule_enabled'] and db.setting('last_daily','')!=ai.today():spawn(scheduled())
    yield
    scheduler.shutdown(wait=False)
    for task in list(tasks):task.cancel()
    if tasks:await asyncio.gather(*tasks,return_exceptions=True)


app=FastAPI(title='PaperNest',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])


@app.middleware('http')
async def local_protection(request,call_next):
    if request.url.path.startswith('/api'):
        origin=request.headers.get('origin')
        if origin and origin not in {'http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173'}:
            return JSONResponse({'detail':'仅允许本机应用访问。'},403)
        if request.method in {'POST','PUT','PATCH','DELETE'} and request.headers.get('x-papernest-token')!=CSRF:
            return JSONResponse({'detail':'页面会话已过期，请刷新。'},403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    if request.url.path.startswith('/api'):response.headers['Cache-Control']='no-store'
    return response


@app.exception_handler(ValueError)
async def value_error(request,exc):return JSONResponse({'detail':str(exc)},400)


@app.exception_handler(httpx.HTTPStatusError)
async def source_http_error(request,exc):
    return JSONResponse({'detail':f'外部来源返回 HTTP {exc.response.status_code}。请稍后重试，或手动导入 PDF。'},502)


@app.exception_handler(httpx.RequestError)
async def source_network_error(request,exc):
    return JSONResponse({'detail':'连接外部来源失败，请检查网络后重试。'},502)


def paper_or_404(pid):
    p=db.get('papers',pid)
    if not p:raise HTTPException(404,'论文不存在。')
    return p


def direction_or_default(did=''):
    d=db.get('directions',did) if did else next(iter(db.all_rows('directions')),None)
    return d or dict(id='none',name='',description='',keywords=[],excludes=[],categories=[])


def compact(p):
    return {k:v for k,v in p.items() if k not in {'pages'}} | {'page_count':len(p.get('pages',[]))}


@app.get('/api/bootstrap')
async def bootstrap():
    return dict(token=CSRF,directions=db.all_rows('directions'),settings=ai.settings(),
        providers=ai.public_providers(),secrets={k:bool(v) for k,v in db.setting('secrets',{}).items()},
        counts={'papers':len(db.all_rows('papers')),'saved':sum(p.get('saved',False) for p in db.all_rows('papers'))})


@app.get('/api/settings')
async def settings_get():return {'settings':ai.settings(),'providers':ai.public_providers(),'usage':ai.usage_rows(),
    'secrets':{k:bool(v) for k,v in db.setting('secrets',{}).items()}}


@app.put('/api/settings')
async def settings_put(request:Request):
    values=await request.json();s=ai.settings()
    for k in DEFAULT_SETTINGS:
        if k in values and k!='openalex_key':s[k]=values[k]
    for k,low,high in [('daily_limit',1,30),('lookback_days',1,30),('schedule_hour',0,23),('ai_candidates',1,100),('daily_ai_calls',1,10000),('daily_token_limit',1000,100000000)]:
        if not isinstance(s[k],int) or not low<=s[k]<=high:raise ValueError(f'{k} 必须在 {low}–{high} 之间。')
    try:ZoneInfo(s['timezone'])
    except Exception:raise ValueError('时区无效。')
    for k in ['active_provider','deep_provider']:
        if s[k]:ai.provider(s[k])
    secret=db.setting('secrets',{})
    for k in ['openalex_key','embedding_key','zotero_key']:
        if values.get(k):secret[k]=encrypt(values[k])
        if values.get('clear_'+k):secret[k]=''
    db.set_setting('secrets',secret);db.set_setting('general',s);configure_schedule()
    return {'ok':True}


@app.put('/api/providers/{pid}')
async def provider_put(pid:str,request:Request):
    ai.save_provider(pid,await request.json());return {'ok':True}


@app.post('/api/providers/{pid}/test')
async def provider_test(pid:str):
    result=await ai.generate('只回复 OK。','连接测试。','test',pid,cache=False)
    return dict(ok=True,model=result['model'],message=result['text'][:100])


@app.post('/api/directions')
async def direction_save(request:Request):
    d=await request.json()
    if not d.get('name','').strip():raise ValueError('请填写方向名称。')
    if len(d.get('description',''))>4000:raise ValueError('研究描述请控制在 4000 字以内。')
    for field in ['keywords','excludes','categories','authors','venues']:
        d[field]=[str(x).strip()[:150] for x in d.get(field,[]) if str(x).strip()][:30]
    d['id']=d.get('id') or db.uid();d['name']=d['name'][:100]
    db.put('directions',d['id'],d);return d


@app.delete('/api/directions/{did}')
async def direction_delete(did:str):
    with db.connect() as c:
        c.execute('DELETE FROM directions WHERE id=?',(did,));c.execute('DELETE FROM recommendations WHERE direction_id=?',(did,))
    return {'ok':True}


@app.get('/api/papers')
async def paper_list(view='library',direction_id='',mode='recommended',q='',status='',collection=''):
    d=direction_or_default(direction_id)
    if view=='today':rows=recommend.daily(d,mode) if d['id']!='none' else []
    elif view=='classics':
        rows=[p for p in recommend.rank(d) if p.get('classic')]
        if mode=='personal' and d['id']!='none':rows=[p for p in rows if not p['excluded'] and p['rank_score']>=.18]
    else:rows=[p for p in db.all_rows('papers') if p.get('saved')]
    if status:rows=[p for p in rows if p.get('status')==status]
    if collection:rows=[p for p in rows if collection in p.get('collections',[])]
    if q:
        query=q.lower();note_ids={n['paper_id'] for n in db.notes() if query in (n['text']+' '+n['quote']).lower()}
        rows=[p for p in rows if query in (sources_doc(p)).lower() or p['id'] in note_ids]
    return [compact(p) for p in rows]


def sources_doc(p):
    return ' '.join([p['title'],p.get('abstract',''),' '.join(p.get('authors',[])),' '.join(p.get('tags',[])),* [x['text'] for x in p.get('pages',[])]])


@app.get('/api/papers/{pid}')
async def paper_get(pid:str):return paper_or_404(pid)


@app.patch('/api/papers/{pid}')
async def paper_patch(pid:str,request:Request):
    values=await request.json();p=paper_or_404(pid)
    allowed={'saved','status','feedback','tags','collections','read_page','classic','curation','evidence'}
    if values.get('status',p['status']) not in {'未读','稍后读','正在读','已读'}:raise ValueError('阅读状态无效。')
    if values.get('feedback',p.get('feedback','')) not in {'','helpful','irrelevant','keep'}:raise ValueError('反馈无效。')
    for k,v in values.items():
        if k in allowed:p[k]=v
    if p.get('classic') and not p.get('evidence'):raise ValueError('加入经典清单时，请提供推荐依据。')
    db.put('papers',pid,p);return compact(p)


@app.post('/api/import/link')
async def import_link(request:Request):
    values=await request.json();p=await sources.import_link(values.get('url',''));p['saved']=True;db.put('papers',p['id'],p)
    return compact(p)


@app.post('/api/import/pdf')
async def import_pdf(file:UploadFile=File(...),paper_id:str=''):
    content=await file.read(40*1024*1024+1)
    if len(content)>40*1024*1024:raise ValueError('PDF 不能超过 40 MB。')
    digest=hashlib.sha256(content).hexdigest()
    existing=next((p for p in db.all_rows('papers') if p.get('pdf_hash')==digest),None)
    if existing and not paper_id:
        existing['saved']=True;db.put('papers',existing['id'],existing);return compact(existing)
    p=paper_or_404(paper_id) if paper_id else sources.make_paper(title=Path(file.filename or '导入论文.pdf').stem,source='本地导入',saved=True)
    return compact(await asyncio.to_thread(sources.attach_pdf,p,content))


@app.post('/api/papers/{pid}/download')
async def download(pid:str):
    p=paper_or_404(pid)
    if not p.get('pdf_url'):raise ValueError('没有可用的开放 PDF 地址，请手动上传全文。')
    content=await sources.download_public(p['pdf_url'])
    return compact(await asyncio.to_thread(sources.attach_pdf,p,content))


@app.post('/api/papers/{pid}/metadata')
async def metadata(pid:str):
    p=paper_or_404(pid)
    if not (p.get('arxiv_id') or p.get('doi')):raise ValueError('该论文没有 DOI 或 arXiv 编号。')
    return compact(await sources.import_link(p.get('arxiv_id') or p['doi']))


@app.get('/api/papers/{pid}/pdf')
async def pdf(pid:str):
    p=paper_or_404(pid)
    if not p.get('pdf_file'):raise HTTPException(404,'尚未保存 PDF。')
    path=db.FILES/Path(p['pdf_file']).name
    if not path.is_file():raise HTTPException(404,'PDF 文件丢失，请重新下载。')
    return FileResponse(path,media_type='application/pdf',filename=re.sub(r'[\\/:*?"<>|]','_',p['title'])[:100]+'.pdf',content_disposition_type='inline')


@app.post('/api/papers/{pid}/summary')
async def summary(pid:str,request:Request):
    values=await request.json();p=paper_or_404(pid)
    result=await ai.paper_summary(p,values.get('deep',False),direction_or_default(values.get('direction_id','')))
    # Reload to avoid losing notes/status changes made while the model was running.
    p=paper_or_404(pid);p['deep_summary' if values.get('deep') else 'summary']=result;db.put('papers',pid,p)
    return result


@app.post('/api/papers/{pid}/ask')
async def ask(pid:str,request:Request):
    values=await request.json();p=paper_or_404(pid);action=values.get('action','question');text=str(values.get('text',''))[:6000]
    if not text.strip():raise ValueError('请先选中文字或输入问题。')
    page=int(values.get('page',1));pages=p.get('pages',[])
    context=next((x['text'] for x in pages if x['page']==page),p.get('abstract',''))[:14000]
    instruction={'translate':'翻译选中的文字，必要时解释术语，保留原意，不扩写。','explain':'结合上下文解释选中的段落。','question':'根据提供的正文回答问题；无法回答时明确说明。','concepts':'列出该论文涉及的前置知识，按基础到进阶排序，只给知识概念与学习理由，不编造课程链接。'}.get(action)
    if not instruction:raise ValueError('不支持的阅读操作。')
    result=await ai.generate(ai.SYSTEM,f"标题：{p['title']}\n提供的是第{page}页文字或摘要节选，并非全部论文。\n上下文：{context}\n选文/问题：{text}\n{instruction}",action)
    return result | {'basis':f'第 {page} 页及选文' if pages else '仅摘要'}


@app.get('/api/notes')
async def notes_get(paper_id:str=''):
    titles={p['id']:p['title'] for p in db.all_rows('papers')}
    return [n | {'paper_title':titles.get(n['paper_id'],'')} for n in db.notes(paper_id or None)]


@app.post('/api/notes')
async def note_post(request:Request):
    v=await request.json();p=paper_or_404(v['paper_id'])
    if not v.get('text','').strip() and not v.get('quote','').strip():raise ValueError('笔记或选文不能为空。')
    return db.note_add(p['id'],str(v.get('text',''))[:20000],str(v.get('quote',''))[:10000],int(v.get('page',0)),v.get('rects',[])[:100],p.get('pdf_hash',''))


@app.delete('/api/notes/{nid}')
async def note_delete(nid:str):
    with db.connect() as c:c.execute('DELETE FROM notes WHERE id=?',(nid,))
    return {'ok':True}


@app.get('/api/courses')
async def courses_get(direction_id='',q='',free_only:bool=True):return recommend.courses_for(direction_or_default(direction_id),q,free_only)


@app.post('/api/courses')
async def courses_post(request:Request):
    item=await request.json()
    if not item.get('title','').strip() or urlparse(item.get('url','')).scheme not in {'https','http'}:raise ValueError('请填写课程名称和有效链接。')
    item=dict(id=db.uid(),author='',platform='个人添加',language='中文',level='不限',free='待核验',kind='课程',tags=[],description='',saved=True,status='未学习',verified='')|item
    db.put('courses',item['id'],item);return item


@app.patch('/api/courses/{cid}')
async def courses_patch(cid:str,request:Request):
    c=db.get('courses',cid)
    if not c:raise HTTPException(404,'课程不存在。')
    values=await request.json()
    for field in ['saved','status']:
        if field in values:c[field]=values[field]
    db.put('courses',cid,c);return c


@app.post('/api/concepts')
async def concepts(request:Request):
    v=await request.json();known=db.setting('known_concepts',[])
    if v.get('name') and v['name'] not in known:known.append(v['name'])
    db.set_setting('known_concepts',known);return {'ok':True}


def new_job(kind,direction_id='',query='',source='arxiv'):
    j=dict(id=db.uid(),kind=kind,direction_id=direction_id,query=query,source=source,status='queued',message='等待执行',created=db.now(),added=0,warnings=[])
    db.put('jobs',j['id'],j);return j


async def run_job(j):
    async with job_lock:
        def update(message):j['message']=message;db.put('jobs',j['id'],j)
        j['status']='running';update('连接论文来源')
        try:
            ds=[direction_or_default(j['direction_id'])] if j['direction_id'] else db.all_rows('directions')
            if j['kind']=='手动搜索':ds=[direction_or_default(j['direction_id'])]
            if not ds:raise ValueError('请先添加研究方向。')
            s=ai.settings();fetched=0;source_success=0
            for d in ds:
                phrases,_=recommend.terms(d)
                query=j['query'] or ' OR '.join('all:"'+k.replace('"','')+'"' for k in phrases[:8])
                if not j['query'] and d.get('authors'):
                    authored=' OR '.join('au:"'+a.replace('"','')+'"' for a in d['authors'][:5])
                    query='('+query+') OR ('+authored+')' if query else authored
                cats=' OR '.join('cat:'+c for c in d.get('categories',[]) if re.fullmatch(r'[A-Za-z.-]+',c))
                if not query:query=cats or 'cat:cs.AI'
                elif cats and j['kind']!='手动搜索':query='('+query+') AND ('+cats+')'
                days=None if j['kind']=='手动搜索' else s['lookback_days']
                for source in ([j['source']] if j['kind']=='手动搜索' else ['arxiv','openalex']):
                    update(f"获取 {d['name'] or '搜索'} · {source}")
                    try:
                        if source=='arxiv':rows,total=await sources.fetch_arxiv(query,days=days,limit=200)
                        else:rows,total=await sources.fetch_openalex(j['query'] or ' '.join(phrases[:4]) or d['name'],days=days,limit=100)
                        source_success+=1;fetched+=len(rows)
                        for p in rows:
                            _,added=sources.merge_paper(p);j['added']+=int(added)
                        if total>len(rows):j['warnings'].append(f'{source} 本次获取 {len(rows)}/{total} 条候选，请细化方向以降低遗漏。')
                    except Exception as e:
                        message=str(e) if isinstance(e,ValueError) else '网络或来源服务暂时不可用'
                        j['warnings'].append(f'{source}：{message}')
                if d['id']!='none' and (s['auto_ai'] or s['embedding_enabled']):j['warnings']+=await recommend.refine(d,update)
            if not source_success:raise ValueError('所有论文来源均未成功，请检查网络后重试。')
            j.update(status='done',fetched=fetched,finished=db.now());update(f'完成，获取 {fetched} 条，新增 {j["added"]} 篇')
            if j['kind']=='每日更新':db.set_setting('last_daily',ai.today())
        except Exception as e:
            j.update(status='failed',finished=db.now());update(str(e) if isinstance(e,ValueError) else '任务失败，请检查来源配置后重试。')


@app.post('/api/jobs')
async def jobs_post(request:Request):
    v=await request.json()
    if any(j['status'] in {'queued','running'} for j in db.all_rows('jobs')):raise ValueError('已有任务正在运行，请等待完成。')
    j=new_job('手动搜索' if v.get('query') else '每日更新',v.get('direction_id',''),v.get('query',''),v.get('source','arxiv'))
    spawn(run_job(j));return j


@app.get('/api/jobs')
async def jobs_get():return sorted(db.all_rows('jobs'),key=lambda j:j['created'],reverse=True)[:30]


@app.get('/api/search-results')
async def search_results(q=''):return [compact(p) for p in sorted(db.all_rows('papers'),key=lambda p:p['created'],reverse=True) if not q or q.lower() in sources_doc(p).lower()][:200]


@app.post('/api/zotero/test')
async def zotero_test():return await zotero.connection()


@app.post('/api/zotero/import')
async def zotero_import(request:Request):return await zotero.import_items((await request.json()).get('collection',''))


@app.post('/api/papers/{pid}/zotero')
async def zotero_export(pid:str,request:Request):
    v=await request.json();return await zotero.export_paper(paper_or_404(pid),v.get('collection',''),v.get('include_pdf',False))


@app.get('/api/export/notes')
async def export_notes():
    blocks=[]
    for n in db.notes():
        p=paper_or_404(n['paper_id']);blocks.append(f"## {p['title']}\n\n第 {n['page']} 页 · {n['created']}\n\n> {n['quote']}\n\n{n['text']}\n")
    return Response('\n'.join(blocks),media_type='text/markdown',headers={'Content-Disposition':'attachment; filename="notes.md"'})


@app.get('/api/export/citations')
async def citations(format='bibtex',paper_id=''):
    rows=[paper_or_404(paper_id)] if paper_id else [p for p in db.all_rows('papers') if p.get('saved')]
    blocks=[]
    clean=lambda s:str(s).replace('{','').replace('}','').replace('\\','').replace('\n',' ')
    for p in rows:
        if format=='ris':
            blocks.append('\n'.join(['TY  - JOUR','TI  - '+p['title'],*['AU  - '+a for a in p.get('authors',[])],
                'PY  - '+p.get('published','')[:4],'DO  - '+p.get('doi',''),'UR  - '+p.get('url',''),'ER  - ']))
        else:
            fields=dict(title=p['title'],author=' and '.join(p.get('authors',[])),year=p.get('published','')[:4],doi=p.get('doi',''),url=p.get('url',''))
            blocks.append('@article{paper'+re.sub('[^A-Za-z0-9]','',p['id'])+',\n'+',\n'.join('  '+k+' = {'+clean(v)+'}' for k,v in fields.items() if v)+'\n}')
    return Response('\n\n'.join(blocks),media_type='text/plain',headers={'Content-Disposition':f'attachment; filename="papers.{"ris" if format=="ris" else "bib"}"'})


@app.post('/api/import/citations')
async def import_citations(file:UploadFile=File(...)):
    raw=await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise ValueError('引用文件超过 5 MB。')
    text=raw.decode('utf-8-sig');items=[]
    if (file.filename or '').lower().endswith('.ris'):
        for chunk in text.split('ER  -'):
            fields={}
            for line in chunk.splitlines():
                m=re.match(r'^([A-Z0-9]{2})\s+-\s?(.*)',line)
                if m:fields.setdefault(m[1],[]).append(m[2])
            if not (fields.get('TI') or fields.get('T1')):continue
            items.append(sources.make_paper(title=(fields.get('TI') or fields['T1'])[0],authors=fields.get('AU',[]),
                published=fields.get('PY',[''])[0],doi=fields.get('DO',[''])[0],url=fields.get('UR',[''])[0],source='RIS 导入',saved=True))
    else:
        import bibtexparser
        library=bibtexparser.parse_string(text)
        if library.failed_blocks:raise ValueError('BibTeX 解析失败，请检查格式后重试。')
        for entry in library.entries:
            f={k:v.value for k,v in entry.fields_dict.items()}
            if f.get('title'):items.append(sources.make_paper(title=f['title'],authors=f.get('author','').split(' and '),published=f.get('year',''),doi=f.get('doi',''),url=f.get('url',''),abstract=f.get('abstract',''),source='BibTeX 导入',saved=True))
    for p in items:
        item,_=sources.merge_paper(p);item['saved']=True;db.put('papers',item['id'],item)
    return {'imported':len(items)}


@app.get('/api/backup')
async def backup():
    import sqlite3
    target=db.DATA/'backup.sqlite3'
    with db.connect() as src:
        dest=sqlite3.connect(target);src.backup(dest);dest.execute("DELETE FROM settings WHERE key='secrets' OR key LIKE 'provider:%'");dest.execute('DELETE FROM usage');dest.execute('DELETE FROM ai_cache');dest.commit();dest.execute('VACUUM');dest.close()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(target,'papernest.sqlite3')
        for p in db.FILES.glob('*.pdf'):z.write(p,'papers/'+p.name)
        z.writestr('README.txt','PaperNest backup v1. API keys and AI caches are excluded. Restore through the application.\n')
    target.unlink(missing_ok=True)
    return Response(stream.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="papernest-backup.zip"'})


@app.post('/api/restore')
async def restore(file:UploadFile=File(...)):
    import sqlite3,tempfile
    if job_lock.locked():raise ValueError('请等待获取任务完成后恢复。')
    content=await file.read(250*1024*1024+1)
    if len(content)>250*1024*1024:raise ValueError('备份超过 250 MB，请通过本地数据目录迁移。')
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        if sum(i.file_size for i in z.infolist())>1024*1024*1024:raise ValueError('解压大小超过限制。')
        if 'papernest.sqlite3' not in z.namelist():raise ValueError('不是 PaperNest 备份文件。')
        with tempfile.TemporaryDirectory(dir=db.DATA) as temp:
            path=Path(temp)/'restore.sqlite3';path.write_bytes(z.read('papernest.sqlite3'))
            source=sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True)
            try:
                if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('备份数据库损坏。')
                parsed={table:source.execute(f'SELECT * FROM {table}').fetchall() for table in ['papers','directions','notes','courses','zotero_map']}
                for table,rows in parsed.items():
                    for row in rows:json.loads(row[-1])
                # Restore merges by ID and never imports secrets or untrusted file paths.
                for filename in z.namelist():
                    if re.fullmatch(r'papers/[a-f0-9]{64}\.pdf',filename):
                        blob=z.read(filename)
                        if hashlib.sha256(blob).hexdigest()+'.pdf'!=Path(filename).name:raise ValueError('备份 PDF 校验失败。')
                        (db.FILES/Path(filename).name).write_bytes(blob)
                with db.connect() as dest:
                    for table,rows in parsed.items():
                        for row in rows:
                            if table=='papers':
                                p=json.loads(row[-1])
                                if p.get('pdf_file') and not re.fullmatch(r'[a-f0-9]{64}\.pdf',p['pdf_file']):raise ValueError('无效附件路径。')
                            marks=','.join('?' for _ in row)
                            dest.execute(f'INSERT OR IGNORE INTO {table} VALUES ({marks})',row)
                    for key,value in source.execute("SELECT key,value FROM settings WHERE key IN ('general','known_concepts')"):
                        json.loads(value)
                        dest.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',(key,value))
            finally:source.close()
    return {'ok':True,'message':'备份已合并，现有同编号记录保持不变；密钥需重新配置。'}


DIST=db.ROOT/'frontend'/'dist'
if DIST.exists():
    app.mount('/',StaticFiles(directory=DIST,html=True),name='frontend')


if __name__=='__main__':
    import uvicorn
    uvicorn.run('backend.app:app',host='127.0.0.1',port=8765)

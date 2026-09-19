import asyncio
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, unquote
import httpx
import pymupdf
from . import db
from .security import public_url, decrypt

HEADERS={'User-Agent':'PaperNest/0.1 (personal research reader; arXiv API)'}
_arxiv_lock=asyncio.Lock()
_last_arxiv=0.0


def normalize_doi(value):
    return re.sub(r'^https?://(?:dx\.)?doi\.org/','',str(value or '').strip(),flags=re.I).lower()


def arxiv_id(value):
    match=re.search(r'(?:arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?',value)
    return match.group(1) if match else ''


def make_paper(**values):
    return dict(id=db.uid(),title='',authors=[],abstract='',published='',updated=db.now(),created=db.now(),
        doi='',arxiv_id='',url='',pdf_url='',pdf_file='',pdf_hash='',pages=[],versions=[],tags=[],source='',
        saved=False,status='未读',feedback='',collections=[],classic=False,citations=0,summary=None,evidence=[],**{}) | values


def merge_paper(paper):
    """Preserve all user state. DOI/arXiv first; exact title+author/year as fallback."""
    paper['doi']=normalize_doi(paper.get('doi'))
    paper['arxiv_id']=arxiv_id(paper.get('arxiv_id','') or paper.get('url',''))
    title=lambda p:re.sub(r'\W+','',p.get('title','').lower())
    old=next((p for p in db.all_rows('papers') if
        (paper['doi'] and normalize_doi(p.get('doi'))==paper['doi']) or
        (paper['arxiv_id'] and p.get('arxiv_id')==paper['arxiv_id']) or
        (len(title(paper))>20 and title(paper)==title(p) and
         (set(p.get('authors',[]))&set(paper.get('authors',[]))))),None)
    if old:
        if paper.get('abstract') and paper['abstract']!=old.get('abstract'):
            old['summary']=None
        versions=old.get('versions',[])
        if paper.get('version') and paper['version'] != old.get('version'):
            versions=(versions+[dict(version=old.get('version',''),pdf_file=old.get('pdf_file',''),
                pdf_hash=old.get('pdf_hash',''),updated=old.get('updated'))])[-20:]
        # A downloaded file remains a snapshot; only an explicit download replaces it.
        for field in ['title','abstract','published','doi','arxiv_id','url','pdf_url','authors','version','venue']:
            if paper.get(field): old[field]=paper[field]
        old['tags']=list(dict.fromkeys(old.get('tags',[])+paper.get('tags',[])))
        old['citations']=max(old.get('citations',0),paper.get('citations',0))
        old['sources']=sorted(set(old.get('sources',[old['source']])+[paper['source']]))
        old['versions']=versions
        old['updated']=db.now()
        db.put('papers',old['id'],old)
        return old,False
    db.put('papers',paper['id'],paper)
    return paper,True


async def request_json(url,params=None,headers=None):
    async with httpx.AsyncClient(timeout=35,headers=HEADERS) as client:
        for attempt in range(3):
            try:
                r=await client.get(url,params=params,headers=headers)
                if r.status_code in {429,500,502,503,504} and attempt<2:
                    await asyncio.sleep(min(float(r.headers.get('Retry-After','3')),10))
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.TimeoutException:
                if attempt==2: raise ValueError('来源请求超时，请稍后重试。')


async def fetch_arxiv(query='',ids='',days=None,limit=100):
    global _last_arxiv
    params={'max_results':min(limit,200),'sortBy':'submittedDate','sortOrder':'descending'}
    if ids: params['id_list']=ids
    else:
        params['search_query']=query or 'cat:cs.AI'
        if days:
            start=(datetime.now(timezone.utc)-timedelta(days=days)).strftime('%Y%m%d0000')
            end=datetime.now(timezone.utc).strftime('%Y%m%d2359')
            params['search_query']+=f' AND submittedDate:[{start} TO {end}]'
    async with _arxiv_lock:
        await asyncio.sleep(max(0,3.1-(time.monotonic()-_last_arxiv)))
        try:
            async with httpx.AsyncClient(timeout=45,headers=HEADERS) as c:
                r=await c.get('https://export.arxiv.org/api/query',params=params)
                r.raise_for_status()
        finally: _last_arxiv=time.monotonic()
    root=ET.fromstring(r.text)
    ns={'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom','o':'http://a9.com/-/spec/opensearch/1.1/'}
    result=[]
    for entry in root.findall('a:entry',ns):
        text=lambda key:' '.join((entry.findtext(key,'',ns) or '').split())
        ident=arxiv_id(text('a:id'))
        if not ident: continue
        version=re.search(r'v(\d+)$',text('a:id'))
        links=entry.findall('a:link',ns)
        pdf=next((l.get('href','') for l in links if l.get('title')=='pdf'),f'https://arxiv.org/pdf/{ident}')
        result.append(make_paper(id='arxiv-'+ident,title=text('a:title'),arxiv_id=ident,
            authors=[a.findtext('a:name','',ns) for a in entry.findall('a:author',ns)],
            abstract=text('a:summary'),published=text('a:published')[:10],updated=text('a:updated'),
            version=version.group(1) if version else '1',doi=text('x:doi'),venue=text('x:journal_ref'),
            url=f'https://arxiv.org/abs/{ident}',pdf_url=pdf.replace('http:','https:'),source='arXiv',
            tags=[c.get('term','') for c in entry.findall('a:category',ns)]))
    return result,int(root.findtext('o:totalResults','0',ns))


def from_openalex(w):
    inverse=w.get('abstract_inverted_index') or {}
    positions={p:word for word,ps in inverse.items() for p in ps}
    location=w.get('best_oa_location') or w.get('primary_location') or {}
    return make_paper(id='oa-'+w['id'].split('/')[-1],title=w.get('title') or 'Untitled',
        doi=normalize_doi(w.get('doi')),abstract=' '.join(positions[p] for p in sorted(positions)),
        authors=[a['author'].get('display_name','') for a in w.get('authorships',[])],
        published=w.get('publication_date') or '',url=w.get('doi') or location.get('landing_page_url') or w['id'],
        pdf_url=location.get('pdf_url') or '',source='OpenAlex',citations=w.get('cited_by_count',0),
        venue=(location.get('source') or {}).get('display_name',''),
        tags=[t['display_name'] for t in w.get('topics',[])[:6]])


async def fetch_openalex(query,days=None,limit=100):
    params={'search':query,'per-page':min(limit,100),'sort':'publication_date:desc'}
    filters=['type:article|preprint|review','to_publication_date:'+datetime.now(timezone.utc).strftime('%Y-%m-%d')]
    if days: filters.append('from_publication_date:'+(datetime.now(timezone.utc)-timedelta(days=days)).strftime('%Y-%m-%d'))
    params['filter']=','.join(filters)
    key=db.setting('secrets',{}).get('openalex_key','')
    if key: params['api_key']=decrypt(key)
    data=await request_json('https://api.openalex.org/works',params)
    return [from_openalex(w) for w in data.get('results',[])],data.get('meta',{}).get('count',0)


async def import_link(value):
    ident=arxiv_id(value)
    if ident:
        rows,_=await fetch_arxiv(ids=ident)
        if not rows: raise ValueError('没有找到这个 arXiv 编号。')
        return merge_paper(rows[0])[0]
    doi=normalize_doi(value)
    if not doi.startswith('10.'):
        raise ValueError('请输入 DOI、arXiv 编号或对应链接。PDF 文件请使用上传入口。')
    data=await request_json('https://api.crossref.org/works/'+doi)
    w=data['message']
    date=(w.get('published') or {}).get('date-parts',[[datetime.now().year]])[0]
    paper=make_paper(title=(w.get('title') or ['Untitled'])[0],doi=doi,
        authors=[' '.join([a.get('given',''),a.get('family','')]).strip() for a in w.get('author',[])],
        published='-'.join(str(d).zfill(2) for d in date),abstract=re.sub('<[^>]+>',' ',w.get('abstract','')),
        url='https://doi.org/'+doi,venue=(w.get('container-title') or [''])[0],source='Crossref')
    try:
        row=await request_json('https://api.openalex.org/works/https://doi.org/'+doi)
        enriched=from_openalex(row)
        paper.update({k:v for k,v in enriched.items() if k in {'abstract','pdf_url','citations','tags'} and v})
    except Exception: pass
    return merge_paper(paper)[0]


async def download_public(url,max_bytes=40*1024*1024):
    async with httpx.AsyncClient(timeout=60,headers=HEADERS,follow_redirects=False) as c:
        for _ in range(6):
            await asyncio.to_thread(public_url,url)
            async with c.stream('GET',url) as r:
                if r.is_redirect:
                    url=urljoin(url,r.headers['location']);continue
                r.raise_for_status()
                content=bytearray()
                async for chunk in r.aiter_bytes():
                    content.extend(chunk)
                    if len(content)>max_bytes: raise ValueError('文件超过 40 MB，请下载后拆分再导入。')
                return bytes(content)
    raise ValueError('链接重定向次数过多。')


def attach_pdf(paper,content):
    if not content.lstrip().startswith(b'%PDF'): raise ValueError('返回内容不是 PDF。可以手动上传全文。')
    digest=hashlib.sha256(content).hexdigest()
    paper=db.get('papers',paper['id']) or paper
    with pymupdf.open(stream=content,filetype='pdf') as doc:
        if doc.needs_pass: raise ValueError('请先移除 PDF 密码后再导入。')
        if len(doc)>500: raise ValueError('第一版支持 500 页以内的 PDF。')
        pages=[dict(page=i+1,text=p.get_text(sort=True)) for i,p in enumerate(doc)]
        if not paper.get('title') or paper['title']=='Untitled' or paper.get('source')=='本地导入':
            paper['title']=doc.metadata.get('title') or paper.get('title') or '导入论文'
    if paper.get('pdf_hash') and paper['pdf_hash']!=digest:
        paper['versions']=(paper.get('versions',[])+[dict(pdf_hash=paper['pdf_hash'],pdf_file=paper['pdf_file'],updated=db.now())])[-20:]
    filename=digest+'.pdf'
    (db.FILES/filename).write_bytes(content)
    paper.update(pdf_file=filename,pdf_hash=digest,pages=pages,saved=True,updated=db.now(),summary=None,
        deep_summary=None,read_page=1,pdf_version=paper.get('version',''),scanned=sum(len(p['text']) for p in pages)<100)
    db.put('papers',paper['id'],paper)
    return paper

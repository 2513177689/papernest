"""Explicit, user-triggered import/export. Existing remote metadata is never overwritten."""
import hashlib
import html
import json
import httpx
from . import db, ai
from .security import decrypt
from .sources import make_paper,merge_paper,normalize_doi


def config():
    s=ai.settings();secret=decrypt(db.setting('secrets',{}).get('zotero_key',''))
    if not secret:raise ValueError('请先填写 Zotero API Key。')
    return s,{'Zotero-API-Key':secret,'Zotero-API-Version':'3'}


async def check(r):
    if r.status_code>=400:
        msg={403:'Zotero Key 没有对应文献库或附件权限。',401:'Zotero Key 无效。',413:'Zotero 附件存储空间不足。',412:'Zotero 条目已变化，请刷新后重试。',429:'Zotero 暂时限流，请稍后重试。'}.get(r.status_code,f'Zotero 请求失败（{r.status_code}）。')
        raise ValueError(msg)
    return r


async def connection():
    s,h=config()
    async with httpx.AsyncClient(timeout=30) as c:
        r=await check(await c.get('https://api.zotero.org/keys/current',headers=h));data=r.json()
        user=str(data.get('userID') or s.get('zotero_user_id',''))
        if not user:raise ValueError('无法获取 Zotero 用户 ID。')
        general=db.setting('general',{});general['zotero_user_id']=user;db.set_setting('general',general)
        r=await check(await c.get(f'https://api.zotero.org/users/{user}/collections',headers=h,params={'limit':100}))
        return dict(user_id=user,username=data.get('username',''),collections=[dict(id=x['key'],name=x['data']['name']) for x in r.json()])


async def import_items(collection=''):
    s,h=config();user=s.get('zotero_user_id')
    if not user: user=(await connection())['user_id']
    path=f'https://api.zotero.org/users/{user}/'+(f'collections/{collection}/' if collection else '')+'items/top'
    added=0;count=0
    async with httpx.AsyncClient(timeout=35) as c:
        for start in range(0,2000,100):
            r=await check(await c.get(path,headers=h,params={'limit':100,'start':start,'format':'json'}))
            rows=r.json()
            for item in rows:
                d=item['data']
                if d.get('itemType') in {'attachment','note','annotation'}:continue
                paper=make_paper(title=d.get('title','Untitled'),authors=[a.get('name') or (a.get('firstName','')+' '+a.get('lastName','')).strip() for a in d.get('creators',[])],
                    doi=d.get('DOI',''),abstract=d.get('abstractNote',''),published=d.get('date',''),url=d.get('url',''),
                    source='Zotero',tags=[t['tag'] for t in d.get('tags',[])],saved=True)
                paper,new=merge_paper(paper);paper['saved']=True;db.put('papers',paper['id'],paper)
                db.put('zotero_map',paper['id'],dict(paper_id=paper['id'],key=item['key'],user=user,created=db.now()))
                added+=int(new);count+=1
            if len(rows)<100:break
    return dict(imported=count,added=added,capped=count>=2000)


async def create_item(client,base,headers,payload):
    r=await check(await client.post(base+'/items',headers=headers,json=[payload]))
    data=r.json()
    if data.get('failed'):raise ValueError('Zotero 拒绝该条目，请检查条目字段或 Key 写入权限。')
    result=(data.get('successful') or {}).get('0')
    if not result:raise ValueError('Zotero 未确认保存结果，请先在 Zotero 检查后再重试。')
    return result['key']


async def export_paper(paper,collection='',include_pdf=False):
    s,h=config();user=s.get('zotero_user_id') or (await connection())['user_id'];base=f'https://api.zotero.org/users/{user}'
    mapping=db.get('zotero_map',paper['id']) or {}
    if mapping.get('user')!=user:mapping={}
    messages=[]
    async with httpx.AsyncClient(timeout=90) as c:
        key=mapping.get('key','')
        if key:
            r=await c.get(base+'/items/'+key,headers=h)
            if r.status_code==404:key='';mapping={}
            else:await check(r)
        if not key:
            # Search existing library for exact DOI or arXiv URL before creating.
            q=paper.get('doi') or paper.get('arxiv_id') or paper['title']
            r=await check(await c.get(base+'/items/top',headers=h,params={'q':q,'qmode':'everything','limit':100}))
            for entry in r.json():
                d=entry['data']
                if (paper.get('doi') and normalize_doi(d.get('DOI'))==paper['doi']) or (d.get('title','').casefold()==paper['title'].casefold()):
                    key=entry['key'];break
            if not key:
                payload=dict(itemType='journalArticle',title=paper['title'],abstractNote=paper.get('abstract',''),
                    creators=[dict(creatorType='author',name=a) for a in paper.get('authors',[])],date=paper.get('published',''),
                    DOI=paper.get('doi',''),url=paper.get('url',''),tags=[{'tag':t} for t in paper.get('tags',[])],collections=[collection] if collection else [])
                key=await create_item(c,base,h,payload)
            mapping=dict(paper_id=paper['id'],key=key,user=user,created=db.now(),sent_notes=[])
            db.put('zotero_map',paper['id'],mapping)
        if collection:
            r=await check(await c.get(base+'/items/'+key,headers=h));remote=r.json();cols=remote['data'].get('collections',[])
            if collection not in cols:
                await check(await c.patch(base+'/items/'+key,headers=h|{'If-Unmodified-Since-Version':str(remote['version'])},json={'collections':cols+[collection]}))
        entries=[]
        if paper.get('summary'):entries.append(('AI 总结',paper['summary']['text']))
        entries.extend(('阅读笔记',n['quote']+'\n'+n['text']) for n in db.notes(paper['id']))
        # Remote notes are checked too, so a crash after a write cannot duplicate them on retry.
        children=await check(await c.get(base+'/items/'+key+'/children',headers=h,params={'limit':100}))
        remote_notes=' '.join(x['data'].get('note','') for x in children.json())
        for label,text in entries:
            digest=hashlib.sha256(text.encode()).hexdigest()
            marker='PaperNest:'+digest
            if marker in remote_notes:continue
            await create_item(c,base,h,dict(itemType='note',parentItem=key,note=f'<h2>{label}</h2><p>{html.escape(text).replace(chr(10),"<br>")}</p><p>{marker}</p>',tags=[]))
        if include_pdf and paper.get('pdf_file'):
            try:
                content=(db.FILES/paper['pdf_file']).read_bytes();md5=hashlib.md5(content).hexdigest()
                existing=next((x for x in children.json() if x['data'].get('itemType')=='attachment' and x['data'].get('md5')==md5),None)
                if not existing:
                    attach=mapping.get('attachment') if mapping.get('upload_hash')==md5 else ''
                    if not attach:
                        attach=await create_item(c,base,h,dict(itemType='attachment',parentItem=key,linkMode='imported_file',title=paper['title']+'.pdf',contentType='application/pdf',filename='paper.pdf',tags=[]))
                        mapping.update(attachment=attach,upload_hash=md5);db.put('zotero_map',paper['id'],mapping)
                    r=await check(await c.post(base+f'/items/{attach}/file',headers=h|{'If-None-Match':'*'},data={'md5':md5,'filename':'paper.pdf','filesize':str(len(content)),'mtime':str(int(__import__('time').time()*1000))}))
                    auth=r.json()
                    if not auth.get('exists'):
                        r=await c.post(auth['url'],content=auth['prefix'].encode()+content+auth['suffix'].encode(),headers={'Content-Type':auth['contentType']})
                        await check(r)
                        await check(await c.post(base+f'/items/{attach}/file',headers=h|{'If-None-Match':'*'},data={'upload':auth['uploadKey']}))
                messages.append('PDF 已保存')
            except Exception as e:messages.append('文献记录已保存，PDF 上传未完成：'+(str(e) if isinstance(e,ValueError) else '网络或附件服务错误'))
        mapping['updated']=db.now();db.put('zotero_map',paper['id'],mapping)
    return dict(key=key,url=f'https://www.zotero.org/users/{user}/items/{key}',messages=messages or ['论文和笔记已保存'])

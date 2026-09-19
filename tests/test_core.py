import os
import tempfile
from pathlib import Path
os.environ['PAPERNEST_DATA']=tempfile.mkdtemp(prefix='papernest-tests-')

import asyncio
import io
import json
import zipfile
import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient
from backend import db, sources, recommend, ai
from backend.app import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        boot=c.get('/api/bootstrap').json()
        c.headers['X-PaperNest-Token']=boot['token']
        yield c


def pdf_bytes():
    doc=pymupdf.open();p=doc.new_page();p.insert_text((40,60),'Retrieval augmented generation. This is a searchable research document.')
    content=doc.tobytes();doc.close();return content


def test_paper_lifecycle_and_backup(client):
    content=pdf_bytes()
    r=client.post('/api/import/pdf',files={'file':('test.pdf',content,'application/pdf')})
    assert r.status_code==200,r.text
    p=r.json();assert p['saved'] and p['page_count']==1
    repeat=client.post('/api/import/pdf',files={'file':('again.pdf',content,'application/pdf')})
    assert repeat.status_code==200 and repeat.json()['id']==p['id']
    assert client.patch('/api/papers/'+p['id'],json={'status':'正在读','collections':['RAG'],'read_page':1}).status_code==200
    quote='Retrieval augmented generation.'
    n=client.post('/api/notes',json={'paper_id':p['id'],'text':'Compare evidence selection','quote':quote,'page':1,'rects':[{'x':.1,'y':.1,'w':.2,'h':.02}]}).json()
    assert n['file_hash']==p['pdf_hash']
    assert any(x['id']==p['id'] for x in client.get('/api/papers',params={'q':'Compare evidence'}).json())
    assert client.get('/api/papers/'+p['id']+'/pdf').content.startswith(b'%PDF')
    exported=client.get('/api/export/notes').text;assert quote in exported
    bib=client.get('/api/export/citations',params={'paper_id':p['id']}).text;assert '@article' in bib
    restored=client.post('/api/import/citations',files={'file':('papers.bib',bib.encode(),'text/plain')})
    assert restored.status_code==200,restored.text
    assert restored.json()['imported']==1
    db.set_setting('secrets',{'test_secret':'DO_NOT_EXPORT_THIS'})
    backup=client.get('/api/backup');assert backup.status_code==200
    z=zipfile.ZipFile(io.BytesIO(backup.content));assert 'papernest.sqlite3' in z.namelist()
    assert b'DO_NOT_EXPORT_THIS' not in z.read('papernest.sqlite3')
    result=client.post('/api/restore',files={'file':('backup.zip',backup.content,'application/zip')})
    assert result.status_code==200,result.text


def test_csrf_and_origin(client):
    assert client.post('/api/jobs',headers={'X-PaperNest-Token':'bad'},json={}).status_code==403
    assert client.get('/api/bootstrap',headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/bootstrap',headers={'Host':'evil.example'}).status_code==400


def test_dedup_preserves_user_state():
    p=sources.make_paper(title='A sufficiently long title about retrieval',doi='https://doi.org/10.1/ABC',source='arXiv',saved=True)
    p,_=sources.merge_paper(p)
    newer=sources.make_paper(title=p['title'],doi='10.1/abc',abstract='updated',source='OpenAlex')
    merged,added=sources.merge_paper(newer)
    assert not added and merged['id']==p['id'] and merged['saved'] and merged['abstract']=='updated'


def test_ranking_exclusions_and_feedback():
    direction=dict(id='ranking-test',name='RAG',description='',keywords=['retrieval'],excludes=['medical'])
    p=sources.make_paper(title='Retrieval enhanced language models',source='test')
    q=sources.make_paper(title='Medical retrieval enhanced language models',source='test')
    r=sources.make_paper(title='Protein folding methods',source='test')
    ranked=recommend.rank(direction,[p,q,r]);assert ranked[0]['id']==p['id']
    assert next(x for x in ranked if x['id']==q['id'])['excluded']==['medical']
    assert next(x for x in ranked if x['id']==r['id'])['rank_score']==0
    assert len(recommend.select_diverse(ranked,2))==2


def test_ai_missing_key_and_cache(client,monkeypatch):
    monkeypatch.setattr(ai,'public_url',lambda *args,**kwargs:args[0])
    db.set_setting('provider:deepseek',{})
    response=client.post('/api/providers/deepseek/test')
    assert response.status_code==400 and 'API Key' in response.text
    ai.save_provider('deepseek',{'api_key':'not-a-real-key'})
    assert not any('not-a-real-key' in json.dumps(p) for p in ai.public_providers())
    assert 'not-a-real-key' not in (db.DATA/'papernest.sqlite3').read_bytes().decode('latin1')
    monkeypatch.setattr(ai,'public_url',lambda *args,**kwargs:args[0])
    called=[]
    async def post(self,url,**kwargs):
        called.append((url,kwargs));return httpx.Response(200,json={'choices':[{'message':{'content':'有依据的概览'}}],'usage':{'prompt_tokens':10,'completion_tokens':20}})
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    a=asyncio.run(ai.generate('system','unique test input'))
    b=asyncio.run(ai.generate('system','unique test input'))
    assert a['text']==b['text'] and b['cached'] and len(called)==1


@pytest.mark.parametrize('protocol,pid,body',[
    ('responses','openai',{'output':[{'content':[{'type':'output_text','text':'OK'}]}]}),
    ('anthropic','claude',{'content':[{'type':'text','text':'OK'}]}),
    ('gemini','gemini',{'candidates':[{'content':{'parts':[{'text':'OK'}]}}]}),
])
def test_provider_protocols(monkeypatch,protocol,pid,body):
    monkeypatch.setattr(ai,'public_url',lambda *args,**kwargs:args[0])
    ai.save_provider(pid,{'api_key':'test','protocol':protocol})
    async def post(self,url,**kwargs):return httpx.Response(200,json=body)
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    assert asyncio.run(ai.generate('s','p','test',pid,cache=False))['text']=='OK'


def test_pdf_validation(client):
    assert client.post('/api/import/pdf',files={'file':('bad.pdf',b'<html>not pdf</html>','application/pdf')}).status_code==400
    assert client.get('/api/papers/no-such-paper').status_code==404


def test_arxiv_parse_version_and_doi():
    assert sources.arxiv_id('https://arxiv.org/pdf/1706.03762v7')=='1706.03762'
    assert sources.normalize_doi('https://doi.org/10.1000/ABC')=='10.1000/abc'


def test_daily_does_not_fill_with_old_papers():
    d=dict(id='no-fill',name='retrieval',keywords=['retrieval'],description='',excludes=[])
    assert not any(p.get('classic') for p in recommend.daily(d))


def test_restore_rejects_bad_pdf_paths(client):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:z.writestr('../../escape.txt','bad')
    assert client.post('/api/restore',files={'file':('bad.zip',stream.getvalue(),'application/zip')}).status_code==400


def test_course_query_is_not_overridden_by_direction():
    d=dict(id='course-test',name='LLM',description='',keywords=['language model'],excludes=[])
    result=recommend.courses_for(d,query='attention')
    assert result
    assert all('attention' in (c['title']+' '+c['description']+' '+' '.join(c['tags'])).lower() for c in result)


def test_daily_job_retains_partial_source_errors(monkeypatch):
    from backend.app import new_job,run_job
    d=dict(id='job-test',name='RAG',description='',keywords=['retrieval'],excludes=[],categories=[])
    db.put('directions',d['id'],d)
    async def good(*args,**kwargs):return [sources.make_paper(title='Retrieval methods for reliable evidence',source='arXiv',published=ai.today())],500
    async def bad(*args,**kwargs):raise ValueError('Source unavailable')
    monkeypatch.setattr(sources,'fetch_arxiv',good);monkeypatch.setattr(sources,'fetch_openalex',bad)
    job=new_job('每日更新',d['id']);asyncio.run(run_job(job));saved=db.get('jobs',job['id'])
    assert saved['status']=='done' and saved['added']==1 and len(saved['warnings'])==2
    with db.connect() as c:c.execute('DELETE FROM directions WHERE id=?',(d['id'],))


def test_zotero_metadata_export_contract(monkeypatch):
    from backend import zotero
    from backend.security import encrypt
    db.set_setting('secrets',{'zotero_key':encrypt('test-zotero')})
    db.set_setting('general',{'zotero_user_id':'12345'})
    p=sources.make_paper(title='A Test Zotero Paper',doi='10.123/test',authors=['Test Author'],source='test')
    db.put('papers',p['id'],p);calls=[]
    async def get(self,url,**kwargs):
        if url.endswith('/items/ABCD1234'):return httpx.Response(200,json={'key':'ABCD1234','version':1,'data':{'collections':['COLL1234']}})
        return httpx.Response(200,json=[])
    async def post(self,url,**kwargs):
        calls.append(kwargs['json']);return httpx.Response(200,json={'successful':{'0':{'key':'ABCD1234'}}})
    monkeypatch.setattr(httpx.AsyncClient,'get',get);monkeypatch.setattr(httpx.AsyncClient,'post',post)
    first=asyncio.run(zotero.export_paper(p,'COLL1234'))
    second=asyncio.run(zotero.export_paper(p,'COLL1234'))
    assert first['key']==second['key']=='ABCD1234' and len(calls)==1
    assert calls[0][0]['DOI']=='10.123/test' and calls[0][0]['collections']==['COLL1234']


def test_local_model_without_key(monkeypatch):
    monkeypatch.setattr(ai,'public_url',lambda *args,**kwargs:args[0])
    ai.save_provider('custom',{'base_url':'http://localhost:11434/v1','model':'local','clear_key':True})
    seen=[]
    async def post(self,url,**kwargs):
        seen.append(kwargs['headers'])
        return httpx.Response(200,json={'choices':[{'message':{'content':'OK'}}]})
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    assert asyncio.run(ai.generate('s','local','test','custom',cache=False))['text']=='OK'
    assert 'Authorization' not in seen[0]

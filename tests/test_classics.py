from tests.test_core import client
from backend import db, recommend, catalog
from backend.sources import make_paper


def test_catalog_and_seed_preserve_user_data(client):
    assert len(catalog.CLASSICS)==100
    assert len({p['arxiv_id'] for p in catalog.CLASSICS})==100
    p=db.get('papers','arxiv-1706.03762')
    old=dict(p)
    try:
        p.update(saved=True,status='正在读',read_page=7,curation='我的阅读理由')
        db.put('papers',p['id'],p)
        catalog.seed()
        result=db.get('papers',p['id'])
        assert result['saved'] and result['read_page']==7
        assert result['curation']=='我的阅读理由'
    finally:db.put('papers',old['id'],old)


def test_classics_limit_order_and_filter_before_limit(client):
    ids=[]
    try:
        for i in range(105):
            p=make_paper(id=f'test-classic-{i:03}',title=f'Unique filtered classic {i}',classic=True,published='2000',
                evidence=[{'type':'教材章节','url':'https://example.org/reference','label':'test'}])
            ids.append(p['id']);db.put('papers',p['id'],p)
        rows=client.get('/api/papers',params={'view':'classics','mode':'all'}).json()
        assert len(rows)==100
        assert [p['classic_score'] for p in rows]==sorted([p['classic_score'] for p in rows],reverse=True)
        assert [p['classic_rank'] for p in rows]==list(range(1,101))
        result=client.get('/api/papers',params={'view':'classics','mode':'all','q':'Unique filtered classic 104'}).json()
        assert len(result)==1 and result[0]['id']=='test-classic-104'
    finally:
        with db.connect() as c:
            c.executemany('DELETE FROM papers WHERE id=?',[(key,) for key in ids])


def test_personal_ranking_and_score_bounds(client):
    direction={'id':'classic-test','name':'computer vision','keywords':['computer vision'],'description':'','excludes':[]}
    rows=recommend.classics(direction)
    assert rows and all(p['rank_score']>=.18 for p in rows)
    for p in rows:
        assert 0<=p['classic_score']<=100
        assert abs(sum(p['score_parts'].values())-p['classic_score'])<.01
        assert p['score_scope']=='personal'
    assert not recommend.classics(direction | {'keywords':['no-match-zzyyxx'],'name':'no-match-zzyyxx'})
    assert all(p['score_scope']=='all' for p in recommend.classics({'id':'none','name':'','keywords':[]}))

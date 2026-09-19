"""Exercise the real daily pipeline with a temporary profile; keep fetched scholarly records."""
import time
import httpx

with httpx.Client(base_url='http://127.0.0.1:8765',timeout=30) as c:
    c.headers['X-PaperNest-Token']=c.get('/api/bootstrap').json()['token']
    r=c.post('/api/directions',json={'name':'Integration check RAG','description':'retrieval augmented generation',
        'keywords':['retrieval augmented generation'],'categories':['cs.CL'],'excludes':[]})
    r.raise_for_status();d=r.json()
    try:
        r=c.post('/api/jobs',json={'direction_id':d['id']});r.raise_for_status();job=r.json()
        for i in range(90):
            time.sleep(1)
            row=next(j for j in c.get('/api/jobs').json() if j['id']==job['id'])
            if row['status'] in {'done','failed'}:
                recommendations=c.get('/api/papers',params={'view':'today','direction_id':d['id']}).json()
                print({'status':row['status'],'fetched':row.get('fetched',0),'added':row['added'],
                    'warnings':row['warnings'],'recommendations':len(recommendations)},flush=True)
                assert row['status']=='done',row
                assert len(recommendations)<=5
                break
        else:raise TimeoutError('Daily task did not complete within 90 seconds')
    finally:
        c.delete('/api/directions/'+d['id'])

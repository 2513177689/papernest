import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from backend import sources

async def main():
    for name,fn in [('arxiv',lambda:sources.fetch_arxiv(ids='1706.03762',limit=1)),
                    ('openalex',lambda:sources.fetch_openalex('retrieval augmented generation',limit=2))]:
        try:
            rows,total=await fn()
            print(name,{'returned':len(rows),'total':total,'title':rows[0]['title'] if rows else ''})
            if name=='arxiv' and rows:
                p,_=sources.merge_paper(rows[0])
                try:
                    content=await sources.download_public(p['pdf_url'])
                    p=sources.attach_pdf(p,content)
                    # Keep the installed app's library empty until the user starts collecting.
                    p['saved']=False;sources.db.put('papers',p['id'],p)
                    print('pdf',{'bytes':len(content),'pages':len(p['pages'])})
                except Exception as e:print('pdf',type(e).__name__,str(e)[:150])
        except Exception as e:print(name,type(e).__name__,str(e)[:150])

asyncio.run(main())

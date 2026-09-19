"""Browser checks against the running local app; restores any temporary user state."""
import json
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'artifacts';OUT.mkdir(exist_ok=True)
client=httpx.Client(base_url='http://127.0.0.1:8765',timeout=30)
boot=client.get('/api/bootstrap').json();client.headers['X-PaperNest-Token']=boot['token']
pid='arxiv-1706.03762';original=client.get('/api/papers/'+pid).json()
original_notes={n['id'] for n in client.get('/api/notes',params={'paper_id':pid}).json()}
errors=[];direction_id=None
try:
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8765')
        page.get_by_role('button',name='大模型与检索增强').click()
        page.get_by_label('方向名称',exact=True).fill('UI validation RAG')
        page.get_by_role('button',name='保存研究方向',exact=True).click()
        page.wait_for_selector('.topic-banner')
        direction_id=next(d['id'] for d in client.get('/api/bootstrap').json()['directions'] if d['name']=='UI validation RAG')
        page.get_by_role('button',name='经典与必读',exact=True).click()
        page.get_by_role('button',name='全部精选基础',exact=True).click()
        page.get_by_role('button',name='Attention Is All You Need',exact=True).wait_for()
        page.screenshot(path=str(OUT/'classics.png'),full_page=True)
        page.get_by_role('button',name='Attention Is All You Need',exact=True).click()
        page.get_by_role('dialog').get_by_role('button',name='阅读与解读',exact=True).click()
        page.wait_for_selector('.textLayer span',timeout=20000)
        assert page.locator('.pdf-page canvas').evaluate('(e)=>e.width')>100
        page.locator('.textLayer').evaluate('''el=>{const spans=[...el.querySelectorAll('span')].filter(e=>e.textContent.trim().length>10);const range=document.createRange();range.selectNodeContents(spans[0]);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));}''')
        page.get_by_role('button',name='翻译',exact=True).wait_for()
        page.get_by_role('button',name='高亮保存',exact=True).click()
        page.wait_for_selector('.note-list .note')
        assert len(client.get('/api/notes',params={'paper_id':pid}).json())>len(original_notes)
        page.get_by_role('button',name='下一页',exact=True).click()
        page.wait_for_timeout(800)
        assert client.get('/api/papers/'+pid).json()['read_page']==2
        page.get_by_role('button',name='AI 解读',exact=True).click()
        page.screenshot(path=str(OUT/'reader.png'),full_page=True)
        page.get_by_role('button',name='知识与课程',exact=True).click()
        page.wait_for_selector('.course-card')
        page.get_by_label('搜索课程').fill('attention')
        page.wait_for_timeout(500)
        assert page.locator('.course-card').count()>0
        page.get_by_role('button',name='模型与设置',exact=True).click()
        page.wait_for_selector('.provider-grid')
        assert page.locator('.provider-grid button').count()==10
        page.get_by_role('button',name='Claude',exact=True).click()
        assert '已保存' not in page.locator('input[type=password]').first.get_attribute('placeholder')
        page.screenshot(path=str(OUT/'settings.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.get_by_role('button',name='知识与课程',exact=True).click()
        page.wait_for_selector('.course-card')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Mobile overflow'
        page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
        browser.close()
    if errors:raise AssertionError(errors)
    print(json.dumps({'passed':True,'browser_errors':errors,'screenshots':4}))
finally:
    if not direction_id:
        direction_id=next((d['id'] for d in client.get('/api/bootstrap').json()['directions'] if d['name']=='UI validation RAG'),None)
    if direction_id:client.delete('/api/directions/'+direction_id)
    client.patch('/api/papers/'+pid,json={k:original.get(k,1 if k=='read_page' else '') for k in ['saved','status','feedback','collections','read_page']})
    for note in client.get('/api/notes',params={'paper_id':pid}).json():
        if note['id'] not in original_notes:client.delete('/api/notes/'+note['id'])
    client.close()

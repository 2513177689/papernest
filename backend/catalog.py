"""Provider presets are editable: access and available model IDs depend on the account."""
PROVIDERS = [
    dict(id='deepseek',name='DeepSeek',base_url='https://api.deepseek.com',model='deepseek-flash',protocol='chat',help='日常概览的默认选项。使用开放平台按量计费 Key。',docs='https://api-docs.deepseek.com/'),
    dict(id='kimi',name='Kimi',base_url='https://api.moonshot.cn/v1',model='kimi-k2.5',protocol='chat',help='中国站地址；国际站 Key 请改为对应官方地址。模型名称可修改。',docs='https://platform.kimi.com/docs/guide/migrating-from-openai-to-kimi'),
    dict(id='openai',name='OpenAI / GPT',base_url='https://api.openai.com/v1',model='gpt-5-mini',protocol='responses',help='使用 OpenAI API 账户密钥，模型权限以你的账户为准。',docs='https://developers.openai.com/api/docs/guides/text'),
    dict(id='claude',name='Claude',base_url='https://api.anthropic.com/v1',model='claude-sonnet-4-6',protocol='anthropic',help='使用 Claude Console 密钥；跨工作区密钥可填写工作区 ID。',docs='https://platform.claude.com/docs/en/api/overview'),
    dict(id='gemini',name='Gemini',base_url='https://generativelanguage.googleapis.com/v1beta',model='gemini-2.5-flash',protocol='gemini',help='使用 Google AI Studio 的 Gemini API Key。',docs='https://ai.google.dev/gemini-api/docs/api-key'),
    dict(id='qwen',name='通义千问 Qwen',base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',model='qwen-plus',protocol='chat',help='默认北京地域；接口地址必须与 API Key 地域一致。使用按量付费 Key。',docs='https://help.aliyun.com/zh/model-studio/base-url'),
    dict(id='doubao',name='豆包',base_url='https://ark.cn-beijing.volces.com/api/v3',model='doubao-seed-2-0-lite-260215',protocol='chat',help='火山方舟 API Key；可以将模型名称换成你的推理接入点 ID。',docs='https://www.volcengine.com/docs/82379/1795150'),
    dict(id='glm',name='智谱 GLM',base_url='https://open.bigmodel.cn/api/paas/v4',model='glm-4.7-flash',protocol='chat',help='使用智谱开放平台 Key；默认模型的可用性以账户为准。',docs='https://docs.bigmodel.cn/cn/guide/start/model-overview'),
    dict(id='minimax',name='MiniMax',base_url='https://api.minimax.cn/v1',model='MiniMax-M3',protocol='chat',help='使用 MiniMax 开放平台按量计费 Key。',docs='https://platform.minimax.cn/docs/api-reference/text-openai-api'),
    dict(id='custom',name='自定义兼容服务',base_url='',model='',protocol='chat',help='支持 OpenAI Chat / Responses、Claude 和 Gemini 格式；允许本机模型服务。',docs=''),
]

DEFAULT_SETTINGS = dict(active_provider='deepseek',deep_provider='',daily_limit=5,lookback_days=7,
    schedule_enabled=True,schedule_hour=8,timezone='Asia/Hong_Kong',auto_ai=False,
    ai_candidates=10,daily_ai_calls=50,daily_token_limit=200000,
    embedding_enabled=False,embedding_url='https://api.openai.com/v1',embedding_model='text-embedding-3-small',
    openalex_key='',zotero_user_id='',zotero_collection='',zotero_pdf=False,
    knowledge_level='入门',free_only=True,language='中文优先')

COURSES = [
    dict(id='d2l',title='动手学深度学习',author='李沐等',platform='课程官网 / B 站',url='https://zh.d2l.ai/',language='中文',level='入门',free='免费',kind='教材 + 视频',tags=['deep learning','neural network','transformer','attention','深度学习','机器学习','大模型'],description='从数学基础到注意力机制，配合代码与练习。视频入口以作者官网为准。'),
    dict(id='hf-llm',title='Hugging Face LLM Course',author='Hugging Face',platform='Hugging Face',url='https://huggingface.co/learn/llm-course/chapter1/1',language='英文',level='进阶',free='免费',kind='实践教程',tags=['nlp','language model','transformer','fine tuning','rag','retrieval','大模型'],description='学习 Transformers、数据处理与语言模型训练工具。'),
    dict(id='mit-linear',title='Linear Algebra · 18.06',author='Gilbert Strang / MIT',platform='MIT OpenCourseWare',url='https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/',language='英文',level='入门',free='免费',kind='公开课',tags=['linear algebra','matrix','optimization','machine learning','数学','线性代数'],description='向量、矩阵与线性空间，为理解机器学习方法补充基础。'),
    dict(id='cs224n',title='CS224N · Natural Language Processing',author='Stanford',platform='大学课程官网',url='https://web.stanford.edu/class/cs224n/',language='英文',level='进阶',free='免费公开材料',kind='公开课',tags=['nlp','language model','transformer','attention','retrieval','自然语言处理'],description='自然语言处理的模型、表示与学习方法；公开资料以课程网站为准。'),
    dict(id='cs231n',title='CS231n · Deep Learning for Computer Vision',author='Stanford',platform='大学课程官网',url='https://cs231n.stanford.edu/',language='英文',level='进阶',free='免费公开材料',kind='公开课',tags=['computer vision','image','convolution','视觉','图像'],description='图像识别与视觉深度学习的课程笔记和公开资源。'),
    dict(id='csdiy',title='CS 自学指南',author='社区维护',platform='CS 自学指南',url='https://csdiy.wiki/',language='中文',level='入门',free='免费导航',kind='课程导航',tags=['computer','system','algorithm','database','计算机','算法','系统'],description='按学科整理课程与学习路线；外链课程的费用需要逐项确认。'),
    dict(id='mit-ocw',title='MIT OpenCourseWare 学科课程库',author='MIT',platform='MIT OpenCourseWare',url='https://ocw.mit.edu/search/',language='英文',level='不限',free='免费',kind='课程导航',tags=['physics','math','biology','economics','物理','数学','生物','经济'],description='覆盖理工、人文等学科的公开课、讲义与习题。'),
]

CLASSICS = [
    dict(arxiv_id='1706.03762',title='Attention Is All You Need',authors=['Ashish Vaswani','Noam Shazeer','Niki Parmar','Jakob Uszkoreit','Llion Jones','Aidan N. Gomez','Łukasz Kaiser','Illia Polosukhin'],published='2017-06-12',tags=['transformer','attention','nlp','deep learning'],curation='理解 Transformer 与现代语言模型的基础阅读。',evidence=[dict(label='动手学深度学习：Transformer',url='https://zh.d2l.ai/chapter_attention-mechanisms/transformer.html',type='教材章节')]),
    dict(arxiv_id='2005.11401',title='Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks',authors=['Patrick Lewis','Ethan Perez','Aleksandra Piktus','et al.'],published='2020-05-22',tags=['rag','retrieval','nlp','language model'],curation='检索增强生成的代表性方法，适合与后续检索策略一起阅读。',evidence=[dict(label='Hugging Face：RAG 模型文档',url='https://huggingface.co/docs/transformers/model_doc/rag',type='官方技术文档')]),
    dict(arxiv_id='1810.04805',title='BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding',authors=['Jacob Devlin','Ming-Wei Chang','Kenton Lee','Kristina Toutanova'],published='2018-10-11',tags=['bert','transformer','nlp','language model'],curation='理解预训练与微调范式的基础阅读。',evidence=[dict(label='动手学深度学习：BERT',url='https://zh.d2l.ai/chapter_natural-language-processing-pretraining/bert.html',type='教材章节')]),
    dict(arxiv_id='1512.03385',title='Deep Residual Learning for Image Recognition',authors=['Kaiming He','Xiangyu Zhang','Shaoqing Ren','Jian Sun'],published='2015-12-10',tags=['computer vision','image','resnet','deep learning'],curation='理解残差连接与深层网络训练的基础阅读。',evidence=[dict(label='动手学深度学习：ResNet',url='https://zh.d2l.ai/chapter_convolutional-modern/resnet.html',type='教材章节')]),
]


from pathlib import Path
import json
CLASSICS += json.loads(Path(__file__).with_name('classics.json').read_text(encoding='utf-8'))

def seed():
    from . import db
    for c in COURSES:
        if not db.get('courses',c['id']):
            db.put('courses',c['id'],dict(c,status='未学习',saved=False,verified='2026-09-19'))
    for p in CLASSICS:
        key='arxiv-'+p['arxiv_id']
        current=db.get('papers',key) or next((row for row in db.all_rows('papers') if row.get('arxiv_id')==p['arxiv_id']),None)
        if current:
            key=current['id']
            current['tags']=list(dict.fromkeys(current.get('tags',[])+p['tags']))
            if not current.get('classic') and not current.get('evidence'):
                current.update(classic=True,curation=p['curation'],evidence=p['evidence'])
            db.put('papers',key,current)
        if not db.get('papers',key):
            db.put('papers',key,dict(p,id=key,doi='',abstract='',source='人工精选',
                url='https://arxiv.org/abs/'+p['arxiv_id'],pdf_url='https://arxiv.org/pdf/'+p['arxiv_id'],
                pdf_file='',pdf_hash='',pages=[],versions=[],saved=False,status='未读',feedback='',collections=[],
                classic=True,citations=0,created=db.now(),updated=db.now(),summary=None))

# 知阅 PaperNest

**从每日发现到深入阅读，让论文围绕你的研究方向组织起来。**

PaperNest 是在本机运行的个人论文发现与阅读工作台，提供方向订阅、每日推荐、经典论文、AI 总结、PDF 阅读、划词翻译、笔记、免费课程推荐及 Zotero 对接。Python + FastAPI 后端，React + TypeScript 前端，SQLite 数据库。默认只监听 `127.0.0.1:8765`。

Local-first paper discovery and reading workspace with personalized recommendations, AI summaries, PDF annotations, learning resources, and Zotero integration.

当前版本：**v0.1.0 · 首个公开版本**。主要界面为中文，适合个人研究与学习。无需模型密钥即可使用基础功能。

[安装](#安装与开发) · [使用指南](docs/usage.md) · [推荐机制](docs/recommendation.md) · [版本记录](CHANGELOG.md)

## 开始使用

首次下载请先完成下方“安装与开发”。安装完成后，Windows 双击 **start.cmd**，浏览器打开 <http://127.0.0.1:8765>。后台窗口保持运行才能执行每日任务。

已经运行时重复启动只会打开现有应用。需要停止时关闭手动启动的后台窗口，或执行 `stop.ps1`；它只停止本目录启动的 8765 端口进程。

1. 在首页选择或创建研究方向。用英文术语填写检索关键词，用中文描述具体需求；可配置排除词及 arXiv 学科分类。
2. 点击“获取最新论文”。“更新记录”显示来源状态、获取数量和截断情况。每日精选不足时不会凑数。
3. 在“模型与设置”选择服务商，填入 API Key，保存并测试连接。选择日常/全文模型，按需启用自动 AI 精筛，然后保存通用设置。
4. 收藏论文，打开阅读器。可获取开放 PDF，或导入自己的 PDF；选中文字后翻译、解释、高亮或记笔记。
5. Zotero 使用独立的 API Key，需要个人文献库读写权限。连接后选择集合；上传附件会占用 Zotero 文件空间。

未配置 AI 时，论文获取、规则推荐、个人库、阅读器、笔记与课程库都可使用。AI、翻译及 Zotero 的真实服务需要你自己的密钥。源码不包含账户密钥、个人数据库、下载的论文或本地备份。

## 已实现

| 模块 | 第一版内容 |
| --- | --- |
| 研究方向 | 多方向、研究描述、关键词、排除词、arXiv 分类、作者与会议偏好字段 |
| 获取 | arXiv、OpenAlex 每日获取和手动搜索；DOI/Crossref 与 arXiv 链接导入；PDF 批量上传；BibTeX/RIS 导入 |
| 推荐 | BM25、短语匹配、可选向量与 AI 摘要精筛、明确反馈、多样性重排；可查看被过滤候选 |
| 经典 | 少量附教材/官方技术文档依据的计算机基础论文；按方向匹配；可手动补充来源加入清单 |
| 论文库 | 收藏、阅读状态、专题集合、标签、标题/摘要/已提取正文/笔记搜索、PDF 离线保存 |
| 阅读 | PDF.js 原文、缩放、目录、页内文本选择、搜索结果跳页、文字模式、进度恢复、选文翻译/解释、笔记和高亮 |
| AI | 简短概览、按需正文解读、当前页问答、前置知识整理；依据范围、模型和时间；按内容缓存 |
| 模型 | DeepSeek、Kimi、OpenAI、Claude、Gemini、Qwen、豆包、GLM、MiniMax 和自定义兼容服务 |
| 课程 | 免费课程资源库、研究方向/知识点匹配、学习状态与收藏、课程链接添加、B 站搜索入口 |
| Zotero | 个人文献库连接、集合导入、文献保存、总结与笔记导出、可选 PDF 上传、ID/DOI 去重 |
| 数据 | BibTeX/RIS 导出、Markdown 笔记导出、含 PDF 的 ZIP 备份与合并恢复（不含密钥） |
| 运行 | 每日调度、启动补查、任务状态、失败提示、调用次数/token 限额、手填单价费用估算 |

## 运行条件与当前边界

- **本地单用户应用**，尚未提供公网登录和多用户隔离，不应直接绑定公网。服务关闭或电脑休眠时不执行定时任务；重新启动会补查当天。
- arXiv 每方向每次最多 200 条，OpenAlex 最多 100 条；覆盖不足会在更新记录提示，建议细化方向。当前不保证全学科、全来源无遗漏。
- 规则分值是相对排序信号，不是论文质量概率。可选向量和 AI 在候选集上精筛；尚未训练学习排序模型。
- 经典清单是小规模、有证据的种子库。尚未自动爬取全网课程书单、综述或引用图来判定“经典”。
- **PDF 未包含可提取文字时提示需要 OCR**；不内置 OCR。公式、图片和复杂表格的完整理解未实现。正文解读只读取文本，超过上下文预算会标注各页节选。
- 阅读问答基于当前页及选文；全文解读单独生成。AI 页码是模型引用，应回到原文核对。换 PDF 后会清除旧解读，旧版本笔记保留并标注。
- 课程第一版是精选资源、用户导入和外部搜索入口；**未实现 B 站全站自动爬取或自动视频进度同步**。导航站中的外链课程费用需另行核验。
- Zotero 是手动导入/保存，**没有自动双向同步、删除联动或 Zotero 批注同步**。单次导入最多 2,000 条、集合列表最多 100 条。暂不支持群组库和 WebDAV 附件。
- API 预设可编辑，默认模型不代表所有账户都可调用；模型下线时换用平台仍支持的模型。接口密钥与聊天会员/编程套餐不可一概通用。
- 每日预算使用调用次数与 token 上限。输入以字符数保守预留、完成后记录服务商用量；超时可能实际计费，保留预留值。金额仅按用户提供的人民币单价估算，不是账单或严格人民币扣费上限。
- 普通备份排除密钥、用量和 AI 缓存。恢复按 ID 合并新记录，不覆盖当前同 ID 内容。换电脑需重新填密钥；直接复制整个 data 目录会连同密钥文件迁移，应保管好该目录。

## 安装与开发

需要 Python 3.11+（当前验证 3.13）以及 Node.js 20.19+。推荐 pnpm。

下载本仓库 ZIP 并解压，或执行：

```bash
git clone https://github.com/2513177689/papernest.git
cd papernest
```

Windows（在项目目录中运行；首次安装需要联网）：

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
.\.venv\Scripts\python.exe run.py --open
```

`setup.ps1` 创建 Python 虚拟环境、安装后端依赖并构建前端；可使用已安装的 pnpm 或 npm。后续启动无需重复安装。若终端提示找不到 `python` 或 `node`，安装相应运行环境并重新打开终端。

macOS / Linux（提供手动安装流程，当前版本主要在 Windows 验证）：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd frontend
pnpm install --frozen-lockfile
pnpm run build
cd ..
.venv/bin/python run.py
```

前端开发可在 `frontend` 中运行 `pnpm dev`，代理 API 到 8765。生产模式由 FastAPI 托管前端构建产物，无需同时启动 Vite。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q tests
# 运行中的本机应用浏览器检查（需要 Playwright + Chromium）
python scripts/ui_smoke.py
```

浏览器脚本用真实经典 PDF 验证选文、笔记、进度和窄屏布局，结束会清理测试方向与笔记；`smoke_sources.py` 获取真实元数据和 Transformer PDF。常规后端测试使用独立临时数据目录和模型接口模拟。

v0.1.0 开发验证包括 16 项后端测试、TypeScript 与生产构建、桌面/390px 浏览器交互以及真实论文来源获取。模型协议采用模拟接口测试；真实模型和 Zotero 调用效果取决于用户账户权限、服务可用性及所选模型。

## 数据位置与架构

```text
frontend/src/       React 界面、PDF 阅读器、模型设置
backend/app.py     HTTP API、调度、导入导出、备份恢复
backend/sources.py arXiv / OpenAlex / Crossref、去重、PDF 提取
backend/recommend.py 相关性排序与课程匹配
backend/ai.py      模型协议、缓存、预算、总结与向量
backend/zotero.py  文献库导入与导出
backend/catalog.py 模型预设、精选基础论文、免费课程
data/              本地数据库、附件和加密密钥（Git 忽略）
tests/             后端核心行为测试
```

可通过 `PAPERNEST_DATA` 环境变量指定独立数据目录。后台错误对用户显示可理解的提示；不将密钥返回前端。官方服务域名兼容本机 DNS 代理的 fake-IP 地址段；自定义服务与外部 PDF 地址仍做公网/本机范围检查。

第三方软件许可见各依赖；若将本项目分发或用于闭源产品，尤其应核对 PyMuPDF 的 AGPL/商业许可要求。

## 后续计划与反馈

计划逐步完善模型列表选择、经典论文证据库、推荐效果评估、OCR 和 Zotero 同步能力。这些是规划方向，不代表当前版本已经支持。

欢迎通过 GitHub Issues 提交问题或功能建议。请附操作步骤、预期结果及错误提示；不要提交 API Key、个人数据库或包含私人信息的截图。

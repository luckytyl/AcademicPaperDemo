# AcademicPaper Copilot

基于大语言模型的端到端学术论文写作助手，采用 Streamlit 构建，提供从选题到投稿的五步工作流。
直接在线体验：[AcademicPaper Copilot Demo](https://academicpaperdemo-pstq5anzvlthawjyuntdpj.streamlit.app/)

## 功能概览

| 步骤 | 功能 | 说明 |
|------|------|------|
| Step 1 研究选题 | 5W1H 分析 / Gap Analysis / SMART 研究问题 | 结构化拆解研究方向 |
| Step 2 文献调研 | 多源检索 / 引用验证 / BibTeX 导出 | 支持 OpenAlex、Semantic Scholar、arXiv |
| Step 3 论文撰写 | 大纲生成 / 逐章节撰写 | 自动继承选题和文献信息 |
| Step 4 润色翻译 | 中英互译 / 去 AI 痕迹 | 会议级英文输出 |
| Step 5 审稿投稿 | 自审检查 / Rebuttal 生成 / LaTeX 模板 | 支持 6 大顶级会议模板打包下载 |

## 核心特性

- **跨步骤数据继承**：各步骤自动传递上下文，选题→文献→大纲→润色→审稿无缝衔接
- **真实多源检索**：连接 OpenAlex（10K/天）、Semantic Scholar、arXiv 三个学术数据库
- **智能查询改写**：自动将中文研究方向改写为英文检索关键词，支持用户编辑确认
- **引用真实性验证**：四层验证策略（DOI → OpenAlex → arXiv → Semantic Scholar），检测 AI 编造引用
- **会议模板打包**：ICML 2026、ICLR 2026、NeurIPS 2025、ACL、AAAI 2026、COLM 2025

## 技术栈

- **前端**：Streamlit
- **LLM**：GLM-5 API（Anthropic 兼容格式）
- **检索源**：OpenAlex / Semantic Scholar / arXiv
- **语言**：Python 3.12+

## 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/luckytyl/AcademicPaperDemo.git
cd AcademicPaperDemo
pip install -r requirements.txt
```

### 2. 配置 API

复制 `.env.template` 为 `.env`，填入  API Token：

```bash
cp .env.template .env
```

```
ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic
ANTHROPIC_AUTH_TOKEN=your_token_here
ANTHROPIC_MODEL=
```

### 3. 启动

```bash
streamlit run app.py
```

浏览器打开 `http://localhost:8501` 即可使用。

## 项目结构

```
AcademicPaperDemo/
├── app.py                          # 主页入口
├── core/
│   ├── llm.py                      # GLM-5 API 封装
│   └── prompts.py                  # Prompt 模板
├── pages/
│   ├── 1_🎯_research_ideation.py   # Step 1: 研究选题
│   ├── 2_📚_literature_search.py   # Step 2: 文献调研
│   ├── 3_✍️_paper_drafting.py      # Step 3: 论文撰写
│   ├── 4_🔧_writing_polish.py      # Step 4: 润色翻译
│   └── 5_📋_review_submit.py       # Step 5: 审稿投稿
├── scripts/
│   ├── literature-search/lib/      # 多源论文检索引擎
│   └── citation-verifier/lib/      # 引用真实性验证引擎
└── assets/templates/               # 会议 LaTeX 模板
    ├── icml2026/
    ├── iclr2026/
    ├── neurips2025/
    ├── acl/
    ├── aaai2026/
    └── colm2025/
```

## 在线体验

访问部署地址直接体验：[AcademicPaper Copilot Demo](https://academicpaperdemo-pstq5anzvlthawjyuntdpj.streamlit.app/)

## License

MIT

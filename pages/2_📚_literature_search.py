import sys
import os
import streamlit as st
from core.llm import stream_glm
from core.prompts import LITERATURE_SUMMARY, QUERY_REWRITE

st.set_page_config(page_title="AcademicPaper Copilot", page_icon="🎓", layout="wide")

st.title("📚 Step 2: 文献调研")
st.markdown("搜索相关论文，验证引用，生成文献综述。")

# ── 动态导入搜索/验证模块（按序加载，避免 lib 包名冲突）──
scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")

_search_available = False
_verify_available = False
search_papers = None
papers_to_bibtex = None
verify_citations = None
filter_verified_bibtex = None


def _clean_lib_cache():
    """清除 sys.modules 中 lib 包的所有缓存，为下次加载腾位。"""
    for key in list(sys.modules.keys()):
        if key == "lib" or key.startswith("lib."):
            del sys.modules[key]


# 1) 加载 literature-search
_lit_dir = os.path.join(scripts_dir, "literature-search")
if os.path.isdir(_lit_dir):
    sys.path.insert(0, _lit_dir)
    try:
        from lib.search import search_papers, papers_to_bibtex
        _search_available = True
    except ImportError:
        pass
    finally:
        if _lit_dir in sys.path:
            sys.path.remove(_lit_dir)
        _clean_lib_cache()

# 2) 加载 citation-verifier
_cite_dir = os.path.join(scripts_dir, "citation-verifier")
if os.path.isdir(_cite_dir):
    sys.path.insert(0, _cite_dir)
    try:
        from lib.verify import verify_citations, filter_verified_bibtex
        _verify_available = True
    except ImportError:
        pass
    finally:
        if _cite_dir in sys.path:
            sys.path.remove(_cite_dir)
        _clean_lib_cache()

# ── 状态提示 ──
if _search_available and _verify_available:
    st.success("✅ 真实检索模式：已连接 OpenAlex / Semantic Scholar / arXiv 数据源 + 引用验证")
elif _search_available:
    st.success("✅ 真实检索模式：已连接多源论文搜索（引用验证模块未加载）")
elif _verify_available:
    st.warning("⚠️ 引用验证已就绪，但论文搜索模块未加载，将使用 LLM 推荐模式")
else:
    st.warning("⚠️ LLM 推荐模式：真实检索模块未加载，搜索结果为模型推荐，非数据库查询")


# ── 辅助函数：安全读取 Paper 属性 ──
def _get_paper_field(paper, field, default=""):
    """统一读取 Paper 对象或 dict 的字段"""
    val = getattr(paper, field, None)
    if val is None and isinstance(paper, dict):
        val = paper.get(field, default)
    return val if val is not None else default


def _format_authors(authors):
    """统一格式化作者列表"""
    if not authors:
        return "Unknown"
    if isinstance(authors, (list, tuple)):
        if not authors:
            return "Unknown"
        first = authors[0]
        if hasattr(first, "name"):
            # Author dataclass
            return ", ".join(a.name for a in authors[:3])
        elif isinstance(first, dict):
            return ", ".join(a.get("name", str(a)) for a in authors[:3])
        else:
            return ", ".join(str(a) for a in list(authors)[:3])
    return str(authors)


# ── 继承 Step 1 的选题 ──
inherited_topic = st.session_state.get("topic", "")
inherited_ideation = st.session_state.get("ideation_result", "")

if inherited_topic:
    st.info(f"📌 已继承 Step 1 选题：**{inherited_topic}**")

# ── 搜索区 ──
default_query = st.session_state.get("lit_query", inherited_topic)
query = st.text_input(
    "🔍 搜索关键词",
    value=default_query,
    placeholder="例如：time series anomaly detection",
)

search_col1, search_col2 = st.columns([1, 1])
with search_col1:
    num_results = st.slider("返回论文数", 5, 30, 10)
with search_col2:
    source = st.selectbox("搜索源", ["OpenAlex（推荐）", "Semantic Scholar", "arXiv"])

auto_rewrite = st.checkbox("🤖 自动改写关键词（中文题目 → 英文检索词）", value=True,
                           help="自动将中文研究方向改写为适合学术数据库检索的英文关键词")

# 搜索源映射
_source_map = {
    "OpenAlex（推荐）": ("openalex",),
    "Semantic Scholar": ("semantic_scholar",),
    "arXiv": ("arxiv",),
}

btn_search = st.button("🔎 搜索论文", type="primary", use_container_width=True)

# ── 第一步：关键词改写 ──
if btn_search and query:
    st.session_state["lit_query"] = query

    # 判断是否需要改写（含中文字符或超过5个词的长句）
    import re
    _has_chinese = bool(re.search(r'[\u4e00-\u9fff]', query))
    _need_rewrite = auto_rewrite and (_has_chinese or len(query.split()) > 5)

    if not _search_available:
        # 搜索模块不可用，直接 LLM fallback
        st.warning("搜索模块未找到，使用 LLM 直接生成文献推荐")
        try:
            result = st.write_stream(stream_glm(
                "你是学术文献搜索助手，根据关键词推荐相关的重要论文。"
                "列出论文标题、作者、年份、会议/期刊、主要贡献。"
                "只推荐你确信真实存在的论文。",
                f"搜索关键词：{query}\n推荐 {num_results} 篇最重要的相关论文。",
            ))
            st.session_state["lit_summary"] = result
            st.session_state["step2_done"] = True
        except Exception:
            st.error("搜索模块和 LLM 均不可用，请检查网络或 API 配置。")
        st.stop()

    if _need_rewrite:
        with st.spinner("正在改写检索关键词..."):
            try:
                from core.llm import call_glm
                rewrite_result = call_glm(QUERY_REWRITE, query, max_tokens=256)
                rewritten_lines = [q.strip() for q in rewrite_result.strip().split("\n") if q.strip()]
                if rewritten_lines:
                    st.session_state["rewritten_queries"] = "\n".join(rewritten_lines)
                    st.session_state["rewrite_ready"] = True
                    st.rerun()
                else:
                    st.session_state["rewrite_ready"] = False
            except Exception:
                st.session_state["rewrite_ready"] = False
    else:
        st.session_state["final_queries"] = [query]
        st.session_state.pop("rewrite_ready", None)
        st.session_state.pop("rewritten_queries", None)

# ── 改写结果编辑区 ──
if st.session_state.get("rewrite_ready"):
    st.markdown("#### 🔄 已自动改写检索词")
    st.markdown("以下关键词由 AI 根据你的研究方向生成，**可直接修改后再搜索**：")
    edited_queries = st.text_area(
        "检索关键词（每行一个，可编辑/删除/添加）",
        value=st.session_state.get("rewritten_queries", query),
        height=120,
        key="rewritten_queries_editor",
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("✅ 确认并搜索", type="primary", use_container_width=True):
            final_qs = [q.strip() for q in edited_queries.strip().split("\n") if q.strip()]
            st.session_state["final_queries"] = final_qs or [query]
            st.session_state.pop("rewrite_ready", None)
            st.rerun()
    with col_b:
        if st.button("❌ 跳过，用原始关键词搜索", use_container_width=True):
            st.session_state["final_queries"] = [query]
            st.session_state.pop("rewrite_ready", None)
            st.rerun()

# ── 第二步：执行搜索 ──
if st.session_state.get("final_queries"):
    final_queries = st.session_state.pop("final_queries")
    sources = _source_map.get(source)

    if len(final_queries) > 1:
        st.info(f"🔍 将用 {len(final_queries)} 个关键词分别搜索：{', '.join(final_queries)}")

    all_papers = []
    seen_ids = set()
    per_query_limit = max(num_results // len(final_queries), 5)

    for q in final_queries:
        try:
            with st.spinner(f"正在检索: {q}..."):
                batch = search_papers(q, limit=per_query_limit, sources=sources)
            for p in batch:
                pid = _get_paper_field(p, "doi", None) or _get_paper_field(p, "arxiv_id", None) or _get_paper_field(p, "title", "")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_papers.append(p)
        except Exception:
            continue

    papers = all_papers[:num_results]
    if not papers:
        st.warning("未找到相关论文，请尝试其他关键词")
        st.stop()

    try:
        # 显示结果
        st.markdown(f"### 📄 找到 {len(papers)} 篇相关论文")

        paper_titles = []
        for i, paper in enumerate(papers, 1):
            title = _get_paper_field(paper, "title", "Unknown")
            year = _get_paper_field(paper, "year", "N/A")
            authors = _get_paper_field(paper, "authors", [])
            citations = _get_paper_field(paper, "citation_count", "N/A")
            doi = _get_paper_field(paper, "doi", "")

            paper_titles.append(f"{title} ({year})")
            authors_str = _format_authors(authors)

            with st.expander(f"**{i}. {title}** ({year}) - 引用数: {citations}"):
                st.markdown(f"**作者**: {authors_str}")
                if doi:
                    st.markdown(f"**DOI**: `{doi}`")

        # 保存到 session
        st.session_state["papers"] = papers
        st.session_state["paper_titles"] = paper_titles
        st.session_state["step2_done"] = True

    except Exception as e:
        st.error(f"搜索出错: {e}")
        st.info("尝试使用 LLM 直接生成文献推荐...")
        try:
            result = st.write_stream(stream_glm(
                "你是学术文献搜索助手，根据关键词推荐相关的重要论文。"
                "列出论文标题、作者、年份、会议/期刊、主要贡献。"
                "只推荐你确信真实存在的论文。",
                f"搜索关键词：{query}\n推荐 {num_results} 篇最重要的相关论文。",
            ))
            st.session_state["lit_summary"] = result
            st.session_state["step2_done"] = True
        except Exception:
            st.error("搜索和 LLM 均不可用，请检查网络或 API 配置。")

# ── 文献总结 ──
st.markdown("---")
st.markdown("### 📝 文献总结")
btn_summary = st.button("📊 生成文献综述", use_container_width=True)

if btn_summary:
    papers_info = st.session_state.get("papers", [])
    if not papers_info and not query:
        st.warning("请先搜索论文或输入关键词")
    else:
        context = f"搜索关键词：{query}\n"
        if inherited_ideation:
            context += f"\n研究选题背景：{inherited_ideation}\n"
        if papers_info:
            for p in papers_info[:10]:
                title = _get_paper_field(p, "title", "")
                year = _get_paper_field(p, "year", "")
                context += f"- {title} ({year})\n"

        result = st.write_stream(stream_glm(LITERATURE_SUMMARY, context))
        st.session_state["lit_summary"] = result
        st.session_state["step2_done"] = True

# ── BibTeX 导出 ──
st.markdown("---")
btn_bib = st.button("📦 导出 BibTeX")
if btn_bib:
    papers_info = st.session_state.get("papers", [])
    if papers_info:
        if _search_available:
            try:
                bib_text = papers_to_bibtex(papers_info)
                st.code(bib_text, language="bibtex")
                st.download_button("💾 下载 references.bib", bib_text, "references.bib", "text/plain")
            except Exception as e:
                st.error(f"BibTeX 生成出错: {e}")
        else:
            st.info("BibTeX 导出需要搜索模块支持")
    else:
        st.warning("请先搜索论文")

# ── 引用验证 ──
st.markdown("---")
st.markdown("### 🔍 引用验证")
st.markdown("粘贴 BibTeX 内容，验证引用是否真实存在，检测 AI 编造引用。")

bib_input = st.text_area(
    "📝 BibTeX 内容",
    placeholder="粘贴你的 BibTeX 引用列表...",
    height=150,
    key="bib_verify_input",
)

btn_verify = st.button("🔍 验证引用", use_container_width=True)
if btn_verify:
    if not bib_input.strip():
        st.warning("请粘贴 BibTeX 内容")
    elif not _verify_available:
        st.warning("引用验证模块未找到")
    else:
        with st.spinner("正在验证引用（可能需要几分钟）..."):
            try:
                report = verify_citations(bib_input)
                # 摘要
                st.markdown(f"**验证完成！** 完整性评分: **{report.integrity_score:.1%}**")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("已验证", report.verified)
                col2.metric("可疑", report.suspicious)
                col3.metric("编造", report.hallucinated)
                col4.metric("跳过", report.skipped)

                # 详细结果
                for r in report.results:
                    color = {"VERIFIED": "🟢", "SUSPICIOUS": "🟡", "HALLUCINATED": "🔴", "SKIPPED": "⚪"}
                    icon = color.get(r.status.name, "⚪")
                    with st.expander(f"{icon} {r.cite_key} — {r.status.name} ({r.confidence:.0%})"):
                        st.markdown(f"**标题**: {r.title}")
                        st.markdown(f"**验证方式**: {r.method}")
                        st.markdown(f"**详情**: {r.details}")

                # 导出过滤后的 BibTeX
                if report.hallucinated > 0:
                    clean_bib = filter_verified_bibtex(bib_input, report)
                    st.markdown("### 📦 过滤后的 BibTeX（去除编造引用）")
                    st.download_button("💾 下载清洗后的 references.bib", clean_bib, "references_clean.bib", "text/plain")
            except Exception as e:
                st.error(f"引用验证出错: {e}")

# ── 底部 ──
st.markdown("---")
if st.session_state.get("step2_done"):
    st.markdown("✅ **文献调研完成！** 点击左侧 **✍️ 论文撰写** 进入下一步，选题和文献信息会自动带入。")
else:
    st.markdown("💡 搜索结果和文献综述会自动传递给后续步骤。")

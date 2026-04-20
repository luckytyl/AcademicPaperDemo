import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="AcademicPaper Copilot",
    page_icon="🎓",
    layout="wide",
)

# ═══════════════════════════════════════════
# 全局 CSS
# ═══════════════════════════════════════════
st.markdown(
    """
    <style>
    /* ── 背景渐变 ── */
    .stApp {
        background:
            radial-gradient(circle at 0% 0%, rgba(195, 90, 28, 0.14), transparent 24%),
            radial-gradient(circle at 100% 0%, rgba(22, 122, 90, 0.12), transparent 26%),
            linear-gradient(180deg, #F7F1E7 0%, #F3EEE8 48%, #F8F4EC 100%);
    }

    /* ── 侧边栏深色 ── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #10261B 0%, #173326 100%) !important;
    }
    [data-testid="stSidebar"] * {
        color: #F1F7F3 !important;
    }
    [data-testid="stSidebar"] .stMarkdown hr {
        border-color: rgba(255,255,255,0.15) !important;
    }
    [data-testid="stSidebar"] a {
        color: #8FD4B5 !important;
    }

    /* ── 按钮圆角 ── */
    .stButton > button {
        border-radius: 999px !important;
        font-weight: 600 !important;
        transition: transform 120ms ease, box-shadow 120ms ease;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 8px 20px rgba(20, 86, 58, 0.18);
    }

    /* ── 输入框圆角 ── */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        border-radius: 14px !important;
        border: 1px solid rgba(16, 38, 27, 0.1) !important;
        background: rgba(255, 255, 255, 0.6) !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: rgba(28, 124, 84, 0.3) !important;
        box-shadow: 0 0 0 2px rgba(28, 124, 84, 0.1) !important;
    }

    /* ── Radio / Selectbox 圆角 ── */
    .stRadio > div {
        gap: 0.5rem;
    }

    /* ── Expander 圆角 ── */
    .streamlit-expanderHeader {
        border-radius: 12px !important;
    }

    /* ── 去掉顶部白条 ── */
    header[data-testid="stHeader"] {
        background: transparent !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════
# 侧边栏
# ═══════════════════════════════════════════
with st.sidebar:
    st.markdown(
        """
        <div style='text-align:center; padding: 0.5rem 0;'>
            <div style='font-size: 2rem;'>🎓</div>
            <div style='font-size: 1.1rem; font-weight: 700; color: #F1F7F3;'>AcademicPaper</div>
            <div style='font-size: 0.85rem; color: #8FD4B5;'>Copilot</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("#### 📌 写作进度")
    steps = [
        ("🎯", "研究选题", "research_ideation"),
        ("📚", "文献调研", "literature_search"),
        ("✍️", "论文撰写", "paper_drafting"),
        ("🔧", "润色翻译", "writing_polish"),
        ("📋", "审稿投稿", "review_submit"),
    ]
    for i, (icon, name, key) in enumerate(steps, 1):
        done = st.session_state.get(f"step{i}_done", False)
        status = "✅" if done else "⬜"
        st.markdown(f"{status} {icon} {name}")

    st.markdown("---")
    st.markdown(
        "<div style='text-align:center; color: rgba(255,255,255,0.4); font-size: 0.8rem;'>"
        "Powered by GLM-5 | <a href='https://github.com/luckytyl' style='color:#8FD4B5;'>GitHub</a>"
        "</div>",
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════
# 主页 Hero
# ═══════════════════════════════════════════
st.markdown(
    """
    <div style='
        background: rgba(255, 251, 244, 0.85);
        border: 1px solid rgba(16, 38, 27, 0.06);
        border-radius: 28px;
        padding: 2.5rem 2rem 2rem 2rem;
        box-shadow: 0 24px 70px rgba(24, 37, 31, 0.06);
        text-align: center;
        margin-bottom: 2rem;
    '>
        <div style='font-size: 2.6rem; font-weight: 700; letter-spacing: -0.03em; color: #10261B;'>
            🎓 AcademicPaper Copilot
        </div>
        <div style='font-size: 1.1rem; color: #5f6f62; margin-top: 0.5rem; line-height: 1.6;'>
            基于 LLM 的端到端学术论文写作助手<br>
            <span style='font-size: 0.9rem; color: #8a9a8e;'>从选题到投稿，五步完成你的论文</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── 统计卡片 ──
st.markdown(
    """
    <div style='display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 2rem;'>
        <div style='
            background: rgba(255,251,244,0.88);
            border: 1px solid rgba(16,38,27,0.06);
            border-radius: 18px;
            padding: 1.2rem;
            text-align: center;
        '>
            <div style='font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.12em; color: #d9722e; font-weight: 600;'>Workflow</div>
            <div style='font-size: 1.4rem; font-weight: 700; color: #10261B; margin-top: 0.3rem;'>5 个阶段</div>
        </div>
        <div style='
            background: rgba(255,251,244,0.88);
            border: 1px solid rgba(16,38,27,0.06);
            border-radius: 18px;
            padding: 1.2rem;
            text-align: center;
        '>
            <div style='font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.12em; color: #d9722e; font-weight: 600;'>Model</div>
            <div style='font-size: 1.4rem; font-weight: 700; color: #10261B; margin-top: 0.3rem;'>GLM-5</div>
        </div>
        <div style='
            background: rgba(255,251,244,0.88);
            border: 1px solid rgba(16,38,27,0.06);
            border-radius: 18px;
            padding: 1.2rem;
            text-align: center;
        '>
            <div style='font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.12em; color: #d9722e; font-weight: 600;'>Search</div>
            <div style='font-size: 1.4rem; font-weight: 700; color: #10261B; margin-top: 0.3rem;'>3 个数据源</div>
        </div>
        <div style='
            background: rgba(255,251,244,0.88);
            border: 1px solid rgba(16,38,27,0.06);
            border-radius: 18px;
            padding: 1.2rem;
            text-align: center;
        '>
            <div style='font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.12em; color: #d9722e; font-weight: 600;'>Templates</div>
            <div style='font-size: 1.4rem; font-weight: 700; color: #10261B; margin-top: 0.3rem;'>6 个会议</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── 五步流程卡片 ──
st.markdown(
    "<div style='font-size: 1.25rem; font-weight: 700; color: #10261B; margin-bottom: 0.8rem;'>"
    "🚀 五步完成你的论文"
    "</div>",
    unsafe_allow_html=True,
)

step_data = [
    ("🎯", "研究选题", "5W1H 分析", "Gap 分析", "SMART 研究问题"),
    ("📚", "文献调研", "多源论文搜索", "引用验证", "BibTeX 导出"),
    ("✍️", "论文撰写", "生成论文大纲", "逐章节撰写", "实验结果分析"),
    ("🔧", "润色翻译", "中英互译", "去 AI 味", "篇幅调整"),
    ("📋", "审稿投稿", "自审检查", "Rebuttal 模板", "LaTeX 打包"),
]

cards_html = "<div style='display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px;'>"
for icon, title, f1, f2, f3 in step_data:
    cards_html += f"""
    <div style='
        background: linear-gradient(165deg, #183A2A 0%, #244835 100%);
        color: white;
        border-radius: 22px;
        padding: 1.4rem 1rem;
        text-align: center;
        min-height: 180px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    '>
        <div style='font-size: 1.8rem; margin-bottom: 0.5rem;'>{icon}</div>
        <div style='font-size: 1.05rem; font-weight: 700; margin-bottom: 0.6rem;'>{title}</div>
        <div style='font-size: 0.82rem; color: #b8d4c6; line-height: 1.6;'>{f1}<br>{f2}<br>{f3}</div>
    </div>
    """
cards_html += "</div>"
components.html(cards_html, height=220)

# ── 底部提示 ──
st.markdown(
    """
    <div style='
        background: rgba(255,251,244,0.7);
        border: 1px solid rgba(16,38,27,0.06);
        border-radius: 18px;
        padding: 1.2rem 1.5rem;
        margin-top: 2rem;
        text-align: center;
        color: #5f6f62;
        font-size: 0.9rem;
        line-height: 1.6;
    '>
        👈 在左侧导航栏选择步骤，开始你的论文写作之旅<br>
        <span style='font-size: 0.8rem; color: #8a9a8e;'>
            技术栈：Streamlit + GLM-5 API | 支持 OpenAlex / Semantic Scholar / arXiv 多源检索
        </span>
    </div>
    """,
    unsafe_allow_html=True,
)

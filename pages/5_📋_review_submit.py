import os
import io
import zipfile
import streamlit as st
from core.llm import stream_glm
from core.prompts import REVIEW_SELF, REVIEW_REBUTTAL

st.set_page_config(page_title="AcademicPaper Copilot", page_icon="🎓", layout="wide")

st.title("📋 Step 5: 审稿投稿")
st.markdown("论文自审检查、生成 Rebuttal、选择 LaTeX 模板。")

# ── 继承前序数据 ──
inherited_topic = st.session_state.get("topic", "")
drafted = st.session_state.get("drafted_sections", "")
polished = st.session_state.get("polished_text", "")
review_default = st.session_state.get("review_input", "") or polished or drafted

tab1, tab2, tab3 = st.tabs(["🔍 自审检查", "💬 Rebuttal 生成", "📄 LaTeX 模板"])

# ── Tab 1: 自审检查 ──
with tab1:
    if inherited_topic:
        st.info(f"📌 论文主题：**{inherited_topic}**")

    if "review_paper" not in st.session_state:
        st.session_state["review_paper"] = review_default
    if not st.session_state.get("review_paper") and review_default:
        st.session_state["review_paper"] = review_default

    # 让用户主动同步最新上游数据
    current_review = st.session_state.get("review_paper", "")
    if review_default and review_default != current_review:
        if st.button("🔄 同步上游最新内容", use_container_width=True):
            st.session_state["review_paper"] = review_default
            st.rerun()

    paper_text = st.text_area(
        "📝 论文全文或章节（已自动填入前序步骤内容）",
        height=300,
        key="review_paper",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        checklist_type = st.selectbox(
            "审稿标准",
            ["通用检查", "NeurIPS", "ICML", "ICLR", "ACL"],
        )
    with col_b:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_review = st.button("🔍 开始自审", type="primary", use_container_width=True)

    if btn_review:
        if not paper_text.strip():
            st.warning("请粘贴论文内容")
        else:
            context = f"论文内容：\n{paper_text}\n\n审稿标准：{checklist_type}"
            st.markdown("### 🔍 自审报告")
            try:
                st.write_stream(stream_glm(REVIEW_SELF, context))
                st.session_state["step5_done"] = True
            except Exception as e:
                st.error(f"模型调用失败，请检查 API 配置：{e}")

# ── Tab 2: Rebuttal ──
with tab2:
    reviewer_comments = st.text_area(
        "📝 审稿人意见",
        placeholder=(
            "粘贴审稿人的意见，例如：\n\n"
            "Reviewer 1:\n"
            "1. (Major) The paper lacks comparison with XXX baseline.\n"
            "2. (Minor) Figure 2 is not clear enough.\n\n"
            "Reviewer 2:\n"
            "1. (Major) The novelty is limited compared to XXX.\n"
        ),
        height=250,
        key="rebuttal_comments",
    )

    # 自动继承论文内容
    rebuttal_paper_default = ""
    if inherited_topic:
        rebuttal_paper_default += f"主题：{inherited_topic}\n"
    if paper_text:
        rebuttal_paper_default += paper_text[:1000]

    paper_for_rebuttal = st.text_area(
        "📎 论文摘要（已自动填入，帮助生成更准确的回复）",
        value=rebuttal_paper_default,
        height=100,
        key="rebuttal_paper",
    )

    if st.button("💬 生成 Rebuttal", type="primary", use_container_width=True):
        if not reviewer_comments.strip():
            st.warning("请粘贴审稿人意见")
        else:
            context = f"审稿人意见：\n{reviewer_comments}\n"
            if paper_for_rebuttal:
                context += f"\n论文摘要：\n{paper_for_rebuttal}\n"
            st.markdown("### 💬 Rebuttal 回复")
            try:
                st.write_stream(stream_glm(REVIEW_REBUTTAL, context))
                st.session_state["step5_done"] = True
            except Exception as e:
                st.error(f"模型调用失败，请检查 API 配置：{e}")

# ── Tab 3: LaTeX 模板 ──
with tab3:
    st.markdown("### 📄 会议 LaTeX 模板")
    st.markdown("选择目标会议，下载对应的 LaTeX 模板。")

    templates_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "assets", "templates"
    )

    venue_info = {
        "ICML 2026": {"folder": "icml2026", "pages": "8+1"},
        "ICLR 2026": {"folder": "iclr2026", "pages": "9+1"},
        "NeurIPS 2025": {"folder": "neurips2025", "pages": "9"},
        "ACL": {"folder": "acl", "pages": "8"},
        "AAAI 2026": {"folder": "aaai2026", "pages": "7+1"},
        "COLM 2025": {"folder": "colm2025", "pages": "9+1"},
    }

    cols = st.columns(3)
    for i, (venue, info) in enumerate(venue_info.items()):
        with cols[i % 3]:
            folder_path = os.path.join(templates_dir, info["folder"])
            if os.path.exists(folder_path):
                files = os.listdir(folder_path)
                tex_files = [f for f in files if f.endswith(".tex")]
                st.markdown(
                    f"""
                    <div style='
                        background: #f8f9fa;
                        border-radius: 8px;
                        padding: 1rem;
                        border: 1px solid #e0e0e0;
                        margin-bottom: 0.5rem;
                    '>
                        <b>{venue}</b><br>
                        <small>页数限制: {info['pages']}页 | 文件数: {len(files)}</small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if tex_files:
                    # 打包整个模板目录为 zip
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        for fname in files:
                            fpath = os.path.join(folder_path, fname)
                            if os.path.isfile(fpath):
                                zf.write(fpath, arcname=os.path.join(info["folder"], fname))
                    buf.seek(0)
                    st.download_button(
                        f"📥 下载 {venue} 模板包",
                        buf,
                        f"{info['folder']}.zip",
                        "application/zip",
                        key=f"dl_{info['folder']}",
                        use_container_width=True,
                    )

st.markdown("---")
if st.session_state.get("step5_done"):
    st.markdown("🎉 **恭喜！你已完成所有步骤。** 论文写作流程结束。")
else:
    st.markdown("💡 完成自审或 Rebuttal 生成后，即可结束论文写作流程。")

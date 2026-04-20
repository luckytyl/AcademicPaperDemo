import streamlit as st
from core.llm import stream_glm
from core.prompts import DRAFT_OUTLINE, DRAFT_SECTION

st.set_page_config(page_title="AcademicPaper Copilot", page_icon="🎓", layout="wide")

st.title("✍️ Step 3: 论文撰写")
st.markdown("从研究笔记生成论文大纲，再逐章节撰写内容。")

# ── 继承前序步骤数据 ──
inherited_topic = st.session_state.get("topic", "")
inherited_ideation = st.session_state.get("ideation_result", "")
inherited_questions = st.session_state.get("research_questions", "")
inherited_lit = st.session_state.get("lit_summary", "")
inherited_titles = st.session_state.get("paper_titles", [])

if inherited_topic:
    st.info(f"📌 已继承选题：**{inherited_topic}**")
if inherited_lit:
    with st.expander("📚 已继承的文献综述（点击展开）"):
        st.markdown(inherited_lit)
if inherited_titles:
    with st.expander("📖 已找到的相关论文"):
        for t in inherited_titles:
            st.markdown(f"- {t}")

# ── 模式选择 ──
mode = st.radio("选择模式", ["📋 生成论文大纲", "📝 撰写章节内容"], horizontal=True)

if mode == "📋 生成论文大纲":
    st.markdown("### 📋 生成论文大纲")
    st.markdown("输入你的研究内容（实验结果、方法描述、研究笔记等），生成完整大纲。")

    # 自动组合前序数据作为默认内容
    default_content = ""
    if inherited_ideation:
        default_content += f"选题方向：{inherited_ideation}\n\n"
    if inherited_questions:
        default_content += f"研究问题：\n{inherited_questions}\n\n"
    if inherited_lit:
        default_content += f"文献综述摘要：\n{inherited_lit[:500]}...\n"
    # 自动消费 Step 2 的搜索结果（即使没点"生成文献综述"也能利用论文信息）
    if inherited_titles and not inherited_lit:
        default_content += f"已找到的相关论文：\n"
        for t in inherited_titles[:10]:
            default_content += f"- {t}\n"
        default_content += "\n"

    research_content = st.text_area(
        "📝 研究内容（已自动填入前序步骤数据，可自由修改）",
        value=st.session_state.get("research_content_draft", default_content),
        height=250,
    )

    if st.button("🚀 生成大纲", type="primary", use_container_width=True):
        if not research_content.strip():
            st.warning("请输入研究内容")
        else:
            context = research_content
            if inherited_lit:
                context += f"\n\n相关文献：\n{inherited_lit}"
            elif inherited_titles:
                context += "\n\n已找到的相关论文：\n"
                for t in inherited_titles[:10]:
                    context += f"- {t}\n"

            st.markdown("### 📋 论文大纲")
            try:
                result = st.write_stream(stream_glm(DRAFT_OUTLINE, context))
                st.session_state["outline"] = result
                st.session_state["research_content_draft"] = research_content
                st.session_state["step3_done"] = True
            except Exception as e:
                st.error(f"模型调用失败，请检查 API 配置：{e}")

elif mode == "📝 撰写章节内容":
    st.markdown("### 📝 撰写章节")
    st.markdown("选择要撰写的章节，基于大纲生成内容。")

    # 大纲展示
    outline = st.session_state.get("outline", "")
    if outline:
        with st.expander("📋 当前大纲（点击展开）"):
            st.markdown(outline)
    else:
        st.warning("⚠️ 还没有生成大纲，建议先在「生成论文大纲」模式中生成。")

    section_name = st.text_input(
        "📖 要撰写的章节",
        placeholder="例如：3.2 整体框架",
    )

    additional_context = st.text_area(
        "📎 补充材料（可选）",
        placeholder="粘贴相关的实验数据、公式推导、代码片段等...",
        height=150,
    )

    if st.button("✍️ 生成章节", type="primary", use_container_width=True):
        if not section_name:
            st.warning("请输入要撰写的章节名称")
        else:
            context = f"章节：{section_name}\n"
            if inherited_topic:
                context += f"\n论文主题：{inherited_topic}\n"
            if outline:
                context += f"\n论文大纲：\n{outline}\n"
            if inherited_lit:
                context += f"\n相关文献：\n{inherited_lit[:800]}\n"
            if additional_context:
                context += f"\n补充材料：\n{additional_context}\n"

            st.markdown(f"### {section_name}")
            try:
                result = st.write_stream(stream_glm(DRAFT_SECTION, context))
                existing = st.session_state.get("drafted_sections", "")
                st.session_state["drafted_sections"] = existing + f"\n\n## {section_name}\n{result}"
                st.session_state["step3_done"] = True
            except Exception as e:
                st.error(f"模型调用失败，请检查 API 配置：{e}")

# ── 已生成章节一览 ──
drafted = st.session_state.get("drafted_sections", "")
if drafted:
    st.markdown("---")
    st.markdown("### 📑 已生成的章节")
    with st.expander("点击展开查看所有已生成内容"):
        st.markdown(drafted)
    if st.button("📋 复制全部内容到 Step 4 润色"):
        st.session_state["polish_input"] = drafted
        st.success("✅ 已保存！前往 Step 4 即可自动填入。")

# ── 底部 ──
st.markdown("---")
if st.session_state.get("step3_done"):
    st.markdown("✅ **撰写完成！** 点击左侧 **🔧 润色翻译** 进入下一步。")
else:
    st.markdown("💡 生成的大纲和章节内容会自动传递给后续步骤。")

import streamlit as st
from core.llm import stream_glm
from core.prompts import WRITING_ZH2EN, WRITING_EN2ZH, WRITING_ANTI_AI

st.set_page_config(page_title="AcademicPaper Copilot", page_icon="🎓", layout="wide")

st.title("🔧 Step 4: 润色翻译")
st.markdown("翻译论文段落、去除 AI 写作痕迹、调整篇幅。")

# ── 继承前序数据 ──
inherited_topic = st.session_state.get("topic", "")
drafted = st.session_state.get("drafted_sections", "")
polish_from_step3 = st.session_state.get("polish_input", "")

if drafted:
    st.info(f"📌 已继承 Step 3 生成的论文内容（共 {len(drafted)} 字符）")

# ── 模式选择 ──
mode = st.radio(
    "选择功能",
    ["🇨🇳→🇬🇧 中译英", "🇬🇧→🇨🇳 英译中", "🤖 去 AI 味"],
    horizontal=True,
)

# 自动填入从 Step 3 传来的内容
default_text = polish_from_step3 or drafted or ""

# 初始化或同步上游数据
if "polish_text_area" not in st.session_state:
    st.session_state["polish_text_area"] = default_text
elif not st.session_state.get("polish_text_area") and default_text:
    st.session_state["polish_text_area"] = default_text

# 让用户主动同步最新上游数据
upstream_text = polish_from_step3 or drafted or ""
current_text = st.session_state.get("polish_text_area", "")
if upstream_text and upstream_text != current_text:
    if st.button("🔄 同步 Step 3 最新内容", use_container_width=True):
        st.session_state["polish_text_area"] = upstream_text
        st.rerun()

text_input = st.text_area(
    "📝 输入文本（已自动填入前序步骤内容，可自由修改）",
    key="polish_text_area",
    height=250,
)

if mode == "🇨🇳→🇬🇧 中译英":
    if st.button("🔄 翻译为英文", type="primary", use_container_width=True):
        if not text_input.strip():
            st.warning("请输入中文文本")
        else:
            st.markdown("### 📤 翻译结果")
            result = st.write_stream(stream_glm(WRITING_ZH2EN, text_input))
            st.session_state["step4_done"] = True
            st.session_state["polished_text"] = result

elif mode == "🇬🇧→🇨🇳 英译中":
    if st.button("🔄 翻译为中文", type="primary", use_container_width=True):
        if not text_input.strip():
            st.warning("请输入英文文本")
        else:
            st.markdown("### 📤 翻译结果")
            result = st.write_stream(stream_glm(WRITING_EN2ZH, text_input))
            st.session_state["step4_done"] = True
            st.session_state["polished_text"] = result

elif mode == "🤖 去 AI 味":
    col_left, col_right = st.columns(2)
    with col_left:
        if st.button("🔍 分析 AI 痕迹", use_container_width=True):
            if not text_input.strip():
                st.warning("请输入文本")
            else:
                analysis_prompt = """分析以下文本中的 AI 写作痕迹。

列出：
1. 🔴 明显的 AI 特征（如 "crucial", "pivotal", "It is worth noting" 等）
2. 🟡 可能的 AI 特征（如三连句式、破折号过多等）
3. 🟢 自然的表达

给出具体的文本片段和修改建议。"""
                st.markdown("### 🔍 AI 痕迹分析")
                st.write_stream(stream_glm(analysis_prompt, text_input))

    with col_right:
        if st.button("✨ 去除 AI 味", type="primary", use_container_width=True):
            if not text_input.strip():
                st.warning("请输入文本")
            else:
                st.markdown("### ✨ 修改后文本")
                result = st.write_stream(stream_glm(WRITING_ANTI_AI, text_input))
                st.session_state["step4_done"] = True
                st.session_state["polished_text"] = result

# ── 底部 ──
st.markdown("---")
if st.session_state.get("step4_done"):
    st.markdown("✅ **润色完成！** 点击左侧 **📋 审稿投稿** 进入下一步。")
    if st.button("📋 将润色后的内容传递给 Step 5"):
        polished = st.session_state.get("polished_text", "")
        if polished:
            st.session_state["review_input"] = polished
            st.success("✅ 已保存！前往 Step 5 即可自动填入。")
else:
    st.markdown("💡 润色结果会自动传递给 Step 5 审稿投稿。")

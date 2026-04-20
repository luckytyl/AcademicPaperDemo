import streamlit as st
from core.llm import stream_glm
from core.prompts import IDEATION_5W1H, IDEATION_GAP, IDEATION_QUESTION

st.set_page_config(page_title="AcademicPaper Copilot", page_icon="🎓", layout="wide")

st.title("🎯 Step 1: 研究选题")
st.markdown("输入你的研究方向，使用 5W1H / Gap Analysis / 研究问题生成工具进行选题分析。")

# ── 顶部：继承上下文展示 ──
if "ideation_result" in st.session_state:
    st.success("✅ 已有选题数据，可继续深化分析或直接前往 Step 2")

# ── 输入区 ──
default_topic = st.session_state.get("topic", "")
topic = st.text_area(
    "📝 研究方向",
    value=default_topic,
    placeholder="例如：基于大语言模型的时序异常检测方法选择",
    height=100,
)

col1, col2, col3 = st.columns(3)

with col1:
    btn_5w1h = st.button("🔍 5W1H 分析", use_container_width=True, type="primary")
with col2:
    btn_gap = st.button("🕳️ Gap Analysis", use_container_width=True)
with col3:
    btn_question = st.button("❓ 生成研究问题", use_container_width=True)

# ── 约束输入 ──
with st.expander("⚙️ 补充约束（可选）"):
    domain = st.text_input("研究领域", placeholder="如：NLP, CV, 时序分析")
    data = st.text_input("可用数据", placeholder="如：公开 benchmark，自采数据")
    timeline = st.text_input("时间线", placeholder="如：6个月")
    venue = st.text_input("目标会议/期刊", placeholder="如：NeurIPS, ACL")

# ── 处理逻辑 ──
if not topic:
    st.info("👈 请先输入研究方向")
    st.stop()

# 保存 topic 供后续步骤使用
st.session_state["topic"] = topic

constraints = ""
if domain:
    constraints += f"\n研究领域：{domain}"
if data:
    constraints += f"\n可用数据：{data}"
if timeline:
    constraints += f"\n时间线：{timeline}"
if venue:
    constraints += f"\n目标会议/期刊：{venue}"

user_msg = f"研究方向：{topic}{constraints}"

if btn_5w1h:
    st.markdown("### 📊 5W1H 分析结果")
    try:
        result = st.write_stream(stream_glm(IDEATION_5W1H, user_msg))
        st.session_state["ideation_result"] = user_msg
        st.session_state["ideation_5w1h"] = result
        st.session_state["step1_done"] = True
    except Exception as e:
        st.error(f"模型调用失败，请检查 API 配置：{e}")

elif btn_gap:
    st.markdown("### 🕳️ Gap Analysis 结果")
    try:
        result = st.write_stream(stream_glm(IDEATION_GAP, user_msg))
        st.session_state["ideation_result"] = user_msg
        st.session_state["ideation_gap"] = result
        st.session_state["step1_done"] = True
    except Exception as e:
        st.error(f"模型调用失败，请检查 API 配置：{e}")

elif btn_question:
    context = user_msg
    if "ideation_5w1h" in st.session_state:
        context += f"\n\n之前的 5W1H 分析：{st.session_state['ideation_5w1h']}"
    if "ideation_gap" in st.session_state:
        context += f"\n\n之前的 Gap Analysis：{st.session_state['ideation_gap']}"
    st.markdown("### ❓ SMART 研究问题")
    try:
        result = st.write_stream(stream_glm(IDEATION_QUESTION, context))
        st.session_state["research_questions"] = result
        st.session_state["ideation_result"] = user_msg
        st.session_state["step1_done"] = True
    except Exception as e:
        st.error(f"模型调用失败，请检查 API 配置：{e}")

# ── 历史结果展示 ──
if "ideation_5w1h" in st.session_state:
    with st.expander("📊 历次 5W1H 分析结果", expanded=False):
        st.markdown(st.session_state["ideation_5w1h"])
if "ideation_gap" in st.session_state:
    with st.expander("🕳️ 历次 Gap Analysis 结果", expanded=False):
        st.markdown(st.session_state["ideation_gap"])
if "research_questions" in st.session_state:
    with st.expander("❓ 历次研究问题", expanded=False):
        st.markdown(st.session_state["research_questions"])

# ── 底部提示 ──
st.markdown("---")
if st.session_state.get("step1_done"):
    st.markdown("✅ **选题完成！** 点击左侧 **📚 文献调研** 进入下一步，关键词会自动填充。")
else:
    st.markdown("💡 确定研究方向后，分析结果会自动传递给后续步骤。")

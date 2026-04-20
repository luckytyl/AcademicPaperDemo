"""GLM-5 API 调用封装（Anthropic 兼容格式）

兼容两种部署方式：
- 本地开发：读取 .env 文件
- Streamlit Cloud：读取 st.secrets
"""

import os
from pathlib import Path

# 先加载 .env（强制覆盖，不用 setdefault）
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()  # 强制覆盖

import anthropic


def _get_config(key, default=None):
    """从环境变量或 st.secrets 读取配置。优先级：os.environ > st.secrets > default。"""
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default


def _get_client():
    key = _get_config("ANTHROPIC_AUTH_TOKEN")
    base = _get_config("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
    if not key:
        raise ValueError("ANTHROPIC_AUTH_TOKEN 未设置，请检查 .env 文件")
    return anthropic.Anthropic(base_url=base, api_key=key)


def call_glm(system_prompt: str, user_message: str, max_tokens: int = 4096):
    """同步调用 GLM-5，返回完整文本。"""
    client = _get_client()
    model = _get_config("ANTHROPIC_MODEL", "GLM-5")
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return resp.content[0].text


def stream_glm(system_prompt: str, user_message: str, max_tokens: int = 4096):
    """流式调用 GLM-5，yield 文本片段。用于 Streamlit st.write_stream。"""
    client = _get_client()
    model = _get_config("ANTHROPIC_MODEL", "GLM-5")
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for text in stream.text_stream:
            yield text

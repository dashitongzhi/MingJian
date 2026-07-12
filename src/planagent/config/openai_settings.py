"""OpenAI 配置子模型。

OpenAI 配置已有独立模块 config/openai.py 中的 OpenAIConfig，
此处仅提供统一导出入口。
"""

# OpenAI 配置已通过 OpenAIConfig 管理，详见 config/openai.py
from planagent.config.openai import OpenAIConfig as OpenAISettings  # noqa: F401

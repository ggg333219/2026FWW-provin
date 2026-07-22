"""测试 LLM 纠错链路"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

print(f'AI_API_KEY: {"[SET]" if os.getenv("AI_API_KEY") else "[NOT SET]"}')
print(f'AI_GEN_MODE: {os.getenv("AI_GEN_MODE")}')
print(f'AI_MODEL: {os.getenv("AI_MODEL")}')
print(f'AI_BASE_URL: {os.getenv("AI_BASE_URL")}')
print()

from ai_engine.core.llm import LLMClient
from ai_engine.core.config import settings

print(f'settings.is_mock: {settings.is_mock}')
print(f'settings.MODEL: {settings.MODEL}')
print(f'settings.API_KEY set: {bool(settings.API_KEY)}')
print()

client = LLMClient(model="qwen-turbo", temperature=0.1)
print(f'client.api_key set: {bool(client.api_key)}')
print(f'client.base_url: {client.base_url}')
print()

# 模拟一段有错误的 ASR 文本
test_text = """[0.0s-0.7s] 偶奔格
[0.7s-1.5s] 可以不要
[1.5s-2.9s] 但是四个AI是要工具"""

print("调用 LLM 纠错...")
response = client.chat(
    system="你是一个ASR纠错助手，保持时间戳不变，修正识别错误",
    user=f"请纠错：\n\n{test_text}",
)
print(f'used_fallback: {response.used_fallback}')
print(f'fallback_reason: {response.fallback_reason}')
print(f'content: {response.content[:500]}')

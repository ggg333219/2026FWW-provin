"""调试 LLM 纠错 — 细粒度定位问题"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from ai_engine.core.llm import LLMClient
from ai_engine.core.config import settings

print("=== 环境变量 ===")
print(f"AI_BASE_URL = {os.getenv('AI_BASE_URL')}")
print(f"AI_API_KEY  = {'[SET]' if os.getenv('AI_API_KEY') else '[NOT SET]'}")
print(f"AI_MODEL    = {os.getenv('AI_MODEL')}")
print(f"settings.API_KEY = {'[SET]' if settings.API_KEY else '[NOT SET]'}")
print(f"settings.is_mock = {settings.is_mock}")

# 方案 A: 不传 base_url（自动解析）
print("\n=== 方案 A: LLMClient 自动解析 ===")
client_a = LLMClient(model="deepseek-v4-flash", temperature=0.1, timeout=30)
print(f"base_url = {client_a.base_url}")
print(f"api_key  = {'[SET]' if client_a.api_key else '[NOT SET]'}")

resp_a = client_a.chat("你是一个助手", "回复OK即可")
print(f"used_fallback = {resp_a.used_fallback}")
print(f"content = {resp_a.content[:100]}")

# 方案 B: 明确传 base_url
print("\n=== 方案 B: LLMClient 明确指定 base_url ===")
client_b = LLMClient(model="deepseek-v4-flash", temperature=0.1, base_url="https://us-api.53hk.cn/v1", timeout=30)
print(f"base_url = {client_b.base_url}")
print(f"api_key  = {'[SET]' if client_b.api_key else '[NOT SET]'}")

resp_b = client_b.chat("你是一个助手", "回复OK即可")
print(f"used_fallback = {resp_b.used_fallback}")
print(f"content = {resp_b.content[:100]}")

# 测试纠错
print("\n=== 测试纠错 ===")
test_text = """[0.0s-0.7s] 偶奔格
[0.7s-1.5s] 可以不要
[1.5s-2.9s] 但是四个AI是要工具
[2.9s-3.7s] 你必须知道"""

resp_c = client_b.chat(
    system="你是教学ASR纠错助手。修正同音字错误，保持时间戳和换行不变，只改识别错误，使文本通顺。",
    user=f"请纠错：\n\n{test_text}",
)
print(f"used_fallback = {resp_c.used_fallback}")
print(f"结果 = {resp_c.content}")

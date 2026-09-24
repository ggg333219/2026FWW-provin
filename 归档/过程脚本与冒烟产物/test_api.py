"""测试不同 API 端点，找能工作的"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

api_key = os.getenv("AI_API_KEY", "")
print(f"API Key: {api_key[:16]}...{api_key[-8:]}")
print()

# 尝试不同的 base URL
candidates = [
    ("DashScope (阿里云)", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("OpenAI", "https://api.openai.com/v1"),
    ("DeepSeek", "https://api.deepseek.com/v1"),
    ("DeepSeek (no /v1)", "https://api.deepseek.com"),
    ("SiliconFlow", "https://api.siliconflow.cn/v1"),
    ("本地代理", os.getenv("AI_BASE_URL") or "未设置"),
]

for name, url in candidates:
    if url == "未设置":
        print(f"[{name}] 未设置, 跳过")
        continue
    try:
        client = OpenAI(api_key=api_key, base_url=url, timeout=5)
        models = client.models.list()
        model_names = [m.id for m in models][:3]
        print(f"[{name}] {url}")
        print(f"  ✅ 可用! 模型示例: {model_names}")
        break
    except Exception as e:
        msg = str(e)[:80]
        print(f"[{name}] {url}")
        print(f"  ❌ {msg}")

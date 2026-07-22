"""快速验证 LLM API + ASR 纠错"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

api_key = os.getenv("AI_API_KEY")
base_url = os.getenv("AI_BASE_URL", "https://us-api.53hk.cn/v1")
model = os.getenv("AI_MODEL", "deepseek-v4-flash")

print("=== LLM API 连通测试 ===")
print(f"Base URL: {base_url}")
print(f"Model: {model}")

try:
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=15)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "回复OK"}],
        temperature=0.1,
    )
    content = resp.choices[0].message.content
    print(f"✅ API 可用! 响应: {content[:100]}")
except Exception as e:
    print(f"❌ API 失败: {str(e)[:150]}")

print()
print("=== ASR 纠错测试 ===")

from ai_engine.parse.video_processor import VideoProcessor

vp = VideoProcessor(max_keyframes=0, asr_language='zh')
result = vp.process('ai_engine/parse/test4.mp4')

for r in result:
    t = r.get('type')
    if t == 'transcript':
        corrected = r['metadata'].get('llm_corrected', False)
        print(f"llm_corrected: {corrected}")
        print(f"内容长度: {len(r['content'])}")
        if corrected:
            print("--- 纠错后文本前500字 ---")
            print(r['content'][:500])
        else:
            print("--- 原始ASR文本前500字 ---")
            print(r['content'][:500])

"""快速调试 - 直接调 API"""
import os
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

api_key = os.getenv("AI_API_KEY")
base_url = os.getenv("AI_BASE_URL", "https://us-api.53hk.cn/v1")

client = OpenAI(api_key=api_key, base_url=base_url, timeout=60)

text = """[0.0s-0.7s] 偶奔格
[0.7s-1.5s] 可以不要
[1.5s-2.9s] 但是四个AI是要工具
[2.9s-3.7s] 你必须知道
[3.7s-4.8s] 作为靠AI硬身上"""

resp = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[
        {"role": "system", "content": "你是教学ASR纠错助手。修正同音字错误，保持时间戳和换行不变，只改识别错误，使文本通顺。"},
        {"role": "user", "content": f"请纠错：\n\n{text}"},
    ],
    temperature=0.1,
)
print("API响应成功!")
print(resp.choices[0].message.content)

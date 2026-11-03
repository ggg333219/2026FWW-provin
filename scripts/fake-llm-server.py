"""受控的 OpenAI 兼容模型服务（仅用于本地验收，不属于交付物）。

用途：验证 F01「真实模型输出格式校验」在**真实 HTTP 链路**上的行为 ——
    浏览器 → Go 网关 → Python 引擎 → OpenAI 兼容端点 → 引擎 → 网关 → 浏览器

注入的输出刻意保留了真实模型常见的格式偏差：
    with_interactive = "需要"   （字符串而非 bool）
    duration_minutes = "45分钟" （带单位字符串而非整数）
    output_format    = ["PPT"]  （大小写别名）

注意：这是**受控桩**，不是真实大模型。它证明的是"归一与透传逻辑在真实链路上成立"，
不等于"真实模型已验证通过" —— 两者必须分开汇报。
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

# 与团队固定主样例一致的模型输出（含刻意制造的格式偏差）
PAYLOAD = {
    "topic": "冒泡排序与快速排序",
    "duration_minutes": "45分钟",
    "style": "讲练结合",
    "target_student": "大一计算机专业学生",
    "knowledge_points": ["冒泡排序", "快速排序"],
    "output_format": ["PPT"],
    "with_interactive": "需要",
}

# 第二份载荷：模型脑补了教师没说过的知识点（红黑树），用于验证接地校验
HALLUCINATION_PAYLOAD = dict(PAYLOAD, knowledge_points=["冒泡排序", "快速排序", "红黑树"])

# 第三份载荷：更脏的格式偏差，用于验证"逐字段归一 + 不可归一字段单独丢弃"
DIRTY_PAYLOAD = {
    "topic": "冒泡排序与快速排序",
    "duration_minutes": "45分钟",
    "style": "讲练结合",
    "target_student": "大一计算机专业学生",
    "knowledge_points": "冒泡排序、快速排序",
    "output_format": ["PPT", "Word", "flash"],
    "with_interactive": "需要",
    "reasoning": "模型自述的推理过程",
}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)

        # 触发器：请求体里出现该标记时返回 500，用于验证"真实模型失败 → 规则兜底"
        if "触发失败B" in raw.decode("utf-8", errors="ignore"):
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        payload = PAYLOAD
        if "触发脑补A" in raw.decode("utf-8", errors="ignore"):
            payload = HALLUCINATION_PAYLOAD
        if "触发脏格式C" in raw.decode("utf-8", errors="ignore"):
            payload = DIRTY_PAYLOAD

        body = {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": 0,
            "model": "controlled-fake-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        out = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, fmt, *args):  # 静默，避免刷屏
        pass


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8899), Handler)
    print("受控模型桩已启动: http://127.0.0.1:8899/v1/chat/completions", flush=True)
    server.serve_forever()

# Workflow 7/7：generate_audio（讲授节点 TTS 时间轴）

> 对应后端：`DifyClient.GenerateAudio`  
> scene 值：`generate_audio`  
> 业务场景：教师端为当前页 **TeachingNode** 批量生成音频时间轴（`sections`），供课堂播放条同步

---

## 在统一 Workflow 里加第 7 条分支

```
开始
  ↓
IF/ELSE（scene）
  ├─ generate_script          → 已有
  ├─ parse_knowledge          → 已有
  ├─ generate_from_markdown   → 已有
  ├─ generate_node_script     → 已有
  ├─ reconstruct_document     → 已有
  ├─ parse_document           → 已有
  └─ generate_audio           → 本指南
```

---

## 一、开始节点：新增变量

| 变量名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `course_id` | 文本 | 选填 | 本分支必填，课程 ID |
| `page` | 数字 | 选填 | 页码，≥1 |
| `voice_type` | 文本 | 选填 | 音色，如 `standard_female` |
| `format` | 文本 | 选填 | `mp3` / `wav` |
| `provider` | 文本 | 选填 | `dashscope`（默认）/ `mock-tts` |
| `nodes` | 段落/文本 | 选填 | **JSON 字符串**，节点讲稿数组 |
| `playback_id` | 文本 | 选填 | 播放批次 ID，可空 |
| `dashscope_api_key` | 文本 | 选填 | 通义 API Key（后端自动传入；Dify 内测时手动填） |

> 后端会把 `nodes` 数组 `json.Marshal` 后作为 **字符串** 传入。

**nodes 测试示例：**
```json
[
  {
    "node_id": "p1_n1",
    "title": "监督学习",
    "text": "同学们好，今天我们学习监督学习。它使用标注数据训练模型，典型任务包括分类和回归。",
    "duration_sec": 0,
    "start_sec": 0,
    "end_sec": 0
  },
  {
    "node_id": "p1_n2",
    "title": "无监督学习",
    "text": "无监督学习不需要标注，常见应用是聚类和降维。",
    "duration_sec": 0,
    "start_sec": 0,
    "end_sec": 0
  }
]
```

---

## 二、IF/ELSE 新增分支

| 条件 | 分支 |
|------|------|
| `scene` **是** `generate_audio` | → 代码节点（推荐） |
| 其他已有分支 | 保持不变 |

> **推荐纯代码节点**：调用通义 `qwen3-tts-flash` 生成真实 MP3 URL，并组装播放时间轴。  
> `provider=mock-tts` 时仍走占位模式（无真实音频）。

---

## 三、代码节点：真实 TTS + 时间轴组装

### 前置：Sandbox 注入 DashScope Key

项目 `dify/docker-compose.yml` 已为 `dify-sandbox` 配置：

- `AI_API_KEY` ← 后端调用时自动传入 `dashscope_api_key`（代码沙箱读不到容器环境变量）

> **重要：** Dify 代码沙箱 **无法读取** docker 环境变量，必须通过 workflow 输入 `dashscope_api_key` 传入 Key。
- `DASHSCOPE_TTS_URL` ← 默认北京区 multimodal-generation 端点
- `ENABLE_NETWORK=true`（必须，否则无法调 DashScope）

更新后重建 sandbox：

```powershell
cd dify
docker compose up -d --force-recreate dify-sandbox
```

### 输入变量（名称必须与 main 参数一致）

> **必做：** 打开代码节点 → **设置** → 开启 **「网络」**（Allow Network / Enable Network）。  
> 未开启时无法访问 DashScope，`audio_url` 会全部为空，状态为 `fallback_ready`。

| 变量名 | 来源 |
|--------|------|
| `course_id` | 用户输入 / course_id |
| `page` | 用户输入 / page |
| `voice_type` | 用户输入 / voice_type |
| `format` | 用户输入 / format |
| `provider` | 用户输入 / provider |
| `nodes` | 用户输入 / nodes |
| `playback_id` | 用户输入 / playback_id |
| `dashscope_api_key` | 用户输入 / dashscope_api_key |

### 代码（直接复制 — 含真实 TTS）

```python
import json
import os
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Dify 沙箱缺少 CA 证书链，需跳过 SSL 校验（仅用于访问 DashScope/OSS）
_SSL_CTX = ssl._create_unverified_context()

def _urlopen(req, timeout=60):
    return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX)

VOICE_MAP = {
    "standard_female": "Cherry",
    "female": "Serena",
    "standard_male": "Ethan",
    "male": "Kai",
    "cherry": "Cherry",
    "serena": "Serena",
    "ethan": "Ethan",
    "kai": "Kai",
}

def _estimate_duration(node):
    duration = int(node.get("duration_sec") or 0)
    if duration > 0:
        return duration
    text = (node.get("text") or "").strip()
    if not text:
        return 2
    return max(2, min(90, len(text) // 12))

def _map_voice(voice_type):
    voice = (voice_type or "Cherry").strip()
    mapped = VOICE_MAP.get(voice.lower(), voice)
    return mapped or "Cherry"

def _call_dashscope_tts(text, voice, api_key, tts_url):
    payload = {
        "model": "qwen3-tts-flash",
        "input": {
            "text": text[:512],
            "voice": voice,
            "language_type": "Chinese",
        },
    }
    req = urllib.request.Request(
        tts_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with _urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:200]}") from exc

    if body.get("code"):
        raise RuntimeError(body.get("message") or str(body.get("code")))
    output = body.get("output") or {}
    audio = output.get("audio") or {}
    url = (audio.get("url") or "").strip()
    if not url:
        raise RuntimeError("DashScope 未返回 audio.url")
    return url

def _refine_duration(url, fallback):
    try:
        with _urlopen(urllib.request.Request(url), timeout=30) as resp:
            data = resp.read()
        if data:
            return max(fallback, min(120, len(data) // 16000 or fallback))
    except Exception:
        pass
    return fallback

def main(course_id, page, voice_type, format, provider, nodes, playback_id, dashscope_api_key):
    if isinstance(nodes, str):
        try:
            node_list = json.loads(nodes) if nodes.strip() else []
        except Exception:
            node_list = []
    elif isinstance(nodes, list):
        node_list = nodes
    else:
        node_list = []

    course_id = (course_id or "course_unknown").strip()
    page = int(page or 1)
    voice_type = _map_voice(voice_type)
    format = (format or "mp3").strip().lower()
    provider = (provider or "dashscope").strip().lower()

    api_key = (dashscope_api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("AI_API_KEY") or "").strip()
    tts_url = (
        os.getenv("DASHSCOPE_TTS_URL")
        or "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    ).strip()

    use_real_tts = provider in ("dashscope", "qwen3-tts-flash", "tongyi", "通义")
    if use_real_tts and not api_key:
        provider = "mock-tts"
        use_real_tts = False

    sections = []
    total_duration = 0
    fallback_count = 0
    tts_errors = []

    for index, node in enumerate(node_list, start=1):
        if not isinstance(node, dict):
            continue

        text = (node.get("text") or "").strip()
        node_id = (node.get("node_id") or f"node_{index:02d}").strip()
        title = (node.get("title") or node_id).strip()
        duration_sec = _estimate_duration(node)
        start_sec = int(node.get("start_sec") or total_duration)
        if start_sec < total_duration:
            start_sec = total_duration

        audio_url = (node.get("audio_url") or "").strip()
        if use_real_tts and text:
            try:
                audio_url = _call_dashscope_tts(text, voice_type, api_key, tts_url)
                duration_sec = _refine_duration(audio_url, duration_sec)
            except Exception as exc:
                audio_url = ""
                fallback_count += 1
                tts_errors.append({"node_id": node_id, "error": str(exc)[:200]})

        end_sec = start_sec + duration_sec
        total_duration = end_sec

        sections.append({
            "node_id": node_id,
            "title": title,
            "text": text,
            "duration_sec": duration_sec,
            "start_sec": start_sec,
            "end_sec": end_sec,
            "audio_url": audio_url,
        })

    playback_id = (playback_id or "").strip() or f"audio_{course_id}_{page}"
    if not sections:
        status = "empty"
    elif use_real_tts and fallback_count == 0:
        status = "ready"
    elif use_real_tts and fallback_count < len(sections):
        status = "partial_ready"
    elif use_real_tts:
        status = "fallback_ready"
    else:
        status = "placeholder"

    payload = {
        "audio_id": playback_id,
        "audio_url": sections[0]["audio_url"] if sections else "",
        "provider": "dashscope" if use_real_tts else provider,
        "voice_type": voice_type,
        "format": format,
        "status": status,
        "total_duration_sec": total_duration,
        "playback_mode": "audio_timeline",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sections": sections,
    }
    if tts_errors:
        payload["tts_errors"] = tts_errors
    return {"result": json.dumps(payload, ensure_ascii=False)}
```

### 输出变量

| 变量名 | 类型 |
|--------|------|
| `result` | String |

---

## 四、结束节点

| 变量 | 值 |
|------|-----|
| `result` | 代码节点 / result |

---

## 五、后端期望的完整 JSON 示例

```json
{
  "audio_id": "audio_course123_1",
  "audio_url": "",
  "provider": "dashscope",
  "voice_type": "Cherry",
  "format": "mp3",
  "status": "ready",
  "total_duration_sec": 28,
  "playback_mode": "audio_timeline",
  "generated_at": "2026-05-24T10:00:00Z",
  "sections": [
    {
      "node_id": "p1_n1",
      "title": "监督学习",
      "text": "同学们好，今天我们学习监督学习……",
      "duration_sec": 16,
      "start_sec": 0,
      "end_sec": 16,
      "audio_url": "https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/..."
    },
    {
      "node_id": "p1_n2",
      "title": "无监督学习",
      "text": "无监督学习不需要标注……",
      "duration_sec": 12,
      "start_sec": 16,
      "end_sec": 28,
      "audio_url": ""
    }
  ]
}
```

---

## 六、Dify 内测试输入

| 字段 | 值 |
|------|-----|
| scene | `generate_audio` |
| course_id | `course_demo_001` |
| page | `1` |
| voice_type | `Cherry` |
| format | `mp3` |
| provider | `dashscope` |
| playback_id | `audio_course_demo_001_1` |
| dashscope_api_key | 你的 `sk-...` 通义 Key（Dify 内测必填） |
| nodes | 见第一节 JSON 示例（整段粘贴） |

**成功标志：**
- `sections` ≥ 1 条，每条 `audio_url` 为 **https://** 开头的 DashScope OSS 链接
- `status` 为 `ready`（或 `partial_ready`）
- `total_duration_sec` = 最后一条的 `end_sec`

---

## 七、API 验证

```powershell
curl -X POST "http://127.0.0.1:18001/v1/workflows/run" `
  -H "Authorization: Bearer app-你的WorkflowKey" `
  -H "Content-Type: application/json" `
  -d "{\"inputs\":{\"scene\":\"generate_audio\",\"course_id\":\"course_demo_001\",\"page\":1,\"voice_type\":\"Cherry\",\"format\":\"mp3\",\"provider\":\"dashscope\",\"playback_id\":\"audio_course_demo_001_1\",\"nodes\":\"[{\\\"node_id\\\":\\\"p1_n1\\\",\\\"title\\\":\\\"监督学习\\\",\\\"text\\\":\\\"同学们好，今天我们学习监督学习。\\\",\\\"duration_sec\\\":0,\\\"start_sec\\\":0,\\\"end_sec\\\":0}]\"},\"response_mode\":\"blocking\",\"user\":\"test\"}"
```

---

## 八、Go 后端验证

```powershell
cd backend
go run test_workflow_generate_audio.go
```

---

## 九、业务链路说明

后端 `ensurePlaybackAudioAssets` 调用本接口，并将 `sections` 写入：

| 返回字段 | 数据库 / 响应 |
|----------|---------------|
| `sections[].node_id` | `audio_assets.node_id` |
| `sections[].audio_url` | `teaching_nodes.audio_url` |
| `sections[].duration_sec` | `audio_duration_sec` |
| `sections[].start_sec` / `end_sec` | 播放时间轴 |
| `status` | `tts_status` / `audio_status` |

若 Dify 返回空或失败，后端自动降级为 **placeholder 时间轴**（无真实音频文件）。

---

## 十、音色映射（voice_type）

| 传入值 | 通义音色 |
|--------|----------|
| `Cherry` / `standard_female` | 芊悦（默认女声） |
| `Serena` / `female` | 苏瑶 |
| `Ethan` / `standard_male` | 晨煦 |
| `Kai` / `male` | 凯 |

---

## 十一、常见问题

| 现象 | 处理 |
|------|------|
| `unexpected keyword argument` | 代码节点输入变量名与 `main()` 参数不一致 |
| sandbox 报 name resolution | 确认 `dify-sandbox` 容器 healthy，API 已 recreate |
| `sections` 为空 | 检查 `nodes` 是否为合法 JSON 字符串 |
| `audio_url` 仍为空 / `fallback_ready` | ① 代码节点未开 **「网络」**；② Key 无效；③ SSL 错误 → 用最新代码（含 `_SSL_CTX`） |
| `CERTIFICATE_VERIFY_FAILED` | 沙箱缺 CA 证书，代码已用 `ssl._create_unverified_context()` 修复，更新代码节点后重试 |
| DashScope 401/403 | API Key 无效或区域 URL 不匹配 |
| 后端仍走 placeholder | Dify 返回空 sections 或 API 超时，重启 `dify-api` |

---

## 十二、完成标志

- [ ] 代码节点已升级为 DashScope 真实 TTS
- [ ] 测试返回带 `https://` 的 `audio_url`
- [ ] 其他 6 个 scene 回归正常
- [ ] Go `GenerateAudio` 不再走 Python 降级

**全部 7 个 Workflow scene 配置完成。**

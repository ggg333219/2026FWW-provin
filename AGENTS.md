# 泛雅 AI 智课系统 — 项目指令

## 项目架构（多语言混合）

```
ai_engine/     Python (FastAPI + uvicorn)  — 核心 AI 服务
backend/       Go (Gin + GORM)            — 后端 API + 数据持久化
frontend/
  teacher/     Vue 3 (Vite)               — 教师端前端
  student/     Vue 2 (Vue CLI)            — 学生端前端
dify/          Docker compose              — Dify 平台（可选）
docs/          答辩文档 + 设计文档
```

## 关键文件路径（新会话优先阅读）

### 答辩准备（必读）
- `docs/答辩素材_创新点积累.md` — 4 个创新点 + 技术决策
- `docs/交叉验证报告.md` — 评委整改三模块验证数据
- `docs/课件解析核心链路设计原理.md` — 五环节闭环设计 + 需求对照

### 核心源码
- `ai_engine/generator.py` — 三阶段 pipeline（Stage 1 理解→Stage 2 聚类→Stage 3 脚本）
- `ai_engine/qa.py` — 三态理解引擎（_predict_understanding → none/partial/full）
- `ai_engine/parser.py` — 多模态解析（PPTX 图片提取 + PDF 渲染 + 视觉描述）
- `ai_engine/schema.py` — 增强脚本 schema 定义
- `ai_engine/main.py` — FastAPI 应用入口（15 个路由）
- `backend/internal/service/ai_engine_client.go` — AIEngine 接口定义（8 个方法）
- `backend/internal/handler/compat_student.go` — 学生端 SSE 问答 + 续接
- `backend/internal/handler/student.go` — 学生端流式问答
- `backend/internal/handler/teacher.go` — 教师端 AIGenerateScript
- `frontend/teacher/src/App.vue` — 教师端增强脚本面板
- `frontend/student/src/components/student/StudentAskPanel.vue` — 三态徽章 + 续接

## 服务启动命令

```bash
# AI 引擎（多模态模式需 AI_USE_VISION=true）
cd ai_engine
AI_API_KEY=c08a432340a841208ae44d55a9d31f5e.HTOxBYpotXzOMHdd \
AI_MODEL=glm-4-flash \
AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/ \
AI_USE_VISION=true \
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000

# Go 后端
cd backend
go.exe build -o student-server.exe ./cmd/student/ && ./student-server
go.exe build -o teacher-server.exe ./cmd/teacher/ && ./teacher-server

# 前端
cd frontend/teacher && npx vite --host --port 5173
cd frontend/student && npm run build && python3 -m http.server 8081
```

## 关键配置
- AI 模型: glm-4-flash（智谱）, base_url: https://open.bigmodel.cn/api/paas/v4/
- API Key: c08a432340a841208ae44d55a9d31f5e.HTOxBYpotXzOMHdd
- Go 后端网关: 172.22.160.1 (Teacher :8082, Student :8081)
- Go 编译: go.exe（Windows/amd64 1.25.5）

## 待完成重点任务（2026-05-25 状态）
1. Go 后端 AIGenerateScript 改调 /generate-enhanced
2. 138 页真实课件纯文本解析 0 非空页 → 需多模态 vision 模式验证
3. 学生端 dist 需重建
4. Dify 对接：在 localhost:13000 创建 workflow app → 获取 API key
5. 答辩 PPT + 演示链路合练

## 关键设计决策
- 三阶段 pipeline 而非一次性生成：跨页语义聚合需要独立认知阶段
- segment 级脚本粒度：精确续接的必需品
- 三态理解引擎（none/partial/full）而非二态续接
- 多模态视觉描述而非纯文本：138 页课件 116 页含图，纯文本 0 非空页
- SSE 流式输出而非 HTTP 响应：首 token 0.5s 到达

# 任务包 C — Vue 前端

> 负责人：同学 C  |  预估工作量：密集 1 周

## 你的职责

前端是系统的**面孔**：教师工作台需要全新设计，从原来的功能面板改成**对话→资料→预览→导出**的线性工作流。你可以 mock 数据先行开发，不等待后端接口。

**你不需要碰**：后端 API 的实现（同学 A 管）、AI Engine 的逻辑（同学 B 管）。你只需要保证界面正确、交互流畅。

---

## 现有代码概况

```
frontend/
├── teacher/                # 教师端 (Vite + Vue 3)
│   └── src/
│       ├── App.vue         # 主入口 (2261 行 — 需要拆分)
│       ├── views/          # （目前散落在 components 中）
│       └── components/     # 组件
├── student/                # 学生端 (Vue CLI)
│   └── src/
│       └── App.vue         # 主入口 (7408 行 — 暂不动)
└── src/                    # 孤儿目录（与 teacher/student 重叠，确认后删除）
    ├── components/
    │   ├── MistakeBook.vue
    │   └── RecordList.vue
    └── router/
```

**关键问题**：
1. 教师端 `App.vue` 2261 行 — 需要拆分为路由+视图
2. 无 Vue Router — 所有功能在单页面里切换
3. 组件没有按域分组 — 全部平铺在 `components/` 下
4. `frontend/src/` 目录与 `teacher/src/` 和 `student/src/` 重叠

---

## 任务分解

### C1. 清理孤儿目录 ⭐（先做）

**目标**：移除无用的 `frontend/src/` 目录。

**操作**：

1. 确认 `frontend/src/` 下的文件不被任何地方引用：
   ```
   frontend/src/components/MistakeBook.vue  — 无引用
   frontend/src/components/RecordList.vue   — 无引用
   ```

2. 确认后，把整个 `frontend/src/` 目录移到 `frontend/legacy/`：
   ```bash
   mv frontend/src frontend/legacy
   ```

**完成标志**：教师端和学生端的 `npm run dev` 均正常启动。

### C2. 搭建 Vue Router + 视图框架 ⭐

**目标**：把教师端从单页面改为多路由结构。

**在 `frontend/teacher/src/` 下**：

新建 `router/index.js`：

```javascript
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/',            name: 'workspace',    component: () => import('@/views/Workspace.vue') },
  { path: '/conversation', name: 'conversation', component: () => import('@/views/Conversation.vue') },
  { path: '/materials',   name: 'materials',    component: () => import('@/views/Materials.vue') },
  { path: '/preview',     name: 'preview',      component: () => import('@/views/Preview.vue') },
  { path: '/export',      name: 'export',       component: () => import('@/views/Export.vue') },
]
```

新建视图文件：

```
views/
├── Workspace.vue        # 主工作台（导航入口）
├── Conversation.vue     # 对话意图（S1）
├── Materials.vue        # 资料管理（S2）
├── Preview.vue          # 课件预览（S3+S4）
└── Export.vue           # 导出（S4）
```

调整 `App.vue`：
- 提取导航栏为独立组件
- 主体区域改为 `<router-view />`
- 原 2261 行降到 ≤400 行引导代码

**完成标志**：可通过 `/conversation`、`/materials` 等路由切换视图。

### C3. 组件按域分组

**目标**：组件从平铺改为按业务域分组。

**操作**：

在 `frontend/teacher/src/` 下：

```
components/
├── common/               # 通用组件（按钮、输入框、卡片等）
│   ├── AppHeader.vue
│   ├── FileUploader.vue
│   └── StatusBadge.vue
├── conversation/         # 对话意图相关
│   ├── ChatPanel.vue
│   ├── IntentSummary.vue
│   └── FollowUpQuestion.vue
├── materials/            # 资料管理相关
│   ├── MaterialList.vue
│   ├── UploadZone.vue
│   └── ParseResult.vue
├── generation/           # 课件生成相关
│   ├── OutlineTree.vue
│   ├── SlidePreview.vue
│   ├── NodeEditor.vue
│   └── TemplateSelector.vue
└── export/               # 导出相关
    ├── FormatSelector.vue
    └── ExportProgress.vue
```

**现有组件的迁移策略**：
- 保留原有组件不动，新组件逐步替换
- 新建上述目录结构，从简开始

### C4. 对话意图视图（S1）

**目标**：实现教师与系统的对话交互界面。

**在 `views/Conversation.vue` 中**：

布局：
```
┌─────────────────────────────────────┐
│  对话区域                            │
│  ┌─────────────────────────────────┐│
│  │ 教师: 帮我做一份排序算法课件     ││
│  │ 系统: 请问面向哪个年级/专业？    ││
│  │ 教师: 大一计算机专业             ││
│  │ 系统: 需要多少分钟？什么风格？   ││
│  │ 教师: 45分钟，简洁风格           ││
│  └─────────────────────────────────┘│
│  [输入框...] [发送]                  │
├─────────────────────────────────────┤
│  意图摘要面板（右侧/下方）           │
│  ┌─────────────────────────────────┐│
│  │ 主题: 排序算法                  ││
│  │ 时长: 45分钟                    ││
│  │ 风格: 简洁                      ││
│  │ 对象: 大一计算机                 ││
│  │ [...确认按钮...]                ││
│  └─────────────────────────────────┘│
└─────────────────────────────────────┘
```

**交互流程**：
1. 输入消息 → POST `/api/v1/conversations/:id/messages`
2. 返回追问 → 显示在对话区
3. 字段齐备 → 显示确认按钮
4. 教师确认 → POST `/api/v1/conversations/:id/confirm`

**API 对接**（mock 版本）：
```javascript
// 先用 mock 数据，等同学 A 接口就绪后替换
const API = {
  sendMessage: (msg) => mockResponse(msg),
  confirmIntent: () => mockConfirm(),
}
```

**组件**：
- `ChatPanel.vue` — 对话气泡列表
- `IntentSummary.vue` — 右侧结构化摘要
- `FollowUpQuestion.vue` — 追问提示

### C5. 资料管理视图（S2）

**目标**：实现多模态资料上传、解析状态显示。

**在 `views/Materials.vue` 中**：

布局：
```
┌─────────────────────────────────────┐
│  上传区域                            │
│  ┌─────────────────────────────────┐│
│  │ [拖拽上传 / 点击选择]           ││
│  │ 支持 PDF / PPTX / DOCX / 图片  ││
│  │ / 视频                          ││
│  └─────────────────────────────────┘│
├─────────────────────────────────────┤
│  已上传文件列表                      │
│  ┌─────────────────────────────────┐│
│  │ 📄 教材第三章.pdf   [解析中...] ││
│  │ 📊 课程大纲.pptx    [已完成 ✓]  ││
│  │ 🖼️ 架构图.png      [已完成 ✓]  ││
│  └─────────────────────────────────┘│
└─────────────────────────────────────┘
```

**API 对接**：
```
POST /api/v1/upload              — 上传文件
GET  /api/v1/tool/status/:id     — 查询解析状态
```

### C6. 课件预览视图（S3）

**目标**：预览生成的课件，支持简单修改。

**在 `views/Preview.vue` 中**：

布局：
```
┌─────────────────────────────────────┐
│  大纲侧边栏          │ 主预览区域   │
│  ┌────────────────┐ │ ┌───────────┐│
│  │ 📖 排序算法     │ │ │ 当前幻灯片││
│  │   ├ 冒泡排序    │ │ │ 内容渲染  ││
│  │   ├ 快速排序    │ │ │           ││
│  │   ├ 归并排序    │ │ │           ││
│  │   └ 总结        │ │ │           ││
│  │                 │ │ └───────────┘│
│  │ [修改] [换风格] │ │   [上一页][下一页]│
│  └────────────────┘ └───────────────┘│
├─────────────────────────────────────┤
│  操作栏                              │
│  [保存版本] [回退] [锁定] [下一步导出]│
└─────────────────────────────────────┘
```

**交互流程**：
1. 加载生成结果 → GET `/api/v1/generation/:id/preview`
2. 修改节点 → POST `/api/v1/generation/:id/modify`
3. 保存版本 → POST `/api/v1/versions/:gen_id`
4. 锁定 → POST `/api/v1/versions/:gen_id/lock`

### C7. 导出视图（S4）

**目标**：选择格式、触发导出、展示进度、获得下载链接。

**在 `views/Export.vue` 中**：

布局：
```
┌─────────────────────────────────────┐
│  导出设置                            │
│  ┌─────────────────────────────────┐│
│  │ 导出格式: [PPTX] [DOCX] [两者] ││
│  │ 版本: V3（当前锁定）             ││
│  │ [开始导出]                       ││
│  └─────────────────────────────────┘│
├─────────────────────────────────────┤
│  导出历史                            │
│  ┌─────────────────────────────────┐│
│  │ 📊 课件.pptx    2026-07-17 下载 ││
│  │ 📝 教案.docx    2026-07-17 下载 ││
│  └─────────────────────────────────┘│
└─────────────────────────────────────┘
```

**API 对接**：
```
POST /api/v1/exports/:gen_id        — 创建导出任务
GET  /api/v1/exports/status/:job_id — 查询进度
```

### C8. API 服务层

**目标**：统一管理所有后端 API 调用。

**在 `teacher/src/services/` 下**：

```
services/
├── api.js               # axios 实例配置
├── conversation.js      # 对话相关 API
├── materials.js         # 资料管理 API
├── generation.js        # 课件生成 API
├── version.js           # 版本管理 API
└── export.js            # 导出相关 API
```

**示例 `api.js`**：

```javascript
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || 'http://localhost:8080/api/v1',
  timeout: 30000,
})

api.interceptors.response.use(
  response => response.data,
  error => {
    // 统一错误处理
    return Promise.reject(error)
  }
)

export default api
```

**完成标志**：前端所有 API 调用通过 `services/` 层管理，无散落的 `fetch` 调用。

---

## 检验清单

| 任务 | 检验方式 | 预计耗时 |
|------|---------|---------|
| C1 清理孤儿目录 | 前后端 dev 启动正常 | 1 小时 |
| C2 路由+视图框架 | 路由切换正常 | 半天 |
| C3 组件按域分组 | 目录结构完整 | 2 小时 |
| C4 对话意图视图 | mock 模式可发送/确认 | 1 天 |
| C5 资料管理视图 | 上传+状态显示 | 1 天 |
| C6 课件预览视图 | 预览+修改+版本 | 1.5 天 |
| C7 导出视图 | 导出进度+下载 | 半天 |
| C8 API 服务层 | 统一管理、错误处理 | 半天 |

## 如何与同学 A 对接

- 你调同学 A 的 Go 后端 API，baseURL 是 `http://localhost:8080/api/v1`
- 接口还没就绪时用 mock 数据开发
- 等同学 A 接口 Ready 后替换 mock
- 接口格式见 `005-接口契约手册.md`
- 遇到 4xx/5xx 错误 → 显示友好提示，不要裸抛 error

## Mock 数据策略

在每个 `services/` 文件中预留 mock 开关：

```javascript
const USE_MOCK = true  // 改 false 切换到真实 API

export async function sendMessage(msg) {
  if (USE_MOCK) return mockSendMessage(msg)
  return api.post('/conversations/xxx/messages', { message: msg })
}
```

这样前后端可以完全并行开发，最后统一切真实接口。

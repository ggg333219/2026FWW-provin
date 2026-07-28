# 前置条件

在团队成员开始分别开发前，必须先完成以下 3 项基础建设。

## 1. 引入路由与状态管理规范

### 现状

当前 `App.vue` 主要依靠条件渲染或 Tab 切换，刷新页面后状态容易丢失。

### 动作

- 引入 `vue-router`
- 将主流程路由化

推荐路由：

- `/workspace`
- `/courseware/create/s1-intent`
- `/courseware/create/s2-material`
- `/courseware/create/s3-studio`
- `/courseware/create/s4-version`
- `/analytics`

### Store 骨架

先建立 7 个 Pinia Store 的空文件和 State 骨架，确保跨路由传递稳定。

- `authStore`
- `workspaceStore`
- `intentStore`
- `materialStore`
- `generationStore`
- `versionStore`
- `analyticsStore`

## 2. 统一 API 请求契约与 Store 数据流映射

### 动作

按业务拆分 `services/v1`：

- `intentApi.js` -> S1 结构
- `materialApi.js` -> S2 ChunkSchema 结构
- `generationApi.js` -> S3 节点树结构
- `versionApi.js` -> S4 修改指令结构
- `ragApi.js` -> 知识库检索与证据接口
- `analyticsApi.js` -> 学情统计接口

### 要求

- 后端返回格式必须和前端 Store 字段强绑定
- 先定 DTO，再写页面
- 错误码、任务状态、轮询字段要统一

## 3. 抽取 AppShell 基础骨架

### 动作

从现有 `App.vue` 中抽离：

- 顶部 Navigation
- 左侧 Sidebar
- 全局 Toast / Loading
- 主内容容器

### 目标

为后续 4 人并行开发提供稳定的组件容器，避免大家同时改 `App.vue`。

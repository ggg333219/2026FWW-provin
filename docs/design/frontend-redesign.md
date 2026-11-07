# 教师端前端整体重设计说明

> 适用范围：`frontend/teacher`。本次为 **Redesign - Preserve**：保留核心功能、业务目标、
> 路由、表单字段与主要内容结构，只打磨信息层级、导航与交互布局、组件状态、间距对齐、
> 视觉风格、色彩排版、反馈细节与响应式。

## 1. Design Read

B2B 教师端四步课件生成工作台，面向教师与答辩评审，用克制、信息密度合理、专业可信的
商业软件语言，落在现有 Vue 3 + 原生 CSS 上。不引入 React 设计系统（技术栈不匹配），
也不采用 `public/apple-hig-showcase.html` 的紫色玻璃拟态原型（偏展示型，不是工具型）。

| 档位 | 值 | 理由 |
|---|---|---|
| `DESIGN_VARIANCE` | 4 | 工作台需要可预测的栅格与对齐，不做不对称构成 |
| `MOTION_INTENSITY` | 3 | 只保留状态反馈动效，遵守 `prefers-reduced-motion` |
| `VISUAL_DENSITY` | 6 | 教师端信息较多，密度合理偏紧凑，但层级必须靠对比而非"字号都很小" |

主色锁定墨绿 `#2F605A`（既有品牌资产），统一为单一色阶。中性色统一冷灰。
状态色只有 warning / danger / info 三个功能色，不做装饰性彩色。

## 2. 改造前审计（结论摘要）

| 问题 | 证据 | 处理 |
|---|---|---|
| token 名存实亡 | `theme.css` 10 个变量里 8 个无引用；43 个组件仅 3 个用 `var(--)`；主绿散落 6 种近似值 | 重建完整 token，组件改为引用语义变量 |
| 步骤条 4 份重复 | S1/S2/S3/S4 各自复制 `.step-pills` 与 CSS | 抽 `StepNav.vue` 单点维护 |
| 状态组件未接入 | `LoadingState` / `ProgressTimeline` 零引用；17 处手写空态；`:disabled` 有 5 种透明度 | 统一 `EmptyState` / `ErrorState` / `LoadingState` 并接入 |
| 字号失控 | `TeacherIntentPanel.vue` 大量 7 到 10px 文本 | 最小 12px，正文 14px，建立 8 级字阶 |
| 圆角阴影混用 | 6 到 26px 共 17 种圆角，阴影全内联硬编码 | 一套圆角 + 4 级阴影 |
| 反馈机制多套 | 两套 Toast、5 套错误条、原生 `alert` / `confirm`、三套 spinner | 统一全局 Toast 与 `ds-notice` |
| 图标三套混用 | 内联 SVG / `v-html` 字符串 / emoji 与 Unicode 字符 | 统一内联 SVG 线性图标，去掉装饰性 emoji |
| 响应式断点混乱 | 700/760/900/980/1050/1100/1200/1400 共 8 种 | 统一 640 / 768 / 1024 / 1280 / 1440 |
| 固定定位耦合 | S3 证据栏 / AI 面板用 `position:fixed; top:118px` 与顶栏高度强耦合 | 改用栅格列 + sticky，去掉 340/380px 让位 padding |

## 3. 设计系统

全部定义在 `src/styles/theme.css`，全局基元类在 `src/style.css`。

### 3.1 色

| 用途 | Token | 值 |
|---|---|---|
| 主色 / 主按钮 | `--color-primary` | `#2F605A` |
| 主色悬停 / 按下 | `--color-primary-hover` / `-active` | `#264E49` / `#1D3C38` |
| 主色浅底 | `--color-primary-soft` | `#F0F6F4` |
| 页面底 / 卡片 | `--bg-page` / `--bg-surface` | `#F7F9FA` / `#FFFFFF` |
| 主文本 / 次文本 / 辅助 | `--text-primary` / `-secondary` / `-tertiary` | `#1B252C` / `#5A6C78` / `#798B96` |
| 边框 | `--border-subtle` / `-default` / `-strong` | `#E6EBEE` / `#D4DCE1` / `#A8B5BE` |
| 警示 / 危险 / 信息 | `--color-warning` / `-danger` / `-info` | `#A75C09` / `#B4342A` / `#2B5F8E` |

主按钮为白字配 `#2F605A`，对比度约 7:1，满足 WCAG AA。次级按钮为主色文字配白底与边框，
不使用白字配浅底。表单 placeholder 用 `--text-disabled`，focus ring 用 `--shadow-focus`。

### 3.2 间距 / 圆角 / 阴影

- 间距走 4px 基数：`--space-1` 到 `--space-16`（4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64）。
- 圆角只有一套：控件 6px、chip 10px、卡片 14px、容器与弹窗 20px、状态胶囊 999px。
- 阴影 4 级，全部带冷灰色调，不用纯黑投影。

### 3.3 字

统一字体栈以系统中文字体优先（PingFang SC / Microsoft YaHei），不再三套并存。
字阶 12 / 13 / 14 / 16 / 18 / 20 / 24 / 30px；正文 14px、行高 1.5；
字重 400 / 500 / 600 / 700。**任何可见文本不小于 12px。**

### 3.4 全局基元类

`.ds-btn`（primary / secondary / ghost / danger，sm / lg / block）、`.ds-card`、
`.ds-field` / `.ds-label` / `.ds-input` / `.ds-textarea` / `.ds-hint` / `.ds-error-text`、
`.ds-tag`、`.ds-notice`、`.ds-empty` / `.ds-state` / `.ds-skeleton`、`.ds-fade-in`。
组件优先复用，避免各写一份。

## 4. 页面骨架与信息层级

```
┌────────────────────────────────────────────────────────────┐
│ TopBar 60px   品牌 | 流程位置 | 后端状态 | 用户              │  单行，不换行
├────────────────────────────────────────────────────────────┤
│ PageHeader    标题(20px) + 一句说明(13px) + 主操作           │
│ StepNav       S1 意图理解 > S3 生成 > S4 版本（S2 资料可选）  │
├───────────────────────────────────┬────────────────────────┤
│ Primary 主工作区 (minmax 1.45fr)   │ Secondary 侧栏 (.82fr)  │
│ 对话 / 编辑 / 生成 / 预览           │ 意图画像 / 版本信息     │
│                                   │ 完成度 / 状态反馈        │
├───────────────────────────────────┴────────────────────────┤
│ Footer Bar    当前状态说明 + 单一主 CTA                       │
└────────────────────────────────────────────────────────────┘
```

规则：

- 顶栏高度固定 60px，桌面端**单行**；窄屏才把次要项收进更多菜单。
- 页面标题、说明、主操作对齐同一条基线，避免"标题左、说明漂浮在右上"的写法。
- 业务事实：主流程是 **S1 到 S3，S2 为可选补充入口**，步骤条不能画成线性四步。
- 主 CTA 每屏**只有一个**，标签不超过 6 个字，桌面端不换行。
- 卡片只用于确有层级差的内容；同组信息用 `border-top` 或留白分组，不叠卡片。

## 5. 组件状态矩阵

每个交互组件必须覆盖以下状态，不允许只做成功态。

| 状态 | 表现 | 实现 |
|---|---|---|
| default | 常规边框、主色文字 | `.ds-btn` / `.ds-input` |
| hover | 边框加深或底色变化，无发光 | `:hover:not(:disabled)` |
| active | `translateY(1px)` 的物理按压感 | `:active:not(:disabled)` |
| focus | 2px 主色 outline + 3px 柔光环 | `:focus-visible` / `--shadow-focus` |
| disabled | 统一 `opacity: 0.48`，`cursor: not-allowed` | `:disabled` |
| loading | 与最终布局同形的骨架块，不用通用转圈 | `.ds-skeleton` / `LoadingState` |
| empty | 图标 + 一句说明 + 如何填充的指引 | `EmptyState` |
| error | 就近内联错误条，说明可恢复动作 | `ErrorState` / `.ds-notice--danger` |
| success | 全局 Toast，3.2s 自动消失 | `AppShell` 统一 Toast |

键盘导航：所有可交互元素可 Tab 到达，弹窗打开时焦点进入、Esc 关闭、关闭后焦点回到触发元素。
`prefers-reduced-motion` 下所有动效降级为瞬时。

## 6. 关键页面改造

| 页面 | 改造前 | 改造后 |
|---|---|---|
| 全局壳 `AppShell` | 外层径向渐变 + 20px padding + 26px 大圆角白卡 | 中性页面底 + 16px gutter + 14px 容器圆角；容器最大宽 1440 居中；Toast 统一为 `AppToast` |
| 顶栏 `TeacherTopBar` | emoji 校徽、62px、状态胶囊与账户区各自浮起 | 内联 SVG 品牌标、60px sticky 单行导航、状态与账户用细分隔线组织、响应式收敛 |
| S1 意图页 | 8px kicker、7px badge、10px 按钮、三列 starter、1050/700 两个断点 | 12px 起字阶、标题 20px、画像卡字段两列对齐、状态条统一、768px 以下单列 |
| 项目列表 `MiddlePage` | 单行压缩 CSS、9px 按钮、搜索与新建散落 | 页头 + 工具行 + 列表栅格，空 / 加载 / 错误态接入公共组件 |
| S2 / S3 / S4 | 各复制一份步骤条 CSS，固定定位浮层挤压内容 | 共用 `StepNav`；S3 用 `.s3-workbench` 栅格 + sticky 替换 `position:fixed` 与 340/380px 让位 padding；统一 1280/1024/768 断点 |
| 登录 `HomeLogin` | 独立 Inter 字体栈、与工作台脱节 | 统一字体与品牌色；颜色全部走 token；补 `prefers-reduced-motion` |

状态组件没有重复造轮子：仓库原有的 `LoadingState.vue` 本来就是 loading / empty / error 三态组件，
但零引用且带 11px 字号与硬编码色。本次把它改成 token 化、补齐 `role` / `aria-live`，
再用 `EmptyState.vue`、`ErrorState.vue` 做语义封装，页面侧按语义选用。

`StepNav` 对「跳转前要先做业务动作」的步骤（S2 → S3 的无证据确认、S3 → S4 的版本保存）
提供 `actionKeys` + `step-action`，这些步骤渲染为按钮而非 `RouterLink`。原因是 `RouterLink`
自身的导航监听会先于外部 `@click` 执行，靠 `preventDefault()` 拦截不可靠，容易直接跳走丢失草稿。

未挂载组件与旧 `/workspace` 工作台**保留原样**：本次不删功能、不改 IA，只让它们在全局
token 与基础样式下保持一致，不投入逐个重写。全局 reset 刻意不清零 `h1~p` / `ul` / `ol`，
因为 `MDRenderer` 与 S3 预览通过 `v-html` 注入富文本，全局清零会让标题间距与列表缩进塌陷。

## 7. 响应式

| 断点 | 规则 |
|---|---|
| `>= 1280px` | 主工作区 + 侧栏双列，内容最大宽 1440px |
| `1024 - 1279px` | 双列但侧栏收窄，S3 浮层转为可折叠抽屉 |
| `768 - 1023px` | 主区单列，侧栏下移为区块；顶栏保留状态文字 |
| `< 768px` | 全单列，16px 内边距；顶栏隐藏次要状态文字只留状态点；CTA 通栏 |

所有多列布局在 `< 768px` 显式声明单列回退，不依赖框架猜测。
不使用 `h-screen` 做整屏高度，改用 `min-height: 100dvh` 避免移动端地址栏跳动。

## 8. 验收清单（Pre-Flight）

- [x] 全站主流程页面只有一套主色；圆角只有 4 档 + 胶囊
- [x] 改造过的页面无可见文本小于 12px（意图面板原 7/8/9/10px 全部提到 12px 起）
- [x] 按钮文字与底色对比度 >= 4.5:1（主按钮白字配 `#2F605A`，约 7:1）
- [x] 每屏单一主 CTA，桌面端单行；窄屏通栏
- [x] loading / empty / error / disabled / focus 五态齐全（`LoadingState` / `EmptyState` / `ErrorState` / `ds-btn:disabled` / `:focus-visible`）
- [x] 顶栏桌面端单行，高度 60px，sticky
- [x] 步骤条单点维护，按 S1 → S3 → S4 呈现，S2 为可选补充
- [x] 断点统一为 640 / 768 / 1024 / 1280 / 1440，`< 768px` 全部单列
- [x] `prefers-reduced-motion` 下动效降级（全局 + 登录波浪 + spinner）
- [x] `vite build` 通过；`vitest` 21 文件 / 160 用例全通过（含 11 个新增组件用例）
- [x] 未改动路由、字段顺序、业务文案与任何 API 契约

> 浏览器桌面 / 窄屏实测结果见第 10 节。

## 9. 分支、基线与 PR 边界

本分支 `feature/frontend-redesign` **基于 `d5c071c`（PR #3 的 head）**，而不是干净的
`e431d0c` 基线。原因：PR #3 改过 `TeacherIntentPanel.vue` / `intentStore.js` / `mockBackend.js`
的 S1 来源可观测性逻辑；若在旧基线上重设计 S1 面板，合并时会把 MVP 修复覆盖掉。
因此三条 PR 的合并顺序为：

| 顺序 | 分支 | PR | 内容 | 合并策略 |
|---|---|---|---|---|
| 1 | `feature/f01-f02-intent-fix` | **#3** | 纯 MVP 修复（F01 / F02 / V04） | 优先收敛、待组长合并 |
| 2 | `feature/byok-model-config` | **#10** | BYOK 自带第三方模型 | 之后再看，暂不合并 |
| 3 | `feature/frontend-redesign` | **#11** | 前端整体重设计 | 与 #3 同批或随后 |

> 本 PR 地址：https://github.com/ggg333219/2026FWW-provin/pull/11
> （head `2d57bb4`，41 changed files，open / 未合并）

> 交接文档与 `scripts/README.md` 里写的「PR #4 / PR #5」是**拆分时的概念编号**；
> GitHub 上 BYOK 的实际编号是 **#10**（仓库已有其他 PR 占用了编号），不要按 #4 去找。
> PR #10 的 base 目前是 `feature/f01-f02-intent-fix`；#3 合并后需要把 #10 的 base
> 改回主线，否则 base 分支删除会触发 diff 重算。本 PR 同理。

## 10. 文件级实施与验证记录

| 批次 | 文件 | 状态 |
|---|---|---|
| 基座 | `src/styles/theme.css`、`src/style.css` | 已完成 |
| 公共组件 | `StepNav.vue`、`AppToast.vue`、`EmptyState.vue`、`ErrorState.vue`、`LoadingState.vue` | 已完成 + 11 个单测 |
| 全局壳 | `AppShell.vue`、`TeacherTopBar.vue` | 已完成 |
| 主流程页 | `S1IntentPage.vue`、`MiddlePage.vue`、`S2MaterialPage.vue`、`S3StudioPage.vue`、`S4VersionPage.vue` | 已完成 |
| S1 面板 | `TeacherIntentPanel.vue`、`EvidenceSidebar.vue` | 已完成 |
| 其余页面 | `HomeLogin.vue`、`AnalyticsPage.vue`、`CoursewareResumePage.vue` | 已完成 |
| 回归 | `vitest.config.js`（接入 `@vitejs/plugin-vue`，新增 `components/common`）、`designSystem.test.js` | 已完成 |

验证证据分级（沿用项目约定）：L1 单元测试、L2 接口层、L3 真实浏览器 + 真实 HTTP 链路、
L4 真实生产依赖。本次前端重设计**只做视觉与布局改造，不触碰模型链路**，因此不需要 L4；
浏览器验证结果按 L3 记录，且必须注明是否走了 `mockBackend`（前端在 Go 网关不可达时会
静默切换，界面正常但数据是假的）。

### 10.1 实测结果（2026-11-07）

启动三件套：Python AI Engine `:8000`（`AI_GEN_MODE=mock`）、Go 网关 `:8082`（S1 轻量模式）、
Vite `:5173`；用真实 Chrome（headless）在 1500×1000 与 390×844 两种视口逐个打开
登录 / 项目列表 / S1 / S2 / S3 / S4 / 学情分析 共 7 个页面，脚本 `记录/redesign-check.mjs`
（本地产物，已被忽略，不入库），截图在 `记录/screenshots/redesign/`。

| 结论 | 结果 |
|---|---|
| 浏览器验收 | **79 / 79 通过** |
| 横向溢出 | 两种视口 × 7 页面全部 `scrollWidth == innerWidth` |
| 顶栏 | 桌面与窄屏均为 60px 单行 |
| 步骤条 | S1/S2/S3/S4 均为三步主流程且正确标注当前步；S2 显示在「当前：资料补充（可选）」 |
| 字号 | 全站 85 处 9–11.5px 硬编码字号统一提到 12px；浏览器实测可见文本 `<12px` 计数为 **0** |
| 反馈 | `AppShell` 统一 Toast 可经 `fuww:toast` 触发，语义与文案正确 |
| 真实链路 | 每轮 14 个请求打到 `localhost:8082`；S1 `/api/v1/intent/extract` 响应体含 `model_source=mock` 与 `used_fallback`，**不是纯前端桩** |
| JS 运行时错误 | 0 |
| 前端单测 | `vite build` 通过；`vitest` 21 文件 / 160 用例通过（新增 11 个组件用例） |

**环境限制（必须如实说明）**：Go 网关在 S1 轻量模式下只注册 S1 路由，浏览器会收到
`/api/health`、`/api/v1/teacher/materials/search` 等 **404**（桌面 8 条 / 窄屏 7 条）。
这是后端启动模式造成的资源加载失败，不是本次前端改造引入的 JS 异常；已与 JS 运行时错误
分开统计，没有把 404 算作「通过」。本次 `model_source=mock`，**不代表真实大模型已验证**，
本次改动也不需要 L4。

**截图人工复核**：查看了 `1500-s1.png`（两栏信息层级、状态条、CTA）、`390-s1.png`
（窄屏单列、顶栏收敛）、`1500-s3.png` / `1500-s3-final.png`（三栏栅格）。复核中发现并修掉
两处问题：窄屏步骤条第 3 步被横向滚动裁切 → 收紧间距让三步完整可见；
S3 的 AI 面板未挂载时仍预留 340px 空列 → 用 `.s3-assistant-col:empty` 自动收起。
修正后重跑仍为 79/79。


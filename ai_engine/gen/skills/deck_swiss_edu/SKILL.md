---
name: deck-swiss-edu
description: |
  教学课件专用幻灯片生成器。接收教学意图 + 知识点，
  输出结构化 HTML 幻灯片（22 种 Swiss 国际主义布局，Klein Blue 主调）。
  适用于：课程封面、概念讲解、数据展示、互动问答、章节过渡。
triggers:
  - "生成课件幻灯片"
  - "教学 HTML deck"
  - "课件预览 HTML"
  - "生成 HTML 课件"
od:
  mode: deck
  surface: web
  scenario: education
  preview:
    type: html
    entry: index.html
    reload: debounce-100
---

# deck-swiss-edu — Swiss 国际主义教学幻灯片生成器

基于 Swiss International 风格，适配教学场景。固定 22 种布局，4 套配色，Klein Blue 主调。

---

## 配色方案（4 选 1，开工前确定）

- **Klein Blue（默认）** — accent `#002FA7`, paper `#fafaf8`, ink `#0a0a0a`
- **Lemon Yellow** — accent `#FFD500`, paper `#f7f5ee`, ink `#0a0a0a`（年轻/零售场景）
- **Neon Green** — accent `#C5E003`, paper `#f7f5ee`, ink `#0a0a0a`（科技/可持续场景）
- **Safety Orange** — accent `#FF6B35`, paper `#f7f5ee`, ink `#ffffff`（工业/紧急场景）

---

## 布局池（22 种，按内容类型自动匹配）

### 通用布局

| 代号 | 布局名称 | 适用内容 |
|------|---------|---------|
| S01 | Cover | 课程封面标题页 |
| S02 | Vertical Timeline | 时间轴/历史发展 |
| S03 | Statement | 核心概念大字页 |
| S04 | Six Cells | 6 要点网格 |
| S05 | Three Sub-cards | 左侧英雄标题 + 3 张子卡 |
| S06 | KPI Tower | 4 列柱状数据展示 |
| S07 | H-Bar Chart | 水平排名横条图 |
| S08 | Duo Compare | Before/After 对比 |
| S09 | Closing Manifesto | 结语宣言页 |
| S10 | Dot Matrix Statement | 点阵宣言 |
| S11 | Horizontal Timeline | 横向时间轴 |
| S12 | Manifesto + Ink Banner | 标题 + 黑色横幅 |
| S13 | Three Forces Cards | 三力卡片 |
| S14 | Loop Diagram | 循环流程图 |
| S15 | Image Matrix + Hero Stat | 图像矩阵 + 核心数据 |
| S16 | Multi-card Brief | 多微卡 |
| S17 | System Diagram | 系统架构图 |
| S18 | Why Now | 3 列为什么 |
| S19 | Four Cards | 4 张等宽卡 |
| S20 | Stacked KPI Ledger | 堆叠 KPI 账本 |
| S21 | Tech Spec Sheet | 技术规格表 |
| S22 | Image Hero | 全宽图 + 标题覆盖 |

### 教学专用布局

| 代号 | 布局名称 | 适用内容 |
|------|---------|---------|
| S23 | Concept Definition | 概念定义页（大字 + 引用） |
| S24 | Quiz Interactive | 互动问答页 |
| S25 | Code Example | 代码示例页 |
| S26 | Section Divider | 章节过渡页 |

---

## 输出格式约定

生成器输出 JSON：

```json
{
  "slides": [
    {
      "layout": "S01",
      "title": "Python 基础",
      "subtitle": "变量 · 数据类型 · 控制流",
      "content": "",
      "meta": { "date": "2026", "topic": "Python" }
    },
    {
      "layout": "S23",
      "title": "什么是变量",
      "content": "变量是存储数据的容器...",
      "examples": ["x = 10", "name = 'Alice'"],
      "key_points": ["变量必须先声明后使用", "变量可以随时修改"]
    }
  ],
  "palette": "klein-blue",
  "font_scale": { "display": "9.6vw", "body": "14px", "label": "11px" }
}
```

---

## 设计铁律

- **只用直角**：`border-radius: 0`，禁止圆角
- **1px hairline borders**，黑色或 accent 色
- **16 列网格**：`grid-template-columns: repeat(16, 1fr); gap: 0`
- **字体**：Inter Tight（西文 display）/ Inter（body）/ Noto Sans SC（中文）/ JetBrains Mono（数据）
- **字号极端反差**：display 用 9.6vw，body 14-16px，label 11px
- **键盘 ← / → 切换 + hash 同步**，角标固定：`№N/M` 右下，topic 左下
- **不许编造**：数字/内容必须来自输入，无内容则留空
- **单文件 HTML**，Tailwind CDN，不用外部图片 URL

---

## 内容映射规则

根据 intent 的 `key_points` 数量自动决定：

| key_points 数量 | 布局序列（示例） |
|----------------|----------------|
| 3-4 个 | S01 → S23 → S23 → S26 |
| 5-6 个 | S01 → S23 → S04 → S24 → S26 |
| 7-10 个 | S01 → S23 → S04 → S24 → S06 → S08 → S26 |
| 10+ 个 | S01 → S23 → S04 → S24 → S06 → S08 → S14 → S18 → S26 |

每个概念（key_point）生成 1-2 张幻灯片。

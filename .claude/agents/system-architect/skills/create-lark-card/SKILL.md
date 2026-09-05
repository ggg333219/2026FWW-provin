---
name: create-lark-card
label: 飞书互动卡片生成
description: 根据用户的自然语言诉求生成有效的飞书/Lark 互动卡片 JSON。用户要求生成/创建/设计卡片、输出互动卡片 JSON、webhook 请求体、OpenAPI 互动消息载荷，或要求发送卡片、发给我、发到群里、通知某人时使用；核心场景包括报表/仪表盘、宣传推广、表单/操作类卡片、通知、审批、告警、自定义视觉卡片。
---

## 硬性 NEVER 清单

- **NEVER** 在 `img` 中直接放图片 URL，也不写 `TODO_IMG_KEY` 假 key
- **NEVER** 给缺失的数据、人员、ID 补占位物，一律留空
- **NEVER** 给按钮或链接编造地址，包括 `TODO_LINK` 假 URL
- **NEVER** 默认同时输出裸 card 和 webhook/OpenAPI 外层包装
- **NEVER** 发送时把 Card JSON 包成 `{"msg_type":"interactive","card":...}`
- **NEVER** 输出 HTML、CSS、SVG、`class`、组件级 style 字段

## 主题选择

1. `style/dashboard/index.md`: 飞书经典仪表盘风格，适合报表、趋势、排行榜
2. `style/modern-minimal/index.md`: 极简主题风格，克制高级
3. `style/custom-visual/index.md`: 自由卡片风格，类似 HTML 布局

## 工作流

1. 拆解需求 → 选择主题 → 选择组件 & 学习 Schema
2. 生成卡片 JSON（只输出 JSON）
3. 有本地图片时用 `lark-cli im images create` 上传
4. 校验：`npm exec --yes --package=tsx -- tsx scripts/validate_card.ts card.json`
5. 发送：使用 `lark-cli im +messages-send`

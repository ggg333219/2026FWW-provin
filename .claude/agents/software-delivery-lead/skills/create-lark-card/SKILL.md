---
name: create-lark-card
label: 飞书互动卡片生成
description: 根据用户的自然语言诉求生成有效的飞书/Lark 互动卡片 JSON。用户要求生成/创建/设计卡片、输出互动卡片 JSON、webhook 请求体、OpenAPI 互动消息载荷，或要求发送卡片、发给我、发到群里、通知某人时使用；核心场景包括报表/仪表盘、宣传推广、表单/操作类卡片、通知、审批、告警、自定义视觉卡片，以及任何需要输出卡片 JSON 而不是普通文字的任务；会按需求加载 style 目录中的主题风格。
---

## 内容规范

- 文案、信息真实性、来源与引用、缺数据时的留空规则、内容门禁等**内容层规则**统一见 `references/content.md`，本文件与各主题不重复。
- schema 字段与校验见 `references/index.md` 与 `scripts/validate_card.ts`；视觉风格见 `style/*`。

## 硬性 NEVER 清单

- **NEVER** 在 `img` 中直接放图片 URL，也 **NEVER** 写 `TODO_IMG_KEY` 之类的假 key；没有可用 `img_key` 时整个不写该图片组件。
- **NEVER** 给缺失的数据、人员、ID 补占位物。图片、数据、人员等拿不到真实值时一律留空。
- **NEVER** 给按钮或链接编造地址，包括 `TODO_LINK` 之类的占位 URL。
- **NEVER** 默认同时输出裸 card 和 webhook/OpenAPI 外层包装；除非用户明确要求外层请求体，默认只输出 Card JSON 对象本身。
- **NEVER** 发送 `interactive` 消息时再把 Card JSON 包成 `{"msg_type":"interactive","card":...}`。
- **NEVER** 违反 `references/content.md` 的内容层规则。
- **NEVER** 输出 HTML、CSS、SVG、`class`、组件级任意 `style` 字段。
- **NEVER** 为了拿边框或 hover 效果使用空回调、伪交互或无意义 `interactive_container`。

## 主题选择规则

1. `style/dashboard/index.md`: 飞书经典仪表盘风格，适合报表、趋势、排行榜类卡片
2. `style/modern-minimal/index.md`: 极简主题风格，色调偏中和冷淡，克制高级
3. `style/custom-visual/index.md`: 自由卡片风格，把飞书卡片当成类似 HTML 的方式自由布局

## 图表生成规范

- 多条数据类信息有数据比较和可视化价值时，使用图表组件
- 成分构成数据使用饼图
- 同类型数据对比或多周期数据使用折线图

## 工作流

1. 拆解需求 → 选择主题 → 选择组件 & 学习 Schema
2. 生成卡片 JSON（只输出 JSON，不输出发送外层）
3. 有本地图片时用 `lark-cli im images create` 上传获取 img_key
4. 卡片校验：`npm exec --yes --package=tsx -- tsx scripts/validate_card.ts card.json`
5. 发送：使用 `lark-cli im +messages-send` 发送

## 返回格式

默认只输出卡片 JSON；如用户要求发送则执行发送并返回 message_id 和 chat_id。

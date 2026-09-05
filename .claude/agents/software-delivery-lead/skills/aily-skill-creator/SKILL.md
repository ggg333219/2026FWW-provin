---
name: aily-skill-creator
label: AI生成技能
description: 帮助用户创建和更新技能，扩展 agent 的功能。
---

# Skill Creator

帮助用户创建和更新技能，扩展 agent 的功能。

## 关于 Skills

Skills 是模块化、自包含的能力包，通过提供专业知识、工作流程和工具来扩展 Agent 的能力。它们像是特定领域的"入门指南"，将通用 Agent 转化为具备专业程序性知识的专属 Agent。

### Skills 提供的价值

1. 专业化工作流 - 特定领域的多步骤流程
2. 工具集成 - 处理特定文件格式或 API 的说明
3. 领域专业知识 - 公司特定知识、模式、业务逻辑
4. 打包资源 - 复杂重复任务的脚本、参考和资产

## 核心原则

### 简洁为关键

上下文窗口是公共资源。Skills 与系统提示、对话历史、其他 Skills 元数据和实际用户请求共享上下文窗口。

**默认假设：Agent 已经非常智能。** 只添加 Agent 确实需要的上下文。精简示例优于冗长解释。

### 设置适当的自由度

根据任务的脆弱性和可变性匹配自由度级别：

- **高自由度（基于文本的指令）**：多种方法都有效、决策依赖上下文时使用
- **中自由度（伪代码或带参数的脚本）**：存在首选模式、可接受一定变化时使用
- **低自由度（特定脚本，参数少）**：操作脆弱易错、一致性关键、必须按特定顺序执行时使用

## Skill 结构

每个 Skill 包含必需的 `SKILL.md` 文件和可选的打包资源：

```
skill-name/
├── SKILL.md (必需)
│   ├── YAML frontmatter 元数据（必需）
│   │   ├── name: (必需)
│   │   ├── label: (必需) - label 的语言必须与用户查询语言严格匹配
│   │   └── description: (必需)
│   └── Markdown 说明（必需）
└── 打包资源（可选）
    ├── scripts/      - 可执行代码
    ├── references/   - 按需加载的参考文档
    └── assets/       - 用于输出的文件（模板、图标等）
```

## Skill 创建流程

### Step 1: 理解 Skill 与具体示例

跳过此步除非 Skill 的使用模式已经清楚理解。

通过直接用户示例或经验证的生成示例来清楚理解 Skill 将如何使用。

### Step 2: 规划可复用 Skill 内容

将具体示例转化为有效 Skill：

1. 考虑如何从头开始执行
2. 识别哪些脚本、参考和资产有助于重复执行这些工作流

### Step 3: 初始化 Skill

创建新 Skill 时运行 `init_skill.py`：

```bash
scripts/init_skill.py <skill-name> --path <output-directory> --label <label>
```

### Step 4: 编辑 Skill

实现资源文件（scripts/、references/、assets/），然后编写 SKILL.md。

**编写指南：**
- 始终使用祈使句/不定式形式
- frontmatter 包含 `name`、`label`（语言必须与用户查询语言匹配）和 `description`
- description 是主要触发机制，包含 Skill 用途和触发场景
- SKILL.md 正文保持在 500 行以内，使用渐进披露设计

### Step 5: 打包上传 Skill

```bash
scripts/package_skill.py <path/to/skill-folder> <path/to/output-dir>
```

打包脚本会自动：
1. **验证** skill（frontmatter 格式、命名规范、目录结构、描述完整性）
2. **打包** 为 .skill 文件（zip 格式）
3. **上传** 到 SkillHub（沙箱环境有 `AILY_CLI_CALLER_AGENT_UID` 时）

跳过上传：`--no-upload`

### Step 6: 迭代

基于实际使用中的问题持续改进 SKILL.md 或打包资源。

## 参考资源

- [anthropics/skills GitHub仓库](https://github.com/anthropics/skills) - 官方技能示例和模板
- [skill-creator技能](https://github.com/anthropics/skills/tree/main/skills/skill-creator) - 技能创建指导技能

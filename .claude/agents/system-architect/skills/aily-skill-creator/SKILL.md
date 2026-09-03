---
name: aily-skill-creator
label: AI生成技能
description: 帮助用户创建和更新技能，扩展 agent 的功能。
---

# Skill Creator

帮助用户创建和更新技能，扩展 agent 的功能。

## 关于 Skills

Skills 是模块化、自包含的能力包，通过提供专业知识、工作流程和工具来扩展 Agent 的能力。

## 核心原则

### 简洁为关键

上下文窗口是公共资源。只添加 Agent 确实需要的上下文。

### 设置适当的自由度

- **高自由度**：多种方法都有效时使用
- **中自由度**：存在首选模式、可接受一定变化时使用
- **低自由度**：操作脆弱易错、必须按特定顺序执行时使用

## Skill 结构

```
skill-name/
├── SKILL.md (必需)
│   ├── YAML frontmatter: name, label, description (必需)
│   └── Markdown 说明
└── 打包资源（可选）
    ├── scripts/
    ├── references/
    └── assets/
```

## Skill 创建流程

### Step 1: 理解 Skill 与具体示例

### Step 2: 规划可复用 Skill 内容

### Step 3: 初始化 Skill

```bash
scripts/init_skill.py <skill-name> --path <output-directory> --label <label>
```

### Step 4: 编辑 Skill

实现资源文件，然后编写 SKILL.md。frontmatter 包含 `name`、`label`（语言与用户查询匹配）和 `description`。

### Step 5: 打包上传 Skill

```bash
scripts/package_skill.py <path/to/skill-folder> <path/to/output-dir>
```

跳过上传：`--no-upload`

### Step 6: 迭代

基于实际使用持续改进。

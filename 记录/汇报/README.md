# 汇报

> 每个独立任务做完了填。核心目的：**说清楚干了什么、改了啥、跟谁有关、下一步谁接**。

## 汇报归属

| 你的人 | 汇报目录 | 示例 |
|--------|---------|------|
| A - Go 后端 | `A-后端/` | `A-后端/P4-A6-版本管理.md` |
| **B - Python AI 引擎** | **`B-AI引擎/`** | **`B-AI引擎/P4-B1-大纲构建.md`** |
| C - Vue 前端 | `C-前端/` | `C-前端/P4-C5-预览视图.md` |

⚠️ **不要直接往 `汇报/` 根目录下放文件**，放到自己的子目录里，避免冲突。

---

## 模板

```yaml
---
task_id:               # 如 P3-A1、P4-B1
title:                 # 中文标题，如"大纲构建模块"
status: completed      # completed | partial | blocked | failed
summary: >             # 一句话说清楚做了什么、结果怎样
time:                  # 本次耗时，如 2026-07-18 14:00-17:00
changes:
  created:
    - path/to/file.py
  modified:
    - path/to/file.py
  deleted:
    - path/to/file.py
affects:               # 影响谁？A | B | C | AB | BC | ABC | 无
next: >                # 下一步谁接？从哪里开始？注意什么？
---

（选填）详细过程、关键决策、踩坑记录...
```

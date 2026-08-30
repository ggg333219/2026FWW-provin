# Agent 飞书群组交互流程设计方案

> 版本：v1.0
> 日期：2026-08-29
> 目标：实现多成员 Agent 通过飞书群组自主协调任务分配与工作汇报

---

## 一、设计目标

各成员在自己的 Claude Code 会话中，Agent 完成开发任务后：
1. 自动向飞书群组发送工作汇报（谁做的、做了啥、结果如何）
2. 监听群组消息，根据任务分配内容自我认领并执行
3. 各成员 Agent 身份明确，消息归属可追溯

---

## 二、团队成员 ↔ 身份映射

**飞书群组 ID：** `oc_e263e9d0e7cbce2b8ac740ccbaad3870`

| 成员 | 飞书账号 | Bot 名称 | Bot Tenant Key | 群内状态 |
|------|---------|---------|----------------|---------|
| 成员1 | 管逸恬 | Etn的自定义机器人 | `1bd75149e997d74f` | ✅ 已进群 |
| 成员2 | QOKIK | QOKIK的飞书 CLI | `15a1beade3c9d75f` | ✅ 已进群 |
| 成员3 | 向洋 | （未创建/未入群） | — | ❌ 需配置 |
| 成员4 | SOLECA（当前会话） | SOLECA的飞书 CLI | `15964c9ddf25d75f` | ✅ 已进群 |

**群内人类成员：** 徐嘉骏、SOLECA、向洋、管逸恬、苏子恒（共5人，其中向洋=成员3）

---

## 三、Agent 发送消息到群组

### 3.1 前置条件

每个成员的 Claude Code 会话中，飞书 CLI 已完成用户身份授权：

```bash
lark-cli auth login --domain im
```

授权后 `lark-cli auth status` 中 `user: status: ready`。

### 3.2 发送消息命令

```bash
# 使用 user 身份发送，消息在群里显示为「某某的飞书 CLI」或「某某的自定义机器人」
lark-cli im +messages-send \
  --chat-id oc_e263e9d0e7cbce2b8ac740ccbaad3870 \
  --as user \
  --content "【成员4 / szh】T4-P1 已完成\n\n任务：分布式锁指数退避重试 + PID 恢复\n结果：PASS\n备注：已合入 main"
```

### 3.3 Agent 自动发送时机

在任务规划文档（如 `本轮迭代复盘-下一轮任务规划分析报告.md`）的「使用说明」章节中要求：

> Agent 完成开发后，自动将工作汇报发送到飞书群组 `oc_e263e9d0e7cbce2b8ac740ccbaad3870`，使用 `lark-cli im +messages-send --as user` 命令。

---

## 四、Agent 监听群组消息（自我认领任务）

### 4.1 读取消息命令

```bash
# 读取今日群消息（user 身份）
lark-cli im +chat-messages-list \
  --chat-id oc_e263e9d0e7cbce2b8ac740ccbaad3870 \
  --as user \
  --start "$(date +%Y-%m-%d)T00:00:00+08:00" \
  --order asc
```

### 4.2 任务认领逻辑

Agent 读取消息后，根据内容中的关键词自我匹配：

| 触发关键词 | 认领动作 |
|-----------|---------|
| `@成员4` / `@szh` / `@SOLECA` | 成员4 Agent 认领该任务 |
| `@成员1` / `@27968` / `@管逸恬` | 成员1 Agent 认领（Etn的自定义机器人） |
| `@成员2` / `@QOKIK` | 成员2 Agent 认领（QOKIK的飞书 CLI） |
| `@成员3` / `@xy` / `@向洋` | 成员3 Agent 认领（向洋的 Bot） |

### 4.3 认领后的标准工作流

```
1. 读取消息内容，理解任务要求
2. 拉取远程最新代码（git pull origin main）
3. 如有其他成员最新提交，在其基础上继续开发
4. 开发完成后执行自测验证
5. 提交到 main 分支
6. 生成工作汇报，发送到群组
7. 等待下一条任务分配
```

---

## 五、成员3（向洋）Bot 配置待完成

成员3的 Bot 尚未创建和加入群组，需要完成以下步骤：

### 5.1 在向洋的机器上安装并配置飞书 CLI

```bash
# 安装（已在其他成员机器上安装则跳过）
curl -sSL https://lf4-cdn-tos.doutub.com/larkcli/$(uname -s)/$(uname -m)/latest/install.sh | bash

# 授权（使用向洋的飞书账号登录）
lark-cli auth login --domain im
```

### 5.2 将 Bot 添加到群组

在飞书开发者后台（[open.feishu.cn](https://open.feishu.cn)）找到向洋的 App，将 `im:chat:read` / `im:message` 等必要 scope 配置好，然后将 Bot 添加到群组 `oc_e263e9d0e7cbce2b8ac740ccbaad3870`。

### 5.3 确认身份

完成后在群里看到「向洋的飞书 CLI」或类似名称的 Bot，即完成配置。

---

## 六、后续迭代方向

### 6.1 短期（本次迭代）

- [ ] 成员3完成 Bot 配置并加入群组
- [ ] 将本流程文档固化到项目 `docs/` 目录
- [ ] 在每次迭代规划文档中加入「Agent 交互说明」章节

### 6.2 中期（下一轮迭代）

- [ ] Agent 自动解析群消息任务分配（不依赖关键词，而是结构化任务卡片）
- [ ] 支持消息引用（Agent A 的汇报可以被 Agent B 引用并回复）
- [ ] Bot 身份发送消息时带上任务编号，方便追溯

### 6.3 长期（Agent 自治阶段）

- [ ] Agent 读取群消息后自动判断任务优先级
- [ ] 多 Agent 并行开发时自动协调分工（通过群消息协商）
- [ ] 定期汇总各成员进度，生成群内简报

---

## 七、FAQ

**Q: Bot 身份 vs User 身份有什么区别？**
- `--as bot`：以 Bot App 身份操作，显示为「xxx的自定义机器人」，需要 Bot 的 scope 权限
- `--as user`：以当前登录用户身份操作，显示为「xxx的飞书 CLI」，需要用户的授权令牌

**Q: 为什么发送消息用 user 身份而不是 bot 身份？**
- user 身份发送的消息在群里显示为成员本人头像，更易于辨认
- bot 身份适合做自动化提醒/推送，但不便于追踪具体负责人

**Q: user 身份令牌过期了怎么办？**
- 运行 `lark-cli auth login --domain im` 重新授权
- 令牌有效期通常较长，但更换设备后需要重新登录

---

*本文档为 Agent 飞书群组交互流程 v1.0，后续随实践持续迭代更新。*

# 成员 D 任务说明

## 职责定位

WorkspacePage 跨 Store 编排负责人。负责在 WorkspacePage 中实现所有 4 个 Tab（intent / material / script / version）之间的数据联动。

## 目标

- intent Tab → material Tab：切换时自动填充搜索框
- material Tab → script Tab：切换时自动传递证据
- script Tab → version Tab：切换时自动填入 gen_id
- 刷新后所有 Tab 间透传仍然有效

## 前置条件

- 成员 A/B/C 已完成各自 localStorage 写入逻辑
- WorkspacePage 已有 4 个 Tab 的切换逻辑（`activeTab` ref）
- 各 Tab 内嵌组件已正确注册

## 涉及文件

### 唯一文件：`src/pages/WorkspacePage.vue`

**改动位置**：`<script setup>` 部分，在 stores 初始化之后

**改动内容**：添加 watchers，监听关键 Store 变化并跨 Tab 同步。

---

### 改动 1：监听 intentStore 写入 localStorage

```javascript
// 位置：在 store 初始化语句之后

// 1. intentStore.parsedIntent → localStorage（与成员 A 在 S1IntentPage 中的逻辑一致）
watch(() => intentStore.parsedIntent, (val) => {
  if (val && val.topic) {
    localStorage.setItem('fuww_intent_parsed', JSON.stringify(val))
  }
}, { deep: true })
```

### 改动 2：Tab 切换到 material 时自动填充搜索

```javascript
// 2. 监听 activeTab 变化，切换到 material 时尝试恢复 intent 数据
watch(activeTab, (newTab) => {
  if (newTab === 'material') {
    // 延迟一小段时间让组件完成渲染
    setTimeout(() => {
      restoreIntentToMaterial()
    }, 100)
  }
  if (newTab === 'script') {
    setTimeout(() => {
      restoreEvidenceToScript()
    }, 100)
  }
  if (newTab === 'version') {
    setTimeout(() => {
      restoreGenIdToVersion()
    }, 100)
  }
})

// 辅助函数：从 localStorage 恢复 intent 数据到 material Tab
function restoreIntentToMaterial() {
  try {
    const raw = localStorage.getItem('fuww_intent_parsed')
    if (!raw) return
    const intent = JSON.parse(raw)
    // 通过事件总线或 props 通知 S2MaterialWorkspace
    // 如果 S2MaterialWorkspace 暴露了 setSearchQuery 方法
    // 或者通过 ref 获取组件实例调用
    if (materialWorkspaceRef.value?.setSearchQuery) {
      const keywords = [intent.topic, intent.subject].filter(Boolean).join(' ')
      if (keywords) {
        materialWorkspaceRef.value.setSearchQuery(keywords)
      }
    }
  } catch (e) {
    console.warn('[WorkspacePage] 恢复 intent 数据失败', e)
  }
}
```

**注意**：需要确认 S2MaterialWorkspace 是否暴露 `setSearchQuery` 方法。如果未暴露，使用 `defineExpose` 在 S2MaterialWorkspace 中暴露，或通过 localStorage 驱动（S2MaterialWorkspace 已有 mounted 读取逻辑，由成员 A 添加）。

### 改动 3：Tab 切换到 script 时传递证据

```javascript
// 辅助函数：从 localStorage 恢复证据包到 script Tab
function restoreEvidenceToScript() {
  try {
    const raw = localStorage.getItem('fuww_s2_evidence_packet')
    if (!raw) return
    // 证据包已由成员 B 在 S3StudioPage 中读取
    // 这里只需要确保 Store 中有最新的证据引用
    // 如果 script Tab 中的 TeacherScriptPanel 需要证据，通过 ref 调用
    console.log('[WorkspacePage] 检测到证据包，script Tab 将自动使用')
  } catch (e) {
    console.warn('[WorkspacePage] 恢复证据包失败', e)
  }
}
```

### 改动 4：Tab 切换到 version 时自动填入 gen_id

```javascript
// 辅助函数：从 localStorage 恢复 gen_id 到 version Tab
function restoreGenIdToVersion() {
  try {
    const cached = localStorage.getItem('fuww_last_gen_id')
    if (cached && versionStore && !versionStore.genId) {
      versionStore.genId = cached
    }
  } catch (e) {
    console.warn('[WorkspacePage] 恢复 gen_id 失败', e)
  }
}
```

### 改动 5：监听 materialStore 证据包变化写入 localStorage

```javascript
// 3. 监听 materialStore 的证据包变化
watch(() => materialStore.latestEvidencePacket, (packet) => {
  if (packet?.packet) {
    localStorage.setItem('fuww_s2_evidence_packet', JSON.stringify(packet.packet))
  }
}, { deep: true })
```

### 改动 6：监听 generationStore 的 lastGenId 变化写入 localStorage

```javascript
// 4. 监听 generationStore 的 lastGenId 变化
watch(() => generationStore.lastGenId, (genId) => {
  if (genId) {
    localStorage.setItem('fuww_last_gen_id', genId)
  }
})
```

### 改动 7：onMounted 时恢复各 Tab 数据

```javascript
// 5. 在 onMounted 中恢复数据
onMounted(() => {
  // 恢复 gen_id 到 versionStore
  const cachedGenId = localStorage.getItem('fuww_last_gen_id')
  if (cachedGenId && versionStore && !versionStore.genId) {
    versionStore.genId = cachedGenId
  }
  
  // 恢复 intent 数据到 material（如果当前 Tab 是 material）
  if (activeTab.value === 'material') {
    restoreIntentToMaterial()
  }
})
```

## 兼容性考虑

### 1. 避免与独立路由页面重复写入

成员 A 在 S1IntentPage 中写了 localStorage，成员 D 在 WorkspacePage 中也写了同样的 localStorage。这不是问题：
- 写入是幂等的（相同数据覆盖相同数据）
- WorkspacePage 的 watcher 覆盖了所有场景
- 独立路由页面和 WorkspacePage 不会同时使用

### 2. 避免重复触发

使用 `setTimeout(..., 100)` 延迟 Tab 切换后的恢复逻辑，确保目标组件已渲染完成。

### 3. 组件 ref 方式

如果 S2MaterialWorkspace 需要暴露方法给父组件，在 S2MaterialWorkspace.vue 中添加：

```javascript
// 在 S2MaterialWorkspace.vue 的 <script setup> 中
defineExpose({
  setSearchQuery(keywords) {
    searchQuery.value = keywords
    handleSearch()
  }
})
```

## 工作边界

- ❌ 不改任何 Store 的内部实现（只读不写）
- ❌ 不改任何独立路由页面的逻辑
- ❌ 不修改 S1/S2/S3/S4 的组件核心
- ✅ 只改 WorkspacePage.vue 一个文件

## 完成标准

- [ ] intent Tab → material Tab 切换：搜索框自动填充
- [ ] material Tab → script Tab 切换：证据自动传递
- [ ] script Tab → version Tab 切换：gen_id 自动填入
- [ ] 刷新后所有 Tab 间透传仍然有效
- [ ] Tab 切换时无页面报错
- [ ] 与独立路由页面的透传逻辑不冲突

## 验收步骤

1. 进入 WorkspacePage，切换到 intent Tab，输入意图并确认
2. 切换到 material Tab，观察搜索框是否自动填入 intent 关键词
3. 在 material Tab 上传资料并生成证据包
4. 切换到 script Tab，观察证据包是否可用
5. 在 script Tab 生成课件
6. 切换到 version Tab，观察 gen_id 是否自动填入
7. 刷新页面，重复步骤 2-6，确认刷新后数据不丢失
<template>
  <div v-if="visible" class="dialog-overlay" @click.self="!loading && $emit('cancel')" @keydown.esc.prevent="!loading && $emit('cancel')">
    <div class="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="revise-title">
      <div class="dialog-header">
        <div><h3 id="revise-title">AI 调整大纲</h3><p class="dialog-object">当前对象：整份课程大纲</p></div>
        <button class="dialog-close" :disabled="loading" @click="$emit('cancel')" aria-label="关闭">×</button>
      </div>

      <div class="dialog-body">
        <!-- AI 正在生成修订结果 -->
        <div v-if="loading" class="revise-loading">
          <div class="loading-spinner">⏳</div>
          <p>AI 正在生成修订方案...</p>
        </div>

        <template v-else-if="pendingNodes.length">
        <p class="dialog-hint">以下是 AI 返回的大纲草稿。现有后端会保存候选版本；采用后才会切换当前编辑视图。</p>

        <ul v-if="changeSummary.length" class="change-list">
          <li v-for="(item, i) in changeSummary" :key="i" class="change-item">
            <span class="change-icon">✓</span>
            <span>{{ item }}</span>
          </li>
        </ul>

        <div v-if="pendingNodes.length" class="revised-nodes">
          <h4>修订后大纲节点</h4>
          <div v-for="node in pendingNodes" :key="node.node_id" class="node-preview">
            <div class="node-preview-title">
              <span class="node-type-badge">{{ node.node_type }}</span>
              <strong>{{ node.title || '（无标题）' }}</strong>
              <span class="node-duration">⏱ {{ node.estimated_duration_minutes }}分钟</span>
            </div>
            <p class="node-preview-summary">{{ node.summary || '（无摘要）' }}</p>
            <ul v-if="node.key_points?.length" class="node-key-points">
              <li v-for="(kp, j) in node.key_points" :key="j">{{ kp }}</li>
            </ul>
          </div>
        </div>

        </template>
        <div v-else class="revision-compose">
          <p class="dialog-hint">描述希望如何调整整份大纲。提交后后端可能立即保存新的草稿版本。</p>
          <div v-if="errorMessage" class="revise-error" role="alert"><strong>AI 修订失败</strong><p>{{ errorMessage }}</p><span>输入内容已保留，可调整后重试。</span></div>
          <label for="outline-revision-message">修改要求</label>
          <textarea id="outline-revision-message" :value="message" rows="5" maxlength="500" placeholder="例如：增加课堂练习，并调整章节顺序" @input="$emit('update:message', $event.target.value)" @keydown.ctrl.enter.prevent="$emit('submit')"></textarea>
          <div class="suggestions"><span>常用建议</span><button v-for="item in suggestions" :key="item" type="button" @click="$emit('update:message', item)">{{ item }}</button></div>
          <p v-if="submitted && !errorMessage" class="dialog-hint">未返回可用修订结果，请调整要求后重试。</p>
        </div>
      </div>

      <div class="dialog-footer">
        <template v-if="pendingNodes.length">
          <button class="btn btn-outline" :disabled="loading" @click="$emit('cancel')">关闭查看（不撤销后端草稿）</button>
          <button class="btn btn-outline" :disabled="loading" @click="$emit('continue')">采用此版后继续调整</button>
          <button class="btn btn-primary" :disabled="loading" @click="$emit('apply')">采用此版大纲</button>
        </template>
        <template v-else>
          <button class="btn btn-outline" :disabled="loading" @click="$emit('cancel')">{{ submitted ? '关闭窗口（不撤销已提交操作）' : '关闭窗口' }}</button>
          <button class="btn btn-primary" :disabled="loading || !message.trim()" @click="$emit('submit')">{{ loading ? '正在生成…' : '提交并生成草稿' }}</button>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  changeSummary: { type: Array, default: () => [] },
  pendingNodes: { type: Array, default: () => [] },
  errorMessage: { type: String, default: '' },
  message: { type: String, default: '' },
  submitted: { type: Boolean, default: false }
})

defineEmits(['apply', 'continue', 'cancel', 'submit', 'update:message'])
const suggestions = ['精简章节结构', '增加课堂练习', '补充生活案例', '调整知识点顺序']
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.dialog-panel {
  background: #fff;
  border-radius: 16px;
  width: 90%;
  max-width: 620px;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}
.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px 14px;
  border-bottom: 1px solid #e2ece6;
}
.dialog-header h3 {
  margin: 0;
  font-size: 16px;
  color: #1e293b;
}
.dialog-object { margin: 4px 0 0; color: var(--text-secondary); font-size: var(--text-xs); }
.revision-compose { display: grid; gap: var(--space-3); }
.revision-compose label { color: var(--text-primary); font-size: var(--text-xs); font-weight: var(--weight-semibold); }
.revision-compose textarea { width: 100%; box-sizing: border-box; padding: var(--space-3); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); font: inherit; resize: vertical; }
.suggestions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); font-size: var(--text-xs); color: var(--text-secondary); }
.suggestions button { padding: var(--space-2); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: var(--bg-page); color: var(--text-primary); cursor: pointer; }
.dialog-close {
  background: none;
  border: none;
  font-size: 22px;
  color: #94a3b8;
  cursor: pointer;
  line-height: 1;
  padding: 2px 6px;
}
.dialog-close:hover { color: #475569; }
.dialog-body {
  padding: 18px 22px;
  overflow-y: auto;
  flex: 1;
}
.dialog-hint {
  margin: 0 0 14px;
  font-size: 13px;
  color: #64748b;
}
.revise-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 0;
  color: #64748b;
  font-size: 14px;
}
.loading-spinner { font-size: 28px; }
.revise-error {
  padding: 14px 16px;
  border: 1px solid #fecaca;
  border-radius: 10px;
  background: #fff1f2;
  color: #991b1b;
  font-size: 13px;
  line-height: 1.5;
}
.revise-error p { margin: 6px 0 2px; word-break: break-word; }
.revise-error span { color: #b45309; font-size: 12px; }
.change-list {
  list-style: none;
  padding: 0;
  margin: 0 0 18px;
}
.change-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  color: #2f605a;
}
.change-icon {
  color: #2f605a;
  font-weight: 700;
  flex-shrink: 0;
}
.revised-nodes h4 {
  margin: 0 0 10px;
  font-size: 13px;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.node-preview {
  padding: 10px 12px;
  border: 1px solid #e2ece6;
  border-radius: 10px;
  margin-bottom: 8px;
  background: #f8fbf9;
}
.node-preview-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 13px;
}
.node-type-badge {
  font-size: 12px;
  background: #2f605a;
  color: #fff;
  padding: 1px 6px;
  border-radius: 999px;
  flex-shrink: 0;
}
.node-duration {
  margin-left: auto;
  font-size: 12px;
  color: #94a3b8;
}
.node-preview-summary {
  margin: 0 0 6px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}
.node-key-points {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: #64748b;
}
.no-changes {
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
  padding: 20px 0;
}
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 22px;
  border-top: 1px solid #e2ece6;
}
.btn {
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
}
.btn-outline {
  background: #fff;
  border-color: #c6ded6;
  color: #2f605a;
}
.btn-outline:hover { background: #f0f5f2; }
.btn-primary {
  background: #2f605a;
  color: #fff;
}
.btn-primary:hover:not(:disabled) { background: #1e4a44; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
</style>

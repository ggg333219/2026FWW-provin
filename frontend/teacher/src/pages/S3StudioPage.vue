<template>
  <AppShell>
    <div class="s3-page">
      <div v-if="initializing" class="studio-loading" role="status" aria-live="polite">
        <span class="studio-spinner"></span><strong>正在恢复课件工作区</strong><p>正在加载 AI 对话、资料证据与生成记录，请稍候…</p>
      </div>
      <div v-else-if="asyncActivity" class="async-activity" role="status" aria-live="polite">
        <span class="async-spinner"></span>
        <div><strong>{{ asyncActivity.title }}</strong><small>{{ asyncActivity.detail }}</small></div>
        <span v-if="asyncActivity.progress != null" class="async-progress">{{ asyncActivity.progress }}%</span>
      </div>
      <!-- 页面头部 -->
      <header class="page-head">
        <div class="page-head__text">
          <p class="page-head__eyebrow">课件生成流程</p>
          <h1 class="page-head__title">S3 课件生成</h1>
          <p class="page-head__desc">规划大纲 → 生成讲稿和页面 → 审阅课件</p>
        </div>
        <div class="page-head__actions">
          <button v-if="projectStore.projectId" class="ds-btn ds-btn--secondary ds-btn--sm save-state" :class="projectStore.saveState" aria-live="polite" type="button" @click="projectStore.saveNow(draftSnapshot())">{{ projectStore.saveLabel || '保存草稿' }}</button>
          <button v-if="generationStore.currentScriptNodes.length" class="ds-btn ds-btn--secondary ds-btn--sm save-version" type="button" :disabled="saveVersionState === 'saving'" @click="handleSaveNewVersion">{{ saveVersionState === 'saving' ? '正在保存版本…' : (lastSavedVersion ? `已保存 v${lastSavedVersion}` : '保存新版本') }}</button>
        </div>
      </header>
      <StepNav current="s3" :project-id="projectStore.projectId" :action-keys="['s4']" @step-action="onStepAction" />
      <div v-if="genError && currentPhase !== 'content'" class="error-bar" role="alert">{{ genError }}</div>

      <!-- 模式提示条 -->
      <div
        v-if="generationMode === 'without_evidence'"
        class="evidence-warning"
        role="status"
      >
        <div>
          <strong>当前为无参考资料生成模式</strong>
          <span>本次内容仅依据 S1 教学意图生成，不会伪造资料引用。</span>
          <span v-if="evidenceBootstrapState === 'error'" role="alert">{{ evidenceBootstrapError }}</span>
        </div>
        <button class="ds-btn ds-btn--secondary ds-btn--sm" type="button" :disabled="evidenceBootstrapState === 'loading' || materialStore.searching" @click="reconnectKnowledgeBase">{{ evidenceBootstrapState === 'loading' ? '正在检索…' : '重新检索本地知识库' }}</button>
        <router-link :to="{ name: 'S2Material', query: { project_id: projectStore.projectId } }">返回补充资料</router-link>
      </div>
      <div v-if="knowledgeReconnectNotice" class="ds-notice ds-notice--info" role="status">{{ knowledgeReconnectNotice }}</div>

      <div v-if="evidenceBootstrapState === 'error' && requiresAutomaticEvidence" class="evidence-gate" role="alert">
        <div>
          <strong>自动检索尚未完成，已暂停生成大纲</strong>
          <span>{{ evidenceBootstrapError || '暂未检索到可绑定的证据，请重试或补充资料。' }}</span>
        </div>
        <div class="evidence-gate-actions">
          <button :disabled="materialStore.searching" @click="retryAutomaticEvidence">
            {{ materialStore.searching ? '正在检索…' : '重新自动检索' }}
          </button>
          <router-link :to="{ name: 'S2Material', query: { project_id: projectStore.projectId } }">上传补充资料</router-link>
          <button class="plain" @click="continueWithIntentOnly">仅按 S1 意图生成</button>
        </div>
      </div>

      <div v-if="baseVersion > 0" class="version-branch-banner" role="status">
        <strong>当前基于 v{{ baseVersion }} 编辑</strong>
        <span>保存后将生成 v{{ baseVersion + 1 }}，原版本不会被覆盖。</span>
      </div>

      <!-- S3 阶段指示器 -->
      <S3StageNav :phase="currentPhase" :outline-confirmed="outlineStore.isConfirmed" :review-ready="hasReviewContent" @select="currentPhase = $event" />

      <!-- 参考依据按需展开；AI 修改只在主动点击后挂载到模态窗口。 -->
      <div class="s3-workbench" :class="{ 's3-workbench--review': currentPhase === 'review' }">
      <!-- ==================== 大纲阶段 ==================== -->
      <!-- ==================== 大纲阶段 ==================== -->
      <div v-if="currentPhase !== 'review'" class="s3-assistant-col">
      <details class="s3-tool" :open="currentPhase !== 'review'">
        <summary>参考依据</summary>
      <EvidenceSidebar
        :packet="evidencePacket"
        :nodes="generationStore.currentScriptNodes.length ? generationStore.currentScriptNodes : outlineStore.nodes"
        :searching="materialStore.searching"
        :default-query="intentStore.intentSummary?.topic || ''"
        :selected-evidence-ids="selectedEvidenceIds"
        :selection-initialized="evidenceSelectionInitialized"
        @search="handleEvidenceSearch"
        @apply="handleEvidenceApply"
        @selection-change="handleEvidenceSelection"
      />
      </details>
      </div>
      <div v-if="currentPhase === 'outline'" class="phase-panel">
        <section class="outline-brief ds-card">
          <h2>{{ outlineStore.title || intentStore.intentSummary?.topic || '课程大纲' }}</h2>
          <p>预计课时：{{ intentStore.intentSummary?.duration_minutes ? `${intentStore.intentSummary.duration_minutes} 分钟` : '尚未设置' }}</p>
          <p>教学目标：{{ intentStore.intentSummary?.expected_outcomes?.length ? intentStore.intentSummary.expected_outcomes.join('；') : '请在大纲中核对教学目标' }}</p>
          <p>状态：{{ outlineStore.isConfirmed ? '大纲已确认；修改结构需按现有流程重新确认和生成下游内容' : '待确认' }}</p>
        </section>
        <OutlineEditor
          :session-id="intentStore.sessionId"
          :intent-id="intentStore.intentId"
          :intent-summary="intentStore.intentSummary"
          :evidence-packet="selectedEvidencePacket"
          :presentation="{ template_id: templateId, palette, layout: layoutMode, font_family: fontFamily, density }"
          :generation-mode="generationMode === 'without_evidence' ? 'without_evidence' : 'full_pipeline'"
          :page-generation-mode="generateMode"
          :ready="outlineReady"
          :auto-restore="!isVersionFork"
          :allow-auto-generate="!isVersionFork"
          @confirm-complete="handleOutlineConfirmed"
          @outline-created="handleOutlineCreated"
          @node-deleted="handleOutlineNodeDeleted"
          @error="handleError"
        />
        <details v-if="outlineStore.nodes.length" class="outline-references">
          <summary>查看章节关联的资料</summary>
          <ul><li v-for="node in outlineStore.nodes" :key="node.node_id"><strong>{{ node.title || '未命名章节' }}</strong><span>{{ outlineNodeSources(node) }}</span></li></ul>
          <p>关联资料表示已有来源记录，不代表章节内容已逐句核实。</p>
        </details>
        <div v-if="genError" class="error-bar" role="alert">
          {{ genError }}
        </div>
      </div>

      <!-- ==================== 内容生成阶段 ==================== -->
      <div v-else-if="currentPhase === 'content'" class="phase-panel">
        <!-- 大纲信息栏 -->
        <div class="content-info-bar">
          <div class="content-info-left">
            <span class="gen-label">大纲</span>
            <span class="gen-value">{{ outlineStore.isConfirmed ? '已确认' : '待确认' }}{{ outlineStore.outline_version ? ` · v${outlineStore.outline_version}` : '' }}</span>
            <span class="gen-label" style="margin-left: 12px">节点数</span>
            <span class="gen-value">{{ outlineStore.nodes.length }}</span>
          </div>
          <div class="content-info-right">
            <button
              v-if="
                !contentStore.isGenerating && ['idle', 'error'].includes(contentStore.status)
              "
              class="btn btn-primary"
              :disabled="!outlineStore.isConfirmed"
              @click="handleStartContentGeneration"
            >
              {{ contentStore.status === 'error' ? '重试生成讲稿' : '生成课件内容' }}
            </button>
            <button
              v-if="contentStore.status === 'done'"
              class="btn btn-outline"
              @click="goToGeneratingPhase"
            >
              {{ showPageGeneration ? '高级设置已展开' : '查看页面生成高级设置' }}
            </button>
          </div>
        </div>

        <!-- 内容生成进度 -->
        <div
          v-if="contentStore.isGenerating"
          class="gen-progress-panel"
        >
          <div class="progress-bar-wrap">
            <div
              class="progress-bar-fill"
              :style="{ width: contentStore.progress_pct + '%' }"
            ></div>
          </div>
          <div class="progress-text">
            <span>{{ contentStore.current_node_id ? `正在处理第 ${outlineStore.nodes.findIndex(node => node.node_id === contentStore.current_node_id) + 1} 节` : '讲稿生成中' }}</span>
            <span>{{ contentStore.progressText }}</span>
          </div>
        </div>

        <!-- 错误展示 -->
        <div v-if="contentStore.error" class="error-bar" role="alert">
          {{ contentStore.error }}
        </div>

        <!-- 节点讲稿列表 -->
        <div v-if="outlineStore.nodes.length > 0" class="content-nodes-list">
          <div
            v-for="node in outlineStore.nodes"
            :key="node.node_id"
            class="content-node-card"
            :class="{
              'node-done': contentStore.nodesContent[node.node_id],
              'node-pending':
                !contentStore.nodesContent[node.node_id] &&
                !contentStore.isGenerating,
              'node-current':
                contentStore.current_node_id === node.node_id &&
                contentStore.isGenerating,
            }"
          >
            <div class="node-header">
              <span class="node-order">第 {{ node.order }} 节</span>
              <span class="node-title">{{ node.title || "未命名节点" }}</span>
              <span
                class="node-badge"
                v-if="contentStore.nodesContent[node.node_id]"
                >✅ 已完成</span
              >
              <span
                class="node-badge node-badge-pending"
                v-else-if="
                  contentStore.isGenerating &&
                  contentStore.current_node_id === node.node_id
                "
                >⏳ 生成中</span
              >
              <span class="node-badge node-badge-empty" v-else>⏸ 待生成</span>
            </div>
            <div class="node-body">
              <!-- 已生成内容 -->
              <div
                v-if="contentStore.nodesContent[node.node_id]"
                class="node-content-area"
              >
                <div class="node-summary">{{ node.summary }}</div>
                <div class="node-script">
                  {{
                    contentStore.nodesContent[node.node_id].script ||
                    contentStore.nodesContent[node.node_id].lecture_script ||
                    "（内容生成中...）"
                  }}
                </div>
                <div v-if="node.key_points?.length" class="node-key-points">
                  <span
                    v-for="(kp, i) in node.key_points"
                    :key="i"
                    class="key-point-tag"
                  >
                    {{ kp }}
                  </span>
                </div>
                <div class="node-actions">
                  <button class="btn btn-sm" :disabled="contentStore.modifying || scriptSaving" @click="handleEditNodeScript(node.node_id)">
                    手工编辑
                  </button>
                  <button
                    class="btn btn-sm"
                    :disabled="contentStore.modifying || scriptSaving"
                    @click="handleModifyNode(node.node_id)"
                  >
                    ✏️ AI 修改
                  </button>
                </div>
              </div>
              <!-- 待生成占位 -->
              <div v-else class="node-placeholder">
                <span v-if="!contentStore.isGenerating"
                  >点击"生成全部节点讲稿"开始</span
                >
                <span v-else>等待生成...</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="modifyNodeId" class="content-modify-bar" role="dialog" aria-label="AI 修改节点">
          <div class="content-modify-title">修改第 {{ modifyNodeOrder }} 节内容</div>
          <input
            v-model="modifyMessage"
            class="content-modify-input"
            placeholder="例如：精简文字并增加一个生活案例"
            autofocus
            @keyup.enter="submitModifyNode"
          />
          <button
            class="btn btn-primary"
            :disabled="!modifyMessage.trim() || contentStore.modifying || scriptSaving"
            @click="submitModifyNode"
          >
            {{ contentStore.modifying ? "AI 修改中..." : scriptSaving ? "保存中…" : "发送修改" }}
          </button>
          <button class="btn btn-outline" :disabled="contentStore.modifying || scriptSaving" @click="cancelModifyNode">
            取消
          </button>
          <div v-if="contentStore.modifyError" class="content-modify-error" role="alert">
            {{ contentStore.modifyError }}
          </div>
        </div>

        <div v-if="outlineStore.nodes.length === 0" class="pages-empty">
          大纲中暂无节点，请先在大纲编辑中添加节点
        </div>
        <!-- 讲稿生成完成后，才开放原有页面生成调用。 -->
        <section v-if="contentStore.status === 'done' || generationStore.lastTaskId" class="page-generation">
        <div class="section-heading"><h3>生成课件页面</h3><span>讲稿 → 页面，按原顺序执行</span></div>
        <button class="btn btn-primary" :disabled="pageGenerationActive || !canStartPageGeneration(contentStore.status)" @click="handleStartGeneration">{{ pageGenerationActive ? '页面生成中…' : genError ? '重试生成课件页面' : '生成课件页面' }}</button>
        <details class="generation-advanced" :open="showPageGeneration" @toggle="showPageGeneration = $event.target.open">
          <summary>高级设置：生成范围与页面策略</summary>
        <!-- 生成控制栏 -->
        <div class="gen-control-bar">
          <div class="gen-info">
            <span class="gen-label">大纲</span>
            <span class="gen-value">{{ outlineStore.isConfirmed ? '已确认' : '待确认' }}{{ outlineStore.outline_version ? ` · v${outlineStore.outline_version}` : '' }}</span>
            <span class="gen-label" style="margin-left: 12px">生成范围</span>
            <select v-model="generationScope" class="gen-mode-select">
              <option value="content_only">仅生成内容（沿用已确认大纲）</option>
              <option value="full_pipeline">全流程（重建大纲并生成内容）</option>
            </select>
            <span class="gen-label" style="margin-left: 12px">页面策略</span>
            <select v-model="generateMode" class="gen-mode-select">
              <option value="page_incremental">逐页增量生成</option>
              <option value="page_parallel">全页面并行生成</option>
            </select>
          </div>
        </div>
        </details>

        <!-- 进度展示 -->
        <div v-if="pageGenerationActive || genError" class="page-task-panel" :role="genError ? 'alert' : 'status'" aria-live="polite">
          <h4>当前任务：生成课件页面</h4>
          <ol class="page-task-steps">
            <li><span>大纲确认</span><strong>{{ outlineStore.isConfirmed ? '已确认' : '待确认' }}</strong></li>
            <li><span>讲稿生成</span><strong>{{ contentStore.status === 'done' ? '已完成' : contentStore.isGenerating ? '进行中' : '未完成' }}</strong></li>
            <li><span>页面生成</span><strong>{{ genError ? '失败' : pageTaskStatusText }}</strong></li>
          </ol>
          <p v-if="pageGenerationActive">{{ generationStore.generateStageText || '任务正在执行，可查看已生成的讲稿。' }}</p>
          <p v-else-if="genError">{{ genError }}。请核对错误后使用上方“重试生成课件页面”。</p>
          <p v-if="pageGenerationActive">页面生成完成并加载预览后，可进入审阅。</p>
        </div>

        <!-- 错误展示 -->

        <!-- 生成的节点树预览 -->
        <div
          v-if="generationStore.currentScriptNodes.length > 0"
          class="gen-nodes-preview"
        >
          <h4>已生成节点</h4>
          <div class="nodes-summary">
            <span
              v-for="(node, i) in generationStore.currentScriptNodes"
              :key="i"
              class="node-chip"
            >
              {{ i + 1 }}.
              {{ node.title || node.node_title || "节点" + (i + 1) }}
            </span>
          </div>
        </div>

        <!-- 无参考资料提示 -->
        <div v-if="!hasEvidence" class="no-evidence-hint">
          ⚠️ 当前无参考资料，内容将基于 S1 意图自动生成。
          <router-link :to="{ name: 'S2Material' }"
            >前往 S2 补充资料</router-link
          >
        </div>

        <!-- 生成完成后操作 -->
        <div
          v-if="hasReviewContent && !generationStore.isGenerating && !genError"
          class="gen-complete-actions"
        >
          <button class="btn btn-primary" @click="currentPhase = 'review'">
            进入课件审阅
          </button>
        </div>
        </section>
      </div>

      <!-- 审阅：预览为主，页面列表与修改工具围绕当前页面。 -->
      <div v-else-if="currentPhase === 'review'" class="phase-panel review-panel">
        <section class="review-preview preview-section">
          <div class="preview-toolbar"><strong>课件页面预览</strong><div class="review-toolbar-actions">
            <button class="btn btn-sm" :disabled="!activeReviewNode?.node_id || !projectStore.projectId" @click="openPageModify(activeReviewNode)">AI 修改本页</button>
            <button class="btn btn-sm" :disabled="!activeReviewNode || !contentStore.nodesContent[activeReviewNode.node_id]" @click="handleEditNodeScript(activeReviewNode.node_id)">编辑讲稿</button>
            <button class="btn btn-sm" @click="reviewTool = 'style'">调整样式</button>
            <button class="btn btn-sm" @click="reviewTool = 'interactive'">互动内容</button>
            <button class="btn btn-sm" @click="reviewTool = 'evidence'">参考依据</button>
            <button class="btn btn-sm" @click="reviewTool = 'script'">查看讲稿</button>
            <button class="btn btn-sm" :disabled="!projectStore.projectId" @click="openGlobalModify">AI 修改整套课件</button>
            <button class="btn btn-sm" @click="openPreviewWindow">新窗口打开</button>
          </div></div>
          <div class="review-primary-actions"><button class="btn btn-outline" :disabled="saveVersionState === 'saving'" @click="handleSaveNewVersion">{{ saveVersionState === 'saving' ? '正在保存版本…' : '保存新版本' }}</button><button class="btn btn-primary" @click="goToS4">下一步：版本管理与导出 →</button></div>
          <iframe v-if="previewSrcDoc" ref="previewFrameEl" :srcdoc="previewSrcDoc" class="preview-frame" sandbox="allow-scripts allow-same-origin" title="课件预览" @load="previewFrameReady = true; scrollPreviewToActivePage()"></iframe>
          <div v-else class="preview-placeholder">正在恢复预览；可刷新生成状态</div>
          <p class="review-selection">{{ activePageLabel ? `当前选择：${activePageLabel}` : '先在左侧选择一页，再使用“AI 修改本页”。' }}</p>
        </section>
        <div class="review-pages">
          <h3>课件页面</h3>
          <button class="btn btn-sm" @click="loadGenerationStatus">刷新页面状态</button>
        <div class="pages-control-bar">
          <div class="pages-actions">
            <button class="btn btn-sm" @click="loadGenerationStatus">
              🔄 刷新状态
            </button>
          </div>
        </div>

        <!-- 页面列表 -->
        <div v-if="generationPages.length > 0" class="pages-list">
          <div
            v-for="page in generationPages"
            :key="page.page_id"
            class="page-item"
            :class="[`page-status-${page.status}`, {
              'page-modified': modifyStore.recentlyModifiedIds.includes(page.node_id),
              'page-active': isActivePage(page),
            }]"
            role="button"
            tabindex="0"
            :aria-pressed="isActivePage(page)"
            @click="selectPage(page)"
            @keydown.enter.prevent="selectPage(page)"
            @keydown.space.prevent="selectPage(page)"
          >
            <div class="page-item-left">
              <span class="page-order">第 {{ page.page_order }} 页</span>
              <span class="page-node">{{ page.title || page.node_title || '未命名页面' }}</span>
              <span v-if="modifyStore.recentlyModifiedIds.includes(page.node_id)" class="changed-badge">已修改</span>
              <small class="page-evidence-state">{{ pageEvidenceStatus(page) }}</small>
            </div>
            <div class="page-item-right">
              <span class="page-status-badge">{{
                statusLabel(page.status)
              }}</span>
              <button
                v-if="isGeneratedPageOutsideOutline(page, outlineStore.nodes)"
                class="btn btn-sm"
                title="此页已不在大纲中；移除后保存新版本，旧版本不受影响"
                @click.stop="handleOutlineNodeDeleted(page.source_node_id || page.node_id)"
              >移除旧页</button>
              <button
                v-if="page.status === 'failed'"
                class="btn btn-sm"
                :disabled="regeneratingPageId === page.page_id"
                @click="handleRegeneratePage(page)"
              >
                {{
                  regeneratingPageId === page.page_id
                    ? "重生成中..."
                    : "🔄 重试"
                }}
              </button>
              <button
                v-if="page.status === 'done'"
                class="btn btn-sm"
                @click="handlePreviewPage(page)"
              >
                👁 预览
              </button>
            </div>
          </div>
        </div>

        <div v-else class="pages-empty">暂无页面数据，请先生成内容</div>
        </div>
        <div v-if="reviewTool" class="review-drawer-backdrop" @click="reviewTool = ''"></div>
        <aside v-if="reviewTool" class="review-drawer" role="dialog" aria-modal="true" :aria-label="reviewToolTitle" @keydown.esc.prevent="reviewTool = ''">
          <header class="review-drawer-header"><h3>{{ reviewToolTitle }}</h3><button type="button" class="ds-btn ds-btn--ghost ds-btn--sm" aria-label="关闭工具抽屉" @click="reviewTool = ''">关闭</button></header>
          <section v-if="reviewTool === 'style'" class="style-panel">
          <h3>只调整呈现，不改教学事实</h3>
          <p>样式设置不会触发 RAG 检索，也不会修改大纲、引用或生成内容。</p>
          <label>全局模板 <select v-model="templateId"><option value="default">默认教学模板</option><option value="deck-swiss-edu">瑞士教育风</option></select></label>
          <label>配色 <select v-model="palette"><option value="classic">经典青绿</option><option value="klein-blue">克莱因蓝</option></select></label>
          <label>版式 <select v-model="layoutMode"><option value="balanced">图文均衡</option><option value="visual">视觉优先</option><option value="text">内容优先</option></select></label>
          <label>字体 <select v-model="fontFamily"><option value="system">系统默认</option><option value="source-han">思源黑体</option><option value="serif">中文宋体</option></select></label>
          <label>信息密度 <select v-model="density"><option value="comfortable">舒展</option><option value="compact">紧凑</option><option value="minimal">极简</option></select></label>
          <div class="style-ai-hint">需要 AI 调整时可使用预览工具栏的“AI 修改本页”或“AI 修改整套课件”。</div>
          <div class="style-actions"><button class="btn btn-outline" @click="projectStore.saveNow(draftSnapshot())">保存样式草稿</button><button class="btn btn-primary" :disabled="generationStore.previewLoading" @click="applyPresentationStyle">{{ generationStore.previewLoading ? '正在刷新…' : '应用并刷新预览' }}</button></div>
          </section>
          <section v-if="reviewTool === 'script'" class="review-script-tool">
          <p v-if="!activeReviewNode">先从页面列表选择一页。</p>
          <template v-else>
            <strong>{{ activeReviewNode.title || activeReviewNode.node_title }}</strong>
            <p class="review-script">{{ contentStore.nodesContent[activeReviewNode.node_id]?.script || activeReviewNode.script || '当前页暂无讲稿' }}</p>
            <button v-if="contentStore.nodesContent[activeReviewNode.node_id]" class="btn btn-sm" @click="handleEditNodeScript(activeReviewNode.node_id)">编辑讲稿</button>
            <button v-if="contentStore.nodesContent[activeReviewNode.node_id]" class="btn btn-sm" @click="handleModifyNode(activeReviewNode.node_id)">AI 修改讲稿</button>
          </template>
          <div v-if="modifyNodeId" class="content-modify-bar" role="dialog" aria-label="AI 修改讲稿"><input v-model="modifyMessage" class="content-modify-input" placeholder="描述希望修改的讲稿内容" @keyup.enter="submitModifyNode" /><button class="btn btn-primary" :disabled="!modifyMessage.trim() || contentStore.modifying || scriptSaving" @click="submitModifyNode">发送修改</button><button class="btn btn-outline" @click="cancelModifyNode">取消</button><div v-if="contentStore.modifyError" class="content-modify-error" role="alert">{{ contentStore.modifyError }}</div></div>
          </section>

        <!-- 互动资源入口 -->
          <section v-if="reviewTool === 'interactive'" class="interactive-section">
          <h4>🎮 互动资源管理</h4>
          <p class="interactive-hint">
            从大纲中标记为互动的节点可在此生成 HTML5 互动资源
          </p>
          <p v-if="!generationStore.lastGenId" class="interactive-error" role="alert">
            当前页面没有课件生成记录，请先完成“内容生成”后再生成互动。
          </p>
          <p v-if="interactiveStore.error" class="interactive-error" role="alert">
            {{ interactiveStore.error }}
          </p>
          <div class="interactive-node-list">
            <div
              v-for="node in interactiveNodes"
              :key="node.node_id"
              class="interactive-node-row"
            >
              <div class="int-node-info">
                <span class="int-node-title">{{ node.title }}</span>
                <span class="int-node-type">{{ node.node_type }}</span>
              </div>
              <div class="int-node-actions">
                <template v-if="interactiveStore.hasAsset(node.node_id)">
                  <span class="asset-done">✅ 已生成</span>
                  <span v-if="interactiveStore.getAsset(node.node_id)?.items?.length" class="asset-count">
                    {{ interactiveStore.getAsset(node.node_id).items.length }} 项内容
                  </span>
                  <button
                    v-if="interactiveStore.getAsset(node.node_id)?.entry_url"
                    class="btn btn-sm"
                    @click="openInteractiveAsset(node)"
                  >
                    页面内预览
                  </button>
                  <button class="btn btn-sm" :disabled="interactiveStore.loading" @click="handleGenerateInteractive(node)">
                    重新生成互动
                  </button>
                </template>
                <template
                  v-else-if="
                    interactiveStore.getAsset(node.node_id)?.status ===
                    'processing'
                  "
                >
                  <span class="asset-pending">⏳ 生成中...</span>
                </template>
                <template v-else>
                  <button
                    class="btn btn-sm btn-primary"
                    :disabled="interactiveStore.loading || !generationStore.lastGenId"
                    @click="handleGenerateInteractive(node)"
                  >
                    {{ interactiveStore.loading ? "生成中..." : (node.interactive_plan?.kind === 'flashcard' ? '生成并保存翻卡' : '生成互动') }}
                  </button>
                </template>
              </div>
            </div>
            <p v-if="interactiveNodes.length === 0" class="no-interactive-hint">
              大纲中无互动节点，可在编辑大纲时将节点类型改为"互动环节"
            </p>
          </div>
          <div v-if="interactivePreviewUrl" class="interactive-preview-card">
            <div class="interactive-preview-head">
              <div><strong>HTML5 互动预览</strong><span>{{ interactivePreviewTitle }}</span></div>
              <div><button class="btn btn-sm" @click="openInteractiveWindow">新窗口打开</button><button class="btn btn-sm" @click="closeInteractivePreview">关闭</button></div>
            </div>
            <iframe :src="interactivePreviewUrl" class="interactive-preview-frame" sandbox="allow-scripts allow-same-origin allow-forms" title="HTML5 互动资源预览"></iframe>
          </div>
          </section>
          <section v-if="reviewTool === 'evidence'" class="review-evidence-tool">
            <EvidenceSidebar :packet="evidencePacket" :nodes="generationStore.currentScriptNodes.length ? generationStore.currentScriptNodes : outlineStore.nodes" :searching="materialStore.searching" :default-query="intentStore.intentSummary?.topic || ''" :selected-evidence-ids="selectedEvidenceIds" :selection-initialized="evidenceSelectionInitialized" @search="handleEvidenceSearch" @apply="handleEvidenceApply" @selection-change="handleEvidenceSelection" />
          </section>
        </aside>
      </div>
      </div><!-- /.s3-workbench -->
      <div v-if="editScriptNodeId" class="s3-modify-overlay" @click.self="cancelEditNodeScript" @keydown.esc.prevent="cancelEditNodeScript">
        <section class="s3-modify-dialog script-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="script-edit-title">
          <header class="s3-modify-header"><div><h2 id="script-edit-title">编辑讲稿</h2><p>当前章节：{{ editScriptNodeTitle }}</p></div><button type="button" class="ds-btn ds-btn--ghost ds-btn--sm" :disabled="scriptSaving" @click="cancelEditNodeScript">关闭</button></header>
          <div class="script-edit-body"><label for="script-edit-text">讲稿内容</label><textarea id="script-edit-text" v-model="editScriptDraft" class="content-script-textarea" rows="12" autofocus /><div v-if="scriptSaveError" class="content-modify-error" role="alert">{{ scriptSaveError }}</div></div>
          <footer class="script-edit-footer"><button class="btn btn-outline" :disabled="scriptSaving" @click="cancelEditNodeScript">取消</button><button class="btn btn-primary" :disabled="!editScriptDraft.trim() || scriptSaving" @click="saveEditedNodeScript">{{ scriptSaving ? '保存中…' : '保存讲稿' }}</button></footer>
        </section>
      </div>
      <div v-if="modifyDialog" class="s3-modify-overlay" @click.self="closeModifyDialog" @keydown.esc.prevent="closeModifyDialog">
        <section class="s3-modify-dialog" role="dialog" aria-modal="true" aria-labelledby="s3-modify-title">
          <header class="s3-modify-header"><div><h2 id="s3-modify-title">{{ modifyDialog.scope === 'page' ? 'AI 修改本页' : 'AI 修改整套课件' }}</h2><p>{{ modifyDialog.scope === 'page' ? `当前对象：第 ${modifyDialog.pageOrder} 页 · ${modifyDialog.title}` : '当前对象：整套课件' }}</p></div><button type="button" class="ds-btn ds-btn--ghost ds-btn--sm" :disabled="modifyStore.modifying" aria-label="关闭 AI 修改窗口" @click="closeModifyDialog">关闭</button></header>
          <p class="s3-modify-notice">提交后现有服务会立即更新课件草稿和版本；关闭窗口不会撤销已执行的修改。{{ modifyDialog.scope === 'page' ? '如指令涉及其他页面，实际修改范围以服务返回为准。' : '' }}</p>
          <p v-if="modifyStore.pendingTaskId" class="s3-modify-notice">修改任务仍可能在后台执行，关闭窗口不代表取消任务。</p>
          <ModifyPanel :scope="modifyDialog.scope" :target-node-id="modifyDialog.nodeId" :include-special-pages="true" @style-request="handleStyleRequest" @applied="handleModifyApplied" />
        </section>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount, watch } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import AppShell from "../components/layout/AppShell.vue";
import StepNav from "../components/common/StepNav.vue";
import S3StageNav from "../components/teacher/S3StageNav.vue";
import { resolveS3Phase, canStartPageGeneration } from "../utils/s3Phase";
import OutlineEditor from "../components/teacher/OutlineEditor.vue";
import ModifyPanel from "../components/teacher/ModifyPanel.vue";
import EvidenceSidebar from "../components/teacher/EvidenceSidebar.vue";
import { useGenerationStore } from "../stores/generationStore";
import { useOutlineStore } from "../stores/outlineStore";
import { readResumeDraft } from "../utils/coursewareDraft";
import { useInteractiveStore } from "../stores/interactiveStore";
import { useContentStore } from "../stores/contentStore";
import { useIntentStore } from "../stores/intentStore";
import { useMaterialStore, isEvidencePacketUsable } from "../stores/materialStore";
import { useModifyStore } from "../stores/modifyStore";
import { useCoursewareProjectStore } from "../stores/coursewareProjectStore";
import { teacherV1Api } from "../services/v1";
import { projectModifyApi } from "../services/v1/projectModifyApi";
import { resolveSavedProjectVersion } from "../utils/coursewareVersion";
import { API_BASE, AI_API_BASE } from "../config/api";
import { buildIntentEvidenceQuery, evidenceIds, isPlaceholderOutline, shouldRequireOutlineEvidence } from "../utils/intentEvidence";
import { patchPreview, PATCH_MODE } from "../utils/previewPatch";
import { withGeneratedInteractiveAsset } from "../utils/interactiveExport";
import { outlineFromVersion } from "../utils/versionOutline";
import { filterDeletedOutlineNodes, isGeneratedPageOutsideOutline } from "../utils/outlineDeletion";

const generationStore = useGenerationStore();
const outlineStore = useOutlineStore();
const interactiveStore = useInteractiveStore();
const contentStore = useContentStore();
const modifyNodeId = ref("");
const modifyMessage = ref("");
const modifyNodeOrder = computed(() => outlineStore.nodes.findIndex((node) => node.node_id === modifyNodeId.value) + 1);
const editScriptNodeId = ref("");
const editScriptDraft = ref("");
const editScriptNodeTitle = computed(() => outlineStore.nodes.find((node) => node.node_id === editScriptNodeId.value)?.title || "当前节点");
const scriptSaving = ref(false);
const scriptSaveError = ref("");
const intentStore = useIntentStore();
const materialStore = useMaterialStore();
const modifyStore = useModifyStore();
const projectStore = useCoursewareProjectStore();
const route = useRoute();
const router = useRouter();
const isVersionFork = computed(() => Boolean(route.query.from_rollback_version || route.query.editable_outline));

// UI 阶段：outline | content | review；旧阶段在恢复入口统一映射。
const currentPhase = ref("outline");
const reviewTool = ref("");
const reviewToolTitle = computed(() => ({ style: '调整样式', interactive: '互动内容', evidence: '参考依据', script: '讲稿查看与修改' })[reviewTool.value] || '审阅工具');
const showPageGeneration = ref(false);
const pageTaskStatus = ref('idle');
const pageGenerationActive = computed(() => generationStore.isGenerating || ['pending', 'processing', 'generating'].includes(pageTaskStatus.value));
const pageTaskStatusText = computed(() => ({ pending: '等待处理', processing: '处理中', generating: '生成中', done: '已完成', completed: '已完成', success: '已完成', failed: '失败', error: '失败' })[pageTaskStatus.value] || (generationStore.isGenerating ? '处理中' : '未开始'));
const modifyDialog = ref(null);
const generationMode = ref("");
const generateMode = ref("page_incremental");
const generationScope = ref("content_only");
const genError = ref("");
const generationPages = ref([]);
const deletedOutlineNodeIds = ref([]);
const needsVersionSave = ref(false);
const regeneratingPageId = ref("");
const previewFrameEl = ref(null);
/** iframe 当前承载的文档。补丁成功时不更新它 —— 更新了 Vue 就会重设 srcdoc，等于整份重载。 */
const previewSrcDoc = ref("");
/** iframe 里的文档已经加载完，contentDocument 可用。 */
const previewFrameReady = ref(false);
const activePageLabel = computed(() => {
  const nodeId = modifyStore.activeNodeId;
  if (!nodeId) return "";
  const index = generationPages.value.findIndex((page) => page.node_id === nodeId);
  if (index < 0) return "";
  const page = generationPages.value[index];
  const title = page.title || page.node_title || "";
  return `第 ${page.page_order || index + 1} 页${title ? ` · ${title}` : ""}`;
});
const isActivePage = (page) => !!page?.node_id && page.node_id === modifyStore.activeNodeId;
const activeReviewNode = computed(() => generationPages.value.find(isActivePage) || null);
const hasReviewContent = computed(() =>
  generationStore.currentScriptNodes.length > 0 && Boolean(generationStore.previewHtml)
  && !['pending', 'processing', 'generating', 'failed', 'error'].includes(pageTaskStatus.value)
  && !contentStore.isGenerating && contentStore.status !== 'error'
  && !generationStore.isGenerating && !genError.value,
);
const selectPage = (page) => {
  if (modifyDialog.value) return;
  // 再点一次取消选中 —— 取消后指令里的显式页号（「第三页」）仍然照常生效
  modifyStore.setActiveNode(isActivePage(page) ? "" : page.node_id);
  void nextTick(scrollPreviewToActivePage);
};
function openPageModify(page) {
  if (!page?.node_id || modifyStore.modifying || !projectStore.projectId) return;
  if (modifyStore.activeNodeId && modifyStore.activeNodeId !== page.node_id) {
    modifyStore.pendingClarification = null;
    modifyStore.pendingConfirmation = null;
    modifyStore.confirmationReady = false;
  }
  modifyStore.setActiveNode(page.node_id);
  modifyDialog.value = {
    scope: 'page', nodeId: String(page.node_id), pageId: String(page.page_id || page.node_id),
    pageOrder: Number(page.page_order || 1), title: page.title || page.node_title || '未命名页面',
  };
}
function openGlobalModify() {
  if (modifyStore.modifying || !projectStore.projectId) return;
  if (modifyStore.activeNodeId) {
    modifyStore.pendingClarification = null;
    modifyStore.pendingConfirmation = null;
    modifyStore.confirmationReady = false;
  }
  modifyStore.setActiveNode('');
  modifyDialog.value = { scope: 'global', nodeId: '', pageId: '', pageOrder: 0, title: '' };
}
function closeModifyDialog() {
  if (modifyStore.modifying) return;
  modifyDialog.value = null;
}
function scrollPreviewToActivePage() {
  const nodeId = modifyStore.activeNodeId;
  if (!nodeId) return;
  try {
    const pages = [...(previewFrameEl.value?.contentDocument?.querySelectorAll('[data-node-id]') || [])];
    pages.find(element => element.getAttribute('data-node-id') === nodeId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch {
    // iframe 未加载时仍保留页面列表选择。
  }
}
const templateId = ref("default");
const palette = ref("classic");
const layoutMode = ref("balanced");
const fontFamily = ref("system");
const density = ref("comfortable");
const evidencePacket = ref(null);
const selectedEvidenceIds = ref([]);
const evidenceSelectionInitialized = ref(false);
const evidenceScope = ref({ scope: "draft", nodeId: "" });
const saveVersionState = ref("idle");
const lastSavedVersion = ref(0);
const baseVersion = ref(Number(route.query.base_version || 0));
const interactivePreviewUrl = ref("");
const interactivePreviewTitle = ref("");
const initializing = ref(true);
const outlineReady = ref(false);
const evidenceBootstrapState = ref("idle");
const evidenceBootstrapError = ref("");
const knowledgeReconnectNotice = ref("");
// Every new outline needs the S2 evidence handoff unless the teacher explicitly
// chose the intent-only path. Older links do not carry auto_evidence=1.
const requiresAutomaticEvidence = computed(() =>
  shouldRequireOutlineEvidence({
    generationMode: generationMode.value,
    isVersionFork: isVersionFork.value,
    outlineId: outlineStore.outline_id,
    nodeCount: outlineStore.nodes.length,
  }),
);

const asyncActivity = computed(() => {
  if (modifyStore.modifying) {
    // 说得出是哪一页，老师就知道自己刚才那句点中了没有，不必等结果回来
    return {
      title: "AI 正在修改课件",
      detail: activePageLabel.value
        ? `正在修改${activePageLabel.value}，完成后预览里只有这一页会更新。`
        : "正在理解指令并局部更新相关页面，完成后会自动刷新预览。",
    };
  }
  if (materialStore.searching) return { title: "正在检索资料与证据", detail: "正在从知识库筛选并融合可追溯引用。" };
  if (generationStore.isGenerating) return { title: "正在生成课件页面", detail: generationStore.generateStageText || "AI 正在逐页生成，请保持当前页面打开。" };
  if (interactiveStore.loading) return { title: "正在生成互动内容", detail: "正在构建可预览的 HTML5 互动资源。" };
  if (regeneratingPageId.value) return { title: "正在重新生成当前页面", detail: "其他页面不会受到影响。" };
  return null;
});

const evidenceId = (item, index) => String(item?.chunk_id || item?.id || `evidence-${index}`);
const selectedEvidencePacket = computed(() => {
  if (!evidencePacket.value) return null;
  if (!evidenceSelectionInitialized.value) return evidencePacket.value;
  const selected = new Set(selectedEvidenceIds.value);
  const filter = (items = []) => items.filter((item, index) => selected.has(evidenceId(item, index)));
  return {
    ...evidencePacket.value,
    citations: filter(evidencePacket.value.citations || []),
    relevant_chunks: filter(evidencePacket.value.relevant_chunks || []),
  };
});

function draftSnapshot() {
  return {
    intent: intentStore.intentSummary || null,
    outline: {
      outline_id: outlineStore.outline_id,
      outline_version: outlineStore.outline_version,
      status: outlineStore.status,
      title: outlineStore.title,
      forked_from_version: outlineStore.forked_from_version,
      editable_after_rollback: outlineStore.forked_from_version > 0,
      nodes: outlineStore.nodes,
    },
    content: {
      content_id: contentStore.content_id,
      status: contentStore.status,
      nodes: contentStore.nodesContent,
      edited_node_ids: contentStore.editedNodeIds,
    },
    generation: {
      generation_id: generationStore.lastGenId,
      task_id: generationStore.lastTaskId,
      nodes: generationStore.currentScriptNodes,
    },
    deleted_outline_node_ids: deletedOutlineNodeIds.value,
    needs_version_save: needsVersionSave.value,
    evidence_packet: selectedEvidencePacket.value,
    evidence_selection: selectedEvidenceIds.value,
    evidence_scope: evidenceScope.value,
    page_bindings: versionPageBindings(),
    presentation: {
      template_id: templateId.value,
      palette: palette.value,
      layout: layoutMode.value,
      font_family: fontFamily.value,
      density: density.value,
    },
    generation_instruction_set: buildGenerationInstructionSet(selectedEvidencePacket.value, generationScope.value),
  };
}

function versionPageBindings() {
  return generationPages.value.map((page) => ({
    page_id: page.page_id,
    node_id: page.node_id,
    page_order: page.page_order,
    evidence_refs: [...new Set([...(page.citation_refs || []), ...(page.source_chunk_ids || [])])],
    auto_bound: Boolean(page.metadata?.evidence_auto_bound),
    bound_by: page.metadata?.evidence_bound_by || "",
    interactive_asset_id: page.metadata?.interactive_asset?.interactive_asset_id || "",
  }));
}

// 是否有参考资料
const hasEvidence = computed(() => {
  return !!evidencePacket.value;
});

// 需要互动资源的节点（大纲中标记为 interactive / quiz 的节点）
const interactiveNodes = computed(() =>
  (outlineStore.nodes?.length ? outlineStore.nodes : generationStore.currentScriptNodes || []).filter((n) => {
    const nodeType = n.node_type || n.type || "";
    return nodeType === "interactive" || nodeType === "quiz" || n.metadata?.interactive || n.interactive_plan;
  }),
);

onMounted(async () => {
	try {
	let restoredGenerationNodes = false;
	let restoredProjectOutline = false;
  let legacyPhase = String(route.query.phase || '');
  // 恢复 S1 会话/意图（刷新或直接进入 S3 时 store 内存为空，
  // 不恢复会导致 sessionId 缺失 → AI 生成大纲被 "缺少 session_id" 拦截）
  const projectId = String(route.query.project_id || projectStore.projectId || projectStore.restoreActiveId() || '');
  projectStore.setActive(projectId);
  intentStore.initialize(projectId);
  materialStore.activeSessionId = intentStore.sessionId || projectStore.projectId || "";
  if (typeof window !== "undefined") {
    generationMode.value =
      window.localStorage.getItem(
        `fuww_s2_generation_mode:${intentStore.sessionId}`,
      ) || "";
    try {
      const rawEvidence = window.localStorage.getItem(`fuww_s2_evidence_packet:${intentStore.sessionId}`);
      evidencePacket.value = rawEvidence ? JSON.parse(rawEvidence) : null;
    } catch { evidencePacket.value = null; }
  }

  // project_id 才是 AI 对话、草稿与版本的边界；generation_id 只是该项目的生成结果。
  const previousProjectId = projectStore.projectId || projectStore.restoreActiveId() || "";
  projectStore.setActive(String(route.query.project_id || previousProjectId));
  const hasProject = Boolean(projectStore.projectId);
  if (isVersionFork.value || !hasProject || previousProjectId !== projectStore.projectId) {
    outlineStore.reset();
    generationStore.reset();
    contentStore.reset();
  }
  if (projectStore.projectId) {
    // 内容缓存原先是全局 key；以项目草稿为准，避免切换课件时串入上一项目讲稿。
    contentStore.reset();
    // 契约 v1.0 §3.2：按 project_id 拉 /latest-generation-context 作为权威读源，
    // 一次性拿到项目 + 最新版本 + 当前所有页绑定，避免"切 PPT 不重置 AI 对话"
    // 和"左侧资料绑定打开 PPT 不显示"。loadLatestContext 内部会先 bindProject
    // 把内存对话清空，再用响应填回 version_no / pageBindings。
    await modifyStore.loadLatestContext(projectStore.projectId);
    // loadLatestContext 只播下最新一条版本摘要，完整时间线仍要单独拉。
    await modifyStore.loadVersionHistory();
    // 刷新或直接打开 S3 时以后端草稿为准，不能只依赖页面跳转留下的本地缓存。
    await projectStore.resume(projectStore.projectId).catch(() => {});
    await projectStore.updateStep("s3_studio").catch(() => {});
    // 项目身份明确时只恢复服务端项目草稿，不读无项目归属的旧全局缓存。
    try {
      const backendDraft = projectStore.draft;
      let savedDraft = backendDraft;
      if (typeof savedDraft === "string") {
        try { savedDraft = JSON.parse(savedDraft) || null; } catch { savedDraft = null; }
      }
      // 兼容旧版后端曾直接保存的节点数组，避免历史课件刷新后变成空白。
      if (Array.isArray(savedDraft)) savedDraft = { generation: { nodes: savedDraft } };
      if (!legacyPhase) legacyPhase = String(savedDraft?.phase || savedDraft?.current_phase || '');
      // 保存版本时后端把草稿写成 canonical snapshot（content 数组）。刷新 S3 时
      // 仍须把这批节点恢复为生成结果，否则已保存的翻卡素材会从页面状态中消失。
      if (savedDraft && !savedDraft.generation && Array.isArray(savedDraft.content)) {
        savedDraft = { ...savedDraft, generation: { nodes: savedDraft.content } };
      }
      if (!savedDraft || typeof savedDraft !== "object" || (!savedDraft.outline && !savedDraft.generation)) {
        savedDraft = readResumeDraft(projectStore.projectId) || null;
        if (Array.isArray(savedDraft)) savedDraft = { generation: { nodes: savedDraft } };
      }
      deletedOutlineNodeIds.value = Array.isArray(savedDraft?.deleted_outline_node_ids)
        ? savedDraft.deleted_outline_node_ids.map(String) : [];
      needsVersionSave.value = Boolean(savedDraft?.needs_version_save);
      const editableFork = Boolean(
        savedDraft?.outline?.editable_after_rollback
        || route.query.from_rollback_version
        || route.query.editable_outline,
      );
      if (savedDraft?.outline && (savedDraft.outline.outline_id || savedDraft.outline.nodes?.length || editableFork)) {
        if (editableFork) {
          outlineStore.restoreEditableSnapshot(savedDraft.outline);
        } else {
          outlineStore._applyOutlineData(savedDraft.outline);
        }
        outlineStore._persist();
        restoredProjectOutline = true;
      }
      if (savedDraft?.content?.nodes && typeof savedDraft.content.nodes === "object") {
        contentStore.content_id = savedDraft.content.content_id || "";
        contentStore.nodesContent = savedDraft.content.nodes;
        contentStore.editedNodeIds = Array.isArray(savedDraft.content.edited_node_ids) ? savedDraft.content.edited_node_ids : [];
        contentStore.status = ['done', 'pending', 'generating', 'error'].includes(savedDraft.content.status) ? savedDraft.content.status : 'idle';
        contentStore.progress_pct = Number(savedDraft.content.progress_pct) || 0;
        contentStore.current_node_id = savedDraft.content.current_node_id || '';
        contentStore.total_nodes = Number(savedDraft.content.total_nodes) || outlineStore.nodes.length;
        contentStore.completed_nodes = Number(savedDraft.content.completed_nodes) || 0;
        contentStore.error = savedDraft.content.error || '';
        contentStore._persist();
        if (contentStore.isGenerating && contentStore.content_id) {
          await contentStore.pollStatus();
          if (contentStore.isGenerating) contentStore._startPolling();
        } else if (contentStore.status === 'error' && contentStore.content_id) {
          await contentStore.pollStatus();
        } else if (contentStore.isGenerating) {
          contentStore.status = 'error';
          contentStore.error = '讲稿任务记录缺失，请重新生成';
        }
      } else {
        // 保存版本后的 canonical 草稿把 content 存为节点数组，仍允许回到内容层编辑讲稿。
        const scriptNodes = Array.isArray(savedDraft?.content)
          ? savedDraft.content
          : (Array.isArray(savedDraft?.generation?.nodes) ? savedDraft.generation.nodes : []);
        const restoredScripts = Object.fromEntries(
          scriptNodes.filter((node) => node?.node_id && typeof node.script === "string" && node.script.trim())
            .map((node) => [node.node_id, node]),
        );
        if (Object.keys(restoredScripts).length) {
          contentStore.nodesContent = restoredScripts;
          contentStore.status = "done";
          contentStore._persist();
        }
      }
      if (savedDraft?.generation) {
        pageTaskStatus.value = savedDraft.generation.status || 'idle';
        if (['failed', 'error'].includes(pageTaskStatus.value)) genError.value = savedDraft.generation.error || '课件页面生成失败，请在内容阶段重试';
        if (savedDraft.generation.generation_id) generationStore.setLastGenId(savedDraft.generation.generation_id);
        if (savedDraft.generation.task_id) generationStore.setLastTaskId(savedDraft.generation.task_id);
        if (Array.isArray(savedDraft.generation.nodes) && savedDraft.generation.nodes.length) {
          const restoredNodes = filterDeletedOutlineNodes(
            savedDraft.generation.nodes, deletedOutlineNodeIds.value);
          generationStore.setNodes(restoredNodes);
          generationPages.value = restoredNodes.map((node, index) => ({
            ...node,
            page_id: node.page_id || node.node_id || `page_${index + 1}`,
            page_order: Number(node.page_order || node.order || index + 1),
            status: node.status || "completed",
          }));
          modifyStore.syncActiveNode(restoredNodes.map((node) => node.node_id));
          restoredGenerationNodes = restoredNodes.length > 0;
        }
      }
      if (savedDraft?.evidence_packet) evidencePacket.value = savedDraft.evidence_packet;
      if (Array.isArray(savedDraft?.evidence_selection)) {
        selectedEvidenceIds.value = savedDraft.evidence_selection;
        evidenceSelectionInitialized.value = true;
      }
      if (savedDraft?.evidence_scope) evidenceScope.value = savedDraft.evidence_scope;
      if (Array.isArray(savedDraft?.page_bindings) && savedDraft.page_bindings.length) {
        const bindings = new Map(savedDraft.page_bindings.map((item) => [String(item.page_id || item.node_id || ''), item]));
        generationStore.setNodes(generationStore.currentScriptNodes.map((node) => {
          const binding = bindings.get(String(node.page_id || node.node_id || ''));
          return binding ? { ...node, citation_refs: binding.evidence_refs || [], source_chunk_ids: binding.evidence_refs || [] } : node;
        }));
      }
      if (savedDraft?.presentation) { templateId.value = savedDraft.presentation.template_id || "default"; palette.value = savedDraft.presentation.palette || "classic"; layoutMode.value = savedDraft.presentation.layout || "balanced"; fontFamily.value = savedDraft.presentation.font_family || "system"; density.value = savedDraft.presentation.density || "comfortable"; }
    } catch {}
  }
  if (isVersionFork.value && !outlineStore.nodes.length && generationStore.currentScriptNodes.length) {
    try {
      // 修复修复前创建的旧分支：从该分支的内容快照建立草稿，不调用大纲模型。
      const source = outlineFromVersion(null, generationStore.currentScriptNodes, projectStore.project?.title || "课件");
      if (source.nodes.length) {
        const response = await teacherV1Api.outline.createFromNodes({
          session_id: intentStore.sessionId || projectStore.projectId,
          intent_id: intentStore.intentId || "",
          course_name: source.title,
          nodes: source.nodes,
        });
        const recovered = response?.data || response || {};
        if (!recovered.outline_id) throw new Error("版本大纲草稿创建失败");
        outlineStore.restoreEditableSnapshot(recovered);
        await projectStore.saveNow(draftSnapshot());
        restoredProjectOutline = true;
      }
    } catch (error) {
      genError.value = error?.message || "恢复版本大纲失败";
    }
  }
  if (!restoredGenerationNodes && restoredProjectOutline && outlineStore.isConfirmed) currentPhase.value = 'content';
  // 恢复最近生成记录
  if (projectStore.projectId) generationStore.restoreLastGenId();
  if (generationStore.lastGenId) {
    interactiveStore.setGenerationId(generationStore.lastGenId);
    // 旧草稿可能只有 task_id 和节点，先查询真实任务状态，再决定能否进入审阅。
    if (restoredGenerationNodes && generationStore.lastTaskId && pageTaskStatus.value === 'idle') {
      try {
        const response = await teacherV1Api.generation.getGenerationStatus(generationStore.lastTaskId);
        const task = response?.data || response || {};
        pageTaskStatus.value = task.status || 'idle';
        if (['failed', 'error'].includes(pageTaskStatus.value)) genError.value = task.error || '课件页面生成失败，请在内容阶段重试';
      } catch (error) {
        pageTaskStatus.value = 'error';
        genError.value = error?.message || '生成任务状态暂时无法确认';
      }
    }
    // 项目草稿已经包含完整节点时直接使用，避免全局缓存中的旧 task_id
    // 覆盖当前课件的恢复结果。
    if (!restoredGenerationNodes || ['pending', 'processing', 'generating'].includes(pageTaskStatus.value)) await loadGenerationStatus();
    if (['pending', 'processing', 'generating'].includes(pageTaskStatus.value)) void resumePageGeneration();
  }
  if (restoredGenerationNodes) {
    // 草稿中的节点是 AI 修订后的权威内容，刷新时用 inline 节点重建预览，
    // 避免旧 generation/version 快照覆盖最新修改。
    await generationStore.renderCoursewarePreview(
      outlineStore.title || intentStore.intentSummary?.topic || "课件预览",
      { genId: "" },
    ).catch(() => {});
  }
  // 回滚/基于旧版本新建版本时，项目草稿、localStorage 和最新上下文可能
  // 按不同顺序恢复。初始化末尾再次明确切换为可编辑分支，避免旧的
  // confirmed 状态覆盖前面的 restoreEditableSnapshot。
  const editableForkRoute = Boolean(route.query.from_rollback_version || route.query.editable_outline);
  if (editableForkRoute && outlineStore.nodes.length) {
    outlineStore.restoreEditableSnapshot({
      outline_id: outlineStore.outline_id,
      outline_version: outlineStore.outline_version || Number(route.query.base_version || 0),
      title: outlineStore.title,
      nodes: outlineStore.nodes,
    });
  }
  currentPhase.value = resolveS3Phase(legacyPhase || (restoredGenerationNodes ? 'pages' : 'content'), {
    outlineConfirmed: outlineStore.isConfirmed,
    contentStatus: contentStore.status,
    taskStatus: pageTaskStatus.value,
    hasPreview: Boolean(generationStore.previewHtml),
    hasNodes: generationStore.currentScriptNodes.length > 0,
  });
  if (isVersionFork.value) {
    // 历史版本分支复用已有大纲与证据，不因进入 S3 重新检索或生成。
    outlineReady.value = true;
  } else if (generationMode.value === "without_evidence") {
    evidencePacket.value = null;
    selectedEvidenceIds.value = [];
    evidenceSelectionInitialized.value = true;
    evidenceBootstrapState.value = "skipped";
    outlineReady.value = true;
  } else {
    const evidenceReady = await ensureAutomaticEvidence();
    outlineReady.value = evidenceReady || !requiresAutomaticEvidence.value;
  }
  } finally {
    initializing.value = false;
  }
});

function buildGenerationInstructionSet(evidence, mode) {
  return {
    schema_version: 1,
    intent: intentStore.intentSummary || {},
    outline_nodes: (outlineStore.nodes || []).map((node) => ({ ...node })),
    reference_materials: (evidence?.relevant_chunks || []).map((chunk) => ({
      chunk_id: chunk.chunk_id,
      source_ref: chunk.source_ref || chunk.source?.file_name || '',
      page_ref: chunk.page_ref || chunk.source?.page || null,
    })),
    confirmed_evidence: evidence || null,
    output_requirements: {
      formats: intentStore.intentSummary?.output_format || ['ppt'],
      with_interactive: Boolean(intentStore.intentSummary?.with_interactive),
    },
    presentation: {
      template_id: templateId.value,
      palette: palette.value,
      layout: layoutMode.value,
      font_family: fontFamily.value,
      density: density.value,
    },
    generation_mode: mode,
    page_generation_mode: generateMode.value,
  };
}

watch(currentPhase, () => { reviewTool.value = ''; });
watch(() => [outlineStore.nodes, generationStore.currentScriptNodes, templateId.value, palette.value, layoutMode.value, fontFamily.value, density.value], () => projectStore.scheduleSave(draftSnapshot()), { deep: true });
watch(() => contentStore.nodesContent, () => {
  if (!initializing.value) projectStore.scheduleSave(draftSnapshot());
}, { deep: true });
watch(() => [contentStore.status, contentStore.content_id, contentStore.error, pageTaskStatus.value], () => {
  if (!initializing.value) projectStore.scheduleSave(draftSnapshot());
});
watch(() => generationStore.currentScriptNodes, (nodes) => {
  if (!Array.isArray(nodes) || !nodes.length) return;
  generationPages.value = nodes.map((node, index) => {
    const existing = generationPages.value.find((page) => page.node_id === node.node_id) || {};
    return {
      ...existing,
      ...node,
      page_id: existing.page_id || node.page_id || node.node_id || `page_${index + 1}`,
      page_order: Number(node.page_order || node.order || index + 1),
      status: node.status || existing.status || 'done',
    };
  });
  // 节点变化时再把后端 page_bindings 套上去——避免 onMounted 里 loadLatestContext
  // 先于 localStorage 节点恢复执行，导致首次绑定写入被覆盖。
  if (modifyStore.pageBindings?.length) applyPageBindingsToUI(modifyStore.pageBindings)
}, { deep: true });

/**
 * 契约 v1.0 §3.2：把后端 /latest-generation-context 拉来的 page_bindings
 * 应用到当前 generationPages 与证据侧栏选中态。
 *
 * - 每个 node 上 citation_refs / source_chunk_ids 同步为该页绑定的 evidence_refs，
 *   让页面编辑器立刻显示"哪些证据绑到了这页"（不用等用户点"应用"）；
 * - selectedEvidenceIds 合并所有绑定里的 chunk_id，让左侧资料栏在打开 PPT 但
 *   还没点"生成"时就显示已绑定证据的选中态。
 *
 * 只在 projectId 匹配时应用，避免 A 项目的绑定误刷到 B 项目的页面上。
 */
function applyPageBindingsToUI(bindings) {
  const list = Array.isArray(bindings) ? bindings : []
  const byPageId = new Map(list.map((item) => [String(item.page_id || item.node_id || ''), item]))
  // 1) 写回每个生成节点的 citation_refs / source_chunk_ids
  if (generationStore.currentScriptNodes?.length) {
    const nextNodes = generationStore.currentScriptNodes.map((node) => {
      const key = String(node.page_id || node.node_id || '')
      const binding = byPageId.get(key)
      if (!binding) return node
      const refs = Array.isArray(binding.evidence_refs) ? binding.evidence_refs : []
      return {
        ...node,
        citation_refs: refs,
        source_chunk_ids: refs,
      }
    })
    generationStore.setNodes(nextNodes)
  }
  // 2) 把所有绑定的 chunk_id 并入 selectedEvidenceIds（已勾选的优先保留）
  const boundChunkIds = []
  for (const item of list) {
    if (Array.isArray(item.evidence_refs)) boundChunkIds.push(...item.evidence_refs)
  }
  if (boundChunkIds.length) {
    const merged = new Set(selectedEvidenceIds.value.map(String))
    for (const id of boundChunkIds) merged.add(String(id))
    selectedEvidenceIds.value = [...merged]
    evidenceSelectionInitialized.value = true
  }
  projectStore.scheduleSave(draftSnapshot())
}
watch(() => modifyStore.pageBindings, (bindings) => {
  if (!projectStore.projectId) return
  applyPageBindingsToUI(bindings)
})
/**
 * 把新渲染的预览交给 iframe。
 *
 * 首次（或上一次走了整份重设）时设 `srcdoc`；之后按 `data-node-id` 只换变了的页，
 * 滚动位置、其余页与展开的讲稿都不动。补丁不适用时 `patchPreview` 自己返回
 * `'srcdoc'`，这里退回整份重设 —— 与改造前行为一致，只是慢一点，不会白屏。
 */
function applyPreviewHtml(html) {
  if (!html) {
    previewSrcDoc.value = "";
    previewFrameReady.value = false;
    return;
  }
  const iframe = previewFrameEl.value;
  if (!iframe || !previewFrameReady.value) {
    previewSrcDoc.value = html;
    return;
  }
  const { mode } = patchPreview(iframe, html);
  if (mode === PATCH_MODE.SRCDOC) {
    previewFrameReady.value = false;
    previewSrcDoc.value = html;
  }
}

watch(() => generationStore.previewHtml, applyPreviewHtml);
onBeforeUnmount(() => { projectStore.saveNow(draftSnapshot()).catch(() => {}); });
onBeforeRouteLeave(async () => { await projectStore.saveNow(draftSnapshot()).catch(() => {}); });

function statusLabel(status) {
  return (
    {
      pending: "等待",
      processing: "生成中",
      done: "完成",
      failed: "失败",
    }[status] || status
  );
}

function pageEvidenceStatus(page) {
  const refs = [...(page?.citation_refs || []), ...(page?.source_chunk_ids || [])].filter(Boolean);
  if (refs.length) return `有关联资料（${new Set(refs).size} 处），内容待核对`;
  return generationMode.value === 'without_evidence' ? '仅依据教学意图' : '资料关联待核对';
}

function outlineNodeSources(node) {
  const refs = [...(node?.citation_refs || []), ...(node?.source_chunk_ids || [])].filter(Boolean);
  if (!refs.length) return '暂无章节级资料关联';
  const chunks = selectedEvidencePacket.value?.relevant_chunks || [];
  const sources = [...new Set(refs.map(id => chunks.find(chunk => chunk.chunk_id === id)?.source_ref).filter(Boolean))];
  return sources.length ? `${sources.join('、')} · 待核对` : `${new Set(refs).size} 处引用关联 · 来源待核对`;
}

// 大纲创建完成
function handleOutlineCreated({ outline_id, outline_version }) {
  deletedOutlineNodeIds.value = [];
  // OutlineBuilder 已使用整份证据包生成结构；创建完成后再把引用 ID
  // 落到每个大纲节点，保证后续内容生成和版本快照都保留绑定关系。
  bindEvidenceToWholeDraft();
  projectStore.scheduleSave(draftSnapshot(), 0);
  console.log(
    "[S3StudioPage] 大纲创建完成:",
    outline_id,
    "v" + outline_version,
  );
}

async function handleOutlineNodeDeleted(nodeId) {
  const removedId = String(nodeId || '');
  if (!removedId) return;
  deletedOutlineNodeIds.value = [...new Set([...deletedOutlineNodeIds.value, removedId])];
  generationPages.value = filterDeletedOutlineNodes(generationPages.value, [removedId]);
  generationStore.setNodes(filterDeletedOutlineNodes(generationStore.currentScriptNodes, [removedId]));
  delete contentStore.nodesContent[removedId];
  contentStore._persist();
  if (modifyNodeId.value === removedId) cancelModifyNode();
  saveVersionState.value = 'idle';
  lastSavedVersion.value = 0;
  needsVersionSave.value = true;
  // The old preview and version cache belong to the pre-deletion page tree.
  generationStore.clearPreview();
  try {
    await projectStore.saveNow(draftSnapshot());
    if (generationStore.currentScriptNodes.length) {
      await generationStore.renderCoursewarePreview(
        outlineStore.title || intentStore.intentSummary?.topic || '课件预览',
        { genId: '' },
      );
    }
  } catch (error) {
    handleError('删除节点后保存或刷新预览失败: ' + (error?.message || '未知错误'));
  }
}

// 大纲确认完成，进入生成阶段
function handleOutlineConfirmed() {
  currentPhase.value = "content";
}

// 开始内容生成（P1：outline → content）
async function handleStartContentGeneration() {
  if (!outlineStore.isConfirmed) {
    handleError("请先确认大纲");
    return;
  }
  if (!outlineStore.nodes || outlineStore.nodes.length === 0) {
    handleError("大纲中无节点");
    return;
  }
  contentStore.error = "";
  contentStore.status = "idle";
  contentStore.progress_pct = 0;
  contentStore.completed_nodes = 0;
  contentStore.total_nodes = outlineStore.nodes.length;

  try {
    // 调用 content API 创建任务
    await contentStore.startGeneration({
      nodes: outlineStore.nodes,
      course_name: outlineStore.title || "课件",
      mode: "llm",
      enhanced: false,
      outline_id: outlineStore.outline_id,
      outline_version: outlineStore.outline_version,
      generation_instruction_set: buildGenerationInstructionSet(selectedEvidencePacket.value, "content_only"),
    });
  } catch (err) {
    handleError("启动内容生成失败: " + (err?.message || ""));
  }
}

function syncScriptToGeneratedNodes(nodeId, script) {
  if (!generationStore.currentScriptNodes.length) return;
  generationStore.setNodes(generationStore.currentScriptNodes.map((node) =>
    node.node_id === nodeId ? { ...node, script, segments: [] } : node,
  ));
  generationStore.setScript(generationStore.currentScriptNodes.map((node) => node.script || "").filter(Boolean).join("\n\n"));
  needsVersionSave.value = true;
  saveVersionState.value = "idle";
}

function withEditedScripts(nodes) {
  return (nodes || []).map((node) => {
    const content = contentStore.nodesContent[node.node_id];
    const script = content?.script ?? content?.lecture_script;
    return typeof script === "string" && script.trim()
      ? { ...node, script, segments: [] }
      : node;
  });
}

function handleEditNodeScript(nodeId) {
  const current = contentStore.nodesContent[nodeId];
  if (!current) return;
  reviewTool.value = '';
  cancelModifyNode();
  editScriptNodeId.value = nodeId;
  editScriptDraft.value = current.script ?? current.lecture_script ?? "";
  scriptSaveError.value = "";
}

function cancelEditNodeScript() {
  if (scriptSaving.value) return;
  editScriptNodeId.value = "";
  editScriptDraft.value = "";
  scriptSaveError.value = "";
}

async function persistScriptRevision(nodeId, script) {
  const previous = contentStore.nodesContent[nodeId];
  if (!previous) throw new Error("当前节点尚无讲稿");
  const revisedContent = { ...previous, script, lecture_script: script, segments: [] };
  const revisedNodes = generationStore.currentScriptNodes.map((node) =>
    node.node_id === nodeId ? { ...node, script, segments: [] } : node,
  );
  const snapshot = draftSnapshot();
  snapshot.content = { ...snapshot.content, nodes: { ...snapshot.content.nodes, [nodeId]: revisedContent } };
  snapshot.content.edited_node_ids = [...new Set([...(snapshot.content.edited_node_ids || []), nodeId])];
  snapshot.generation = { ...snapshot.generation, nodes: revisedNodes };
  snapshot.needs_version_save = needsVersionSave.value || revisedNodes.length > 0;
  await projectStore.saveNow(snapshot);
  contentStore.saveNodeScript(nodeId, script);
  syncScriptToGeneratedNodes(nodeId, script);
  if (revisedNodes.length) { needsVersionSave.value = true; saveVersionState.value = 'idle'; }
  if (generationStore.currentScriptNodes.length) {
    await generationStore.renderCoursewarePreview(
      outlineStore.title || intentStore.intentSummary?.topic || "课件预览", { genId: "" },
    ).catch((error) => console.warn("[S3StudioPage] 讲稿已保存，但预览刷新失败", error));
  }
}

async function saveEditedNodeScript() {
  const nodeId = editScriptNodeId.value;
  const script = editScriptDraft.value.trim();
  if (!nodeId || !script || scriptSaving.value) return;
  scriptSaving.value = true;
  scriptSaveError.value = "";
  try {
    await persistScriptRevision(nodeId, script);
    editScriptNodeId.value = "";
    editScriptDraft.value = "";
  } catch (error) {
    scriptSaveError.value = `保存讲稿失败：${error?.message || error}`;
  } finally {
    scriptSaving.value = false;
  }
}

// AI 修改单个节点讲稿
function handleModifyNode(nodeId) {
  if (!contentStore.nodesContent[nodeId] || scriptSaving.value) return;
  cancelEditNodeScript();
  modifyNodeId.value = nodeId;
  modifyMessage.value = "";
}

function cancelModifyNode() {
  if (contentStore.modifying || scriptSaving.value) return;
  modifyNodeId.value = "";
  modifyMessage.value = "";
}

async function submitModifyNode() {
  const message = modifyMessage.value.trim();
  if (!modifyNodeId.value || !message) return;
  try {
    const node = outlineStore.nodes.find((item) => item.node_id === modifyNodeId.value);
    const result = await contentStore.modifyNode({
      node_id: modifyNodeId.value,
      title: node?.title || "",
      message,
      course_name: outlineStore.title || "课件",
    });
    scriptSaving.value = true;
    await persistScriptRevision(modifyNodeId.value, result.script);
    modifyNodeId.value = "";
    modifyMessage.value = "";
  } catch (err) {
    handleError("修改内容失败: " + (err?.message || ""));
  } finally {
    scriptSaving.value = false;
  }
}

// 从 content 阶段跳转到 generating 阶段
function goToGeneratingPhase() {
  showPageGeneration.value = true;
  currentPhase.value = 'content';
}

// AI 修订成功后立即刷新右侧 PPT 预览，并把最新节点写入项目草稿。
async function handleModifyApplied({ allNodes = [] } = {}) {
  // 即使当前内存中没有 generation 节点，也以修改接口返回的完整节点树恢复预览。
  if (!generationStore.currentScriptNodes?.length && Array.isArray(allNodes) && allNodes.length) {
    generationStore.setNodes(allNodes)
  }
  if (generationStore.currentScriptNodes?.length) {
    await generationStore.renderCoursewarePreview(
      outlineStore.title || intentStore.intentSummary?.topic || "课件预览",
      { genId: "" },
    );
    if (generationStore.previewHtml) currentPhase.value = 'review';
    needsVersionSave.value = true;
    saveVersionState.value = 'idle';
  }
  await projectStore.saveNow(draftSnapshot());
}

// 开始生成内容
async function handleStartGeneration() {
  if (pageGenerationActive.value) return;
  if (!canStartPageGeneration(contentStore.status)) {
    handleError('请先完成讲稿生成，再生成课件页面');
    return;
  }
  if (generationScope.value === "content_only" && (!outlineStore.outline_id || !outlineStore.isConfirmed)) {
    handleError("请先确认大纲");
    return;
  }
  if (!intentStore.sessionId || !intentStore.intentSummary) {
    handleError("缺少有效的 S1 意图会话，请返回 S1 完成意图确认");
    return;
  }
  genError.value = "";
  pageTaskStatus.value = 'pending';
  generationStore.setGenerating(true);
  generationStore.setGenerateProgress(5, "准备生成环境");

  try {
    const evidence = selectedEvidencePacket.value;

    if (generationScope.value === "full_pipeline") {
      generationStore.setGenerateProgress(10, "根据当前意图与已确认资料重新生成大纲");
      await outlineStore.createOutline({
        session_id: intentStore.sessionId,
        intent_id: intentStore.intentId,
        intent: intentStore.intentSummary,
        evidence_packet: evidence,
        generation_instruction_set: buildGenerationInstructionSet(evidence, "full_pipeline"),
      });
      await outlineStore.confirmOutline();
      deletedOutlineNodeIds.value = [];
    }

    generationStore.setGenerateProgress(15, "创建生成任务");
    const resp = await teacherV1Api.generation.createGeneration({
      session_id: intentStore.sessionId,
      outline_id: outlineStore.outline_id,
      outline_version: outlineStore.outline_version,
      outline_confirmed: true,
      template_id: templateId.value,
      project_id: projectStore.projectId,
      generate_mode: generateMode.value,
      generation_scope: generationScope.value,
      intent: intentStore.intentSummary || undefined,
      evidence_packet: evidence,
      generation_instruction_set: buildGenerationInstructionSet(evidence, generationScope.value),
      outline_nodes: outlineStore.nodes,
    });

    const task = resp?.data || resp || {};
  const taskId = task.task_id || task.generation_id;
    if (!taskId) throw new Error("页面生成任务启动失败，请重试");
    generationStore.setLastTaskId(taskId);

    // 记录 generation_id
    const genId = task.generation_id || taskId;
    generationStore.setLastTaskId(task.task_id || taskId);
    generationStore.setLastGenId(genId);
    projectStore.scheduleSave(draftSnapshot(), 0);
    interactiveStore.setGenerationId(genId);

    generationStore.setGenerateProgress(25, "正在生成内容");
    const status = await generationStore.waitForCoursewareGeneration(taskId, {
      intervalMs: 800,
      // LLM 节点生成可能超过 4 分钟；保留较长轮询窗口，避免前端
      // 提前超时后任务虽在后端完成，页面却永远收不到结果。
      maxAttempts: 4500,
    });
    pageTaskStatus.value = status.status;

    // 加载生成状态（页面列表）
    await loadGenerationStatus();
    bindEvidenceToWholeDraft();

    // 渲染预览 —— renderCoursewarePreview 写 generationStore.previewHtml，
    // 由上面的 watcher 统一交给 iframe（首次设 srcdoc，之后只补变了的页）。
    generationStore.setGenerateProgress(92, "正在加载预览");
    await generationStore.renderCoursewarePreview(
      outlineStore.title || intentStore.intentSummary?.topic || "课件预览",
      { genId: "" },
    );

    generationStore.setGenerateProgress(100, "生成完成");
    if (hasReviewContent.value) currentPhase.value = 'review';
  } catch (err) {
    genError.value = err?.message || "生成失败，请重试";
    pageTaskStatus.value = 'error';
    generationStore.setGenerateProgress(0, "生成失败");
  } finally {
    generationStore.setGenerating(false);
  }
}

// 加载生成状态
async function loadGenerationStatus() {
  const taskId = generationStore.lastTaskId || generationStore.restoreLastTaskId();
  if (!taskId) return;
  try {
    const resp = await teacherV1Api.generation.getGenerationStatus(taskId);
    const data = resp?.data || resp || {};
    pageTaskStatus.value = data.status || 'idle';
    if (!['failed', 'error'].includes(pageTaskStatus.value)) genError.value = '';
    if (['failed', 'error'].includes(pageTaskStatus.value)) {
      genError.value = data.error || '课件页面生成失败，请在内容阶段重试';
      currentPhase.value = 'content';
    }
    const nodes = withEditedScripts(filterDeletedOutlineNodes(data.nodes, deletedOutlineNodeIds.value));

    // 状态轮询既用于展示页面列表，也用于刷新/恢复 S3 编辑状态。
    // 之前这里只更新 generationPages，导致后端已 done 但
    // currentScriptNodes 仍为空，预览和“保存新版本”按钮都不会出现。
    if (data.task_id) generationStore.setLastTaskId(data.task_id);
    if (data.generation_id) generationStore.setLastGenId(data.generation_id);
    if (['done', 'completed', 'success'].includes(data.status) && nodes.length) {
      generationStore.setNodes(nodes);
      generationStore.setScript(
        nodes
          .map((node) => node.script || node.content || node.summary || '')
          .filter(Boolean)
          .join('\n\n'),
      );
      generationStore.setGenerateProgress(100, '生成完成');
      generationStore.setGenerating(false);
      await generationStore.renderCoursewarePreview(
        outlineStore.title || intentStore.intentSummary?.topic || '课件预览',
        { genId: '' },
      ).catch((previewError) => {
        console.warn('[S3StudioPage] 已完成任务预览恢复失败', previewError);
      });
      bindEvidenceToWholeDraft();
      projectStore.scheduleSave(draftSnapshot(), 0);
      if (generationStore.previewHtml) currentPhase.value = 'review';
    }

    generationPages.value = nodes.map((node, index) => ({
      ...node,
      page_id: node.page_id || node.node_id || `page_${index + 1}`,
      page_order: Number(node.page_order || node.order || index + 1),
      status: node.status || 'completed'
    }));
  } catch (err) {
    console.warn("[S3StudioPage] 加载生成状态失败", err);
    pageTaskStatus.value = 'error';
    genError.value = `无法获取课件任务状态：${err?.message || '请稍后重试'}`;
    currentPhase.value = 'content';
  }
}

async function resumePageGeneration() {
  const taskId = generationStore.lastTaskId;
  if (!taskId) return;
  generationStore.setGenerating(true);
  currentPhase.value = 'content';
  try {
    await generationStore.waitForCoursewareGeneration(taskId, { intervalMs: 800, maxAttempts: 4500 });
    await loadGenerationStatus();
  } catch (error) {
    pageTaskStatus.value = 'error';
    genError.value = error?.message || '页面生成恢复失败，请检查任务状态';
  } finally {
    generationStore.setGenerating(false);
  }
}

// 单页重生成
async function handleRegeneratePage(page) {
  regeneratingPageId.value = page.page_id;
  try {
    await teacherV1Api.generation.regeneratePage(
      generationStore.lastGenId,
      page.page_id,
      { reason: "教师手动重试", mode: "ai" },
    );
    await loadGenerationStatus();
    needsVersionSave.value = true;
    saveVersionState.value = 'idle';
  } catch (err) {
    handleError("重生成失败: " + (err?.message || ""));
  } finally {
    regeneratingPageId.value = "";
  }
}

// 预览单页
async function handlePreviewPage(page) {
  try {
    const resp = await teacherV1Api.generation.getPage(
      generationStore.lastGenId,
      page.page_id,
    );
    const data = resp?.data || resp || {};
    if (data.preview_url) {
      window.open(data.preview_url, "_blank");
    }
  } catch (err) {
    handleError("预览加载失败");
  }
}

// 生成互动资源
async function handleGenerateInteractive(node) {
  if (!generationStore.lastGenId) {
    handleError("当前课件还没有生成结果，请先完成内容生成");
    return;
  }
  try {
    await interactiveStore.generateInteractive({
      generation_id: generationStore.lastGenId,
      node_id: node.node_id,
      node,
      interactive_plan: node.interactive_plan || {
        enabled: true,
        kind: "quiz",
        question_count: 3,
        duration_minutes: 5,
        auto_grading: true,
        delivery: "html5_link",
      },
    });
    const asset = await interactiveStore.pollAssetStatus(node.node_id);
    if (asset?.status === "done") {
      if (node.interactive_plan?.kind === "flashcard" && !asset.items?.some((item) => item.type === "flashcard" && item.front)) {
        throw new Error("生成结果没有知识翻卡，请检查互动类型后重试");
      }
      const page = generationPages.value.find((item) => item.node_id === node.node_id);
      if (page?.page_id && asset.interactive_asset_id) {
        const link = await interactiveStore.linkToPage({
          generation_id: generationStore.lastGenId,
          page_id: page.page_id,
          interactive_asset_id: asset.interactive_asset_id,
          label: node.title || "互动练习",
        });
        asset.entry_url = link.entry_url || asset.entry_url;
      }
      const nodes = withGeneratedInteractiveAsset(generationStore.currentScriptNodes, node, asset);
      generationStore.setNodes(nodes);
      needsVersionSave.value = true;
      saveVersionState.value = 'idle';
      projectStore.scheduleSave(draftSnapshot(), 0);
      await handleSaveNewVersion();
      if (saveVersionState.value !== "saved") {
        throw new Error("互动内容已生成，但保存新版本失败；请点击页面顶部“保存新版本”后再到 S4 导出");
      }
    }
  } catch (err) {
    handleError("生成互动资源失败: " + (err?.message || ""));
  }
}

// 打开互动资源
function openInteractiveAsset(node) {
  const asset = interactiveStore.getAsset(node.node_id);
  if (asset?.entry_url) {
    interactivePreviewUrl.value = asset.entry_url;
    interactivePreviewTitle.value = node.title || "互动资源";
  }
}

function openInteractiveWindow() {
  if (interactivePreviewUrl.value) window.open(interactivePreviewUrl.value, "_blank", "noopener");
}

function closeInteractivePreview() {
  interactivePreviewUrl.value = "";
  interactivePreviewTitle.value = "";
}

// 新窗口打开 HTML5 预览
function openPreviewWindow() {
  if (!generationStore.previewHtml) return;
  const blob = new Blob([generationStore.previewHtml], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

async function applyPresentationStyle() {
  const presentation = {
    template_id: templateId.value,
    palette: palette.value,
    layout: layoutMode.value,
    font_family: fontFamily.value,
    density: density.value,
  };
  generationStore.setNodes((generationStore.currentScriptNodes || []).map((node) => ({
    ...node,
    layout_hint: layoutMode.value === "visual" ? "text_with_media" : (layoutMode.value === "text" ? "text_only" : (node.layout_hint || "two_column")),
    font_size_hint: density.value === "minimal" ? "large" : (density.value === "compact" ? "small" : "medium"),
    slide_background: palette.value === "klein-blue" ? "preset_blue" : "preset_green",
    metadata: { ...(node.metadata || {}), presentation },
  })));
  if (generationStore.currentScriptNodes.length) {
    needsVersionSave.value = true;
    saveVersionState.value = 'idle';
  }
  await generationStore.renderCoursewarePreview(
    outlineStore.title || intentStore.intentSummary?.topic || "课件预览",
    { genId: "" },
  );
  projectStore.scheduleSave(draftSnapshot(), 0);
  currentPhase.value = 'review';
}

async function handleStyleRequest({ instruction = '', presentation = {} } = {}) {
  const text = String(instruction).toLowerCase();
  const style = presentation && typeof presentation === 'object' ? presentation : {};
  if (style.template_id) templateId.value = style.template_id;
  if (style.palette) palette.value = style.palette;
  if (style.layout) layoutMode.value = style.layout;
  if (style.font_family) fontFamily.value = style.font_family;
  if (style.density) density.value = style.density;
  // 兼容旧 AI 响应：仅当结构化字段为空时才使用本地兜底映射。
  if (!Object.values(style).some(Boolean)) {
    if (/商务|business|简洁/.test(text)) { templateId.value = 'deck-swiss-edu'; density.value = 'minimal'; }
    if (/蓝|blue/.test(text)) palette.value = 'klein-blue';
    if (/图|视觉|visual/.test(text)) layoutMode.value = 'visual';
    if (/文字|内容优先/.test(text)) layoutMode.value = 'text';
  }
  currentPhase.value = 'review';
  await applyPresentationStyle();
}

async function handleEvidenceSearch(query) {
  const packet = await materialStore.generateEvidence({
    query,
    context: { intent: intentStore.intentSummary || {}, project_id: projectStore.projectId },
  });
  if (packet) {
    adoptEvidencePacket(packet);
    projectStore.scheduleSave(draftSnapshot(), 0);
  }
}

function adoptEvidencePacket(packet, { bindToDraft = true } = {}) {
  evidencePacket.value = packet;
  selectedEvidenceIds.value = evidenceIds(packet);
  evidenceSelectionInitialized.value = true;
  evidenceScope.value = { scope: "draft", nodeId: "" };
  generationMode.value = isEvidencePacketUsable(packet) ? "with_evidence" : "without_evidence";
  if (typeof window !== "undefined") {
    window.localStorage.setItem(`fuww_s2_generation_mode:${intentStore.sessionId}`, generationMode.value);
  }
  if (bindToDraft) bindEvidenceToWholeDraft();
}

function bindEvidenceToWholeDraft() {
  const refs = evidenceIds(selectedEvidencePacket.value);
  if (!refs.length) return;
  outlineStore.bindEvidenceRefs(refs);
  if (generationStore.currentScriptNodes?.length) {
    generationStore.setNodes(generationStore.currentScriptNodes.map((node) => ({
      ...node,
      citation_refs: refs,
      source_chunk_ids: refs,
      metadata: {
        ...(node.metadata || {}),
        evidence_scope: "draft",
        evidence_auto_bound: true,
        evidence_bound_by: "s1_intent_auto_search",
      },
    })));
  }
}

function discardPlaceholderOutline() {
  if (isPlaceholderOutline(outlineStore.nodes)) outlineStore.reset();
}

async function ensureAutomaticEvidence({ bindToDraft = true } = {}) {
  if (isEvidencePacketUsable(evidencePacket.value)) {
    adoptEvidencePacket(evidencePacket.value, { bindToDraft });
    discardPlaceholderOutline();
    projectStore.scheduleSave(draftSnapshot(), 0);
    evidenceBootstrapState.value = "ready";
    evidenceBootstrapError.value = "";
    return true;
  }
  const query = buildIntentEvidenceQuery(intentStore.intentSummary || {});
  if (!query) {
    evidenceBootstrapState.value = "error";
    evidenceBootstrapError.value = "S1 教学意图不完整，无法构造自动检索条件。";
    return false;
  }
  evidenceBootstrapState.value = "loading";
  evidenceBootstrapError.value = "";
  try {
    const packet = await materialStore.generateEvidence({
      query,
      context: {
        intent: intentStore.intentSummary || {},
        project_id: projectStore.projectId,
        binding_scope: "draft",
        auto_bind: true,
      },
    });
    if (isEvidencePacketUsable(packet)) {
      adoptEvidencePacket(packet, { bindToDraft });
      discardPlaceholderOutline();
      evidenceBootstrapState.value = "ready";
      await projectStore.saveNow(draftSnapshot()).catch(() => {});
      return true;
    }
    evidenceBootstrapState.value = "error";
    evidenceBootstrapError.value = materialStore.error || "知识库暂未返回可用证据。";
    return false;
  } catch (error) {
    evidenceBootstrapState.value = "error";
    evidenceBootstrapError.value = error?.message || "自动检索失败，请重试。";
    return false;
  }
}

async function retryAutomaticEvidence() {
  const ready = await ensureAutomaticEvidence();
  if (ready) outlineReady.value = true;
}

async function reconnectKnowledgeBase() {
  if (evidenceBootstrapState.value === 'loading' || materialStore.searching) return;
  knowledgeReconnectNotice.value = '';
  const hasExistingOutput = Boolean(outlineStore.outline_id || generationStore.currentScriptNodes.length);
  const ready = await ensureAutomaticEvidence({ bindToDraft: !hasExistingOutput });
  if (ready) {
    outlineReady.value = true;
    if (hasExistingOutput) knowledgeReconnectNotice.value = '已取得本地知识库的参考片段，可供后续生成使用。已有大纲和页面不会自动改写或补上引用。';
  }
}

function continueWithIntentOnly() {
  generationMode.value = "without_evidence";
  evidencePacket.value = null;
  selectedEvidenceIds.value = [];
  evidenceSelectionInitialized.value = true;
  evidenceBootstrapState.value = "skipped";
  evidenceBootstrapError.value = "";
  // 明确由教师选择无资料生成时，仍只使用结构化 S1 意图，不能读取旧版 S2 Markdown。
  if (typeof window !== "undefined") {
    window.localStorage.removeItem("fuww_s2_markdown");
    window.localStorage.removeItem(`fuww_s2_evidence_packet:${intentStore.sessionId}`);
    window.localStorage.setItem(`fuww_s2_generation_mode:${intentStore.sessionId}`, generationMode.value);
  }
  discardPlaceholderOutline();
  outlineReady.value = true;
}

function handleEvidenceSelection(ids) {
  selectedEvidenceIds.value = Array.isArray(ids) ? ids : [];
  evidenceSelectionInitialized.value = true;
  projectStore.scheduleSave(draftSnapshot());
}

async function handleEvidenceApply({ scope, nodeId, selectedIds = [] }) {
  selectedEvidenceIds.value = selectedIds;
  evidenceSelectionInitialized.value = true;
  evidenceScope.value = { scope, nodeId: nodeId || "" };
  if (scope === "none") {
    if (generationStore.currentScriptNodes?.length) {
      generationStore.setNodes(generationStore.currentScriptNodes.map((node) => ({
        ...node,
        citation_refs: [],
        source_chunk_ids: [],
        metadata: { ...(node.metadata || {}), evidence_scope: "none" },
      })));
    }
    projectStore.scheduleSave(draftSnapshot(), 0);
    return;
  }
  if (!evidencePacket.value) {
    projectStore.scheduleSave(draftSnapshot(), 0);
    return;
  }
  const activePacket = selectedEvidencePacket.value || {};
  const refs = [
    ...(activePacket.citations || []).map((item) => item.chunk_id),
    ...(activePacket.relevant_chunks || []).map((item) => item.chunk_id),
  ].filter(Boolean);
  const uniqueRefs = [...new Set(refs)];
  if (generationStore.currentScriptNodes?.length) {
    generationStore.setNodes(generationStore.currentScriptNodes.map((node) => {
      const selected = scope === "draft" || node.node_id === nodeId;
      return selected ? {
        ...node,
        // 采用替换语义，确保取消勾选后旧证据不会继续残留在页面绑定中。
        citation_refs: uniqueRefs,
        source_chunk_ids: uniqueRefs,
        metadata: { ...(node.metadata || {}), evidence_scope: scope },
      } : node;
    }));
    await generationStore.renderCoursewarePreview(outlineStore.title || intentStore.intentSummary?.topic || "课件预览", { genId: "" });
  }
  projectStore.scheduleSave(draftSnapshot(), 0);
}

async function handleSaveNewVersion() {
  if (!generationStore.currentScriptNodes.length || saveVersionState.value === "saving") return;
  saveVersionState.value = "saving";
  genError.value = "";
  try {
    await projectStore.saveNow(draftSnapshot());
    const summary = `教师保存：${new Date().toLocaleString()}`;
    // 内容生成页的讲稿存放在 contentStore，不能只保存 PPT 节点的脚本。
    // 仅在该节点确有讲稿时覆盖，避免空内容擦掉课件生成阶段的脚本。
    const versionNodes = filterDeletedOutlineNodes(
      generationStore.currentScriptNodes, deletedOutlineNodeIds.value).map((node) => {
      const generatedContent = contentStore.nodesContent[node.node_id];
      const teacherScript = generatedContent?.script || generatedContent?.lecture_script;
      return typeof teacherScript === "string" && teacherScript.trim()
        ? { ...node, script: teacherScript }
        : node;
    });
    if (!versionNodes.length) {
      throw new Error('删除后没有可保存的页面，请先重新生成页面');
    }
    let savedVersion = 0;
    if (projectStore.projectId) {
      const snapshot = {
        outline: {
          outline_id: outlineStore.outline_id,
          outline_version: outlineStore.outline_version,
          title: outlineStore.title,
          nodes: outlineStore.nodes,
        },
        content: versionNodes,
        page_bindings: versionPageBindings(),
        style: draftSnapshot().presentation,
        generation_instruction_set: draftSnapshot().generation_instruction_set,
      };
      const projectResponse = await projectModifyApi.createVersion(projectStore.projectId, {
        nodes: versionNodes,
        presentation: draftSnapshot().presentation,
        page_bindings: versionPageBindings(),
        generation_instruction_set: draftSnapshot().generation_instruction_set,
        version_summary: summary,
        version_no: Math.max(baseVersion.value + 1, 1),
        snapshot,
        change_note: summary,
      });
      const projectVersion = projectResponse?.data || projectResponse || {};
      savedVersion = resolveSavedProjectVersion(projectVersion, 0);
    }

    // AI Engine finalize is a secondary snapshot; the project version above is
    // already durable before this slower request starts.
    let response = null;
    try {
      response = await teacherV1Api.generation.finalize({
      generation_id: generationStore.lastGenId,
      nodes: versionNodes,
      course_name: outlineStore.title || intentStore.intentSummary?.topic || "未命名课件",
      summary,
      outline_id: outlineStore.outline_id,
      outline_version: outlineStore.outline_version,
      page_bindings: versionPageBindings(),
      presentation: draftSnapshot().presentation,
      generation_instruction_set: draftSnapshot().generation_instruction_set,
      });
    } catch (finalizeError) {
      // 项目版本已经先保存；AI Engine 快照失败不应撤销可刷新的项目版本。
      console.warn('[S3StudioPage] AI Engine finalize failed after project version save', finalizeError);
    }
    const data = response?.data || response || {};
    if (data.generation_id) generationStore.setLastGenId(data.generation_id);
    const generationVersion = Number(data.version_number || 0);
    if (!savedVersion) savedVersion = generationVersion;
    lastSavedVersion.value = savedVersion;
    if (savedVersion > 0) baseVersion.value = savedVersion;
    saveVersionState.value = "saved";
    needsVersionSave.value = false;
    await modifyStore.loadVersionHistory().catch(() => {});
  } catch (error) {
    saveVersionState.value = "error";
    genError.value = error?.message || "保存新版本失败";
  }
}

async function goToS4() {
  if (needsVersionSave.value) {
    if (!filterDeletedOutlineNodes(generationStore.currentScriptNodes, deletedOutlineNodeIds.value).length) {
      handleError('删除后没有可保存的页面，请先重新生成页面再进入 S4');
      return;
    }
    await handleSaveNewVersion();
    if (saveVersionState.value !== 'saved') return;
  }
  // 同步大纲信息到 localStorage，供 S4 使用
  try {
    window.localStorage.setItem(
      "fuww_s3_outline_info",
      JSON.stringify({
        outline_id: outlineStore.outline_id,
        outline_version: outlineStore.outline_version,
        generation_id: generationStore.lastGenId,
      }),
    );
  } catch {}
  projectStore.updateStep("s4_version").catch(() => {});
  router.push({ name: "S4Version", query: { project_id: projectStore.projectId, generation_id: generationStore.lastGenId } });
}

/** 流程条上的「版本与导出」仍需先保存版本，不能直接跳路由。 */
function onStepAction(key) {
  if (key === "s4") void goToS4();
}

function handleError(msg) {
  genError.value = msg;
  console.warn("[S3StudioPage]", msg);
}
</script>

<style scoped>
.s3-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-6);
  min-height: calc(100dvh - var(--topbar-height) - var(--shell-gutter) * 2);
  background: var(--bg-page);
}
.studio-loading {
  position: fixed;
  inset: var(--topbar-height) var(--shell-gutter) var(--shell-gutter);
  z-index: var(--z-overlay);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  text-align: center;
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  color: var(--color-primary);
  box-shadow: var(--shadow-md);
}
.studio-loading strong { font-size: var(--text-lg); }
.studio-loading p { color: var(--text-secondary); font-size: var(--text-xs); }
.studio-spinner { width: 36px; height: 36px; border: 3px solid var(--brand-100); border-top-color: var(--color-primary); border-radius: 50%; animation: studio-spin .8s linear infinite; }
@keyframes studio-spin { to { transform: rotate(360deg); } }
.async-activity {
  position: fixed;
  top: calc(var(--topbar-height) + var(--space-4));
  left: 50%;
  z-index: calc(var(--z-overlay) + 1);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: min(440px, calc(100vw - 40px));
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  box-shadow: var(--shadow-md);
  color: var(--text-primary);
  transform: translateX(-50%);
}
.async-activity > div { display: grid; gap: 2px; flex: 1; }
.async-activity strong { font-size: var(--text-xs); }
.async-activity small { color: var(--text-tertiary); font-size: var(--text-2xs); }
.async-spinner { width: 20px; height: 20px; flex: 0 0 auto; border: 3px solid var(--brand-100); border-top-color: var(--color-primary); border-radius: 50%; animation: studio-spin .75s linear infinite; }
.async-progress { font-size: var(--text-2xs); font-weight: var(--weight-semibold); color: var(--color-primary); font-variant-numeric: tabular-nums; }

/* 三栏工作区：栅格列 + sticky，替代原来的 position:fixed 与让位 padding */
.s3-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  grid-template-areas: "main assistant";
  gap: var(--space-4);
  align-items: start;
  flex: 1;
  min-height: 0;
}
.s3-workbench > .phase-panel { grid-area: main; min-width: 0; }
.s3-workbench > .s3-assistant-col { grid-area: assistant; width: 320px; min-width: 0; display: grid; gap: var(--space-3); }
/* Vue 的 v-if 占位是注释节点，CSS :empty 会忽略注释 —— 正好用来收起空列 */
.s3-workbench > .s3-assistant-col:empty { display: none; }
.s3-tool, .review-tool { min-width: 0; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--bg-surface); }
.s3-tool > summary, .review-tool > summary { padding: var(--space-3); cursor: pointer; color: var(--text-primary); font-size: var(--text-sm); font-weight: var(--weight-semibold); }
.s3-tool :deep(.evidence-sidebar) { position: static; width: 100%; max-height: 460px; overflow: auto; }
.review-toolbar-actions { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.s3-modify-overlay { position: fixed; inset: 0; z-index: calc(var(--z-overlay) + 2); display: grid; place-items: center; padding: var(--space-4); background: rgb(17 31 27 / 55%); }
.s3-modify-dialog { width: min(720px, 100%); max-height: min(88dvh, 880px); display: flex; flex-direction: column; overflow: auto; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--bg-surface); box-shadow: var(--shadow-md); }
.s3-modify-header { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-3); padding: var(--space-4); border-bottom: 1px solid var(--border-subtle); }
.s3-modify-header h2 { margin: 0; font-size: var(--text-md); }
.s3-modify-header p { margin: var(--space-1) 0 0; color: var(--text-secondary); font-size: var(--text-xs); overflow-wrap: anywhere; }
.s3-modify-notice { margin: var(--space-3) var(--space-4) 0; color: var(--text-secondary); font-size: var(--text-xs); line-height: var(--leading-relaxed); }
.s3-modify-dialog :deep(.modify-panel) { width: 100%; max-width: none; min-width: 0; border: 0; background: transparent; }
.script-edit-dialog { overflow: hidden; }
.script-edit-body { display: grid; gap: var(--space-2); min-height: 0; padding: var(--space-4); overflow: auto; }
.script-edit-body label { color: var(--text-primary); font-size: var(--text-xs); font-weight: var(--weight-semibold); }
.script-edit-body .content-script-textarea { min-height: 260px; max-height: 55dvh; overflow: auto; }
.script-edit-footer { display: flex; justify-content: flex-end; gap: var(--space-2); padding: var(--space-3) var(--space-4); border-top: 1px solid var(--border-subtle); background: var(--bg-surface); }
.page-task-panel { display: grid; gap: var(--space-2); padding: var(--space-4); border: 1px solid var(--color-primary-border); border-radius: var(--radius-md); background: var(--color-primary-soft); }
.page-task-panel h4, .page-task-panel p { margin: 0; }
.page-task-panel p { color: var(--text-secondary); font-size: var(--text-xs); }
.page-task-steps { display: grid; gap: var(--space-2); margin: 0; padding-left: var(--space-5); }
.page-task-steps li { padding-left: var(--space-1); font-size: var(--text-xs); }
.page-task-steps li strong { margin-left: var(--space-3); color: var(--color-primary); }
.s3-workbench--review { grid-template-columns: minmax(0, 1fr); grid-template-areas: 'main'; }
.review-primary-actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: var(--space-2); }
.review-drawer-backdrop { position: fixed; inset: 0; z-index: calc(var(--z-overlay) + 1); background: rgb(17 31 27 / 45%); }
.review-drawer { position: fixed; top: 0; right: 0; bottom: 0; z-index: calc(var(--z-overlay) + 2); width: min(480px, 100vw); box-sizing: border-box; padding: var(--space-4); overflow: auto; background: var(--bg-surface); box-shadow: var(--shadow-md); }
.review-drawer-header { position: sticky; top: calc(-1 * var(--space-4)); z-index: 1; display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); padding: var(--space-3) 0; border-bottom: 1px solid var(--border-subtle); background: var(--bg-surface); }
.review-drawer-header h3 { margin: 0; font-size: var(--text-md); }
.review-drawer .style-panel { max-width: none; padding: var(--space-3) 0; border: 0; }
.review-drawer .interactive-section { max-width: none; padding: var(--space-3) 0; border: 0; }
.review-drawer :deep(.evidence-sidebar) { position: static; width: 100%; max-height: none; }
.review-script-tool { padding: var(--space-3) 0; }
.page-generation { display: grid; gap: var(--space-4); margin-top: var(--space-5); padding-top: var(--space-4); border-top: 1px solid var(--border-subtle); }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.section-heading h3 { margin: 0; color: var(--text-primary); }
.section-heading span { color: var(--text-secondary); font-size: var(--text-xs); }
.generation-advanced { border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: var(--space-3); }
.generation-advanced > summary { cursor: pointer; color: var(--text-secondary); font-size: var(--text-xs); }
.phase-panel.review-panel { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: var(--space-4); align-items: start; }
.review-preview { grid-column: 2; grid-row: 1; min-width: 0; padding: var(--space-4); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--bg-surface); }
.review-preview .preview-frame { height: min(68vh, 760px); }
.review-pages { grid-column: 1; grid-row: 1 / span 4; display: grid; align-content: start; gap: var(--space-3); min-width: 0; max-height: 75vh; overflow: auto; }
.review-pages h3 { margin: 0; font-size: var(--text-sm); }
.review-pages .page-item { display: grid; }
.review-pages .pages-control-bar { display: none; }
.review-tool, .review-finish { grid-column: 2; padding: var(--space-3); }
.review-script { white-space: pre-wrap; max-height: 240px; overflow: auto; font-size: var(--text-xs); }
.page-evidence-state, .review-selection { color: var(--text-secondary); font-size: var(--text-2xs); }
.outline-brief { padding: var(--space-4); margin-bottom: var(--space-4); }
.outline-brief h2 { margin: 0 0 var(--space-2); font-size: var(--text-md); }
.outline-brief p { margin: var(--space-1) 0; color: var(--text-secondary); font-size: var(--text-xs); }
.outline-references { margin-top: var(--space-4); padding: var(--space-3); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); font-size: var(--text-xs); }
.outline-references summary { cursor: pointer; }
.outline-references ul { display: grid; gap: var(--space-2); padding: 0; list-style: none; }
.outline-references li { display: flex; gap: var(--space-3); justify-content: space-between; }
.outline-references p, .outline-references span { color: var(--text-secondary); }

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-5);
}
.page-head__eyebrow {
  margin: 0 0 var(--space-1);
  font-size: var(--text-2xs);
  font-weight: var(--weight-semibold);
  letter-spacing: 0.06em;
  color: var(--color-primary);
}
.page-head__title {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: var(--weight-semibold);
  line-height: var(--leading-tight);
  color: var(--text-primary);
}
.page-head__desc {
  margin: var(--space-1) 0 0;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
.page-head__actions { display: flex; align-items: center; gap: var(--space-2); flex-shrink: 0; }
.page-body {
  flex: 1;
}
.evidence-warning {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 14px;
  padding: 13px 16px;
  border: 1px solid #f0d5a8;
  border-radius: 12px;
  background: #fffaf0;
  color: #7c4a15;
}
.evidence-warning div {
  display: grid;
  flex: 1 1 320px;
  gap: 4px;
  min-width: 0;
}
.evidence-warning strong {
  flex-shrink: 0;
  font-size: 13px;
}
.evidence-warning span {
  font-size: 12px;
  line-height: 1.55;
  color: #8a6337;
}
.evidence-warning a {
  flex-shrink: 0;
  color: #2f605a;
  font-size: 12px;
  font-weight: 700;
  text-decoration: none;
}

.evidence-gate { display:flex; align-items:center; justify-content:space-between; gap:18px; margin:0 0 16px; padding:16px 18px; border:1px solid #e5b66d; border-radius:14px; background:#fff8ea; color:#714d18; }
.evidence-gate>div:first-child { display:flex; flex-direction:column; gap:5px; }
.evidence-gate strong { font-size:14px; }
.evidence-gate span { font-size:12px; color:#8b6b3d; }
.evidence-gate-actions { display:flex; align-items:center; gap:9px; flex-wrap:wrap; }
.evidence-gate-actions button,.evidence-gate-actions a { padding:8px 12px; border:1px solid #ba8437; border-radius:9px; background:#8f5f20; color:#fff; font:600 12px/1.2 inherit; text-decoration:none; cursor:pointer; }
.evidence-gate-actions button:disabled { opacity:.55; cursor:not-allowed; }
.evidence-gate-actions .plain { background:#fff; color:#77501c; }
.version-branch-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 14px;
  padding: 11px 15px;
  border: 1px solid #b9d9cd;
  border-radius: 12px;
  background: #eff8f4;
  color: #24594d;
  font-size: 13px;
}
.version-branch-banner span { color: #617c73; }

/* 阶段面板 */
.phase-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.s3-ai-panel { background: var(--bg-surface); }
.style-ai-hint { padding: var(--space-3); border-radius: var(--radius-sm); background: var(--color-primary-soft); color: var(--text-secondary); font-size: var(--text-xs); line-height: var(--leading-relaxed); }

/* 统一断点：1280 / 1024 / 768；不再用 1400 / 1100 / 700 让位 padding */
@media (max-width: 1279px) {
  .s3-workbench {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: "main" "assistant";
  }
  .s3-workbench > .s3-assistant-col { width: 100%; }
  .s3-workbench :deep(.s3-ai-panel) { position: static; max-height: 480px; }
}
@media (max-width: 1023px) {
  .s3-workbench {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: "main" "assistant";
  }
  .s3-workbench > :deep(.evidence-sidebar) { position: static; max-height: 420px; }
  .s3-workbench :deep(.s3-ai-panel) { max-height: 480px; }
  .phase-panel.review-panel { grid-template-columns: minmax(0, 1fr); }
  .review-preview, .review-pages, .review-tool, .review-finish { grid-column: 1; grid-row: auto; }
  .review-pages { max-height: 320px; }
}
@media (max-width: 767px) {
  .s3-page { padding: var(--space-4); gap: var(--space-3); }
  .page-head { flex-direction: column; align-items: flex-start; }
  .page-head__actions { flex-wrap: wrap; }
  .evidence-warning { align-items: flex-start; flex-direction: column; }
  .evidence-warning div { align-items: flex-start; flex-direction: column; gap: var(--space-1); }
  .style-panel { padding: var(--space-4); }
  .style-actions,.gen-complete-actions { flex-direction: column; }
  .style-actions button,.gen-complete-actions button { width: 100%; }
  .preview-frame { height: 360px; }
  .page-item { align-items: flex-start; flex-direction: column; }
  .page-item-right { width: 100%; justify-content: flex-end; }
}
.save-state.saving { color: var(--color-warning); border-color: var(--color-warning-border); }
.save-state.error { color: var(--color-danger); border-color: var(--color-danger-border); }
.save-version:disabled { opacity: 0.48; cursor: not-allowed; }
.style-panel { max-width: 680px; padding: 22px; border: 1px solid #dce9e3; border-radius: 14px; background: #fff; }
.style-panel h3 { margin: 0; color: #24483e; }.style-panel p { color: #667b73; font-size: 13px; }
.style-panel label { display: grid; gap: 6px; margin-top: 14px; color: #365e52; font-size: 13px; font-weight: 600; }
.style-panel select { padding: 9px; border: 1px solid #c7ddd4; border-radius: 8px; background: #fff; }.style-actions { display: flex; gap: 10px; margin-top: 20px; }

/* 生成控制栏 */
.gen-control-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px 16px;
  background: #f8fbf9;
  border: 1px solid #e4ede8;
  border-radius: 12px;
}
.gen-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  flex-wrap: wrap;
}
.gen-label {
  font-weight: 600;
  color: #2f605a;
}
.gen-value {
  color: #475569;
}
.gen-mode-select {
  padding: 4px 8px;
  border: 1px solid #c6ded6;
  border-radius: 6px;
  font-size: 12px;
  color: #2f605a;
  background: #fff;
  outline: none;
  cursor: pointer;
}
.gen-actions {
  display: flex;
  gap: 8px;
}

/* 进度条 */
.gen-progress-panel {
  padding: 12px 16px;
  background: #f8fbf9;
  border: 1px solid #e4ede8;
  border-radius: 12px;
}
.progress-bar-wrap {
  height: 8px;
  background: #e2ece6;
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 8px;
}
.progress-bar-fill {
  height: 100%;
  background: #2f605a;
  border-radius: 999px;
  transition: width 0.4s ease;
}
.progress-text {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #607a71;
}

/* 错误条 */
.error-bar {
  padding: 10px 14px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #dc2626;
  font-size: 13px;
}

/* 节点预览 */
.gen-nodes-preview {
  padding: 12px 16px;
  background: #f8fbf9;
  border: 1px solid #e4ede8;
  border-radius: 12px;
}
.gen-nodes-preview h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #2f605a;
}
.nodes-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.node-chip {
  font-size: 12px;
  background: #e8f5f0;
  color: #2f605a;
  padding: 3px 10px;
  border-radius: 999px;
}

/* 预览区 */
.preview-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.preview-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: #2f605a;
  font-weight: 600;
}
.preview-frame {
  width: 100%;
  height: 480px;
  border: 1px solid #e2ece6;
  border-radius: 12px;
  background: #fff;
}
.preview-placeholder {
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed #c6ded6;
  border-radius: 12px;
  color: #94a3b8;
  font-size: 13px;
}

/* 无资料提示 */
.no-evidence-hint {
  font-size: 12px;
  color: #7c4a15;
  background: #fffaf0;
  border: 1px solid #f0d5a8;
  border-radius: 8px;
  padding: 10px 14px;
}
.no-evidence-hint a {
  color: #2f605a;
  font-weight: 600;
}

/* 生成完成操作 */
.gen-complete-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

/* 内容生成阶段 */
.content-info-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px 16px;
  background: #f8fbf9;
  border: 1px solid #e4ede8;
  border-radius: 12px;
}
.content-info-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  flex-wrap: wrap;
}
.content-info-right {
  display: flex;
  gap: 8px;
}
.content-nodes-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.content-node-card {
  border: 1.5px solid #e2ece6;
  border-radius: 12px;
  padding: 12px 16px;
  background: #fff;
  transition: border-color 0.15s;
}
.content-node-card.node-done {
  border-color: #6ee7b7;
}
.content-node-card.node-pending {
  border-color: #e2ece6;
  opacity: 0.85;
}
.content-node-card.node-current {
  border-color: #fcd34d;
  box-shadow: 0 0 0 1px #fcd34d33;
}
.node-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.node-order {
  font-size: 12px;
  font-weight: 700;
  color: #2f605a;
  background: #e8f5f0;
  padding: 2px 8px;
  border-radius: 999px;
}
.node-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}
.node-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
  background: #d1fae5;
  color: #065f46;
}
.node-badge-pending {
  background: #fef9c3;
  color: #854d0e;
}
.node-badge-empty {
  background: #f3f4f6;
  color: #6b7280;
}
.node-body {
  font-size: 13px;
}
.node-summary {
  font-size: 12px;
  color: #607a71;
  margin-bottom: 6px;
}
.node-script {
  font-size: 13px;
  color: #334155;
  line-height: 1.6;
  white-space: pre-wrap;
  padding: 8px 12px;
  background: #f8fbf9;
  border-radius: 8px;
}
.content-script-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
  padding: 14px;
  background: #f8fbf9;
  border: 1px solid #c6ded6;
  border-radius: 10px;
}
.content-script-editor label { color: #2f605a; font-size: 13px; font-weight: 600; }
.content-script-textarea {
  box-sizing: border-box;
  width: 100%;
  min-height: 180px;
  padding: 10px 12px;
  border: 1px solid #c6ded6;
  border-radius: 8px;
  font: inherit;
  line-height: 1.6;
  resize: vertical;
}
.content-script-textarea:focus { border-color: #5ca68f; outline: none; }
.node-key-points {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
.key-point-tag {
  font-size: 12px;
  background: #e8f5f0;
  color: #2f605a;
  padding: 2px 8px;
  border-radius: 999px;
}
.node-actions {
  margin-top: 8px;
  display: flex;
  gap: 6px;
}
.content-modify-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  padding: 12px 14px;
  background: #f0f5f2;
  border: 1px solid #c6ded6;
  border-radius: 10px;
}
.content-modify-title {
  color: #2f605a;
  font-size: 13px;
  white-space: nowrap;
}
.content-modify-input {
  flex: 1;
  min-width: 220px;
  padding: 7px 10px;
  border: 1px solid #c6ded6;
  border-radius: 8px;
  font-size: 13px;
  outline: none;
}
.content-modify-input:focus { border-color: #5ca68f; }
.content-modify-error {
  flex-basis: 100%;
  color: #dc2626;
  font-size: 12px;
}
.node-content-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.node-placeholder {
  font-size: 13px;
  color: #94a3b8;
  padding: 8px 0;
}

/* 页面管理 */
.pages-control-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 14px;
  background: #f8fbf9;
  border: 1px solid #e4ede8;
  border-radius: 12px;
}
.pages-info {
  font-size: 13px;
  color: #475569;
}
.pages-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.page-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px;
  background: #fff;
  border: 1.5px solid #e2ece6;
  border-radius: 10px;
  cursor: pointer;
}
.page-item:focus-visible {
  outline: 2px solid #4a90d9;
  outline-offset: 2px;
}
/* 选中页 = 对话里「这页」的所指，所以用比 hover 更实的左边条标出来 */
.page-item.page-active {
  border-color: #4a90d9;
  box-shadow: inset 3px 0 0 #4a90d9;
}
.page-item.page-modified {
  border-color: #24a36f;
  background: #effdf7;
  box-shadow: 0 0 0 3px rgba(36, 163, 111, .12);
  animation: pageModified 2s ease-out;
}
.changed-badge {
  padding: 2px 7px;
  border-radius: 999px;
  background: #24a36f;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}
@keyframes pageModified {
  from { transform: translateY(-2px); }
  to { transform: translateY(0); box-shadow: none; }
}
.page-status-done {
  border-color: #6ee7b7;
}
.page-status-failed {
  border-color: #fca5a5;
}
.page-status-processing {
  border-color: #fcd34d;
}
.page-item-left {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.page-order {
  font-weight: 600;
  color: #2f605a;
}
.page-node {
  color: #64748b;
  font-size: 12px;
}
.page-item-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.page-status-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
}
.page-status-done .page-status-badge {
  background: #d1fae5;
  color: #065f46;
}
.page-status-failed .page-status-badge {
  background: #fee2e2;
  color: #991b1b;
}
.page-status-processing .page-status-badge {
  background: #fef9c3;
  color: #854d0e;
}
.page-status-pending .page-status-badge {
  background: #f3f4f6;
  color: #6b7280;
}
.pages-empty {
  text-align: center;
  padding: 40px;
  color: #94a3b8;
  font-size: 13px;
}

/* 互动资源 */
.interactive-section {
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #e4ede8;
  border-radius: 12px;
}
.interactive-section h4 {
  margin: 0 0 6px;
  font-size: 14px;
  color: #1e293b;
}
.interactive-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: #64748b;
}
.interactive-node-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.interactive-node-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px;
  background: #f8fbf9;
  border-radius: 8px;
}
.int-node-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.int-node-title {
  font-size: 13px;
  color: #1e293b;
}
.int-node-type {
  font-size: 12px;
  background: #e8f5f0;
  color: #2f605a;
  padding: 1px 6px;
  border-radius: 999px;
}
.int-node-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.asset-done {
  font-size: 12px;
  color: #065f46;
}
.asset-pending {
  font-size: 12px;
  color: #854d0e;
}
.no-interactive-hint {
  font-size: 12px;
  color: #94a3b8;
  text-align: center;
  padding: 10px 0;
}
.interactive-preview-card { margin-top: 14px; overflow: hidden; border: 1px solid #c8ddd5; border-radius: 12px; background: #fff; }
.interactive-preview-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border-bottom: 1px solid #e3ece8; background: #f5faf8; }
.interactive-preview-head > div { display: flex; align-items: center; gap: 8px; }
.interactive-preview-head strong { color: #23584c; font-size: 13px; }
.interactive-preview-head span { color: #70837c; font-size: 12px; }
.interactive-preview-frame { display: block; width: 100%; min-height: 520px; border: 0; background: #fff; }

/* 通用按钮 */
.btn {
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s;
  border: 1px solid transparent;
}
.btn-sm {
  padding: 5px 12px;
  font-size: 12px;
}
.btn-outline {
  background: #fff;
  border-color: #c6ded6;
  color: #2f605a;
}
.btn-outline:hover {
  background: #f0f5f2;
}
.btn-primary {
  background: #2f605a;
  color: #fff;
}
.btn-primary:hover:not(:disabled) {
  background: #1e4a44;
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 步骤导航已抽为公共组件 StepNav，流程条样式不再在此重复定义 */
@media (max-width: 767px) {
  .gen-control-bar { flex-direction: column; align-items: flex-start; }
}
.s3-workbench--review { grid-template-columns: minmax(0, 1fr); grid-template-areas: 'main'; }
@media (max-width: 767px) {
  .review-drawer { width: 100vw; }
  .review-primary-actions > button { flex: 1 1 180px; }
  .review-toolbar-actions { width: 100%; }
}
</style>

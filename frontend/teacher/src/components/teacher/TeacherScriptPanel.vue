<template>
  <div class="editor-workbench">
    <header class="workbench-hero">
      <div class="workbench-hero-text">
        <h2>智能备课工作台 - 讲稿编辑</h2>
        <p>左侧课件与节点时间线，右侧讲稿与知识库资源联动；顶部可进入学情迭代建议。</p>
      </div>
      <button type="button" class="iteration-entry-btn" @click="$emit('open-iteration')">学情迭代建议</button>
    </header>

    <header class="window-toolbar">
      <button type="button" class="window-toggle-btn" :class="{ active: isPreviewWindowOpen }" @click="toggleWindow('preview')">
        <span class="toggle-dot"></span>
        课件预览
      </button>
      <button type="button" class="window-toggle-btn" :class="{ active: isEditorWindowOpen }" @click="toggleWindow('editor')">
        <span class="toggle-dot"></span>
        讲稿编辑
      </button>
    </header>

    <section v-if="!isPreviewWindowOpen && !isEditorWindowOpen" class="workbench-empty-state">
      <div class="empty-state-copy">
        <h4>暂无打开窗口</h4>
        <p>点击上方按钮打开课件预览或内容编辑器，窗口支持独立关闭与再次打开。</p>
      </div>
    </section>

    <div v-else class="window-grid" :class="windowGridClass">
      <section v-if="isPreviewWindowOpen" class="dock-window">
        <header class="dock-head dock-head--labeled">
          <div class="dock-title">
            <span class="dock-signal"></span>
            <div class="dock-title-text">
              <span class="dock-title-main">课件预览</span>
              <span class="dock-title-sub">画布与时间线 · 与右侧讲稿同一节点联动</span>
            </div>
          </div>
          <button type="button" class="dock-close-btn" @click="isPreviewWindowOpen = false" title="关闭预览面板">×</button>
        </header>

        <section class="viewer-stage">
          <div v-if="iterationSyncNotice" class="iteration-sync-banner">
            <strong>学情迭代已回填</strong>
            <span>{{ iterationSyncNotice }}</span>
          </div>
          <header class="stage-head stage-head--compact">
            <div class="stage-head-left">
              <span class="stage-badge">当前页</span>
              <span class="stage-page-line">第 <strong>{{ currentEditPage }}</strong> / {{ totalPages || 1 }} 页</span>
            </div>
          </header>

          <div class="slide-wrap" v-if="currentCourseId">
            <button
              class="slide-nav-btn prev"
              @click="$emit('prev-page')"
              :disabled="currentEditPage <= 1"
              title="上一页"
            >
              ‹
            </button>
            <div class="slide-canvas">
              <img
                v-if="previewUrl && !previewImageFailed"
                :src="previewUrl"
                alt="课件预览"
                class="preview-image"
                @load="previewImageFailed = false"
                @error="previewImageFailed = true"
              />
              <div
                v-else
                class="slide-preview-mock"
                role="img"
                :aria-label="`第${currentEditPage}页课件预览占位`"
              >
                <div class="slide-preview-mock__frame">
                  <header class="slide-preview-mock__top">
                    <span class="slide-preview-mock__brand" aria-hidden="true">
                      <svg class="slide-preview-mock__icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M4 5a2 2 0 012-2h12a2 2 0 012 2v11a2 2 0 01-2 2H6l-4 3V5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
                        <path d="M8 9h8M8 13h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
                      </svg>
                    </span>
                    <div class="slide-preview-mock__head-text">
                      <span class="slide-preview-mock__title">{{ slideTitleText }}</span>
                      <span class="slide-preview-mock__sub">{{ slideSubtitleText }}</span>
                    </div>
                    <span class="slide-preview-mock__page-pill">第 {{ currentEditPage }} / {{ totalPages || 1 }} 页</span>
                  </header>
                  <div class="slide-preview-mock__body">
                    <span
                      v-for="w in mockLineWidths"
                      :key="w.key"
                      class="slide-preview-mock__line"
                      :style="{ width: w.pct }"
                    />
                  </div>
                  <p class="slide-preview-mock__hint">
                    {{ previewHintText }}
                  </p>
                </div>
              </div>
            </div>
            <button
              class="slide-nav-btn next"
              @click="$emit('next-page')"
              :disabled="currentEditPage >= totalPages"
              title="下一页"
            >
              ›
            </button>
          </div>
          <div class="no-preview" v-else>请先选择课件</div>

          <div class="timeline-heading">
            <span class="timeline-heading__label">讲解节点时间线</span>
            <span class="timeline-heading__hint">点击节点与右侧讲稿对应；时长为预估参考</span>
          </div>
          <div class="timeline-area">
            <div class="timeline-curve"></div>
            <div class="timeline-line"></div>
            <div
              v-for="(node, index) in timelineNodes"
              :key="node.nodeId || index"
              class="timeline-node"
              :class="{ active: selectedNodeIndex === index }"
              @click="selectedNodeIndex = index"
            >
              <div class="node-bubble">
                <strong>{{ node.title || `节点 ${index + 1}` }}</strong>
                <span>{{ Number(node.estimatedDuration) || 20 }}秒</span>
                <small v-if="nodeInsightLine(node)" class="node-insight">{{ nodeInsightLine(node) }}</small>
              </div>
              <span class="node-dot"></span>
            </div>
          </div>

          <footer class="stage-actions">
            <div v-if="scriptGenerating || aiGenerateProgress > 0" class="ai-progress-card">
              <div class="ai-progress-head">
                <strong>{{ aiGenerateStageText || 'AI 处理中' }}</strong>
                <span>{{ Math.max(0, Math.min(100, Number(aiGenerateProgress) || 0)) }}%</span>
              </div>
              <div class="ai-progress-track">
                <i :style="{ width: `${Math.max(0, Math.min(100, Number(aiGenerateProgress) || 0))}%` }"></i>
              </div>
            </div>

            <div class="action-strip action-strip--nodes">
              <div class="action-strip__head">
                <span class="action-strip__title">节点结构</span>
                <span class="action-strip__desc">增删与 AI 建议仅作用于本页时间线</span>
              </div>
              <div class="action-strip__row">
                <button type="button" class="btn-tool" @click="addNode" :disabled="!currentCourseId">+ 新增节点</button>
                <button type="button" class="btn-tool" @click="$emit('generate-ai-script')" :disabled="!currentCourseId || scriptGenerating || scriptSaving">
                  {{ scriptGenerating ? '生成中…' : '智能生成节点建议' }}
                </button>
                <button type="button" class="btn-tool btn-tool--warn" @click="rebuildNodesFromScript" :disabled="!currentCourseId">按全文重建节点</button>
              </div>
            </div>

            <div class="action-strip action-strip--page">
              <div class="action-strip__head">
                <span class="action-strip__title">幻灯片定位</span>
                <span class="action-strip__desc">与上方画布箭头一致，便于底部快速翻页</span>
              </div>
              <div class="action-strip__row action-strip__row--page">
                <button type="button" class="btn-tool btn-tool--pager" @click="$emit('prev-page')" :disabled="currentEditPage <= 1" title="上一页">上一页</button>
                <span class="page-pill">第 {{ currentEditPage }} / {{ totalPages || 1 }} 页</span>
                <button type="button" class="btn-tool btn-tool--pager" @click="$emit('next-page')" :disabled="currentEditPage >= totalPages" title="下一页">下一页</button>
              </div>
              <div class="action-strip__audio">
                <button type="button" class="btn-tool" @click="$emit('generate-audio')" :disabled="!currentCourseId || scriptGenerating">
                  生成页面音频
                </button>
              </div>
            </div>

            <div class="action-strip action-strip--save">
              <p class="save-hint">保存后写入当前课件页，并参与发布与学情统计</p>
              <button type="button" class="btn-save-primary" @click="$emit('save-script')" :disabled="!currentCourseId || scriptSaving || scriptGenerating">
                {{ scriptSaving ? '保存中…' : '保存讲稿与节点' }}
              </button>
            </div>
            <div class="action-strip action-strip--audio">
              <div v-if="audioGenerating" class="audio-status">生成音频中…</div>
              <div v-else-if="currentPageAudio && currentPageAudio.sections && currentPageAudio.sections.length">
                <div class="audio-player">
                  <div class="audio-controls">
                    <button type="button" class="btn-tool" @click="playPrevSection" :disabled="currentSectionIndex <= 0">上段</button>
                    <button type="button" class="btn-tool" @click="togglePlay">{{ isPlaying ? '暂停' : '播放' }}</button>
                    <button type="button" class="btn-tool" @click="playNextSection" :disabled="currentSectionIndex >= sections.length - 1">下段</button>
                    <span class="audio-meta">段 {{ currentSectionIndex + 1 }} / {{ sections.length }}</span>
                    <label class="rate-label">速率
                      <select class="rate-select" v-model.number="playbackRate">
                        <option :value="0.75">0.75x</option>
                        <option :value="1">1x</option>
                        <option :value="1.25">1.25x</option>
                        <option :value="1.5">1.5x</option>
                        <option :value="2">2x</option>
                      </select>
                    </label>
                    <button type="button" class="btn-tool" @click="downloadCurrentSection" :disabled="!currentSection || !currentSection.audio_url">下载</button>
                  </div>
                  <audio ref="audioEl" controls @timeupdate="onTimeUpdate" @ended="onEnded"></audio>
                  <ul class="audio-section-list">
                    <li v-for="(s, idx) in sections" :key="s.node_id || idx" :class="{ active: idx === currentSectionIndex }" @click="playSection(idx)">
                      <strong>{{ idx + 1 }}. {{ s.title || '段落' }}</strong>
                      <div class="section-hint">{{ s.duration_sec || s.audio_duration_sec || 0 }}s · {{ s.tts_status || s.status || '' }}</div>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </footer>
        </section>
      </section>

      <section v-if="isEditorWindowOpen" class="dock-window editor-dock">
        <header class="dock-head dock-head--labeled">
          <div class="dock-title">
            <span class="dock-signal dock-signal--blue"></span>
            <div class="dock-title-text">
              <span class="dock-title-main">讲稿编辑</span>
              <span class="dock-title-sub">正文写入当前选中节点 · 右侧可插入知识库素材</span>
            </div>
          </div>
          <button type="button" class="dock-close-btn" @click="isEditorWindowOpen = false" title="关闭讲稿面板">×</button>
        </header>

        <div class="editor-split">
          <aside class="copilot-panel">
            <div class="copilot-heading">
              <h4>节点讲稿</h4>
              <p class="copilot-sub">与左侧时间线选中项一一对应，切换节点分别编辑</p>
            </div>

            <section class="panel-block grow">
              <h5 class="panel-block__title">正文</h5>
              <div class="node-tabs" v-if="timelineNodes.length">
                <button
                  v-for="(node, idx) in timelineNodes"
                  :key="node.nodeId || idx"
                  type="button"
                  :class="{ active: selectedNodeIndex === idx }"
                  @click="selectedNodeIndex = idx"
                >
                  节点{{ idx + 1 }}：{{ node.title || '未命名' }}
                </button>
              </div>
              <textarea
                class="linked-editor"
                :value="selectedNodeScript"
                placeholder="在这里编辑当前节点讲稿..."
                @input="updateSelectedNodeText($event.target.value)"
              ></textarea>
            </section>
          </aside>

          <aside class="kb-rail" aria-label="知识库资源">
            <div class="kb-rail-head">
              <h4>知识库资源</h4>
              <p class="kb-rail-hint">与「知识库 · 我的教学资源」同源；拖拽或插入到当前节点文末</p>
            </div>
            <ul class="kb-rail-list">
              <li
                v-for="item in kbRailItems"
                :key="item.id"
                class="kb-rail-item"
                draggable="true"
                @dragstart="onKbDragStart($event, item)"
              >
                <strong>{{ item.title }}</strong>
                <span>{{ item.tag }}</span>
                <button type="button" class="kb-insert" @click="insertKbSnippet(item)">插入</button>
              </li>
            </ul>
          </aside>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const previewImageFailed = ref(false)
const props = defineProps({
  previewUrl: {
    type: String,
    default: ''
  },
  currentCourseName: {
    type: String,
    default: ''
  },
  currentCourseId: {
    type: String,
    default: ''
  },
  currentEditPage: {
    type: Number,
    default: 1
  },
  totalPages: {
    type: Number,
    default: 1
  },
  currentScript: {
    type: String,
    default: ''
  },
  currentScriptNodes: {
    type: Array,
    default: () => []
  },
  scriptGenerating: {
    type: Boolean,
    default: false
  },
  scriptSaving: {
    type: Boolean,
    default: false
  },
  aiGenerateProgress: {
    type: Number,
    default: 0
  },
  aiGenerateStageText: {
    type: String,
    default: ''
  },
  iterationSyncNotice: {
    type: String,
    default: ''
  },
  nodeInsights: {
    type: Object,
    default: () => ({})
  }
  ,
  currentPageAudio: {
    type: Object,
    default: null
  },
  audioGenerating: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['generate-ai-script', 'generate-audio', 'save-script', 'update:current-script', 'update:current-script-nodes', 'prev-page', 'next-page', 'open-iteration'])

const localNodes = ref([])
const selectedNodeIndex = ref(0)
const isPreviewWindowOpen = ref(true)
const isEditorWindowOpen = ref(true)
const audioEl = ref(null)
const isPlaying = ref(false)
const currentSectionIndex = ref(0)
const playbackRate = ref(1)

const currentSection = computed(() => sections.value[currentSectionIndex.value] || null)

watch(() => playbackRate.value, (v) => {
  try { if (audioEl.value) audioEl.value.playbackRate = Number(v) || 1 } catch {}
})

const sections = computed(() => {
  if (!props.currentPageAudio || !Array.isArray(props.currentPageAudio.sections)) return []
  return props.currentPageAudio.sections
})

const kbRailItems = [
  { id: 'kb1', title: '分治·简案片段', tag: '教案' },
  { id: 'kb2', title: '递归微课 12′', tag: '视频' },
  { id: 'kb3', title: '随堂测 6 题', tag: '习题' }
]

const slideTitleText = computed(() => {
  const t = String(props.currentCourseName || '').trim()
  return t || '当前课件'
})

const slideSubtitleText = computed(() => '课件页预览 · 版式示意')

const mockLineWidths = computed(() => {
  const p = Number(props.currentEditPage) || 1
  const sets = [
    ['88%', '72%', '91%', '64%'],
    ['92%', '68%', '85%', '76%'],
    ['78%', '94%', '70%', '82%'],
    ['86%', '80%', '88%', '58%'],
    ['90%', '76%', '82%', '70%'],
    ['84%', '88%', '74%', '86%']
  ]
  const row = sets[(p - 1) % sets.length]
  return row.map((pct, i) => ({ key: `L${p}_${i}`, pct }))
})

const previewHintText = computed(() => {
  if (props.previewUrl && previewImageFailed.value) {
    return '预览图加载失败，已使用版式占位。可稍后刷新或检查课件预览服务。'
  }
  return '文档类课件将在此显示页面切片；当前为版式占位，右侧讲稿与节点可照常编辑。'
})

watch(
  () => [props.previewUrl, props.currentEditPage],
  () => {
    previewImageFailed.value = false
  }
)

const nodeInsightLine = (node) => {
  const id = String(node?.nodeId || '').trim()
  if (!id) return ''
  const row = props.nodeInsights?.[id]
  if (!row) return ''
  const m = row.mastery != null ? `掌握度 ${row.mastery}%` : ''
  const c = row.card != null ? `卡点 ${row.card}` : ''
  return [m, c].filter(Boolean).join(' · ')
}

const onKbDragStart = (event, item) => {
  try {
    event.dataTransfer.setData('text/plain', `【知识库】${item.title}`)
    event.dataTransfer.effectAllowed = 'copy'
  } catch {
    /* ignore */
  }
}

const insertKbSnippet = (item) => {
  const line = `\n【知识库引用】${item.title}（${item.tag}）\n`
  updateSelectedNodeText(String(selectedNodeScript.value || '') + line)
}

const windowGridClass = computed(() => {
  if (isPreviewWindowOpen.value && isEditorWindowOpen.value) return 'two-open'
  if (isPreviewWindowOpen.value) return 'single-open preview-only'
  if (isEditorWindowOpen.value) return 'single-open editor-only'
  return 'single-open'
})

const toggleWindow = (windowType) => {
  if (windowType === 'preview') {
    isPreviewWindowOpen.value = !isPreviewWindowOpen.value
    return
  }
  if (windowType === 'editor') {
    isEditorWindowOpen.value = !isEditorWindowOpen.value
  }
}

const syncNodesFromProps = (nodes) => {
  const mapped = (nodes || []).map((node, index, list) => ({
    id: node.id || '',
    nodeId: node.nodeId || `p${props.currentEditPage}_n${index + 1}`,
    type: node.type || inferNodeType(index, list.length),
    title: node.title || `${index === 0 ? '节点1：开场' : `节点${index + 1}：讲解`}`,
    summary: node.summary || node.text || '',
    scriptText: node.scriptText || node.text || '',
    reteachScript: node.reteachScript || '',
    transitionText: node.transitionText || '',
    estimatedDuration: Number(node.estimatedDuration) || estimateDuration(node.scriptText || node.summary || node.text || ''),
    sortOrder: Number(node.sortOrder) || index + 1
  }))

  localNodes.value = mapped
  if (selectedNodeIndex.value > mapped.length - 1) {
    selectedNodeIndex.value = Math.max(0, mapped.length - 1)
  }
}

watch(() => props.currentScriptNodes, (value) => {
  syncNodesFromProps(value)
}, { immediate: true, deep: true })

watch(() => props.currentEditPage, () => {
  selectedNodeIndex.value = 0
})

const emitNodes = () => {
  emit('update:current-script-nodes', localNodes.value.map((node, index, list) => ({
    ...node,
    type: inferNodeType(index, list.length),
    sortOrder: index + 1,
    estimatedDuration: Number(node.estimatedDuration) || estimateDuration(node.scriptText || node.summary || '')
  })))
}

const syncScriptFromNodes = () => {
  const merged = localNodes.value
    .map(node => String(node.scriptText || node.summary || '').trim())
    .filter(Boolean)
    .join('\n')
  emit('update:current-script', merged)
}

const timelineNodes = computed(() => {
  if (localNodes.value.length > 0) return localNodes.value
  return [{
    nodeId: `p${props.currentEditPage}_n1`,
    type: 'opening',
    title: '节点1：开场',
    scriptText: props.currentScript || '',
    estimatedDuration: 20
  }]
})

const selectedNodeScript = computed(() => {
  const node = timelineNodes.value[selectedNodeIndex.value]
  return node?.scriptText || ''
})

const updateNode = (index, field, value) => {
  localNodes.value = localNodes.value.map((node, currentIndex) => {
    if (currentIndex !== index) return node
    return {
      ...node,
      [field]: field === 'estimatedDuration' ? Number(value) || 0 : value
    }
  })
  emitNodes()
  syncScriptFromNodes()
}

const addNode = () => {
  localNodes.value = [...localNodes.value, {
    id: '',
    nodeId: `p${props.currentEditPage}_n${localNodes.value.length + 1}`,
    type: inferNodeType(localNodes.value.length, localNodes.value.length + 1),
    title: `节点${localNodes.value.length + 1}：讲解`,
    summary: '',
    scriptText: '',
    reteachScript: '',
    transitionText: '',
    estimatedDuration: 30,
    sortOrder: localNodes.value.length + 1
  }]
  selectedNodeIndex.value = localNodes.value.length - 1
  emitNodes()
  syncScriptFromNodes()
}

const rebuildNodesFromScript = () => {
  const raw = String(props.currentScript || '').trim()
  if (!raw) {
    localNodes.value = []
    emitNodes()
    emit('update:current-script', '')
    return
  }
  localNodes.value = raw
    .split(/\n{2,}|(?<=[。！？])\s*/)
    .map(item => item.trim())
    .filter(Boolean)
    .map((text, index, list) => ({
      id: '',
      nodeId: `p${props.currentEditPage}_n${index + 1}`,
      type: inferNodeType(index, list.length),
      title: `${index === 0 ? '节点1：开场' : `节点${index + 1}：核心代码`}`,
      summary: text.length > 48 ? `${text.slice(0, 48)}...` : text,
      scriptText: text,
      reteachScript: '',
      transitionText: '',
      estimatedDuration: estimateDuration(text),
      sortOrder: index + 1
    }))
  selectedNodeIndex.value = 0
  emitNodes()
  syncScriptFromNodes()
}

const updateSelectedNodeText = (value) => {
  if (!localNodes.value.length) {
    localNodes.value = [{
      id: '',
      nodeId: `p${props.currentEditPage}_n1`,
      type: 'opening',
      title: '节点1：开场',
      summary: '',
      scriptText: value,
      reteachScript: '',
      transitionText: '',
      estimatedDuration: estimateDuration(value),
      sortOrder: 1
    }]
  } else {
    updateNode(selectedNodeIndex.value, 'scriptText', value)
    return
  }
  emitNodes()
  syncScriptFromNodes()
}

const playSection = (index) => {
  const list = sections.value
  if (!list.length) return
  const idx = Math.max(0, Math.min(index, list.length - 1))
  const s = list[idx]
  if (!s || !s.audio_url) return
  currentSectionIndex.value = idx
  const el = audioEl.value
  if (!el) return
  el.src = s.audio_url
  try { el.playbackRate = Number(playbackRate.value) || 1 } catch {}
  el.play().then(() => { isPlaying.value = true }).catch(() => { isPlaying.value = false })
}

const playNextSection = () => {
  playSection(currentSectionIndex.value + 1)
}

const playPrevSection = () => {
  playSection(currentSectionIndex.value - 1)
}

const togglePlay = () => {
  const el = audioEl.value
  if (!el) return
  if (isPlaying.value) {
    el.pause(); isPlaying.value = false
  } else {
    el.play().then(() => { isPlaying.value = true }).catch(() => { isPlaying.value = false })
  }
}

const onTimeUpdate = (ev) => {
  const el = audioEl.value
  if (!el) return
  const t = Number(el.currentTime || 0)
  for (let i = 0; i < sections.value.length; i++) {
    const s = sections.value[i]
    const start = Number(s.audio_start_sec ?? s.start_sec ?? 0)
    const end = Number(s.audio_end_sec ?? s.end_sec ?? (s.audio_duration_sec ? start + Number(s.audio_duration_sec) : start + 9999))
    if (t >= start && t < end) {
      if (currentSectionIndex.value !== i) currentSectionIndex.value = i
      break
    }
  }
}

const onEnded = () => {
  isPlaying.value = false
  // 自动继续下一段
  if (currentSectionIndex.value < sections.value.length - 1) {
    playNextSection()
  }
}

const downloadCurrentSection = () => {
  const s = currentSection.value
  if (!s || !s.audio_url) return
  const a = document.createElement('a')
  a.href = s.audio_url
  const fname = `${props.currentCourseId || 'course'}_p${props.currentEditPage || 1}_${currentSectionIndex.value + 1}.wav`
  a.download = fname
  document.body.appendChild(a)
  a.click()
  a.remove()
}

function inferNodeType(index, total) {
  if (total <= 1 || index === 0) return 'opening'
  if (index === total - 1) return 'transition'
  return 'explain'
}

function estimateDuration(text) {
  const size = Math.ceil(String(text || '').trim().length / 14)
  return Math.max(20, Math.min(90, size || 20))
}
</script>

<style scoped>
.editor-workbench {
  --wb-bg-top: #ffffff;
  --wb-bg-bottom: #f8fcfa;
  --wb-surface: #ffffff;
  --wb-surface-soft: #f4faf7;
  --wb-border: rgba(125, 162, 146, 0.22);
  --wb-border-strong: rgba(86, 130, 112, 0.34);
  --wb-text: #0f172a;
  --wb-muted: #5f7467;
  --wb-accent: #5ca68f;
  --wb-shadow: 0 12px 28px rgba(45, 79, 66, 0.12);

  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
  padding: 12px;
  box-sizing: border-box;
  background: linear-gradient(180deg, var(--wb-bg-top) 0%, var(--wb-bg-bottom) 100%);
}

.workbench-hero {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 4px 2px;
}

.workbench-hero-text h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333333;
}

.workbench-hero-text p {
  margin: 6px 0 0;
  font-size: 14px;
  color: #666666;
  line-height: 1.5;
  max-width: 56ch;
}

.iteration-entry-btn {
  border: 1px solid #2d8cf0;
  background: #fff;
  color: #2d8cf0;
  font-size: 14px;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.iteration-entry-btn:hover {
  box-shadow: 0 2px 8px rgba(45, 140, 240, 0.2);
}

.iteration-entry-btn:active {
  transform: scale(0.96);
}

.window-toolbar {
  /* 出现动画：用于卡片进入时的淡入 + 轻微上移 */
  animation: dock-appear 240ms cubic-bezier(.16,.84,.44,1) both;
  will-change: transform, opacity;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 0;
  border: 0;
  border-radius: 18px;
  background: transparent;
}

.window-toggle-btn {
  border: 0;
  border-radius: 18px;
  background: transparent;
  color: #5f7467;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.window-toggle-btn:hover {
  background: rgba(236, 247, 242, 0.9);
  color: #2f6052;
}

.window-toggle-btn.active {
  border: 0;
  background: rgba(227, 245, 238, 0.96);
  color: #2f6052;
  box-shadow: 0 6px 14px rgba(92, 166, 143, 0.2);
}

.toggle-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #94a3b8;
  box-shadow: 0 0 0 2px rgba(125, 162, 146, 0.2);
}

.window-toggle-btn.active .toggle-dot {
  background: var(--wb-accent);
  box-shadow: 0 0 0 2px rgba(92, 166, 143, 0.28);
}

.workbench-empty-state {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 28px 12px 14px;
  color: var(--wb-muted);
}

.empty-state-copy {
  text-align: center;
  max-width: 460px;
}

.empty-state-copy h4 {
  margin: 0 0 8px;
  font-size: 21px;
  font-weight: 600;
  color: #1e293b;
}

.empty-state-copy p {
  margin: 0;
  font-size: 13px;
  line-height: 1.65;
}

.window-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1.28fr) minmax(0, 1fr);
}

.window-grid.two-open {
  grid-template-columns: minmax(0, 1.28fr) minmax(0, 1fr);
}

.window-grid.single-open {
  align-items: stretch;
}

.window-grid.single-open .dock-window {
  height: 100%;
}

.window-grid.single-open.preview-only {
  grid-template-columns: minmax(0, 1.28fr) minmax(0, 1fr);
}
.window-grid.single-open.preview-only .dock-window {
  grid-column: 1 / 2;
}

.window-grid.single-open.editor-only {
  grid-template-columns: minmax(0, 1.28fr) minmax(0, 1fr);
}
.window-grid.single-open.editor-only .dock-window {
  grid-column: 2 / 3;
}

.dock-window {
  min-width: 0;
  min-height: 0;
  border: 0;
  border-radius: 22px;
  background: var(--wb-surface);
  box-shadow: var(--wb-shadow);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.editor-dock {
  flex: 1;
  min-height: 0;
}

.editor-split {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: stretch;
}

.kb-rail {
  flex: 0 0 220px;
  border-left: 1px solid var(--wb-border);
  padding: 10px 12px;
  overflow-y: auto;
  background: #fafafa;
  box-sizing: border-box;
}

.kb-rail-head h4 {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 650;
  color: #1e293b;
}

.kb-rail-hint {
  font-size: 11px;
  color: #64748b;
  line-height: 1.45;
  margin: 0 0 10px;
}

.kb-rail-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.kb-rail-item {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px;
  background: #ffffff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  cursor: grab;
}

.kb-rail-item strong {
  display: block;
  font-size: 12px;
  color: #333333;
}

.kb-rail-item span {
  font-size: 11px;
  color: #2d8cf0;
}

.kb-insert {
  margin-top: 6px;
  border: none;
  background: #2d8cf0;
  color: #fff;
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 8px;
  cursor: pointer;
}

.kb-insert:active {
  transform: scale(0.96);
}

.node-insight {
  display: block;
  margin-top: 4px;
  font-size: 10px;
  color: #64748b;
  line-height: 1.3;
}

.dock-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 12px 14px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(255, 255, 255, 0.55);
}

.dock-head--labeled {
  align-items: center;
}

.dock-title {
  display: inline-flex;
  align-items: flex-start;
  gap: 10px;
  color: #334155;
  font-size: 15px;
  font-weight: 650;
  min-width: 0;
}

.dock-title-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.dock-title-main {
  font-size: 15px;
  font-weight: 650;
  color: #0f172a;
  letter-spacing: -0.01em;
}

.dock-title-sub {
  font-size: 11px;
  font-weight: 450;
  color: #64748b;
  line-height: 1.4;
  max-width: 46ch;
}

.dock-signal {
  flex-shrink: 0;
  margin-top: 5px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--wb-accent);
  box-shadow: 0 0 0 3px rgba(92, 166, 143, 0.22);
}

.dock-signal--blue {
  background: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.22);
}

.dock-close-btn {
  width: 30px;
  height: 30px;
  border-radius: 10px;
  border: 0;
  background: rgba(255, 255, 255, 0.6);
  color: #64748b;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.dock-close-btn:hover {
  background: rgba(255, 255, 255, 0.86);
  color: #334155;
}

.viewer-stage {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 4px 12px 12px;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: #c7cde8 #edf2f7;
}

.iteration-sync-banner {
  margin-bottom: 10px;
  border: 1px solid rgba(92, 166, 143, 0.45);
  background: #eef8f3;
  color: #295a4f;
  border-radius: 12px;
  padding: 8px 10px;
  display: grid;
  gap: 2px;
  animation: dock-appear 220ms ease both;
}

.iteration-sync-banner strong {
  font-size: 12px;
}

.iteration-sync-banner span {
  font-size: 12px;
}

.viewer-stage::-webkit-scrollbar {
  width: 8px;
}

.viewer-stage::-webkit-scrollbar-track {
  background: #edf2f7;
  border-radius: 999px;
}

.viewer-stage::-webkit-scrollbar-thumb {
  background: #c7cde8;
  border-radius: 999px;
}

.stage-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.stage-head--compact {
  margin-bottom: 8px;
}

.stage-head-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.stage-badge {
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #64748b;
  background: #f1f5f9;
  padding: 4px 9px;
  border-radius: 999px;
}

.stage-page-line {
  font-size: 14px;
  color: #475569;
}

.stage-page-line strong {
  color: #0f172a;
  font-weight: 650;
}

.slide-wrap {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 clamp(12px, 4vw, 40px);
}

.slide-nav-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 36px;
  height: 36px;
  border-radius: 999px;
  border: 0;
  background: rgba(255, 255, 255, 0.82);
  color: #475569;
  font-size: 24px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 3;
}

.slide-nav-btn.prev {
  left: 0;
}

.slide-nav-btn.next {
  right: 0;
}

.slide-nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.slide-canvas {
  /* 宽度按列宽与视口比例自适应，最大不超过 820px；高度由 aspect-ratio 决定，保证按比例缩放 */ 
  width: min(100%, clamp(360px, 44vw, 820px));
  aspect-ratio: 16 / 9;
  max-height: 80vh;
  background: linear-gradient(145deg, #f8fafc 0%, #eef6f2 48%, #e8f0ec 100%);
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 16px;
  padding: 8px;
  box-sizing: border-box;
  transition: width 180ms ease, height 180ms ease;
  display: flex;
  align-items: stretch;
  justify-content: center;
  overflow: hidden;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.75);
}

.preview-image {
  width: 100%;
  height: 100%;
  border-radius: 12px;
  background: #ffffff;
  border: 0;
  object-fit: contain;
  display: block;
}

.slide-preview-mock {
  flex: 1;
  min-height: 0;
  min-width: 0;
  width: 100%;
  display: flex;
  align-items: stretch;
  justify-content: center;
}

.slide-preview-mock__frame {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfd 100%);
  border: 1px solid rgba(226, 232, 240, 0.95);
  box-shadow:
    0 14px 36px rgba(15, 23, 42, 0.08),
    0 0 0 1px rgba(255, 255, 255, 0.9) inset;
  overflow: hidden;
}

.slide-preview-mock__top {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px 10px;
  background: linear-gradient(90deg, rgba(228, 246, 239, 0.65) 0%, rgba(241, 245, 249, 0.9) 100%);
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
}

.slide-preview-mock__brand {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(92, 166, 143, 0.18);
  color: #2f6052;
  display: flex;
  align-items: center;
  justify-content: center;
}

.slide-preview-mock__icon {
  width: 22px;
  height: 22px;
}

.slide-preview-mock__head-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.slide-preview-mock__title {
  font-size: clamp(13px, 1.35vw, 15px);
  font-weight: 650;
  color: #0f172a;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.slide-preview-mock__sub {
  font-size: 11px;
  color: #64748b;
  letter-spacing: 0.02em;
}

.slide-preview-mock__page-pill {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 650;
  color: #334155;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(203, 213, 225, 0.95);
}

.slide-preview-mock__body {
  flex: 1;
  min-height: 0;
  padding: 16px 18px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  justify-content: center;
  background-image: linear-gradient(rgba(148, 163, 184, 0.06) 1px, transparent 1px);
  background-size: 100% 28px;
  background-position: 0 8px;
}

.slide-preview-mock__line {
  display: block;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(90deg, #e2e8f0 0%, #cbd5e1 55%, #e2e8f0 100%);
  opacity: 0.85;
}

.slide-preview-mock__hint {
  margin: 0;
  padding: 8px 14px 11px;
  font-size: 11px;
  line-height: 1.45;
  color: #64748b;
  background: rgba(248, 250, 252, 0.95);
  border-top: 1px solid rgba(241, 245, 249, 0.95);
}

.no-preview {
  color: #93a69f;
  font-size: 14px;
  text-align: center;
  padding: 80px 0;
}

.timeline-heading {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 14px;
  padding: 0 2px;
}

.timeline-heading__label {
  font-size: 13px;
  font-weight: 650;
  color: #334155;
}

.timeline-heading__hint {
  font-size: 11px;
  color: #94a3b8;
  line-height: 1.35;
}

.timeline-area {
  position: relative;
  margin-top: 8px;
  padding: 18px 8px 10px;
  min-height: 136px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  overflow-x: auto;
  overflow-y: visible;
}

.timeline-line {
  position: absolute;
  left: 22px;
  right: 22px;
  top: 80px;
  border-top: 2px solid rgba(125, 162, 146, 0.36);
  pointer-events: none;
}

.timeline-curve {
  position: absolute;
  left: 22px;
  right: 22px;
  top: 64px;
  height: 34px;
  border-bottom: 2px solid rgba(125, 162, 146, 0.28);
  border-radius: 0 0 56px 56px;
  opacity: 0.75;
  pointer-events: none;
}

.timeline-node {
  position: relative;
  z-index: 1;
  text-align: center;
  cursor: pointer;
  flex: 0 0 150px;
}

.node-bubble {
  min-height: 54px;
  border-radius: 16px;
  border: 0;
  background: rgba(255, 255, 255, 0.95);
  padding: 8px 10px;
  color: #334155;
  display: flex;
  flex-direction: column;
  gap: 6px;
  justify-content: center;
}

.node-bubble strong {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-bubble span {
  font-size: 12px;
  color: var(--wb-muted);
}

.node-dot {
  display: inline-block;
  margin-top: 12px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #d8e8e2;
  border: 0;
  box-shadow: 0 2px 8px rgba(87, 124, 109, 0.2);
}

.timeline-node.active .node-bubble {
  border-color: rgba(92, 166, 143, 0.38);
  background: rgba(228, 246, 239, 0.88);
}

.timeline-node.active .node-dot {
  background: rgba(92, 166, 143, 0.7);
}

.stage-actions {
  margin-top: auto;
  padding: 12px 0 4px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ai-progress-card {
  width: 100%;
  border: 1px solid rgba(125, 162, 146, 0.3);
  background: #f5fbf8;
  border-radius: 12px;
  padding: 8px 10px;
}

.ai-progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: #2f6052;
}

.ai-progress-track {
  margin-top: 6px;
  height: 7px;
  border-radius: 999px;
  background: #dbece5;
  overflow: hidden;
}

.ai-progress-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #79c3ab 0%, #4f9c84 100%);
  transition: width 220ms ease;
}

.action-strip {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 2px;
}

.action-strip--nodes,
.action-strip--page {
  border-top: 1px solid rgba(226, 232, 240, 0.95);
  padding-top: 10px;
}

.action-strip__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.action-strip__title {
  font-size: 12px;
  font-weight: 650;
  color: #475569;
  letter-spacing: 0.02em;
}

.action-strip__desc {
  font-size: 11px;
  color: #94a3b8;
  line-height: 1.35;
  text-align: right;
  max-width: 28ch;
}

.action-strip__row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.action-strip__row--page {
  justify-content: flex-start;
}

.btn-tool {
  border: 1px solid #e2e8f0;
  background: #ffffff;
  color: #334155;
  padding: 8px 12px;
  border-radius: 10px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    box-shadow 0.15s ease,
    transform 0.12s ease;
}

.btn-tool:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #cbd5e1;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.07);
}

.btn-tool:active:not(:disabled) {
  transform: translateY(0);
}

.btn-tool--warn {
  border-color: rgba(251, 191, 36, 0.55);
  color: #92400e;
  background: #fffbeb;
}

.btn-tool--pager {
  min-width: 76px;
}

.page-pill {
  font-size: 12px;
  font-weight: 600;
  color: #334155;
  padding: 7px 12px;
  border-radius: 999px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
}

.action-strip--save {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 14px;
  margin-top: 2px;
  border-radius: 14px;
  border: 1px solid rgba(92, 166, 143, 0.38);
  background: linear-gradient(180deg, #f7fcf9 0%, #ecf6f0 100%);
}

.save-hint {
  margin: 0;
  font-size: 12px;
  color: #3f5f55;
  line-height: 1.45;
  flex: 1;
  min-width: 0;
}

.btn-save-primary {
  flex-shrink: 0;
  border: 0;
  padding: 10px 20px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 650;
  cursor: pointer;
  color: #ffffff;
  background: linear-gradient(180deg, #4f9c84 0%, #3a7d6a 100%);
  box-shadow: 0 4px 14px rgba(58, 125, 106, 0.38);
  transition:
    transform 0.15s ease,
    box-shadow 0.15s ease,
    filter 0.15s ease;
}

.btn-save-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(58, 125, 106, 0.45);
  filter: brightness(1.02);
}

button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

@media (max-width: 720px) {
  .action-strip__desc {
    text-align: left;
    max-width: none;
  }

  .action-strip--save {
    flex-direction: column;
    align-items: stretch;
  }

  .btn-save-primary {
    width: 100%;
  }
}

.copilot-panel {
  flex: 1;
  width: auto;
  border-left: none;
  background: transparent;
  padding: 10px 10px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  overflow-y: auto;
  padding-bottom: 16px;
  scrollbar-width: thin;
  scrollbar-color: #b8d1c6 #edf7f2;
}

.copilot-panel::-webkit-scrollbar {
  width: 8px;
}

.copilot-panel::-webkit-scrollbar-track {
  background: #edf7f2;
  border-radius: 999px;
}

.copilot-panel::-webkit-scrollbar-thumb {
  background: #b8d1c6;
  border-radius: 999px;
}

.copilot-heading {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.copilot-heading h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
  color: #0f172a;
  letter-spacing: -0.01em;
}

.copilot-sub {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.45;
}

.panel-block {
  border: 1px solid var(--wb-border);
  border-radius: 16px;
  padding: 12px;
  background: #ffffff;
  flex-shrink: 0;
}

.panel-block__title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 650;
  color: #1f2937;
}

.linked-editor {
  width: 100%;
  border: 1px solid var(--wb-border);
  border-radius: 14px;
  background: #ffffff;
  padding: 12px;
  box-sizing: border-box;
  font-size: 15px;
  font-family: inherit;
}

.grow {
  flex: 0 0 auto;
  min-height: 180px;
  display: flex;
  flex-direction: column;
  overflow: visible;
}

.node-tabs {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 8px;
}

.node-tabs button {
  border: 0;
  border-radius: 999px;
  background: rgba(242, 248, 245, 0.92);
  color: #5f7467;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}

.node-tabs button.active {
  background: rgba(226, 244, 237, 0.95);
  color: #2f6052;
}

.linked-editor {
  flex: 0 0 auto;
  height: 150px;
  min-height: 130px;
  margin-top: 10px;
  resize: none;
  line-height: 1.8;
  overflow-y: auto;
}

@media (max-width: 1200px) {
  .window-grid.two-open {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 980px) {
  .editor-workbench {
    padding: 8px;
  }

  .window-toolbar {
    gap: 6px;
  }

  .window-toggle-btn {
    flex: 1;
    justify-content: center;
  }
  
  /* 窄屏时单卡回退为全宽 */
  .window-grid.single-open {
    grid-template-columns: 1fr;
    justify-content: stretch;
    align-items: stretch;
  }

  .window-grid.single-open.preview-only .dock-window,
  .window-grid.single-open.editor-only .dock-window {
    width: 100%;
    max-width: none;
    grid-column: auto;
  }
}

@keyframes orbit-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@keyframes dock-appear {
  from {
    opacity: 0;
    transform: translateY(8px) scale(0.995);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes orbit-spin-rev {
  from {
    transform: rotate(360deg);
  }
  to {
    transform: rotate(0deg);
  }
}

@keyframes pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.86;
  }
  50% {
    transform: scale(1.24);
    opacity: 1;
  }
}

</style>
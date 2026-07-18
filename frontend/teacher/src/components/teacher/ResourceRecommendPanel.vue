<template>
  <transition name="rr-mask-fade">
    <div v-if="visible" class="rr-mask" @click="closePanel"></div>
  </transition>

  <transition name="rr-drawer-slide">
    <aside v-if="visible" class="rr-drawer" role="dialog" aria-modal="true" aria-label="智能资源推荐">
      <header class="rr-header">
        <div>
          <h3>智能资源匹配 - 基于知识点与学情精准推荐</h3>
          <p class="rr-sub">{{ resourceSubtitle }}</p>
        </div>
        <button type="button" class="rr-close" @click="closePanel">关闭</button>
      </header>

      <section class="rr-config">
        <div class="rr-config-grid">
          <label>
            关键词
            <input v-model.trim="searchForm.keyword" placeholder="关键词自动填充自当前知识点 / 学情卡点" />
          </label>
          <label>
            学段
            <select v-model="searchForm.stage">
              <option value="">不限</option>
              <option value="初中">初中</option>
              <option value="高中">高中</option>
              <option value="大学">大学</option>
            </select>
          </label>
          <label>
            学科
            <input v-model.trim="searchForm.subject" placeholder="如：计算机" />
          </label>
          <label>
            资源类型
            <select v-model="searchForm.type">
              <option value="">全部</option>
              <option value="网课">网课</option>
              <option value="题库">题库</option>
            </select>
          </label>
          <label>
            难度
            <select v-model="searchForm.difficulty">
              <option value="">不限</option>
              <option :value="0.3">基础</option>
              <option :value="0.6">进阶</option>
              <option :value="0.9">冲刺</option>
            </select>
          </label>
          <label>
            时长/题量
            <input v-model.trim="searchForm.duration" placeholder="如：30" />
          </label>
          <label>
            语言
            <select v-model="searchForm.lang">
              <option value="">不限</option>
              <option value="zh-CN">中文</option>
              <option value="en">英文</option>
            </select>
          </label>
          <label>
            预算
            <select v-model="searchForm.budget">
              <option value="">不限</option>
              <option :value="0">免费优先</option>
              <option :value="99">付费可选</option>
            </select>
          </label>
          <label>
            来源偏好
            <input v-model.trim="searchForm.source" placeholder="如：Bilibili/高校慕课" />
          </label>
        </div>

        <div class="rr-actions">
          <button class="btn btn-primary" :disabled="loading" @click="searchResources(true)">重新推荐</button>
          <button class="btn btn-light" :disabled="loading" @click="resetConfig">重置条件</button>
        </div>
      </section>

      <section class="rr-result-wrap">
        <div class="rr-toolbar">
          <div class="rr-sort">
            <span>排序</span>
            <button class="chip" :class="{ active: sortBy === 'relevance' }" @click="sortBy = 'relevance'">相关度</button>
            <button class="chip" :class="{ active: sortBy === 'duration' }" @click="sortBy = 'duration'">时长</button>
            <button class="chip" :class="{ active: sortBy === 'hot' }" @click="sortBy = 'hot'">热度</button>
          </div>
          <div class="rr-filter">
            <button class="chip" :class="{ active: quickTypeFilter === 'all' }" @click="quickTypeFilter = 'all'">全部</button>
            <button class="chip" :class="{ active: quickTypeFilter === 'video' }" @click="quickTypeFilter = 'video'">仅看网课</button>
            <button class="chip" :class="{ active: quickTypeFilter === 'question' }" @click="quickTypeFilter = 'question'">仅看题库</button>
          </div>
        </div>

        <div class="rr-list-container">
          <div v-if="loading && !resourceList.length" class="rr-loading">正在为你匹配高质量资源...</div>

          <div v-else-if="errorMsg" class="rr-error">
            <p>{{ errorMsg }}</p>
            <button class="btn btn-primary" @click="searchResources(true)">重试</button>
          </div>

          <div v-else-if="!displayList.length" class="rr-empty">
            当前条件下暂无结果，建议调整关键词或放宽筛选范围。
          </div>

          <div v-else class="rr-grid">
            <article v-for="item in displayList" :key="item.id" class="rr-card">
              <div class="rr-card-head">
                <h4>{{ item.title }}</h4>
                <span class="type-tag" :class="item.type">{{ typeLabel(item.type) }}</span>
              </div>

              <div class="rr-meta">
                <span>来源：{{ item.source || '-' }}</span>
                <span v-if="item.target">适用对象：{{ item.target }}</span>
                <span v-if="item.duration">{{ item.duration }}</span>
              </div>

              <p class="rr-reason">{{ formatReason(item) }}</p>

              <div class="rr-card-actions">
                <button type="button" class="btn btn-primary" :disabled="!item.url" @click="openResourceLink(item)">
                  去查看
                </button>
                <button type="button" class="btn btn-light" @click="toggleFavorite(item)">
                  {{ item.is_favorite ? '已收藏' : '收藏' }}
                </button>
                <button type="button" class="btn btn-outline" @click="insertIntoScript(item)">插入到讲稿</button>
              </div>
            </article>
          </div>

          <div v-if="hasMore && !loading" class="rr-more">
            <button class="btn btn-light" :disabled="loadingMore" @click="loadMore">
              {{ loadingMore ? '加载中...' : '加载更多' }}
            </button>
          </div>

          <transition name="rr-refresh-fade">
            <div v-if="refreshingMask" class="rr-refresh-mask">
              <div class="rr-refresh-spinner"></div>
              <span>正在刷新推荐结果...</span>
            </div>
          </transition>

          <transition name="rr-refresh-fade">
            <div v-if="loading" class="rr-request-mask">
              <div class="rr-refresh-spinner"></div>
              <span>正在请求推荐资源...</span>
            </div>
          </transition>
        </div>
      </section>
    </aside>
  </transition>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { fetchRecommendedResources } from '../../services/teacher.v1'
import { useResourceStore } from '../../stores/resourceStore'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  currentCourseContext: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:visible', 'insert-to-script', 'toast'])

const store = useResourceStore()

const searchForm = reactive({
  keyword: '',
  stage: '',
  subject: '',
  type: '',
  difficulty: '',
  duration: '',
  lang: '',
  budget: '',
  source: ''
})

const resourceList = ref([])
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const hasMore = ref(false)

const loading = ref(false)
const loadingMore = ref(false)
const errorMsg = ref('')
const sortBy = ref('relevance')
const quickTypeFilter = ref('all')
const refreshingMask = ref(false)

const contextKeyword = computed(() => {
  if (!props.currentCourseContext || typeof props.currentCourseContext !== 'object') return ''
  return String(
    props.currentCourseContext.nodeKeyword
      || props.currentCourseContext.pageKeyword
      || props.currentCourseContext.keyword
      || props.currentCourseContext.courseName
      || ''
  ).trim()
})

const resourceSubtitle = computed(() => {
  const ctx = props.currentCourseContext || {}
  const kw = String(ctx.nodeKeyword || ctx.keyword || '').trim()
  const reason = String(ctx.matchReason || ctx.bottleneckHint || '').trim()
  if (kw && reason) return `当前匹配知识点：${kw} | 匹配依据：${reason}`
  if (kw) return `当前匹配知识点：${kw} | 匹配依据：结合班级学情与知识点语义相关度`
  return '根据课程上下文与学情权重（语义匹配 + 学情修正）自动推荐'
})

function formatReason(item) {
  const ctx = props.currentCourseContext || {}
  const kw = String(ctx.nodeKeyword || ctx.keyword || '本课重点').trim()
  const basis = String(ctx.matchReason || '').trim()
  const src = item.source || '-'
  const dur = item.duration || '-'
  const extra = String(item.recommend_reason || item.reason || '').trim()
  if (extra.length > 12) {
    return `来源：${src} | 时长/题量：${dur} | ${extra}`
  }
  return `来源：${src} | 时长/题量：${dur} | 推荐理由：针对「${kw}」${basis ? `（${basis}）` : ''} 的专项补充，适合课堂穿插与课后巩固。`
}

function insertIntoScript(item) {
  emit('insert-to-script', item)
}

const normalizedConfig = computed(() => ({
  keyword: searchForm.keyword,
  stage: searchForm.stage,
  subject: searchForm.subject,
  type: searchForm.type,
  difficulty: searchForm.difficulty,
  duration: searchForm.duration,
  lang: searchForm.lang,
  budget: searchForm.budget,
  source: searchForm.source
}))

const displayList = computed(() => {
  let list = [...resourceList.value]

  if (quickTypeFilter.value !== 'all') {
    list = list.filter(item => item.type === quickTypeFilter.value)
  }

  if (sortBy.value === 'duration') {
    list.sort((a, b) => String(a.duration || '').localeCompare(String(b.duration || '')))
  } else if (sortBy.value === 'hot') {
    list.sort((a, b) => Number(b.hot_score || 0) - Number(a.hot_score || 0))
  }

  return list
})

function applyContext() {
  if (!props.currentCourseContext || typeof props.currentCourseContext !== 'object') return
  const keywordFromContext = contextKeyword.value
  const contextSubject = String(props.currentCourseContext.subject || '').trim()

  if (keywordFromContext) searchForm.keyword = keywordFromContext
  if (contextSubject) searchForm.subject = contextSubject
}

function closePanel() {
  emit('update:visible', false)
}

function resetConfig() {
  Object.assign(searchForm, {
    keyword: '',
    stage: '',
    subject: '',
    type: '',
    difficulty: '',
    duration: '',
    lang: '',
    budget: '',
    source: ''
  })
  store.setLastSearchConfig({ ...normalizedConfig.value })
}

function normalizeResource(item, index) {
  const rawType = String(item?.type || '').trim()
  const normalizedType = rawType === '题库' || rawType.toLowerCase() === 'question' ? 'question' : 'video'
  return {
    id: item?.id || item?.ID || `tmp_${Date.now()}_${index}`,
    title: item?.title || item?.Title || '未命名资源',
    type: normalizedType,
    target: item?.target || '',
    duration: item?.duration || '',
    source: item?.source || item?.Source || '',
    recommend_reason: item?.fit_reason || item?.recommend_reason || item?.reason || item?.Reason || '',
    url: item?.url || item?.link || item?.Link || '',
    is_favorite: Boolean(item?.is_favorite),
    hot_score: Number(item?.hot_score || 0)
  }
}

function buildKeywordForRequest() {
  const manualKeyword = String(searchForm.keyword || '').trim()
  if (manualKeyword) return manualKeyword

  const fallback = contextKeyword.value
  if (fallback) return fallback

  const page = props.currentCourseContext?.currentPage
  return page ? `第${page}页` : ''
}

function buildMockResources(keyword, type) {
  const baseKeyword = String(keyword || '').trim() || '重点知识点'
  const isQuestion = type === '题库'
  return Array.from({ length: 8 }).map((_, index) => {
    const id = `${Date.now()}_${index}`
    return {
      id,
      title: isQuestion
        ? `${baseKeyword} 题库练习 ${index + 1}（前端模拟）`
        : `${baseKeyword} 精讲视频 ${index + 1}（前端模拟）`,
      type: isQuestion ? 'question' : 'video',
      target: props.currentCourseContext?.courseName || '课堂演示',
      duration: isQuestion ? `${12 + index * 3}题` : `${10 + index * 2}分钟`,
      source: isQuestion ? '校内题库' : 'Bilibili',
      recommend_reason: `基于“${baseKeyword}”自动补齐的演示资源，保证推荐链路可演示。`,
      url: isQuestion
        ? `https://example.com/demo-question/${encodeURIComponent(baseKeyword)}/${index + 1}`
        : `https://www.bilibili.com/video/BV1demo${index + 1}`,
      is_favorite: false,
      hot_score: 88 - index * 4
    }
  })
}

async function searchResources(reset = true) {
  if (loading.value) return

  if (reset) {
    page.value = 1
    errorMsg.value = ''
    if (resourceList.value.length) refreshingMask.value = true
  }

  loading.value = true
  const requestParams = {
    ...normalizedConfig.value,
    keyword: buildKeywordForRequest(),
    page: page.value,
    pageSize: pageSize.value,
    sortBy: sortBy.value
  }

  try {
    store.setLastSearchConfig({ ...normalizedConfig.value })
    const cacheKey = store.buildCacheKey({ ...requestParams, page: 1 })

    if (reset && store.recommendationCache.key === cacheKey && store.recommendationCache.items.length) {
      const cache = store.recommendationCache
      resourceList.value = cache.items.map(normalizeResource)
      total.value = cache.total
      page.value = cache.page
      pageSize.value = cache.pageSize
      hasMore.value = cache.hasMore
      return
    }

    const data = await fetchRecommendedResources(requestParams)
    const incoming = (data.list || []).map(normalizeResource)

    if (reset) {
      resourceList.value = incoming
    } else {
      resourceList.value = [...resourceList.value, ...incoming]
    }

    total.value = Number(data.total || resourceList.value.length)
    page.value = Number(data.page || page.value)
    pageSize.value = Number(data.pageSize || pageSize.value)
    hasMore.value = Boolean(data.hasMore)

    if (reset) {
      store.setRecommendationCache({
        key: cacheKey,
        items: resourceList.value,
        total: total.value,
        page: page.value,
        pageSize: pageSize.value,
        hasMore: hasMore.value
      })
    }
  } catch (error) {
    const mockItems = buildMockResources(requestParams.keyword, requestParams.type)
    resourceList.value = reset ? mockItems : [...resourceList.value, ...mockItems]
    total.value = resourceList.value.length
    hasMore.value = false
    errorMsg.value = ''
  } finally {
    loading.value = false
    loadingMore.value = false
    refreshingMask.value = false
  }
}

async function loadMore() {
  if (!hasMore.value || loadingMore.value || loading.value) return
  loadingMore.value = true
  page.value += 1
  await searchResources(false)
}

function toggleFavorite(item) {
  item.is_favorite = !item.is_favorite
  if (item.is_favorite) {
    emit('toast', '已收藏至知识库，可在备课时一键引用')
  }
}

function openResourceLink(item) {
  if (!item?.url) return
  window.open(item.url, '_blank', 'noopener,noreferrer')
}

function typeLabel(type) {
  if (type === 'question') return '题库'
  return '网课'
}

watch(
  () => props.currentCourseContext,
  () => {
    applyContext()
  },
  { immediate: true, deep: true }
)

watch(
  () => props.visible,
  (next) => {
    if (!next) return

    store.hydrate()
    Object.assign(searchForm, store.lastSearchConfig)
    applyContext()
    searchResources(true)
  },
  { immediate: true }
)

watch(sortBy, () => {
  if (!props.visible || !resourceList.value.length) return
  searchResources(true)
})

onMounted(() => {
  store.hydrate()
  Object.assign(searchForm, store.lastSearchConfig)
})
</script>

<style scoped>
.rr-mask {
  position: fixed;
  inset: 0;
  background: rgba(9, 24, 21, 0.35);
  z-index: 800;
}

.rr-drawer {
  position: fixed;
  right: 0;
  top: 0;
  width: min(860px, 94vw);
  height: 100vh;
  z-index: 810;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #f2fbfa 0%, #f8fcfc 52%, #ffffff 100%);
  border-left: 1px solid #cde3de;
  box-shadow: -8px 0 36px rgba(26, 59, 54, 0.22);
}

.rr-header {
  padding: 16px 18px;
  border-bottom: 1px solid #d7e7e3;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.rr-header h3 {
  margin: 0;
  color: #333333;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.35;
}

.rr-sub {
  margin: 8px 0 0;
  font-size: 12px;
  color: #666666;
  line-height: 1.5;
  max-width: 52ch;
}

.rr-header p {
  margin: 6px 0 0;
  font-size: 12px;
  color: #52756f;
}

.rr-close {
  border: 1px solid #c8ddd8;
  background: #fff;
  border-radius: 10px;
  padding: 6px 10px;
  cursor: pointer;
}

.rr-config {
  flex: 0 0 20vh;
  min-height: 140px;
  overflow-y: auto;
  padding: 14px 16px;
  border-bottom: 1px solid #d7e7e3;
  background: #f5fbfa;
}

.rr-config-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.rr-config-grid label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 14px;
  color: #666666;
}

.rr-config-grid input,
.rr-config-grid select {
  border: 1px solid #c8ddd8;
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 13px;
  background: #fff;
}

.rr-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}

.rr-result-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.rr-toolbar {
  padding: 12px 16px;
  border-bottom: 1px solid #e3efec;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.rr-sort,
.rr-filter {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rr-sort span {
  font-size: 12px;
  color: #5c7d77;
}

.chip {
  border: 1px solid #c9dfda;
  background: #fff;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}

.chip.active {
  background: #2f605a;
  border-color: #2f605a;
  color: #fff;
}

.rr-list-container {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 14px 16px 20px;
}

.rr-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.rr-card {
  border: 1px solid #d2e5e1;
  border-radius: 14px;
  background: #fff;
  padding: 12px;
}

.rr-card-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.rr-card-head h4 {
  margin: 0;
  font-size: 15px;
  line-height: 1.4;
  color: #193b36;
}

.type-tag {
  border-radius: 999px;
  font-size: 11px;
  padding: 2px 8px;
  height: fit-content;
}

.type-tag.video {
  background: #e7f6f2;
  color: #256b5f;
}

.type-tag.question {
  background: #e8f0ff;
  color: #3f5f92;
}

.rr-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: #5b7872;
}

.rr-reason {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: #355f5a;
  min-height: 42px;
}

.rr-card-actions {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}

.btn {
  border: 1px solid transparent;
  border-radius: 10px;
  padding: 7px 12px;
  cursor: pointer;
  font-size: 12px;
  text-decoration: none;
}

.btn[disabled],
.btn.disabled {
  pointer-events: none;
  opacity: 0.6;
}

.btn-primary {
  background: #2d8cf0;
  color: #fff;
  border-radius: 8px;
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 600;
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(0.95);
}

.btn-light {
  background: #fff;
  color: #2d8cf0;
  border: 1px solid #2d8cf0;
  border-radius: 8px;
}

.btn-outline {
  background: #fff;
  color: #2d8cf0;
  border: 1px dashed #7eb8fc;
  border-radius: 8px;
}

.btn-outline:hover {
  background: rgba(45, 140, 240, 0.06);
}

.rr-loading,
.rr-empty,
.rr-error {
  min-height: 180px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #4f706a;
  gap: 10px;
}

.rr-more {
  margin-top: 14px;
  display: flex;
  justify-content: center;
}

.rr-refresh-mask {
  position: absolute;
  inset: 0;
  background: rgba(242, 251, 250, 0.8);
  backdrop-filter: blur(1px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
}

.rr-request-mask {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.74);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
}

.rr-refresh-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid #a4c9c2;
  border-top-color: #2f605a;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.rr-mask-fade-enter-active,
.rr-mask-fade-leave-active,
.rr-refresh-fade-enter-active,
.rr-refresh-fade-leave-active {
  transition: opacity 0.2s ease;
}

.rr-mask-fade-enter-from,
.rr-mask-fade-leave-to,
.rr-refresh-fade-enter-from,
.rr-refresh-fade-leave-to {
  opacity: 0;
}

.rr-drawer-slide-enter-active,
.rr-drawer-slide-leave-active {
  transition: transform 0.25s ease;
}

.rr-drawer-slide-enter-from,
.rr-drawer-slide-leave-to {
  transform: translateX(100%);
}

@media (max-width: 960px) {
  .rr-config-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .rr-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .rr-config-grid {
    grid-template-columns: 1fr;
  }

  .rr-drawer {
    width: 100vw;
  }
}
</style>

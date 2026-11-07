<template>
  <AppShell>
    <main class="page">
      <header class="head">
        <div><p class="eyebrow">我的课件</p><h1>继续完善你的教学设计</h1><p>课件、AI 迭代记录与版本会保存在同一项目中。</p></div>
        <div class="head-actions"><button class="secondary" @click="router.push({ name: 'S2Material' })">资料与证据中心</button><button class="secondary" :disabled="projects.loading" @click="load">刷新</button><button class="primary" @click="openCreate">＋ 新建课件</button></div>
      </header>

      <section v-if="projects.items.length" class="toolbar" aria-label="课件筛选与排序">
        <label class="search-field"><span class="sr-only">搜索课件</span><input v-model.trim="keyword" type="search" placeholder="搜索课件名称" /></label>
        <label class="sort-field"><span>排序</span><select v-model="sortBy"><option value="updated">最近编辑</option><option value="title">名称</option><option value="version">版本号</option></select></label>
        <span class="result-count">{{ filteredProjects.length }} 份课件</span>
      </section>

      <p v-if="notice" class="notice" role="status">{{ notice }}</p>
      <div v-if="projects.loading && !projects.items.length" class="state-wrap" aria-live="polite">
        <LoadingState type="loading" text="正在加载课件…" hint="正在读取你的课件项目与版本记录" />
      </div>
      <div v-else-if="projects.error && !projects.items.length" class="state-wrap">
        <ErrorState title="课件加载失败" :description="projects.error" retry-text="重试加载" @retry="load" />
      </div>
      <div v-else-if="!projects.items.length" class="state-wrap">
        <EmptyState title="还没有课件" description="开始创建第一份课件，让 AI 和你一起完成备课。" action-text="开始创建第一份课件" icon="file" @action="openCreate" />
      </div>
      <div v-else-if="!filteredProjects.length" class="state-wrap state-wrap--compact">
        <EmptyState title="没有匹配的课件" description="换一个关键词试试，或清除搜索查看全部课件。" action-text="清除搜索" icon="search" @action="keyword = ''" />
      </div>
      <section v-else class="grid" aria-label="课件列表">
        <article v-for="item in filteredProjects" :key="projectId(item)" class="card">
          <div class="card-top"><span class="status" :class="item.status">{{ statusText(item.status) }}</span><span class="version">v{{ item.version_no || item.version || 1 }}</span></div>
          <h2>{{ item.title || '未命名课件' }}</h2><p class="meta">最近编辑：{{ formatTime(item.updated_at) }}</p><p class="step">{{ stepText(item.current_step) }}</p>
          <div class="card-actions"><button class="primary" @click="resume(item)">继续编辑</button><button class="secondary" @click="viewVersions(item)">查看版本</button><button class="secondary" @click="exportProject(item)">导出</button><button class="danger" :disabled="deletingId === projectId(item)" @click="confirmDelete(item)">{{ deletingId === projectId(item) ? '删除中…' : '删除' }}</button></div>
        </article>
      </section>

      <Transition name="create-panel">
        <section v-if="showCreate" class="create-panel" aria-labelledby="create-title">
          <div class="create-visual" aria-hidden="true"><span>✦</span><b>AI</b><small>从教学目标开始创作</small></div>
          <form class="create-form" @submit.prevent="createProject">
            <div class="create-heading"><div><p class="eyebrow">创建项目</p><h2 id="create-title">这份课件准备讲什么？</h2><p>填写一个清晰的主题，下一步由 AI 协助完善教学意图、大纲与内容。</p></div><button type="button" class="close-create" :disabled="creating" aria-label="收起创建区域" @click="closeCreate">×</button></div>
            <label>课件主题<input ref="titleInput" v-model="newTitle" maxlength="200" placeholder="例如：大一数据结构——排序算法" /></label>
            <div class="title-suggestions" aria-label="主题示例"><button v-for="title in titleSuggestions" :key="title" type="button" @click="newTitle = title">{{ title }}</button></div>
            <p v-if="dialogError" class="dialog-error" role="alert">{{ dialogError }}</p>
            <div class="dialog-actions"><span>{{ newTitle.length }}/200</span><button class="primary" :disabled="creating || !newTitle.trim()">{{ creating ? '正在创建项目…' : '开始智能备课 →' }}</button></div>
          </form>
        </section>
      </Transition>

      <div v-if="deleteTarget" class="dialog-backdrop" @click.self="deleteTarget = null">
        <section class="dialog" role="dialog" aria-modal="true" aria-labelledby="delete-title"><h2 id="delete-title">删除课件？</h2><p>“{{ deleteTarget.title || '未命名课件' }}”将从列表移除。服务端采用可恢复删除，不会立即清除历史数据。</p><div class="dialog-actions"><button class="secondary" @click="deleteTarget = null">取消</button><button class="danger solid" @click="removeProject">确认删除</button></div></section>
      </div>
    </main>
  </AppShell>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '../components/layout/AppShell.vue'
import LoadingState from '../components/common/LoadingState.vue'
import EmptyState from '../components/common/EmptyState.vue'
import ErrorState from '../components/common/ErrorState.vue'
import { useCoursewareProjectStore } from '../stores/coursewareProjectStore'
import { useIntentStore } from '../stores/intentStore'
import { useMaterialStore } from '../stores/materialStore'
import { useOutlineStore } from '../stores/outlineStore'
import { useGenerationStore } from '../stores/generationStore'
import { useVersionStore } from '../stores/versionStore'
import { useModifyStore } from '../stores/modifyStore'
import { useContentStore } from '../stores/contentStore'
import { clearLegacyResumeDraft } from '../utils/coursewareDraft'

const router = useRouter(); const projects = useCoursewareProjectStore()
const keyword = ref(''); const sortBy = ref('updated'); const showCreate = ref(false); const newTitle = ref(''); const dialogError = ref(''); const creating = ref(false); const titleInput = ref(null); const deleteTarget = ref(null); const deletingId = ref(''); const notice = ref('')
const titleSuggestions = ['排序算法入门', '人工智能基础', '网络安全实践']
const statusText = (status) => ({ draft: '草稿', active: '编辑中', archived: '已归档', completed: '已完成', done: '已完成', locked: '已锁定' }[status] || '编辑中')
const stepText = (step) => ({ s1_intent: '当前：教学意图', s2_material: '当前：参考资料', s3_studio: '当前：AI 生成与迭代', s4_version: '当前：版本与导出' }[step] || '当前：教学意图')
const formatTime = (time) => time ? new Date(time).toLocaleString() : '刚刚'
const projectId = (item) => item.id || item.project_id || ''
const filteredProjects = computed(() => {
  const query = keyword.value.toLocaleLowerCase(); const items = projects.items.filter((item) => !query || String(item.title || '').toLocaleLowerCase().includes(query))
  return [...items].sort((a, b) => sortBy.value === 'title' ? String(a.title || '').localeCompare(String(b.title || ''), 'zh-CN') : sortBy.value === 'version' ? Number(b.version_no || 1) - Number(a.version_no || 1) : new Date(b.updated_at || 0) - new Date(a.updated_at || 0))
})
const load = () => projects.loadProjects().catch(() => {})
async function openCreate() { showCreate.value = true; dialogError.value = ''; newTitle.value = ''; await nextTick(); titleInput.value?.focus(); titleInput.value?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }
function closeCreate() { if (!creating.value) showCreate.value = false }
async function createProject() {
  const title = newTitle.value.trim(); if (!title || creating.value) return
  creating.value = true; dialogError.value = ''
  try { const project = await projects.create(title); for (const store of [useIntentStore(), useMaterialStore(), useOutlineStore(), useGenerationStore(), useVersionStore(), useModifyStore(), useContentStore()]) store.reset?.(); clearLegacyResumeDraft(); await projects.updateStep('s1_intent'); router.push({ name: 'S1Intent', query: { project_id: project.id || project.project_id } }) }
  catch (error) { dialogError.value = error?.message || '新建课件失败，请稍后重试' } finally { creating.value = false }
}
function resume(item) { router.push({ name: 'CoursewareResume', query: { project_id: projectId(item), generation_id: item.gen_id || item.generation_id || '' } }) }
function viewVersions(item) { router.push({ name: 'S4Version', query: { project_id: projectId(item), generation_id: item.gen_id || item.generation_id || '' } }) }
function exportProject(item) { viewVersions(item) }
function confirmDelete(item) { deleteTarget.value = item }
async function removeProject() { const item = deleteTarget.value; if (!item) return; deletingId.value = projectId(item); deleteTarget.value = null; notice.value = ''; try { await projects.remove(deletingId.value); notice.value = `已删除“${item.title || '未命名课件'}”` } catch (error) { notice.value = error?.message || '删除课件失败，请稍后重试' } finally { deletingId.value = '' } }
const handleKeydown = (event) => {
  if (event.key !== 'Escape') return
  if (deleteTarget.value) deleteTarget.value = null
  else closeCreate()
}
onMounted(() => { load(); window.addEventListener('keydown', handleKeydown) })
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeydown))
</script>

<style scoped>
.page {
  min-height: calc(100dvh - var(--topbar-height) - var(--shell-gutter) * 2);
  padding: var(--space-10) var(--space-8);
  background: var(--bg-page);
}

.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: var(--space-6);
  margin-bottom: var(--space-6);
}
.eyebrow {
  margin: 0 0 var(--space-1);
  color: var(--color-primary);
  font-size: var(--text-2xs);
  font-weight: var(--weight-semibold);
  letter-spacing: 0.06em;
}
.head h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: var(--text-2xl);
  font-weight: var(--weight-semibold);
  line-height: var(--leading-tight);
}
.head p:not(.eyebrow) { margin: var(--space-2) 0 0; color: var(--text-secondary); font-size: var(--text-xs); }

.head-actions, .card-actions, .dialog-actions { display: flex; gap: var(--space-2); flex-wrap: wrap; }
button, input, select { font: inherit; }

.primary, .secondary, .danger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  padding: 0 var(--space-4);
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard);
}
.primary { border-color: var(--color-primary); background: var(--color-primary); color: var(--color-on-primary); }
.primary:hover:not(:disabled) { background: var(--color-primary-hover); }
.secondary { border-color: var(--border-default); background: var(--bg-surface); color: var(--color-primary); }
.secondary:hover:not(:disabled) { border-color: var(--color-primary-border); background: var(--color-primary-soft); }
.danger { border-color: var(--color-danger-border); background: var(--bg-surface); color: var(--color-danger); }
.danger:hover:not(:disabled) { background: var(--color-danger-soft); }
.danger.solid { border-color: var(--color-danger); background: var(--color-danger); color: var(--color-on-primary); }
.primary:disabled, .secondary:disabled, .danger:disabled { opacity: 0.48; cursor: not-allowed; }

.toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  box-shadow: var(--shadow-xs);
}
.search-field { flex: 1; min-width: 0; }
.search-field input,
.sort-field select,
.dialog input {
  width: 100%;
  min-height: 36px;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: var(--text-xs);
  transition: border-color var(--duration-fast) var(--ease-standard),
              box-shadow var(--duration-fast) var(--ease-standard);
}
.search-field input:focus,
.sort-field select:focus,
.dialog input:focus { outline: none; border-color: var(--color-primary); box-shadow: var(--shadow-focus); }
.sort-field { display: flex; align-items: center; gap: var(--space-2); color: var(--text-secondary); font-size: var(--text-2xs); white-space: nowrap; }
.result-count { margin-left: auto; color: var(--text-tertiary); font-size: var(--text-2xs); white-space: nowrap; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-4); }
.card {
  display: flex;
  flex-direction: column;
  min-height: 200px;
  padding: var(--space-5);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  box-shadow: var(--shadow-xs);
  transition: border-color var(--duration-fast) var(--ease-standard),
              box-shadow var(--duration-fast) var(--ease-standard);
}
.card:hover { border-color: var(--color-primary-border); box-shadow: var(--shadow-sm); }
.card-top { display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); }
.status, .version { padding: 2px var(--space-2); border-radius: var(--radius-pill); background: var(--color-primary-soft); color: var(--color-primary); font-size: var(--text-2xs); font-weight: var(--weight-medium); }
.status.draft { background: var(--color-warning-soft); color: var(--color-warning); }
.status.locked { background: var(--color-info-soft); color: var(--color-info); }
.card h2 { margin: var(--space-4) 0 var(--space-1); color: var(--text-primary); font-size: var(--text-md); font-weight: var(--weight-semibold); overflow-wrap: anywhere; }
.meta { margin: 0; color: var(--text-tertiary); font-size: var(--text-2xs); }
.step { margin: var(--space-2) 0 0; color: var(--color-primary); font-size: var(--text-2xs); }
.card-actions { margin-top: auto; padding-top: var(--space-4); }

.state-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 360px;
  border: 1px dashed var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
}
.state-wrap--compact { min-height: 260px; }
.notice {
  margin: 0 0 var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-control);
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-size: var(--text-xs);
}

.create-panel {
  display: grid;
  grid-template-columns: 220px 1fr;
  margin: 0 0 var(--space-6);
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  box-shadow: var(--shadow-sm);
}
.create-visual {
  display: grid;
  place-content: center;
  justify-items: center;
  gap: var(--space-1);
  min-height: 250px;
  color: var(--color-on-primary);
  background: var(--color-primary);
}
.create-visual span { font-size: var(--text-2xl); }
.create-visual b { font-size: var(--text-3xl); letter-spacing: -0.04em; }
.create-visual small { font-size: var(--text-2xs); opacity: 0.86; }
.create-form { padding: var(--space-6); }
.create-heading { display: flex; justify-content: space-between; gap: var(--space-5); }
.create-heading h2 { margin: var(--space-1) 0 var(--space-2); color: var(--text-primary); font-size: var(--text-lg); font-weight: var(--weight-semibold); }
.create-heading p:last-child { margin: 0 0 var(--space-5); color: var(--text-secondary); font-size: var(--text-2xs); line-height: var(--leading-relaxed); }
.close-create { align-self: flex-start; width: 32px; height: 32px; border: 1px solid var(--border-subtle); border-radius: 50%; background: var(--bg-subtle); color: var(--text-secondary); font-size: var(--text-lg); line-height: 1; cursor: pointer; }
.close-create:hover { background: var(--bg-muted); color: var(--text-primary); }
.create-form > label { display: grid; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-xs); font-weight: var(--weight-medium); }
.create-form input {
  width: 100%;
  min-height: 42px;
  padding: var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: var(--text-sm);
}
.create-form input:focus { outline: none; border-color: var(--color-primary); box-shadow: var(--shadow-focus); }
.title-suggestions { display: flex; gap: var(--space-2); flex-wrap: wrap; margin-top: var(--space-3); }
.title-suggestions button { min-height: 30px; padding: 0 var(--space-3); border: 1px solid var(--border-subtle); border-radius: var(--radius-pill); background: var(--bg-subtle); color: var(--text-secondary); font-size: var(--text-2xs); cursor: pointer; }
.title-suggestions button:hover { border-color: var(--color-primary-border); color: var(--color-primary); background: var(--color-primary-soft); }
.create-form .dialog-actions { align-items: center; justify-content: space-between; margin-top: var(--space-5); }
.create-form .dialog-actions span { color: var(--text-tertiary); font-size: var(--text-2xs); font-variant-numeric: tabular-nums; }
.dialog-error { margin: var(--space-3) 0 0; color: var(--color-danger); font-size: var(--text-2xs); }
.create-panel-enter-active, .create-panel-leave-active { transition: opacity var(--duration-base) var(--ease-standard), transform var(--duration-base) var(--ease-standard); }
.create-panel-enter-from, .create-panel-leave-to { opacity: 0; transform: translateY(-8px); }

.dialog-backdrop { position: fixed; inset: 0; z-index: var(--z-modal); display: grid; place-items: center; padding: var(--space-5); background: var(--bg-overlay); }
.dialog { width: min(460px, calc(100vw - 40px)); padding: var(--space-6); border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); background: var(--bg-surface); box-shadow: var(--shadow-lg); }
.dialog h2 { margin: 0; color: var(--text-primary); font-size: var(--text-lg); font-weight: var(--weight-semibold); }
.dialog > p { margin: var(--space-3) 0 0; color: var(--text-secondary); font-size: var(--text-xs); line-height: var(--leading-relaxed); }
.dialog label { display: grid; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-xs); font-weight: var(--weight-medium); }
.dialog-actions { justify-content: flex-end; margin-top: var(--space-5); }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }

@media (max-width: 1279px) {
  .page { padding: var(--space-8) var(--space-6); }
}
@media (max-width: 767px) {
  .page { padding: var(--space-6) var(--space-4); }
  .head { align-items: flex-start; flex-direction: column; gap: var(--space-4); }
  .head-actions { width: 100%; }
  .head-actions button { flex: 1; }
  .toolbar { align-items: stretch; flex-direction: column; }
  .sort-field { justify-content: space-between; }
  .result-count { align-self: flex-end; }
  .card-actions button { flex: 1; }
  .grid { grid-template-columns: 1fr; }
  .create-panel { grid-template-columns: 1fr; }
  .create-visual { display: none; }
  .create-form { padding: var(--space-5) var(--space-4); }
  .create-form .dialog-actions { align-items: stretch; flex-direction: column; }
  .create-form .dialog-actions button { width: 100%; }
}
</style>

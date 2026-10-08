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
      <section v-if="projects.loading && !projects.items.length" class="empty" aria-live="polite">正在加载课件…</section>
      <section v-else-if="projects.error && !projects.items.length" class="empty error" role="alert"><p>{{ projects.error }}</p><button class="secondary" @click="load">重试</button></section>
      <section v-else-if="!projects.items.length" class="empty"><div class="empty-icon" aria-hidden="true">▤</div><h2>还没有课件</h2><p>开始创建第一份课件，让 AI 和你一起完成备课。</p><button class="primary" @click="openCreate">开始创建第一份课件</button></section>
      <section v-else-if="!filteredProjects.length" class="empty compact"><h2>没有匹配的课件</h2><p>换一个关键词试试。</p><button class="secondary" @click="keyword = ''">清除搜索</button></section>
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
.page{min-height:calc(100vh - 84px);padding:44px max(24px,calc((100vw - 1200px)/2));background:linear-gradient(145deg,#f5faf7,#fff)}.head{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;margin-bottom:24px}.eyebrow{color:#25806d;font-weight:700;margin:0}.head h1{margin:6px 0;color:#173b33}.head p:not(.eyebrow),.meta{color:#6b7e77}.head-actions,.card-actions,.dialog-actions{display:flex;gap:10px;flex-wrap:wrap}button,input,select{font:inherit}.primary,.secondary,.danger{border-radius:9px;padding:9px 14px;font-weight:650;cursor:pointer}.primary{border:1px solid #277765;background:#277765;color:#fff}.secondary{border:1px solid #bfd5cd;background:#fff;color:#27594e}.danger{border:1px solid #f1c1c1;background:#fff;color:#a33}.danger.solid{background:#a33;color:#fff}.primary:disabled,.secondary:disabled,.danger:disabled{opacity:.55;cursor:not-allowed}
.toolbar{display:flex;align-items:center;gap:12px;margin-bottom:18px;padding:12px;border:1px solid #dce9e3;border-radius:13px;background:#fff}.search-field{flex:1}.search-field input,.sort-field select,.dialog input{width:100%;box-sizing:border-box;padding:9px 11px;border:1px solid #c7dbd3;border-radius:9px;background:#fff;color:#263b34}.search-field input:focus,.sort-field select:focus,.dialog input:focus{outline:3px solid #87c7b34d;border-color:#32826c}.sort-field{display:flex;align-items:center;gap:8px;color:#62766f;font-size:13px}.result-count{color:#72837d;font-size:13px;white-space:nowrap}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}.card{min-height:192px;padding:20px;border:1px solid #d9e8e1;border-radius:16px;background:#fff;box-shadow:0 8px 24px #235a4810;transition:transform .16s,box-shadow .16s}.card:hover{transform:translateY(-2px);box-shadow:0 14px 32px #235a4818}.card-top{display:flex;justify-content:space-between;color:#71847d;font-size:12px}.status,.version{padding:3px 8px;border-radius:999px;background:#ecf7f2;color:#28735f}.status.draft{background:#fff5df;color:#a56709}.status.locked{background:#f0edff;color:#6246a8}.card h2{font-size:18px;color:#193d34;margin:18px 0 6px}.step{font-size:13px;color:#26715f}.card-actions{margin-top:20px}.empty{min-height:320px;display:grid;place-content:center;text-align:center;border:1px dashed #bdd7cc;border-radius:18px;background:#ffffffaa;color:#62766f}.empty.compact{min-height:220px}.empty-icon{font-size:42px;color:#59a18d}.error,.dialog-error{color:#a33}.notice{padding:10px 13px;border-radius:9px;background:#edf8f3;color:#236a55}
.create-panel{display:grid;grid-template-columns:220px 1fr;gap:0;margin:0 0 24px;overflow:hidden;border:1px solid #cfe4db;border-radius:20px;background:#fff;box-shadow:0 18px 50px #214d3e14}.create-visual{min-height:250px;display:grid;place-content:center;justify-items:center;gap:5px;color:#fff;background:radial-gradient(circle at 20% 15%,#77baa5,#28735f 58%,#17493d)}.create-visual span{font-size:30px}.create-visual b{font-size:44px;letter-spacing:-2px}.create-visual small{opacity:.85}.create-form{padding:26px 30px}.create-heading{display:flex;justify-content:space-between;gap:20px}.create-heading h2{margin:4px 0 7px;color:#173b33}.create-heading p:last-child{margin:0 0 20px;color:#6b7e77}.close-create{align-self:flex-start;border:0;background:#f2f7f5;color:#5c746c;width:32px;height:32px;border-radius:50%;font-size:22px;cursor:pointer}.create-form>label{display:grid;gap:8px;color:#31594d;font-size:13px;font-weight:700}.create-form input{width:100%;box-sizing:border-box;padding:13px 14px;border:1px solid #bcd7cc;border-radius:11px;font-size:16px}.create-form input:focus{outline:3px solid #87c7b34d;border-color:#32826c}.title-suggestions{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.title-suggestions button{padding:6px 10px;border:1px solid #d6e7e0;border-radius:999px;background:#f8fbfa;color:#517067;font-size:12px;cursor:pointer}.create-form .dialog-actions{align-items:center;justify-content:space-between;margin-top:22px}.create-form .dialog-actions span{color:#8a9994;font-size:12px}.create-panel-enter-active,.create-panel-leave-active{transition:.22s ease}.create-panel-enter-from,.create-panel-leave-to{opacity:0;transform:translateY(-10px)}
.dialog-backdrop{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:20px;background:#10251e66}.dialog{width:min(460px,calc(100vw - 40px));box-sizing:border-box;padding:24px;border-radius:18px;background:#fff;box-shadow:0 24px 80px #10251e38}.dialog h2{margin:0;color:#193d34}.dialog>p{color:#697b74;line-height:1.6}.dialog label{display:grid;gap:7px;color:#31594d;font-size:13px;font-weight:700}.dialog-actions{justify-content:flex-end;margin-top:22px}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}@media(max-width:700px){.page{padding:24px 16px}.head{align-items:flex-start;flex-direction:column}.head-actions{width:100%}.head-actions button{flex:1}.toolbar{align-items:stretch;flex-direction:column}.sort-field{justify-content:space-between}.card-actions button{flex:1}.result-count{align-self:flex-end}.create-panel{grid-template-columns:1fr}.create-visual{display:none}.create-form{padding:22px 18px}.create-form .dialog-actions{align-items:flex-end;flex-direction:column}.create-form .dialog-actions button{width:100%}}
</style>

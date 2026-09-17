<template>
  <AppShell>
    <main class="page">
      <header class="head">
        <div><p class="eyebrow">我的课件</p><h1>继续完善你的教学设计</h1><p>课件、AI 迭代记录与版本会保存在同一项目中。</p></div>
        <div class="head-actions"><button class="secondary" @click="router.push({ name: 'S2Material' })">资料与证据中心</button><button class="secondary" @click="load">刷新</button><button class="primary" @click="createProject">＋ 新建课件</button></div>
      </header>
      <section v-if="projects.loading" class="empty">正在加载课件…</section>
      <section v-else-if="projects.error" class="empty error"><p>{{ projects.error }}</p><button class="secondary" @click="load">重试</button></section>
      <section v-else-if="!projects.items.length" class="empty"><div class="empty-icon">▤</div><h2>还没有课件</h2><p>开始创建第一份课件，让 AI 和你一起完成备课。</p><button class="primary" @click="createProject">开始创建第一份课件</button></section>
      <section v-else class="grid">
        <article v-for="item in projects.items" :key="projectId(item)" class="card">
          <div class="card-top"><span class="status" :class="item.status">{{ statusText(item.status) }}</span><span>v{{ item.version_no || item.version || 1 }}</span></div>
          <h2>{{ item.title || '未命名课件' }}</h2><p class="meta">最近编辑：{{ formatTime(item.updated_at) }}</p><p class="step">{{ stepText(item.current_step) }}</p>
          <div class="card-actions"><button class="primary" @click="resume(item)">继续编辑</button><button class="secondary" @click="viewVersions(item)">查看版本</button><button class="secondary" @click="exportProject(item)">导出</button><button class="danger" @click="removeProject(item)">删除</button></div>
        </article>
      </section>
    </main>
  </AppShell>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '../components/layout/AppShell.vue'
import { useCoursewareProjectStore } from '../stores/coursewareProjectStore'
import { useIntentStore } from '../stores/intentStore'
import { useMaterialStore } from '../stores/materialStore'
import { useOutlineStore } from '../stores/outlineStore'
import { useGenerationStore } from '../stores/generationStore'
import { useVersionStore } from '../stores/versionStore'
import { useModifyStore } from '../stores/modifyStore'

const router = useRouter(); const projects = useCoursewareProjectStore()
const statusText = (status) => ({ draft: '草稿', active: '编辑中', archived: '已归档', completed: '已完成' }[status] || '编辑中')
const stepText = (step) => ({ s1_intent: '当前：教学意图', s2_material: '当前：参考资料', s3_studio: '当前：AI 生成与迭代', s4_version: '当前：版本与导出' }[step] || '当前：教学意图')
const formatTime = (time) => time ? new Date(time).toLocaleString() : '刚刚'
const projectId = (item) => item.id || item.project_id || ''
const load = () => projects.loadProjects().catch(() => {})
async function createProject() {
  const title = window.prompt('请输入课件名称')?.trim(); if (!title) return
  try {
    const project = await projects.create(title)
    for (const store of [useIntentStore(), useMaterialStore(), useOutlineStore(), useGenerationStore(), useVersionStore(), useModifyStore()]) store.reset?.()
    await projects.updateStep('s1_intent')
    router.push({ name: 'S1Intent', query: { project_id: project.id || project.project_id } })
  } catch (error) { window.alert(error?.message || '新建课件失败') }
}
function resume(item) { router.push({ name: 'CoursewareResume', query: { project_id: projectId(item), generation_id: item.gen_id || item.generation_id || '' } }) }
function viewVersions(item) { router.push({ name: 'S4Version', query: { project_id: projectId(item), generation_id: item.gen_id || item.generation_id || '' } }) }
function exportProject(item) { viewVersions(item) }
async function removeProject(item) {
  if (!window.confirm(`确定删除“${item.title || '未命名课件'}”吗？删除后将从课件列表移除。`)) return
  try { await projects.remove(projectId(item)) } catch (error) { window.alert(error?.message || '删除课件失败') }
}
onMounted(load)
</script>

<style scoped>
.page{min-height:calc(100vh - 84px);padding:44px max(24px,calc((100vw - 1200px)/2));background:linear-gradient(145deg,#f5faf7,#fff)}.head{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;margin-bottom:30px}.eyebrow{color:#25806d;font-weight:700;margin:0}.head h1{margin:6px 0;color:#173b33}.head p:not(.eyebrow),.meta{color:#6b7e77}.head-actions,.card-actions{display:flex;gap:10px;flex-wrap:wrap}.primary,.secondary,.danger{border-radius:9px;padding:9px 14px;font-weight:650;cursor:pointer}.primary{border:1px solid #277765;background:#277765;color:#fff}.secondary{border:1px solid #bfd5cd;background:#fff;color:#27594e}.danger{border:1px solid #f1c1c1;background:#fff;color:#a33}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}.card{min-height:192px;padding:20px;border:1px solid #d9e8e1;border-radius:16px;background:#fff;box-shadow:0 8px 24px #235a4810}.card-top{display:flex;justify-content:space-between;color:#71847d;font-size:12px}.status{padding:3px 8px;border-radius:999px;background:#ecf7f2;color:#28735f}.status.draft{background:#fff5df;color:#a56709}.card h2{font-size:18px;color:#193d34;margin:18px 0 6px}.step{font-size:13px;color:#26715f}.card-actions{margin-top:20px}.empty{min-height:320px;display:grid;place-content:center;text-align:center;border:1px dashed #bdd7cc;border-radius:18px;background:#ffffffaa;color:#62766f}.empty-icon{font-size:42px;color:#59a18d}.error{color:#a33}@media(max-width:640px){.page{padding:24px 16px}.head{align-items:flex-start;flex-direction:column}}
</style>

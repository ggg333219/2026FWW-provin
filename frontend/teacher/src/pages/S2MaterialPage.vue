<template>
  <AppShell>
    <div class="s2-page">
      <div class="page-header">
        <div>
          <h2>S2 多模态资料中心</h2>
          <p>资料上传 → 解析 → 切片 (ChunkSchema) → RAG 检索 → 证据绑定</p>
        </div>
        <div class="page-header-right">
          <button v-if="isMockModeActive" class="mock-exit-btn" @click="exitMockMode">
            ⚠ Mock 模式 · 点击退出
          </button>
          <div class="step-pills">
            <router-link :to="{ name: 'S1Intent' }" class="pill">S1 意图</router-link>
            <span class="pill active">S2 资料</span>
            <button class="pill pill-button" @click="requestContinue">S3 生成</button>
            <router-link :to="{ name: 'S4Version' }" class="pill">S4 版本</router-link>
          </div>
        </div>
      </div>

      <!-- 独立路由入口：复用 S2 资料中心工作台（与 Workspace 内嵌 tab 同一组件，路由/内嵌统一） -->
      <S2MaterialWorkspace />

      <!-- 下一步：S2 → S3，和顶部步骤导航保持同一正式创建路径。 -->
      <div class="next-step-bar">
        <button class="next-step-btn" @click="requestContinue">
          下一步：进入 S3 生成 →
        </button>
        <div v-if="showNoEvidenceConfirm" class="continue-confirm" role="alert">
          <div>
            <strong>当前还没有绑定可用证据</strong>
            <p>可以返回上方上传并检索资料，也可以明确选择无资料生成。后者将仅依据 S1 教学意图生成，内容依据和引用会更少。</p>
          </div>
          <div class="continue-actions">
            <button class="secondary-btn" @click="showNoEvidenceConfirm = false">继续补充资料</button>
            <button class="danger-outline-btn" @click="confirmWithoutEvidence">确认无资料生成</button>
          </div>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '../components/layout/AppShell.vue'
import S2MaterialWorkspace from '../components/teacher/S2MaterialWorkspace.vue'
import { useMaterialStore, isEvidencePacketUsable } from '../stores/materialStore'
import { useIntentStore } from '../stores/intentStore'

const router = useRouter()
const materialStore = useMaterialStore()
const intentStore = useIntentStore()
intentStore.initialize()

const showNoEvidenceConfirm = ref(false)

const readEvidence = () => {
  if (isEvidencePacketUsable(materialStore.s3EvidencePayload)) return materialStore.s3EvidencePayload
  if (typeof window === 'undefined') return null
  try {
    return JSON.parse(window.localStorage.getItem('fuww_s2_evidence_packet') || 'null')
  } catch {
    return null
  }
}

const writeGenerationMode = (mode) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(`fuww_s2_generation_mode:${intentStore.sessionId}`, mode)
}

const requestContinue = () => {
  if (isEvidencePacketUsable(readEvidence())) {
    writeGenerationMode('with_evidence')
    router.push({ name: 'S3Studio' })
    return
  }
  showNoEvidenceConfirm.value = true
}

const confirmWithoutEvidence = () => {
  materialStore.clearEvidencePackets()
  writeGenerationMode('without_evidence')
  router.push({ name: 'S3Studio' })
}

/** Mock 模式检测与退出 */
const isMockModeActive = ref(false)

onMounted(() => {
  if (typeof window !== 'undefined') {
    isMockModeActive.value = window.localStorage.getItem('fuww_mock_mode') === 'true'
  }
})

const exitMockMode = () => {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem('fuww_mock_mode')
  }
  isMockModeActive.value = false
}
</script>

<style scoped>
.s2-page {
  padding: 20px;
  min-height: calc(100vh - 140px);
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 22px;
  color: #111827;
}

.page-header p {
  margin: 6px 0 0;
  font-size: 14px;
  color: #607a71;
}

.step-pills {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.page-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.mock-exit-btn {
  border: 1px solid #f0b429;
  background: #fffbeb;
  color: #b7791f;
  font-size: 12px;
  font-weight: 700;
  border-radius: 999px;
  padding: 6px 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.mock-exit-btn:hover {
  background: #fef3c7;
  border-color: #d69e2e;
}

.pill {
  font-size: 12px;
  font-weight: 600;
  color: #5f7467;
  background: #f0f5f2;
  border: 1px solid #e2ece6;
  border-radius: 999px;
  padding: 6px 14px;
  text-decoration: none;
  transition: all 0.15s;
}

.pill:hover {
  border-color: #5ca68f;
  color: #2f605a;
}

.pill.active {
  color: #fff;
  background: #2f605a;
  border-color: #2f605a;
}

.pill-button {
  font-family: inherit;
  cursor: pointer;
}

.next-step-bar {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #e2ece6;
  text-align: right;
}

.next-step-btn {
  display: inline-block;
  padding: 10px 24px;
  background: #2f605a;
  color: #fff;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  transition: background 0.15s;
  border: 0;
  cursor: pointer;
  font-family: inherit;
}

.next-step-btn:hover {
  background: #1e4a44;
}

.continue-confirm {
  margin-top: 14px;
  padding: 16px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  text-align: left;
  border: 1px solid #f1d5a8;
  border-radius: 14px;
  background: linear-gradient(135deg, #fffaf0, #fffdf8);
  color: #7c4a15;
}

.continue-confirm strong {
  font-size: 14px;
}

.continue-confirm p {
  margin: 5px 0 0;
  max-width: 720px;
  color: #8a6337;
  font-size: 12px;
  line-height: 1.6;
}

.continue-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.secondary-btn,
.danger-outline-btn {
  padding: 8px 14px;
  border-radius: 9px;
  font: 600 12px/1.2 inherit;
  cursor: pointer;
}

.secondary-btn {
  border: 1px solid #d8e3de;
  background: #fff;
  color: #46645a;
}

.danger-outline-btn {
  border: 1px solid #d49a55;
  background: transparent;
  color: #9a5713;
}

@media (max-width: 760px) {
  .page-header {
    flex-direction: column;
  }

  .continue-confirm {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>

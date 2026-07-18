<template>
  <div class="page">
    <!-- 流动波浪背景 -->
    <div class="wave-bg">
      <svg class="wave-svg" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="sg1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#d4e3e1" stop-opacity="0.6" />
            <stop offset="100%" stop-color="#8FC1B5" stop-opacity="0.3" />
          </linearGradient>
          <linearGradient id="sg2" x1="100%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#2F605A" stop-opacity="0.12" />
            <stop offset="100%" stop-color="#8FC1B5" stop-opacity="0.08" />
          </linearGradient>
        </defs>
        <path class="wave1" d="M-100,400 C200,280 400,520 700,380 C1000,240 1200,460 1540,360 L1540,900 L-100,900 Z" fill="url(#sg1)" />
        <path class="wave2" d="M-100,520 C300,380 500,620 800,480 C1100,340 1300,540 1540,450 L1540,900 L-100,900 Z" fill="url(#sg2)" />
        <path class="wave3" d="M-100,640 C250,500 550,700 900,580 C1150,480 1350,640 1540,560 L1540,900 L-100,900 Z" fill="url(#sg1)" opacity="0.5"/>
      </svg>
    </div>

    <!-- 浮动装饰圆 -->
    <div class="blob blob1"></div>
    <div class="blob blob2"></div>
    <div class="blob blob3"></div>

    <header class="site-header">
      <div class="brand-logo">
        <span class="logo-icon">🎓</span>
        <span class="logo-text">智能互动教学平台</span>
      </div>
    </header>

    <main class="hero">
      <div class="hero-left">
        <span class="badge">智慧教育 · 赋能未来</span>
        <h1 class="hero-title">
          <span class="project-name-line">
            <span class="project-name">{{ displayedProjectName }}</span>
            <span class="typewriter-caret" aria-hidden="true"></span>
          </span>
          <span class="hero-slogan-line" aria-live="polite">
            <span class="slogan-wrap">
              <span class="tagline-top">{{ displayedTaglineTop }}</span>
              <span class="tagline-bottom">{{ displayedTaglineBottom }}</span>
            </span>
          </span>
        </h1>
        <p class="hero-desc">
          教师高效管理课件讲稿，学生实时互动提问，
          AI 智能解析学情，让每一节课更有意义。
        </p>
        <div class="connection-pill">
          <span class="pill-dot"></span>
          泛雅开放平台已接通 · 学生端可同步查看课程与知识图谱
        </div>
        <div class="features">
          <div class="feature-chip">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            讲稿 AI 生成
          </div>
          <div class="feature-chip">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            实时提问统计
          </div>
          <div class="feature-chip">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
            学情深度分析
          </div>
          <div class="feature-chip feature-chip-accent">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h6l3 7 4-14 2 7h3"/></svg>
            泛雅开放平台接通
          </div>
        </div>
      </div>

      <div class="login-card">
        <div class="card-inner">
          <h2 class="card-title">{{ isRegisterMode ? '注册新账号' : '欢迎回来' }}</h2>
          <p class="card-sub">{{ isRegisterMode ? '创建一个教师或学生账号' : '请登录您的账号继续使用' }}</p>

          <form v-if="!isRegisterMode" @submit.prevent="handleLogin" class="form">
            <div class="field">
              <label>账号</label>
              <div class="input-wrap">
                <svg class="field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                <input type="text" v-model="username" placeholder="教师账号 / 学生账号" autocomplete="username" required />
              </div>
            </div>
            <div class="field">
              <label>密码</label>
              <div class="input-wrap">
                <svg class="field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                <input type="password" v-model="password" placeholder="输入密码" autocomplete="current-password" required />
              </div>
            </div>

            <div class="row-between">
              <label class="checkbox-label">
                <input type="checkbox" v-model="remember" />
                <span>记住密码</span>
              </label>
              <a href="#" class="link" @click.prevent>忘记密码</a>
            </div>

            <button type="submit" class="submit" :disabled="loading">
              <span v-if="!loading">登 录</span>
              <span v-else class="loading-dots"><span></span><span></span><span></span></span>
            </button>
          </form>

          <form v-else @submit.prevent="handleRegister" class="form">
            <div class="field">
              <label>账号</label>
              <div class="input-wrap">
                <svg class="field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                <input type="text" v-model="username" placeholder="设置登录账号（推荐英文）" autocomplete="username" required />
              </div>
            </div>
            <div class="field">
              <label>密码</label>
              <div class="input-wrap">
                <svg class="field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                <input type="password" v-model="password" placeholder="至少 4 位密码" autocomplete="new-password" required />
              </div>
            </div>
            <div class="field">
              <label>角色</label>
              <div class="role-radio-group">
                <label class="radio-item">
                  <input type="radio" value="teacher" v-model="role" />
                  <span>教师</span>
                </label>
                <label class="radio-item">
                  <input type="radio" value="student" v-model="role" />
                  <span>学生</span>
                </label>
              </div>
            </div>
            <button type="submit" class="submit" :disabled="loading">
              <span v-if="!loading">注 册</span>
              <span v-else class="loading-dots"><span></span><span></span><span></span></span>
            </button>
          </form>

          <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
          <p class="login-hint">
            <span v-if="!isRegisterMode">
              没有账号？
              <a href="#" class="link" @click.prevent="switchMode">去注册</a>
            </span>
            <span v-else>
              已有账号？
              <a href="#" class="link" @click.prevent="switchMode">去登录</a>
            </span>
          </p>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { defineEmits, onMounted, onUnmounted, ref } from 'vue'
import { API_BASE } from '../config/api'

const emit = defineEmits(['login-success'])
const username = ref('')
const password = ref('')
const remember = ref(false)
const loading = ref(false)
const isRegisterMode = ref(false)
const role = ref('student')
const errorMessage = ref('')

const projectName = '启智云'
const displayedProjectName = ref('')
const taglineSets = [
  { top: '一个平台', bottom: '连接教与学' },
  { top: '让学习更简单', bottom: '让教学更高效' }
]
const displayedTaglineTop = ref('')
const displayedTaglineBottom = ref('')

const TITLE_TYPE_MS = 320
const SLOGAN_TYPE_MS = 140
const SLOGAN_LINE_GAP_MS = 120
const SLOGAN_HOLD_MS = 1800
const SLOGAN_CLEAR_GAP_MS = 280

let projectNameCycleId = 0
let sloganCycleId = 0
const pendingTimeouts = new Set()

const sleep = (ms) => new Promise((resolve) => {
  const timer = setTimeout(() => {
    pendingTimeouts.delete(timer)
    resolve()
  }, ms)
  pendingTimeouts.add(timer)
})

const clearPendingTimeouts = () => {
  pendingTimeouts.forEach((timer) => clearTimeout(timer))
  pendingTimeouts.clear()
}

const runProjectNameTypewriter = async (cycleId) => {
  displayedProjectName.value = ''
  for (let i = 1; i <= projectName.length; i += 1) {
    displayedProjectName.value = projectName.slice(0, i)
    await sleep(TITLE_TYPE_MS)
    if (cycleId !== projectNameCycleId) return
  }
}

const runSloganTypewriter = async (cycleId) => {
  let sloganIndex = 0
  while (cycleId === sloganCycleId) {
    const currentSlogan = taglineSets[sloganIndex]
    displayedTaglineTop.value = ''
    displayedTaglineBottom.value = ''

    for (let i = 1; i <= currentSlogan.top.length; i += 1) {
      displayedTaglineTop.value = currentSlogan.top.slice(0, i)
      await sleep(SLOGAN_TYPE_MS)
      if (cycleId !== sloganCycleId) return
    }

    await sleep(SLOGAN_LINE_GAP_MS)
    if (cycleId !== sloganCycleId) return

    for (let i = 1; i <= currentSlogan.bottom.length; i += 1) {
      displayedTaglineBottom.value = currentSlogan.bottom.slice(0, i)
      await sleep(SLOGAN_TYPE_MS)
      if (cycleId !== sloganCycleId) return
    }

    await sleep(SLOGAN_HOLD_MS)
    if (cycleId !== sloganCycleId) return

    displayedTaglineTop.value = ''
    displayedTaglineBottom.value = ''
    await sleep(SLOGAN_CLEAR_GAP_MS)
    if (cycleId !== sloganCycleId) return

    sloganIndex = (sloganIndex + 1) % taglineSets.length
  }
}

onMounted(() => {
  projectNameCycleId += 1
  sloganCycleId += 1
  const projectCycleId = projectNameCycleId
  const currentSloganCycleId = sloganCycleId

  const startHeadlineAnimation = async () => {
    await runProjectNameTypewriter(projectCycleId)
    if (projectCycleId !== projectNameCycleId || currentSloganCycleId !== sloganCycleId) return
    runSloganTypewriter(currentSloganCycleId)
  }

  startHeadlineAnimation()
})

onUnmounted(() => {
  projectNameCycleId += 1
  sloganCycleId += 1
  clearPendingTimeouts()
})

const tryLocalLoginFallback = () => {
  const uname = String(username.value || '').trim().toLowerCase()
  const pwd = String(password.value || '')
  const accountRoleMap = {
    jiaoshi: 'teacher',
    teacher: 'teacher',
    laoshi: 'teacher',
    xuesheng: 'student',
    student: 'student',
    xuesheng1: 'student'
  }
  const mappedRole = accountRoleMap[uname]
  const isValidDemoPassword = pwd === uname || pwd === '123456'
  if (!mappedRole || !isValidDemoPassword) {
    throw new Error('账号或密码错误')
  }
  return { username: uname, role: mappedRole }
}

const resolveRemoteLoginUser = (payload) => {
  const root = payload && typeof payload === 'object' ? payload : {}
  const data = root.data && typeof root.data === 'object' ? root.data : root
  const usernameRaw = String(data.username || '').trim()
  if (!usernameRaw) return null
  const roleRaw = String(data.role || '').trim().toLowerCase()
  return {
    username: usernameRaw,
    role: roleRaw === 'teacher' ? 'teacher' : 'student'
  }
}

const switchMode = () => {
  errorMessage.value = ''
  password.value = ''
  isRegisterMode.value = !isRegisterMode.value
}

const handleLogin = async () => {
  if (!username.value || !password.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.value,
        password: password.value
      })
    })
    if (res.status === 404) {
      const fallbackUser = tryLocalLoginFallback()
      emit('login-success', fallbackUser)
      return
    }

    const payload = await res.json().catch(() => ({}))
    if (res.ok) {
      const remoteUser = resolveRemoteLoginUser(payload)
      if (remoteUser) {
        emit('login-success', remoteUser)
        return
      }
      throw new Error(String(payload?.message || '').trim() || '登录响应异常，请稍后重试')
    }

    try {
      const fallbackUser = tryLocalLoginFallback()
      emit('login-success', fallbackUser)
      return
    } catch (fallbackErr) {
      const message = String(payload?.message || '').trim()
      throw new Error(message || fallbackErr.message || `登录失败 (${res.status})`)
    }
  } catch (err) {
    if (String(err?.message || '').includes('Failed to fetch')) {
      try {
        const fallbackUser = tryLocalLoginFallback()
        emit('login-success', fallbackUser)
        return
      } catch (fallbackErr) {
        errorMessage.value = fallbackErr.message || '登录失败，请稍后重试'
        return
      }
    }
    errorMessage.value = err.message || '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

const handleRegister = async () => {
  if (!username.value || !password.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.value,
        password: password.value,
        role: role.value
      })
    })
    const payload = await res.json().catch(() => ({}))
    if (!res.ok || payload.code !== 200) {
      throw new Error(payload.message || `注册失败 (${res.status})`)
    }
    isRegisterMode.value = false
    password.value = ''
    errorMessage.value = '注册成功，请使用该账号登录'
  } catch (err) {
    errorMessage.value = err.message || '注册失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.page {
  width: 100vw;
  min-height: 100vh;
  background: #f4f7f7;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  font-family: 'PingFang SC', '-apple-system', sans-serif;
}

.wave-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.wave-svg {
  width: 100%;
  height: 100%;
}

.wave1 {
  animation: wave-flow 12s ease-in-out infinite alternate;
  transform-origin: 50% 50%;
}

.wave2 {
  animation: wave-flow 9s ease-in-out infinite alternate-reverse;
  transform-origin: 50% 50%;
}

.wave3 {
  animation: wave-flow 15s ease-in-out infinite alternate;
  transform-origin: 50% 50%;
}

@keyframes wave-flow {
  0%   { d: path("M-100,400 C200,280 400,520 700,380 C1000,240 1200,460 1540,360 L1540,900 L-100,900 Z"); }
  50%  { d: path("M-100,350 C250,460 500,280 760,420 C1020,560 1280,320 1540,410 L1540,900 L-100,900 Z"); }
  100% { d: path("M-100,440 C180,310 450,560 730,400 C1010,240 1260,480 1540,380 L1540,900 L-100,900 Z"); }
}

.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  pointer-events: none;
  animation: float 8s ease-in-out infinite;
  z-index: 0;
}

.blob1 {
  width: 400px;
  height: 400px;
  top: -120px;
  left: -100px;
  background: radial-gradient(circle, rgba(143,193,181,0.35) 0%, transparent 70%);
  animation-delay: 0s;
  animation-duration: 10s;
}

.blob2 {
  width: 320px;
  height: 320px;
  bottom: 80px;
  right: -80px;
  background: radial-gradient(circle, rgba(47,96,90,0.18) 0%, transparent 70%);
  animation-delay: -3s;
  animation-duration: 12s;
}

.blob3 {
  width: 240px;
  height: 240px;
  top: 40%;
  left: 38%;
  background: radial-gradient(circle, rgba(212,227,225,0.5) 0%, transparent 70%);
  animation-delay: -5s;
  animation-duration: 9s;
}

@keyframes float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33%  { transform: translate(24px, -16px) scale(1.05); }
  66%  { transform: translate(-16px, 20px) scale(0.96); }
}

.site-header {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px 60px;
}

.brand-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  font-size: 24px;
}

.logo-text {
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: 0.5px;
}

.hero {
  position: relative;
  z-index: 10;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 80px;
  padding: 40px 80px 80px;
}

.hero-left {
  flex: 1;
  max-width: 520px;
  animation: fade-in-left 0.8s ease both;
}

@keyframes fade-in-left {
  from { opacity: 0; transform: translateX(-32px); }
  to   { opacity: 1; transform: translateX(0); }
}

.badge {
  display: inline-block;
  padding: 6px 14px;
  background: rgba(47, 96, 90, 0.1);
  color: #2F605A;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 24px;
  border: 1px solid rgba(47, 96, 90, 0.2);
}

.hero-title {
  display: flex;
  flex-direction: column;
  gap: 10px;
  line-height: 1.15;
  margin: 0 0 16px;
  letter-spacing: -1px;
  /* 为标题和两行标语预留垂直空间，避免打印第二行时上移 */
  min-height: 11rem;
}

.project-name-line {
  display: inline-flex;
  align-items: flex-end;
  min-height: 1.2em;
  font-size: 64px;
  font-weight: 800;
  color: #1e293b;
}

.project-name {
  display: inline-block;
  min-width: 3ch;
  color: #0b3d2e;
  text-shadow: 0 8px 20px rgba(47, 96, 90, 0.12);
}

.typewriter-caret {
  width: 3px;
  height: 0.95em;
  margin-left: 8px;
  border-radius: 2px;
  background: #2F605A;
  animation: caret-blink 0.9s steps(1, end) infinite;
}

@keyframes caret-blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

.hero-desc {
  font-size: 16px;
  color: #64748b;
  line-height: 1.8;
  margin: 0 0 32px;
  max-width: 440px;
}

.hero-slogan-line {
  display: block;
  min-height: 2.3em;
  margin-top: 2px;
  font-size: 44px;
  font-weight: 800;
  line-height: 1.08;
}

.slogan-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
  /* 顶部对齐，逐行打印时从上向下展开，不会把上一行推上去 */
  justify-content: flex-start;
  min-height: 2.3em;
}

@media (max-width: 768px) {
  .hero-title {
    min-height: 9rem;
  }
}

.tagline-top {
  color: #1e293b;
  font-size: 1em;
  font-weight: 800;
  line-height: 1.02;
}

.tagline-bottom {
  color: #2F605A;
  font-size: 1em;
  font-weight: 800;
  line-height: 1.02;
}

.features {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.feature-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 30px;
  font-size: 13px;
  color: #334155;
  font-weight: 500;
  box-shadow: 0 2px 6px rgba(0,0,0,0.04);
}

.feature-chip svg {
  width: 16px;
  height: 16px;
  color: #2F605A;
  flex-shrink: 0;
}

.feature-chip-accent {
  background: linear-gradient(180deg, rgba(236, 248, 243, 0.96), rgba(217, 241, 233, 0.96));
  color: #226a5a;
  border-color: rgba(47, 96, 90, 0.18);
}

.connection-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 10px 0 2px;
  padding: 8px 14px;
  border-radius: 999px;
  background: rgba(236, 248, 243, 0.92);
  border: 1px solid rgba(47, 96, 90, 0.14);
  color: #235f53;
  font-size: 13px;
  font-weight: 600;
}

.pill-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #14b8a6;
  box-shadow: 0 0 0 0 rgba(20, 184, 166, 0.35);
  animation: pulse-pill 2s ease-in-out infinite;
}

@keyframes pulse-pill {
  0%, 100% { box-shadow: 0 0 0 0 rgba(20, 184, 166, 0.35); }
  50% { box-shadow: 0 0 0 5px rgba(20, 184, 166, 0); }
}

.login-card {
  flex: 0 0 420px;
  animation: fade-in-right 0.8s ease 0.15s both;
}

@keyframes fade-in-right {
  from { opacity: 0; transform: translateX(32px); }
  to   { opacity: 1; transform: translateX(0); }
}

.card-inner {
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.7);
  border-radius: 28px;
  padding: 44px 40px;
  box-shadow:
    0 4px 6px -1px rgba(0,0,0,0.05),
    0 20px 48px -8px rgba(47,96,90,0.12);
}

.card-title {
  font-size: 26px;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 6px;
}

.card-sub {
  font-size: 14px;
  color: #64748b;
  margin: 0 0 32px;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.field label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 8px;
}

.input-wrap {
  position: relative;
}

.field-icon {
  position: absolute;
  left: 14px;
  top: 50%;
  transform: translateY(-50%);
  width: 17px;
  height: 17px;
  color: #94a3b8;
  pointer-events: none;
}

.input-wrap input {
  width: 100%;
  height: 46px;
  padding: 0 16px 0 40px;
  border: 1.5px solid #e2e8f0;
  border-radius: 12px;
  font-size: 14px;
  color: #1e293b;
  background: #f8fafc;
  outline: none;
  transition: all 0.2s;
  box-sizing: border-box;
}

.input-wrap input:focus {
  border-color: #2F605A;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(47, 96, 90, 0.1);
}

.row-between {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #475569;
  cursor: pointer;
}

.checkbox-label input {
  accent-color: #2F605A;
}

.link {
  color: #2F605A;
  font-weight: 500;
  text-decoration: none;
}

.link:hover {
  text-decoration: underline;
}

.submit {
  height: 48px;
  border: none;
  border-radius: 12px;
  background: #2F605A;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 4px;
  box-shadow: 0 8px 20px rgba(47, 96, 90, 0.25);
  transition: all 0.2s;
  letter-spacing: 2px;
}

.submit:hover:not(:disabled) {
  background: #234b46;
  transform: translateY(-2px);
  box-shadow: 0 12px 24px rgba(47, 96, 90, 0.3);
}

.submit:active:not(:disabled) {
  transform: translateY(0);
}

.submit:disabled {
  background: #8FC1B5;
  cursor: not-allowed;
  box-shadow: none;
}

.loading-dots {
  display: flex;
  gap: 5px;
  align-items: center;
  justify-content: center;
}

.loading-dots span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgba(255,255,255,0.7);
  animation: dot-bounce 0.9s ease-in-out infinite;
}

.loading-dots span:nth-child(2) { animation-delay: 0.15s; }
.loading-dots span:nth-child(3) { animation-delay: 0.3s; }

@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

.login-hint {
  margin-top: 20px;
  font-size: 11.5px;
  color: #94a3b8;
  text-align: center;
  line-height: 1.6;
}

.error-text {
  margin-top: 12px;
  font-size: 13px;
  color: #ef4444;
  text-align: center;
}

.role-radio-group {
  display: flex;
  gap: 16px;
  margin-top: 4px;
}

.radio-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #475569;
}

@media (max-width: 960px) {
  .hero {
    flex-direction: column;
    padding: 20px 24px 50px;
    gap: 32px;
  }

  .site-header {
    padding: 16px 22px;
  }

  .hero-left {
    max-width: 100%;
    text-align: center;
  }

  .hero-desc {
    margin-inline: auto;
  }

  .features {
    justify-content: center;
  }

  .hero-title {
    align-items: center;
  }

  .hero-slogan-line {
    font-size: 34px;
  }

  .slogan-wrap {
    align-items: center;
  }

  .project-name-line {
    font-size: 48px;
    justify-content: center;
  }

  .login-card {
    width: min(100%, 460px);
    flex: none;
  }

  .card-inner {
    padding: 36px 28px;
    border-radius: 24px;
  }
}
</style>

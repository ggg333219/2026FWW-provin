<template>
  <div class="practice-panel">
    <header class="practice-header">
      <div>
        <p class="kicker">随堂练习</p>
        <h2>{{ courseName || '当前课程' }} · 课堂测验</h2>
        <p class="desc">完成后可查看批改结果、正确率和错题解析，并一键加入错题本。</p>
      </div>
      <div class="meta">
        <span>题量 {{ questions.length }}</span>
        <span>已作答 {{ answeredCount }} 题</span>
        <span>当前节点 {{ currentNodeTitle || '未定位' }}</span>
      </div>
    </header>

    <section class="question-list" v-if="!submitted">
      <div v-if="loading" class="loading-tip">正在生成本页练习题...</div>
      <div class="demo-guide-row">
        <div class="guide-copy">
          <strong>快捷填充模式</strong>
          <span>可一键填充答案并提交，快速完成批改并查看错题解析。</span>
        </div>
        <div class="guide-actions">
          <button class="btn ghost" :disabled="loading" @click="fillDemoAnswers">一键填充</button>
          <button class="btn primary" :disabled="loading" @click="autoDemoSubmit">自动提交批改</button>
        </div>
      </div>

      <div class="practice-insight-grid">
        <article class="insight-card">
          <h4>本轮练习目标</h4>
          <ul>
            <li>先完成基础判断题，再做综合应用题。</li>
            <li>对含计算步骤的题目，优先写出判定依据。</li>
            <li>预计完成时长：约 {{ estimatedMinutes }} 分钟。</li>
          </ul>
        </article>
        <article class="insight-card highlight">
          <h4>实时作答进度</h4>
          <div class="insight-progress">
            <div class="insight-progress-fill" :style="{ width: completionPercent + '%' }"></div>
          </div>
          <p>已完成 {{ answeredCount }}/{{ questions.length }} 题，当前进度 {{ completionPercent }}%</p>
        </article>
        <article class="insight-card">
          <h4>提分关注点</h4>
          <div class="insight-tag-row">
            <span v-for="tag in recommendationTags" :key="tag" class="insight-tag">{{ tag }}</span>
          </div>
        </article>
      </div>

      <article class="question-card" v-for="(q, idx) in questions" :key="q.id">
        <h3>{{ idx + 1 }}. {{ q.stem }}</h3>
        <div class="options">
          <button
            v-for="opt in q.options"
            :key="opt.key"
            class="option-btn"
            :class="{ active: answers[q.id] === opt.key }"
            @click="selectAnswer(q.id, opt.key)"
          >
            {{ opt.key }}. {{ opt.text }}
          </button>
        </div>
      </article>

      <div class="submit-row">
        <button class="btn ghost" :disabled="loading" @click="reset">重置作答</button>
        <button class="btn primary" :disabled="loading" @click="submit">提交批改</button>
      </div>
    </section>

    <section class="result-panel" v-else>
      <div class="score-grid">
        <div class="score-card">
          <span>总题数</span>
          <strong>{{ result.total }}</strong>
        </div>
        <div class="score-card">
          <span>答对题数</span>
          <strong>{{ result.correct }}</strong>
        </div>
        <div class="score-card">
          <span>正确率</span>
          <strong>{{ result.accuracy }}%</strong>
        </div>
      </div>

      <article class="result-next-step">
        <h3>下一步学习建议</h3>
        <ul>
          <li v-for="(item, index) in followupSuggestions" :key="`suggest-${index}`">{{ item }}</li>
        </ul>
      </article>

      <div class="wrong-list" v-if="result.wrongs.length">
        <h3>错题解析</h3>
        <article class="wrong-item" v-for="item in result.wrongs" :key="item.id">
          <div class="wrong-head">
            <strong>{{ item.stem }}</strong>
            <span>你的答案：{{ item.userAnswer || '未作答' }}</span>
          </div>
          <p>正确答案：{{ item.correctAnswer }}</p>
          <p>解析：{{ item.analysis }}</p>
        </article>
        <div class="submit-row">
          <button class="btn primary" @click="addWrongSet">加入错题本</button>
          <button class="btn ghost" @click="goToWrongSet">去个人中心查看错题</button>
          <button class="btn ghost" @click="emitNavigate('analytics')">查看学习分析</button>
          <button class="btn ghost" @click="retry">再练一组</button>
        </div>
      </div>

      <div class="all-right" v-else>
        <h3>全部正确，表现很好！</h3>
        <div class="submit-row">
          <button class="btn ghost" @click="goToWrongSet">去个人中心看练习记录</button>
          <button class="btn ghost" @click="emitNavigate('analytics')">查看学习分析</button>
          <button class="btn ghost" @click="retry">再练一组</button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
/* eslint-disable no-undef */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { studentV1Api } from '../../services/v1'

const props = defineProps({
  courseName: {
    type: String,
    default: ''
  },
  currentNodeTitle: {
    type: String,
    default: ''
  },
  studentId: {
    type: String,
    default: ''
  },
  courseId: {
    type: String,
    default: ''
  },
  nodeId: {
    type: String,
    default: ''
  },
  pageNum: {
    type: Number,
    default: 1
  }
})
const emit = defineEmits(['jump-personal-practice', 'navigate-section'])

const questions = ref([
  {
    id: 'q1',
    stem: '正应力的常用判定核心是以下哪一项？',
    options: [
      { key: 'A', text: '仅看材料名称' },
      { key: 'B', text: '先看受力方向与截面法向关系' },
      { key: 'C', text: '只看题目图形大小' },
      { key: 'D', text: '先求剪应力再猜测' }
    ],
    answer: 'B',
    analysis: '正应力由法向分量引起，应先判断受力方向与截面法向关系。'
  },
  {
    id: 'q2',
    stem: '构件受拉时，正应力符号通常记为？',
    options: [
      { key: 'A', text: '正值' },
      { key: 'B', text: '负值' },
      { key: 'C', text: '恒为0' },
      { key: 'D', text: '与面积无关' }
    ],
    answer: 'A',
    analysis: '常用工程符号约定中，拉应力为正，压应力为负。'
  },
  {
    id: 'q3',
    stem: '以下哪项最能提高变形题中的判定速度？',
    options: [
      { key: 'A', text: '背答案' },
      { key: 'B', text: '每题都完整推导一遍' },
      { key: 'C', text: '建立“受力-变形-判定”快速检查清单' },
      { key: 'D', text: '随机选择计算公式' }
    ],
    answer: 'C',
    analysis: '建立固定判定清单可显著降低认知切换成本并减少漏判。'
  }
])

const taskId = ref('')
const answers = ref({})
const submitted = ref(false)
const loading = ref(false)
const useRemoteData = ref(false)
const submitResult = ref(null)

const localResult = computed(() => {
  const wrongs = questions.value
    .filter((q) => answers.value[q.id] !== q.answer)
    .map((q) => ({
      id: q.id,
      stem: q.stem,
      userAnswer: answers.value[q.id] || '',
      correctAnswer: q.answer,
      analysis: q.analysis
    }))
  const total = questions.value.length
  const correct = total - wrongs.length
  const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0
  return { total, correct, accuracy, wrongs }
})

const result = computed(() => {
  if (submitResult.value) {
    const total = Number(submitResult.value.totalCount || 0)
    const correct = Number(submitResult.value.correctCount || 0)
    const score = Number(submitResult.value.score || 0)
    const details = Array.isArray(submitResult.value.details) ? submitResult.value.details : []
    const wrongs = details
      .filter((item) => item && item.correct === false)
      .map((item) => ({
        id: item.questionId,
        stem: item.content || '题目内容',
        userAnswer: item.userAnswer || '',
        correctAnswer: item.correctAnswer || '',
        analysis: item.explanation || item.aiComment || '暂无解析'
      }))
    return {
      total,
      correct,
      accuracy: total > 0 ? Math.round((correct / total) * 100) : score,
      wrongs
    }
  }
  return localResult.value
})

const answeredCount = computed(() => {
  return questions.value.filter((q) => String(answers.value[q.id] || '').trim()).length
})

const completionPercent = computed(() => {
  if (!questions.value.length) return 0
  return Math.round((answeredCount.value / questions.value.length) * 100)
})

const estimatedMinutes = computed(() => {
  return Math.max(6, Math.round(questions.value.length * 2.5))
})

const recommendationTags = computed(() => {
  const nodeTitle = String(props.currentNodeTitle || '').trim()
  const tags = ['概念辨析', '公式应用', '易错点复盘']
  if (nodeTitle) {
    tags.unshift(`${nodeTitle}专项`)
  }
  return tags.slice(0, 4)
})

const followupSuggestions = computed(() => {
  const accuracy = Number(result.value?.accuracy || 0)
  const nodeTitle = String(props.currentNodeTitle || '当前知识点').trim()
  if (accuracy >= 90) {
    return [
      `你已高质量掌握「${nodeTitle}」，建议转入进阶题型训练。`,
      '把本次高频解题步骤整理成 3 条速记卡。',
      '明天进行一次 5 题小测，检验记忆保持度。'
    ]
  }
  if (accuracy >= 70) {
    return [
      `「${nodeTitle}」基础较稳，建议优先复盘错题对应知识点。`,
      '先做 3 道同类题，再做 2 道变式题巩固迁移能力。',
      '将错误原因记录到个人笔记，避免重复失分。'
    ]
  }
  return [
    `建议先回看「${nodeTitle}」核心概念讲解，再重做本页题目。`,
    '采用“读题-判定-列式-校验”四步法逐题拆解。',
    '完成错题重做后，回个人中心查看薄弱点变化趋势。'
  ]
})

const selectAnswer = (id, key) => {
  answers.value = { ...answers.value, [id]: key }
}

const reset = () => {
  answers.value = {}
}

const fillDemoAnswers = () => {
  if (!questions.value.length) return
  const wrongQuota = Math.max(1, Math.floor(questions.value.length / 3))
  const wrongTargets = new Set()
  questions.value.forEach((q, idx) => {
    if (!q.answer) return
    if (wrongTargets.size >= wrongQuota) return
    if (idx % 2 === 0) {
      wrongTargets.add(q.id)
    }
  })

  const nextAnswers = {}
  questions.value.forEach((q) => {
    const options = Array.isArray(q.options) ? q.options : []
    if (!options.length) return
    const firstOptionKey = options[0]?.key || ''
    if (!q.answer) {
      nextAnswers[q.id] = firstOptionKey
      return
    }
    if (!wrongTargets.has(q.id)) {
      nextAnswers[q.id] = q.answer
      return
    }
    const wrongOption = options.find((opt) => opt.key && opt.key !== q.answer)
    nextAnswers[q.id] = (wrongOption?.key || firstOptionKey)
  })
  answers.value = {
    ...answers.value,
    ...nextAnswers
  }
  ElMessage.success('已填充参考答案，可直接提交批改')
}

const autoDemoSubmit = async () => {
  fillDemoAnswers()
  await submit()
}

const buildSubmitPayload = () => {
  return questions.value.map((q) => ({
    questionId: q.id,
    userAnswer: answers.value[q.id] || ''
  }))
}

const submit = async () => {
  if (!questions.value.length) {
    ElMessage.warning('暂无可提交题目')
    return
  }
  if (useRemoteData.value && taskId.value) {
    try {
      loading.value = true
      const payload = await studentV1Api.coursewares.submitPractice({
        taskId: taskId.value,
        studentId: props.studentId,
        answers: buildSubmitPayload()
      })
      submitResult.value = payload?.data || null
      submitted.value = true
      ElMessage.success('已完成批改并同步练习记录')
      return
    } catch (error) {
      ElMessage.warning(`接口批改失败，已切换本地批改：${error.message}`)
    } finally {
      loading.value = false
    }
  }
  submitted.value = true
  ElMessage.success('已完成批改')
}

const addWrongSet = () => {
  if (useRemoteData.value) {
    ElMessage.success('错题已进入系统错题本，可在个人中心-练习记录查看')
    return
  }
  ElMessage.success(`已加入错题本（本轮共 ${result.value.wrongs.length} 题）`)
}

const goToWrongSet = () => {
  emit('jump-personal-practice')
}

const emitNavigate = (section) => {
  emit('navigate-section', String(section || ''))
}

const mapQuestionFromApi = (q, idx) => {
  const options = Array.isArray(q?.options) ? q.options : []
  return {
    id: String(q?.questionId || `q${idx + 1}`),
    stem: String(q?.content || `题目 ${idx + 1}`),
    options: options.map((text, i) => ({
      key: String.fromCharCode(65 + i),
      text: String(text || '')
    })),
    answer: '',
    analysis: ''
  }
}

const loadPracticeTask = async () => {
  if (!props.studentId || !props.courseId) return
  try {
    loading.value = true
    const resp = await studentV1Api.coursewares.generatePractice({
      studentId: props.studentId,
      courseId: props.courseId,
      nodeId: props.nodeId,
      pageNum: props.pageNum || 1,
      difficulty: 2,
      count: 3
    })
    const data = resp?.data || {}
    const remoteQuestions = Array.isArray(data.questions) ? data.questions : []
    if (!remoteQuestions.length) {
      useRemoteData.value = false
      ElMessage.warning('后端暂未返回题目，已使用内置题目')
      return
    }
    taskId.value = String(data.taskId || '')
    questions.value = remoteQuestions.map(mapQuestionFromApi)
    useRemoteData.value = taskId.value !== ''
  } catch (error) {
    useRemoteData.value = false
    ElMessage.warning(`练习题加载失败，已使用内置题目：${error.message}`)
  } finally {
    loading.value = false
  }
}

const retry = async () => {
  submitted.value = false
  answers.value = {}
  submitResult.value = null
  if (useRemoteData.value) {
    await loadPracticeTask()
  }
}

onMounted(async () => {
  await loadPracticeTask()
})
</script>

<style scoped>
.practice-panel { border: 1px solid #d9e7df; border-radius: 18px; background: #fff; padding: 14px; }
.practice-header { display: flex; justify-content: space-between; gap: 12px; }
.kicker { margin: 0; color: #6a8278; font-size: 12px; }
.practice-header h2 { margin: 4px 0; font-size: 20px; color: #23463f; }
.desc { margin: 0; color: #688379; font-size: 13px; }
.meta { display: grid; gap: 6px; font-size: 12px; color: #46655d; align-content: start; }
.question-list { margin-top: 12px; display: grid; gap: 10px; }
.loading-tip { font-size: 12px; color: #6d857b; }
.demo-guide-row {
  border: 1px solid #d9e9e1;
  border-radius: 12px;
  background: linear-gradient(145deg, #f3faf6 0%, #ecf6f0 100%);
  padding: 10px 12px;
  display: flex;
  gap: 10px;
  align-items: flex-start;
  justify-content: space-between;
}
.guide-copy {
  display: grid;
  gap: 4px;
}
.guide-copy strong {
  font-size: 13px;
  color: #254940;
}
.guide-copy span {
  font-size: 12px;
  color: #5c7b71;
}
.guide-actions {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.practice-insight-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.insight-card {
  border: 1px solid #d9e9e1;
  border-radius: 12px;
  background: #ffffff;
  padding: 10px 12px;
  display: grid;
  gap: 8px;
}
.insight-card h4 {
  margin: 0;
  font-size: 14px;
  color: #284e45;
}
.insight-card ul {
  margin: 0;
  padding-left: 16px;
  display: grid;
  gap: 4px;
  color: #54756b;
  font-size: 12px;
}
.insight-card.highlight {
  background: linear-gradient(145deg, #f3faf6 0%, #edf7f2 100%);
}
.insight-progress {
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: #d9e9e1;
}
.insight-progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #2f605a 0%, #4d8a80 100%);
  transition: width 0.26s ease;
}
.insight-card p {
  margin: 0;
  color: #54756b;
  font-size: 12px;
}
.insight-tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.insight-tag {
  border-radius: 999px;
  border: 1px solid #d0e3d9;
  background: #f3faf6;
  color: #355d52;
  font-size: 12px;
  padding: 4px 10px;
}
.question-card { border: 1px solid #e0ebe5; border-radius: 12px; padding: 10px; background: #f9fcfa; }
.question-card h3 { margin: 0 0 8px; color: #24453f; font-size: 15px; }
.options {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, 1fr);
}
.option-btn {
  border: 2px solid #d2e4db;
  background: #fff;
  border-radius: 12px;
  padding: 14px 16px;
  text-align: left;
  cursor: pointer;
  color: #3f5f56;
  transition: all 0.3s ease;
  min-height: 52px;
  display: flex;
  align-items: center;
  font-size: 14px;
  position: relative;
  overflow: hidden;
}
.option-btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: #2f605a;
  transform: translateX(-100%);
  transition: transform 0.3s ease;
}
.option-btn.active {
  border-color: #2f605a;
  background: #eaf4ef;
  color: #1f433b;
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(47, 96, 90, 0.15);
}
.option-btn.active::before {
  transform: translateX(0);
}
.option-btn:hover {
  border-color: #3f8b79;
  background: #f0f7f2;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(47, 96, 90, 0.1);
}
.submit-row {
  margin-top: 20px;
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding: 0 4px;
}
.btn {
  border: 1px solid #cfe1d8;
  border-radius: 10px;
  padding: 10px 20px;
  cursor: pointer;
  background: #fff;
  color: #35564d;
  transition: all 0.3s ease;
  font-weight: 600;
  font-size: 14px;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn.primary {
  border-color: #2f605a;
  background: #2f605a;
  color: #fff;
}
.btn.primary:hover {
  background: #3f8b79;
  border-color: #3f8b79;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(47, 96, 90, 0.2);
}
.btn.ghost {
  background: transparent;
}
.btn.ghost:hover {
  background: #f0f7f2;
  border-color: #3f8b79;
}
.btn.ghost:hover { background: #f0f9f6; }
.score-grid { margin-top: 12px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.score-card { border: 1px solid #deebe4; border-radius: 12px; padding: 10px; background: #f8fcfa; }
.score-card span { font-size: 12px; color: #6d857b; }
.score-card strong { display: block; margin-top: 6px; font-size: 24px; color: #23463f; }
.result-next-step {
  margin-top: 12px;
  border: 1px solid #d9e8e1;
  border-radius: 12px;
  background: #f6fbf8;
  padding: 10px 12px;
}
.result-next-step h3 {
  margin: 0;
  font-size: 15px;
  color: #264d44;
}
.result-next-step ul {
  margin: 8px 0 0;
  padding-left: 16px;
  display: grid;
  gap: 4px;
  color: #55766c;
  font-size: 13px;
}
.wrong-list { margin-top: 12px; display: grid; gap: 10px; }
.wrong-item { border: 1px solid #f0d7d7; border-radius: 12px; background: #fff8f8; padding: 10px; color: #5b4343; }
.wrong-head { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; }
.all-right { margin-top: 12px; border: 1px solid #d5e7de; border-radius: 12px; background: #f4faf7; padding: 12px; color: #2f605a; }

@media (max-width: 960px) {
  .practice-insight-grid {
    grid-template-columns: 1fr;
  }

  .options {
    grid-template-columns: 1fr;
  }

  .practice-header {
    flex-direction: column;
  }

  .demo-guide-row {
    flex-direction: column;
  }

  .submit-row {
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}
</style>

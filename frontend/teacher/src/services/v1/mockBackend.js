const MOCK_STORAGE_KEY = 'fuww_teacher_demo_backend_v1'
const ONE_DAY_MS = 24 * 60 * 60 * 1000

let mockStoreCache = null

function deepClone(value) {
  return JSON.parse(JSON.stringify(value))
}

function nowIso() {
  return new Date().toISOString()
}

function isoDaysAgo(days) {
  return new Date(Date.now() - days * ONE_DAY_MS).toISOString()
}

function uid(prefix = 'id') {
  const seed = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
  return `${prefix}_${seed}`
}

function cleanText(value) {
  return String(value || '').trim()
}

function safeNumber(value, fallback = 0) {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function splitPath(path) {
  const [pathname, queryString = ''] = String(path || '').split('?')
  const searchParams = new URLSearchParams(queryString)
  return { pathname, searchParams }
}

function parseJsonBody(options = {}) {
  if (!options || !options.body) return {}
  if (typeof options.body === 'string') {
    try {
      return JSON.parse(options.body)
    } catch {
      return {}
    }
  }
  if (typeof options.body === 'object') {
    return options.body
  }
  return {}
}

function buildPagination(items, params = {}) {
  const page = Math.max(1, safeNumber(params.page, 1))
  const pageSize = Math.max(1, safeNumber(params.pageSize, 20))
  const total = items.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const start = (page - 1) * pageSize
  const pagedItems = items.slice(start, start + pageSize)
  return {
    items: pagedItems,
    pagination: { page, pageSize, total, totalPages }
  }
}

function ensureMockStore() {
  if (mockStoreCache) return mockStoreCache

  if (typeof window !== 'undefined') {
    try {
      const raw = window.localStorage.getItem(MOCK_STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed === 'object') {
          mockStoreCache = parsed
          return mockStoreCache
        }
      }
    } catch {
      // noop
    }
  }

  mockStoreCache = buildDefaultStore()
  persistMockStore()
  return mockStoreCache
}

function persistMockStore() {
  if (typeof window === 'undefined' || !mockStoreCache) return
  try {
    window.localStorage.setItem(MOCK_STORAGE_KEY, JSON.stringify(mockStoreCache))
  } catch {
    // noop
  }
}

function createDefaultNodes(courseTitle, page) {
  return [
    {
      id: uid('node'),
      nodeId: `p${page}_n1`,
      title: `节点1：${courseTitle}导入`,
      summary: '概念引入与学习目标说明',
      scriptText: `同学们好，今天我们进入第${page}页内容，先快速回顾学习目标。`,
      reteachScript: '',
      transitionText: '',
      estimatedDuration: 28,
      sortOrder: 1
    },
    {
      id: uid('node'),
      nodeId: `p${page}_n2`,
      title: `节点2：核心知识点`,
      summary: '通过示例讲解核心知识点',
      scriptText: `接下来讲解第${page}页的核心知识点，并配合一个贴近考试场景的示例。`,
      reteachScript: '',
      transitionText: '',
      estimatedDuration: 36,
      sortOrder: 2
    },
    {
      id: uid('node'),
      nodeId: `p${page}_n3`,
      title: `节点3：练习与总结`,
      summary: '做题演练并总结易错点',
      scriptText: `最后通过两道快问快答巩固第${page}页内容，并总结常见易错点。`,
      reteachScript: '',
      transitionText: '',
      estimatedDuration: 30,
      sortOrder: 3
    }
  ]
}

function scriptFromNodes(courseTitle, page, nodes) {
  const lines = [
    `${courseTitle} · 第${page}页讲稿`,
    ''
  ]
  nodes.forEach((node, idx) => {
    lines.push(`【${idx + 1}】${node.title}`)
    lines.push(node.scriptText || node.summary || '请围绕该节点进行讲解。')
    lines.push('')
  })
  return lines.join('\n').trim()
}

function createCourseScripts(courseTitle, totalPages) {
  const scripts = {}
  for (let page = 1; page <= totalPages; page += 1) {
    const nodes = createDefaultNodes(courseTitle, page)
    scripts[String(page)] = {
      content: scriptFromNodes(courseTitle, page, nodes),
      nodes,
      updatedAt: nowIso()
    }
  }
  return scripts
}

function createQuestionsForCourse(courseId, scriptsByPage, studentIds) {
  const result = []
  Object.entries(scriptsByPage).forEach(([pageKey, scriptData]) => {
    const page = Number(pageKey)
    const nodes = Array.isArray(scriptData?.nodes) ? scriptData.nodes : []
    nodes.forEach((node, idx) => {
      const extra = (page + idx * 2) % 3
      const count = 1 + extra
      for (let k = 0; k < count; k += 1) {
        result.push({
          id: uid('q'),
          user_id: studentIds[(page + idx + k) % studentIds.length] || 'student-001',
          page_index: page,
          nodeId: node.nodeId,
          nodeTitle: node.title,
          question:
            k === 0
              ? `关于“${node.title}”，如果换一种题型应该如何判断解题入口？`
              : `【第${page}页·追问${k}】“${node.title}”与上一页结论冲突时先检查哪一步？`,
          answer: `建议先定位题干关键词，再回到“${node.title}”对应的方法步骤进行判断。`,
          created_at: isoDaysAgo((page + idx + k) % 8)
        })
      }
    })
  })
  return result.map((item) => ({ ...item, courseId }))
}

function buildDefaultStore() {
  const users = [
    {
      userId: 'user_teacher_001',
      platformId: 'demo-platform',
      externalId: 'teacher-001',
      username: 'jiaoshi',
      displayName: '联调教师A',
      role: 'teacher',
      status: 'active',
      orgCode: 'SCH-01',
      schoolName: '示例中学',
      major: '信息技术',
      grade: '教师',
      classExternalId: '',
      className: '',
      email: 'teacher001@example.com',
      phone: '13800000001',
      updatedAt: isoDaysAgo(1)
    },
    {
      userId: 'user_assistant_001',
      platformId: 'demo-platform',
      externalId: 'assistant-001',
      username: 'assistant01',
      displayName: '助教小林',
      role: 'assistant',
      status: 'active',
      orgCode: 'SCH-01',
      schoolName: '示例中学',
      major: '教学支持',
      grade: '教师',
      classExternalId: '',
      className: '',
      email: 'assistant001@example.com',
      phone: '13800000002',
      updatedAt: isoDaysAgo(2)
    },
    {
      userId: 'user_student_001',
      platformId: 'demo-platform',
      externalId: 'student-001',
      username: 'xuesheng',
      displayName: '学生张同学',
      role: 'student',
      status: 'active',
      orgCode: 'SCH-01',
      schoolName: '示例中学',
      major: '理科',
      grade: '高二',
      classExternalId: 'class-001',
      className: '高二(1)班',
      email: 'student001@example.com',
      phone: '13800000003',
      updatedAt: isoDaysAgo(1)
    },
    {
      userId: 'user_student_002',
      platformId: 'demo-platform',
      externalId: 'student-002',
      username: 'student02',
      displayName: '学生李同学',
      role: 'student',
      status: 'active',
      orgCode: 'SCH-01',
      schoolName: '示例中学',
      major: '理科',
      grade: '高二',
      classExternalId: 'class-001',
      className: '高二(1)班',
      email: 'student002@example.com',
      phone: '13800000004',
      updatedAt: isoDaysAgo(3)
    }
  ]

  const courses = [
    {
      courseId: 'course_demo_001',
      platformId: 'demo-platform',
      externalId: 'course-001',
      code: 'CS-ALGO-01',
      title: '算法基础与排序策略',
      description: '用于课堂演示的算法课程',
      teacherId: 'user_teacher_001',
      orgCode: 'SCH-01',
      schoolName: '示例中学',
      semester: '2026-Spring',
      credit: 2,
      period: 32,
      status: 'active',
      updatedAt: isoDaysAgo(1)
    },
    {
      courseId: 'course_demo_002',
      platformId: 'demo-platform',
      externalId: 'course-002',
      code: 'MATH-ANL-01',
      title: '函数与导数进阶',
      description: '用于课堂演示的数学课程',
      teacherId: 'user_teacher_001',
      orgCode: 'SCH-01',
      schoolName: '示例中学',
      semester: '2026-Spring',
      credit: 3,
      period: 48,
      status: 'active',
      updatedAt: isoDaysAgo(4)
    }
  ]

  const classes = [
    {
      classId: 'class_demo_001',
      platformId: 'demo-platform',
      externalId: 'class-001',
      teachingCourseId: 'course_demo_001',
      courseId: 'course_demo_001',
      teacherId: 'user_teacher_001',
      className: '高二(1)班',
      classCode: 'G2-1',
      semester: '2026-Spring',
      grade: '高二',
      major: '理科',
      capacity: 50,
      status: 'active',
      updatedAt: isoDaysAgo(1)
    },
    {
      classId: 'class_demo_002',
      platformId: 'demo-platform',
      externalId: 'class-002',
      teachingCourseId: 'course_demo_002',
      courseId: 'course_demo_002',
      teacherId: 'user_teacher_001',
      className: '高二(2)班',
      classCode: 'G2-2',
      semester: '2026-Spring',
      grade: '高二',
      major: '理科',
      capacity: 52,
      status: 'active',
      updatedAt: isoDaysAgo(2)
    }
  ]

  const enrollments = [
    {
      enrollmentId: 'enroll_demo_001',
      platformId: 'demo-platform',
      externalId: 'enrollment-001',
      teachingCourseId: 'course_demo_001',
      courseId: 'course_demo_001',
      courseClassId: 'class_demo_001',
      classId: 'class_demo_001',
      userId: 'user_student_001',
      role: 'student',
      status: 'active',
      enrolledAt: isoDaysAgo(8),
      updatedAt: isoDaysAgo(1)
    },
    {
      enrollmentId: 'enroll_demo_002',
      platformId: 'demo-platform',
      externalId: 'enrollment-002',
      teachingCourseId: 'course_demo_001',
      courseId: 'course_demo_001',
      courseClassId: 'class_demo_001',
      classId: 'class_demo_001',
      userId: 'user_student_002',
      role: 'student',
      status: 'active',
      enrolledAt: isoDaysAgo(7),
      updatedAt: isoDaysAgo(2)
    },
    {
      enrollmentId: 'enroll_demo_003',
      platformId: 'demo-platform',
      externalId: 'enrollment-003',
      teachingCourseId: 'course_demo_001',
      courseId: 'course_demo_001',
      courseClassId: 'class_demo_001',
      classId: 'class_demo_001',
      userId: 'user_teacher_001',
      role: 'teacher',
      status: 'active',
      enrolledAt: isoDaysAgo(10),
      updatedAt: isoDaysAgo(2)
    }
  ]

  const coursewares = [
    {
      id: 'cw_demo_001',
      title: '测试样例',
      total_page: 6,
      knowledge_point_count: 18,
      file_type: 'pdf',
      is_published: true,
      teaching_course_id: 'course_demo_001',
      teaching_course_title: '算法基础与排序策略',
      course_class_id: 'class_demo_001',
      course_class_name: '高二(1)班',
      created_at: isoDaysAgo(5),
      updated_at: isoDaysAgo(1)
    },
    {
      id: 'cw_demo_002',
      title: '快速排序强化训练',
      total_page: 4,
      knowledge_point_count: 12,
      file_type: 'pptx',
      is_published: false,
      teaching_course_id: '',
      teaching_course_title: '',
      course_class_id: '',
      course_class_name: '',
      created_at: isoDaysAgo(3),
      updated_at: isoDaysAgo(2)
    }
  ]

  const scriptsByCourse = {
    cw_demo_001: createCourseScripts('测试样例', 6),
    cw_demo_002: createCourseScripts('快速排序强化训练', 4)
  }

  const studentIds = users.filter((item) => item.role === 'student').map((item) => item.userId)
  const questionsByCourse = {
    cw_demo_001: createQuestionsForCourse('cw_demo_001', scriptsByCourse.cw_demo_001, studentIds),
    cw_demo_002: createQuestionsForCourse('cw_demo_002', scriptsByCourse.cw_demo_002, studentIds)
  }

  const iterationByCourse = {
    cw_demo_001: {
      basicNodeTree: [
        { id: 'iter_n1', title: '快速排序的核心思想', type: 'concept' },
        { id: 'iter_n2', title: '分区过程与边界处理', type: 'concept' }
      ],
      pendingNodes: [
        { id: 'iter_p1', title: '递归终止条件复盘', type: 'prerequisite', reason: '学生在边界判断上错误较多' },
        { id: 'iter_p2', title: '基准值策略对复杂度影响', type: 're_teach', reason: '高频追问集中在此节点' }
      ],
      pendingCases: [],
      updatedAt: nowIso()
    }
  }

  return {
    teacher: {
      coursewares,
      scriptsByCourse,
      questionsByCourse,
      iterationByCourse
    },
    platform: {
      users,
      courses,
      classes,
      enrollments
    }
  }
}

function ok(data) {
  return { code: 200, message: 'ok (mock)', data }
}

function listCoursewares(store) {
  return deepClone(store.teacher.coursewares).sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))
}

function ensureScriptPage(store, courseId, page) {
  const course = store.teacher.coursewares.find((item) => item.id === courseId)
  if (!course) return null
  if (!store.teacher.scriptsByCourse[courseId]) {
    store.teacher.scriptsByCourse[courseId] = createCourseScripts(course.title, Number(course.total_page || 1))
  }
  if (!store.teacher.scriptsByCourse[courseId][String(page)]) {
    const nodes = createDefaultNodes(course.title, page)
    store.teacher.scriptsByCourse[courseId][String(page)] = {
      content: scriptFromNodes(course.title, page, nodes),
      nodes,
      updatedAt: nowIso()
    }
  }
  return store.teacher.scriptsByCourse[courseId][String(page)]
}

function recalcKnowledgePointCount(store, courseId) {
  const course = store.teacher.coursewares.find((item) => item.id === courseId)
  if (!course) return
  const scripts = store.teacher.scriptsByCourse[courseId] || {}
  const count = Object.values(scripts).reduce((sum, scriptData) => {
    const nodes = Array.isArray(scriptData?.nodes) ? scriptData.nodes : []
    return sum + nodes.length
  }, 0)
  course.knowledge_point_count = count
  course.updated_at = nowIso()
}

function buildGeneratedScript(courseTitle, page, nodes) {
  const parts = [
    `${courseTitle} · 第${page}页 AI 预制讲稿`,
    '',
    '开场：先用1分钟回顾上页关键点，并抛出本页目标。',
    ''
  ]
  nodes.forEach((node, idx) => {
    parts.push(`节点${idx + 1}：${node.title}`)
    parts.push(`讲解提示：${node.summary || node.scriptText || '围绕该节点展开讲解，并结合一道课堂练习。'}`)
    parts.push('')
  })
  parts.push('结尾：总结本页三条关键结论，并布置课后微练习。')
  return parts.join('\n').trim()
}

function aggregateStats(store, courseId) {
  const scripts = store.teacher.scriptsByCourse[courseId] || {}
  const questions = Array.isArray(store.teacher.questionsByCourse[courseId]) ? store.teacher.questionsByCourse[courseId] : []
  const nodes = []

  Object.entries(scripts).forEach(([pageKey, scriptData]) => {
    const page = Number(pageKey)
    const list = Array.isArray(scriptData?.nodes) ? scriptData.nodes : []
    list.forEach((node) => {
      nodes.push({ ...node, page })
    })
  })

  const nodeStats = nodes.map((node, idx) => {
    const qs = questions.filter((item) => item.nodeId === node.nodeId)
    const questionCount = qs.length
    const dialogueCount = Math.max(questionCount, Math.round(questionCount * 1.8))
    const stayTime = 35 + questionCount * 12 + (idx % 4) * 9
    const errorRate = Math.min(0.92, 0.16 + questionCount * 0.08)
    const masteryScore = Math.max(18, 92 - questionCount * 12 - (idx % 5) * 4)
    return {
      nodeId: node.nodeId,
      title: node.title,
      page: node.page,
      questionCount,
      dialogueCount,
      stayTime,
      errorRate,
      masteryScore,
      needReTeach: errorRate >= 0.45
    }
  })

  const uncoveredNodeIds = nodeStats.filter((item) => item.questionCount === 0).map((item) => item.nodeId)
  const nodeHeatmap = nodeStats.map((item) => ({
    nodeId: item.nodeId,
    title: item.title,
    heat: Math.round(item.questionCount * 2.5 + item.dialogueCount * 1.3 + (item.needReTeach ? 5 : 1))
  }))

  const byPage = {}
  nodeStats.forEach((item) => {
    if (!byPage[item.page]) {
      byPage[item.page] = { page: item.page, count: 0, mastery: 0, question: 0, stay: 0, reteach: 0 }
    }
    byPage[item.page].count += 1
    byPage[item.page].mastery += item.masteryScore
    byPage[item.page].question += item.questionCount
    byPage[item.page].stay += item.stayTime
    byPage[item.page].reteach += item.needReTeach ? 1 : 0
  })

  const masteryRadarPages = Object.values(byPage).sort((a, b) => a.page - b.page)
  const masteryIndicators = masteryRadarPages.map((item) => ({ name: `第${item.page}页`, max: 100 }))
  const jitter = [4, -11, 7, -6, 9, -3, 5]
  const masteryValues = masteryRadarPages.map((item, idx) => {
    const base = Math.round(item.mastery / Math.max(1, item.count))
    const j = jitter[idx % jitter.length]
    return Math.min(98, Math.max(22, base + j))
  })
  const avgMastery = masteryValues.length
    ? Math.round(masteryValues.reduce((sum, value) => sum + value, 0) / masteryValues.length)
    : 0

  const trend = Array.from({ length: 7 }).map((_, idx) => {
    const day = new Date(Date.now() - (6 - idx) * ONE_DAY_MS)
    const weekday = day.getDay()
    const weekendDip = weekday === 0 || weekday === 6 ? -6 : 0
    const baseQuestion = Math.max(4, Math.round(questions.length / 7 + idx * 2 + (idx % 3) * 3))
    const questionCount = baseQuestion + (weekendDip === 0 ? 3 : -1)
    const activeUsers = 19 + idx * 2 + (idx % 4) * 3 + weekendDip + ((idx + 2) % 5)
    const reteachCount = Math.max(0, Math.round(nodeStats.filter((item) => item.needReTeach).length / 4) + (idx % 3) + (idx === 5 ? 1 : 0))
    const errorRate = Math.min(0.52, 0.15 + reteachCount * 0.042 + (idx % 2) * 0.02)
    return {
      day: `${day.getMonth() + 1}/${day.getDate()}`,
      activeUsers,
      questionCount,
      reteachCount,
      errorRate
    }
  })

  const reteachNodes = nodeStats
    .filter((item) => item.needReTeach)
    .sort((a, b) => b.errorRate - a.errorRate)
    .slice(0, 6)

  const prerequisiteGaps = nodeStats
    .filter((item, idx) => item.questionCount >= 2 && idx > 0)
    .slice(0, 6)
    .map((item, idx) => ({
      nodeId: item.nodeId,
      title: item.title,
      suggestedPrereqId: nodeStats[Math.max(0, idx)].nodeId,
      suggestedPrereq: nodeStats[Math.max(0, idx)].title
    }))

  const summary = reteachNodes.length
    ? `建议优先重讲 ${reteachNodes[0].title}，并在讲解前补充 ${prerequisiteGaps[0]?.suggestedPrereq || '基础概念'}。`
    : '当前整体掌握较稳定，建议维持节奏并增加迁移练习。'

  const pageStats = Object.values(byPage).sort((a, b) => a.page - b.page).map((item) => ({
    page: item.page,
    questionCount: item.question,
    stayTime: Math.round(item.stay / Math.max(1, item.count)),
    cardIndex: Number((item.question * 0.7 + item.reteach * 2.2).toFixed(2)),
    reteachCount: item.reteach
  }))

  const activeSessions = Math.max(3, new Set(questions.map((item) => item.user_id)).size)
  const avgTurnsPerSession = questions.length ? Number((questions.length / activeSessions).toFixed(1)) : 0

  return {
    totalQuestions: questions.length,
    activeSessions,
    avgTurnsPerSession,
    nodeStats,
    mappingCoverage: {
      coveredNodeCount: nodeStats.length - uncoveredNodeIds.length,
      uncoveredNodeCount: uncoveredNodeIds.length,
      uncoveredNodeIds
    },
    nodeHeatmap,
    masteryRadar: {
      indicators: masteryIndicators,
      values: masteryValues,
      avgMastery
    },
    classTrend: trend,
    learningInsights: {
      reteachNodes,
      prerequisiteGaps,
      summary
    },
    pageStats
  }
}

function getCoursewareById(store, id) {
  return store.teacher.coursewares.find((item) => item.id === id)
}

function handleTeacherCoursewareRequest(store, pathname, searchParams, method, options) {
  const segments = pathname.split('/').filter(Boolean)

  if (segments.length === 4 && method === 'GET') {
    return ok(listCoursewares(store))
  }

  if (segments.length === 5 && segments[4] === 'upload' && method === 'POST') {
    let title = '演示课件'
    let fileType = 'pdf'
    if (typeof FormData !== 'undefined' && options?.body instanceof FormData) {
      title = cleanText(options.body.get('title')) || cleanText(options.body.get('file')?.name) || title
      const fileName = cleanText(options.body.get('file')?.name)
      if (fileName.includes('.ppt')) fileType = 'pptx'
      if (fileName.includes('.pdf')) fileType = 'pdf'
    }

    const id = uid('cw')
    const totalPages = 6
    const course = {
      id,
      title,
      total_page: totalPages,
      knowledge_point_count: totalPages * 3,
      file_type: fileType,
      is_published: false,
      teaching_course_id: '',
      teaching_course_title: '',
      course_class_id: '',
      course_class_name: '',
      created_at: nowIso(),
      updated_at: nowIso()
    }

    store.teacher.coursewares.unshift(course)
    store.teacher.scriptsByCourse[id] = createCourseScripts(title, totalPages)
    const studentIds = store.platform.users.filter((item) => item.role === 'student').map((item) => item.userId)
    store.teacher.questionsByCourse[id] = createQuestionsForCourse(id, store.teacher.scriptsByCourse[id], studentIds)
    persistMockStore()
    return ok({ courseId: id, title })
  }

  const courseId = decodeURIComponent(segments[4] || '')
  const course = getCoursewareById(store, courseId)
  if (!course) {
    return ok({})
  }

  if (segments.length === 5 && method === 'DELETE') {
    store.teacher.coursewares = store.teacher.coursewares.filter((item) => item.id !== courseId)
    delete store.teacher.scriptsByCourse[courseId]
    delete store.teacher.questionsByCourse[courseId]
    persistMockStore()
    return ok({ removed: true })
  }

  if (segments.length === 6 && segments[5] === 'publish' && method === 'POST') {
    const body = parseJsonBody(options)
    course.is_published = true
    course.teaching_course_id = cleanText(body.teachingCourseId)
    course.teaching_course_title = cleanText(body.teachingCourseTitle)
    course.course_class_id = cleanText(body.courseClassId)
    course.course_class_name = cleanText(body.courseClassName)
    course.updated_at = nowIso()
    persistMockStore()
    return ok({ published: true })
  }

  if (segments.length === 7 && segments[5] === 'scripts' && segments[6] === 'ai-generate' && method === 'POST') {
    const body = parseJsonBody(options)
    const page = Math.max(1, safeNumber(body.pageNum, 1))
    const scriptData = ensureScriptPage(store, courseId, page)
    const nodes = Array.isArray(scriptData?.nodes) ? scriptData.nodes : []
    const content = buildGeneratedScript(course.title, page, nodes)
    scriptData.content = content
    scriptData.updatedAt = nowIso()
    persistMockStore()
    return ok({ content })
  }

  if (segments.length === 7 && segments[5] === 'scripts') {
    const page = Math.max(1, safeNumber(segments[6], 1))
    const scriptData = ensureScriptPage(store, courseId, page)
    if (method === 'GET') {
      return ok({ content: scriptData.content, nodes: deepClone(scriptData.nodes) })
    }
    if (method === 'PUT') {
      const body = parseJsonBody(options)
      scriptData.content = cleanText(body.content) || scriptData.content
      scriptData.updatedAt = nowIso()
      persistMockStore()
      return ok({ saved: true })
    }
  }

  if (segments.length === 8 && segments[5] === 'pages' && segments[7] === 'nodes') {
    const page = Math.max(1, safeNumber(segments[6], 1))
    const scriptData = ensureScriptPage(store, courseId, page)
    if (method === 'GET') {
      return ok({ nodes: deepClone(scriptData.nodes) })
    }
    if (method === 'PUT') {
      const body = parseJsonBody(options)
      const incoming = Array.isArray(body.nodes) ? body.nodes : []
      scriptData.nodes = incoming.map((node, idx) => ({
        ...node,
        nodeId: cleanText(node.nodeId) || `p${page}_n${idx + 1}`,
        title: cleanText(node.title) || `节点${idx + 1}`,
        scriptText: cleanText(node.scriptText || node.text || node.summary),
        summary: cleanText(node.summary || node.scriptText || node.text),
        estimatedDuration: Math.max(12, safeNumber(node.estimatedDuration, 28)),
        sortOrder: idx + 1
      }))
      if (!scriptData.content || !scriptData.content.trim()) {
        scriptData.content = scriptFromNodes(course.title, page, scriptData.nodes)
      }
      scriptData.updatedAt = nowIso()
      recalcKnowledgePointCount(store, courseId)
      persistMockStore()
      return ok({ saved: true })
    }
  }

  if (segments.length === 6 && segments[5] === 'stats' && method === 'GET') {
    const stats = aggregateStats(store, courseId)
    return ok(stats)
  }

  if (segments.length === 6 && segments[5] === 'card-data' && method === 'GET') {
    const stats = aggregateStats(store, courseId)
    return ok({ pageStats: stats.pageStats })
  }

  if (segments.length === 6 && segments[5] === 'questions' && method === 'GET') {
    const all = Array.isArray(store.teacher.questionsByCourse[courseId]) ? store.teacher.questionsByCourse[courseId] : []
    const page = Math.max(1, safeNumber(searchParams.get('page'), 1))
    const pageSize = Math.max(1, safeNumber(searchParams.get('pageSize'), 100))
    const start = (page - 1) * pageSize
    const list = all
      .slice()
      .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
      .slice(start, start + pageSize)
    return ok({
      list,
      pagination: {
        page,
        pageSize,
        total: all.length,
        totalPages: Math.max(1, Math.ceil(all.length / pageSize))
      }
    })
  }

  return null
}

function buildRecommendList(keyword, type) {
  const normalizedKeyword = cleanText(keyword) || '重点知识点'
  return Array.from({ length: 8 }).map((_, idx) => {
    const index = idx + 1
    const isQuestion = type === '题库'
    return {
      id: uid('reco'),
      title: isQuestion
        ? `${normalizedKeyword} 题库演练 ${index}`
        : `${normalizedKeyword} 精讲视频 ${index}`,
      type: isQuestion ? '题库' : '网课',
      source: isQuestion ? '校内题库' : 'Bilibili',
      duration: isQuestion ? `${15 + idx * 5}题` : `${12 + idx * 3}分钟`,
      fit_reason: `与“${normalizedKeyword}”匹配度高，适合课堂演示与课后巩固。`,
      hot_score: 85 - idx * 3,
      link: isQuestion
        ? `https://example.com/question-bank/${encodeURIComponent(normalizedKeyword)}/${index}`
        : `https://www.bilibili.com/video/BV1${String(index).padStart(2, '0')}DEMO`
    }
  })
}

function handleRecommendRequest(options) {
  const body = parseJsonBody(options)
  const type = cleanText(body.type) || '网课'
  const keyword = cleanText(body.keyword)
  const list = buildRecommendList(keyword, type)
  return ok({
    recommended_resources: list,
    total: list.length,
    hasMore: false
  })
}

function handleIterationRequest(store, pathname, method, options) {
  if (pathname === '/api/v1/teacher/iteration/script-generate' && method === 'POST') {
    const body = parseJsonBody(options)
    const nodeOrder = Array.isArray(body.nodeOrder) ? body.nodeOrder : []
    const lines = ['# 下节课讲稿（前端模拟）', '']
    if (nodeOrder.length === 0) {
      lines.push('## 1. 导入')
      lines.push('先回顾上节课，再引入新目标。')
    } else {
      nodeOrder.forEach((nodeId, idx) => {
        lines.push(`## ${idx + 1}. 节点 ${nodeId}`)
        lines.push('教学建议：先讲思路，再做例题，最后留1分钟总结。')
        lines.push('')
      })
    }
    return ok({ content: lines.join('\n').trim() })
  }

  if (pathname.startsWith('/api/v1/teacher/iteration-overview/')) {
    const courseId = decodeURIComponent(pathname.split('/').pop() || '')
    if (!store.teacher.iterationByCourse[courseId]) {
      store.teacher.iterationByCourse[courseId] = {
        basicNodeTree: [
          { id: uid('iter'), title: '基础节点A', type: 'concept' },
          { id: uid('iter'), title: '基础节点B', type: 'concept' }
        ],
        pendingNodes: [
          { id: uid('iterp'), title: '补前置知识：基本概念', type: 'prerequisite', reason: '高频问题集中在概念理解' }
        ],
        pendingCases: [],
        updatedAt: nowIso()
      }
      persistMockStore()
    }

    if (method === 'GET') {
      return ok(deepClone(store.teacher.iterationByCourse[courseId]))
    }

    if (method === 'POST') {
      const body = parseJsonBody(options)
      store.teacher.iterationByCourse[courseId] = {
        ...store.teacher.iterationByCourse[courseId],
        nodeTree: Array.isArray(body.nodeTree) ? body.nodeTree : [],
        bindingMap: body.bindingMap && typeof body.bindingMap === 'object' ? body.bindingMap : {},
        updatedAt: nowIso()
      }
      persistMockStore()
      return ok({ ok: true, updatedAt: nowIso() })
    }
  }

  return null
}

function sortByUpdatedDesc(list) {
  return list.slice().sort((a, b) => String(b.updatedAt || b.updated_at || '').localeCompare(String(a.updatedAt || a.updated_at || '')))
}

function toPlainParams(searchParams) {
  const params = {}
  searchParams.forEach((value, key) => {
    params[key] = value
  })
  return params
}

function includeKeyword(item, keyword, fields) {
  const normalized = cleanText(keyword).toLowerCase()
  if (!normalized) return true
  return fields.some((field) => String(item[field] || '').toLowerCase().includes(normalized))
}

function platformOverview(store) {
  const users = sortByUpdatedDesc(store.platform.users)
  const courses = sortByUpdatedDesc(store.platform.courses)
  const classes = sortByUpdatedDesc(store.platform.classes)
  const enrollments = sortByUpdatedDesc(store.platform.enrollments)

  return {
    counts: {
      users: users.length,
      courses: courses.length,
      classes: classes.length,
      enrollments: enrollments.length
    },
    recentUsers: users.slice(0, 6),
    recentCourses: courses.slice(0, 6),
    recentClasses: classes.slice(0, 6),
    recentEnrollments: enrollments.slice(0, 6)
  }
}

function handlePlatformList(store, entity, params) {
  const source = sortByUpdatedDesc(store.platform[entity])
  let filtered = source

  if (entity === 'users') {
    filtered = source.filter((item) => (
      includeKeyword(item, params.keyword, ['displayName', 'externalId', 'userId', 'username'])
      && (!params.role || item.role === params.role)
      && (!params.orgCode || item.orgCode === params.orgCode)
    ))
  }

  if (entity === 'courses') {
    filtered = source.filter((item) => (
      includeKeyword(item, params.keyword, ['title', 'externalId', 'code'])
      && (!params.status || item.status === params.status)
      && (!params.orgCode || item.orgCode === params.orgCode)
      && (!params.teacherId || item.teacherId === params.teacherId)
    ))
  }

  if (entity === 'classes') {
    filtered = source.filter((item) => (
      includeKeyword(item, params.keyword, ['className', 'externalId', 'classCode'])
      && (!params.status || item.status === params.status)
      && (!params.teacherId || item.teacherId === params.teacherId)
      && (!params.courseId || item.teachingCourseId === params.courseId || item.courseId === params.courseId)
    ))
  }

  if (entity === 'enrollments') {
    filtered = source.filter((item) => (
      includeKeyword(item, params.keyword, ['externalId', 'enrollmentId', 'userId'])
      && (!params.status || item.status === params.status)
      && (!params.role || item.role === params.role)
      && (!params.userId || item.userId === params.userId)
      && (!params.classId || item.courseClassId === params.classId || item.classId === params.classId)
      && (!params.courseId || item.teachingCourseId === params.courseId || item.courseId === params.courseId)
    ))
  }

  return buildPagination(filtered, params)
}

function getPlatformDetail(store, view, id) {
  if (view === 'users') {
    const user = store.platform.users.find((item) => item.userId === id)
    if (!user) return {}
    const enrollments = store.platform.enrollments.filter((item) => item.userId === id)
    const classIds = new Set(enrollments.map((item) => item.classId || item.courseClassId))
    const courseIds = new Set(enrollments.map((item) => item.courseId || item.teachingCourseId))
    const classes = store.platform.classes.filter((item) => classIds.has(item.classId))
    const courses = store.platform.courses.filter((item) => courseIds.has(item.courseId))
    return {
      profile: user,
      summary: {
        courseCount: courses.length,
        classCount: classes.length,
        enrollmentCount: enrollments.length,
        roleDistribution: user.role
      },
      courses,
      classes,
      enrollments
    }
  }

  if (view === 'courses') {
    const course = store.platform.courses.find((item) => item.courseId === id)
    if (!course) return {}
    const classes = store.platform.classes.filter((item) => item.courseId === id || item.teachingCourseId === id)
    const classSet = new Set(classes.map((item) => item.classId))
    const members = store.platform.enrollments
      .filter((item) => classSet.has(item.classId || item.courseClassId))
      .map((item) => {
        const user = store.platform.users.find((candidate) => candidate.userId === item.userId)
        return {
          ...user,
          role: item.role,
          className: store.platform.classes.find((classItem) => classItem.classId === (item.classId || item.courseClassId))?.className || ''
        }
      })
      .filter(Boolean)
    return {
      courseInfo: course,
      summary: {
        classCount: classes.length,
        memberCount: members.length,
        enrollmentCount: members.length,
        statusDistribution: course.status
      },
      teacher: store.platform.users.find((item) => item.userId === course.teacherId) || {},
      classes,
      members
    }
  }

  if (view === 'classes') {
    const classItem = store.platform.classes.find((item) => item.classId === id)
    if (!classItem) return {}
    const enrollments = store.platform.enrollments.filter((item) => (item.classId || item.courseClassId) === id)
    const members = enrollments.map((item) => {
      const user = store.platform.users.find((candidate) => candidate.userId === item.userId)
      return {
        ...user,
        role: item.role
      }
    }).filter(Boolean)
    return {
      classInfo: classItem,
      summary: {
        memberCount: members.length,
        statusDistribution: classItem.status
      },
      course: store.platform.courses.find((item) => item.courseId === classItem.courseId || item.courseId === classItem.teachingCourseId) || {},
      teacher: store.platform.users.find((item) => item.userId === classItem.teacherId) || {},
      members
    }
  }

  const enrollment = store.platform.enrollments.find((item) => item.enrollmentId === id)
  if (!enrollment) return {}
  return {
    enrollmentInfo: enrollment,
    user: store.platform.users.find((item) => item.userId === enrollment.userId) || {},
    course: store.platform.courses.find((item) => item.courseId === (enrollment.courseId || enrollment.teachingCourseId)) || {},
    class: store.platform.classes.find((item) => item.classId === (enrollment.classId || enrollment.courseClassId)) || {}
  }
}

function applyCoursePayload(payload, current = null) {
  return {
    courseId: current?.courseId || uid('course'),
    platformId: cleanText(payload.platformId) || 'demo-platform',
    externalId: cleanText(payload.externalId) || uid('external_course'),
    code: cleanText(payload.code) || 'COURSE-DEMO',
    title: cleanText(payload.title) || '未命名课程',
    description: cleanText(payload.description),
    teacherId: cleanText(payload.teacherId),
    orgCode: cleanText(payload.orgCode),
    schoolName: cleanText(payload.schoolName),
    semester: cleanText(payload.semester),
    credit: safeNumber(payload.credit, 0),
    period: safeNumber(payload.period, 0),
    status: cleanText(payload.status) || 'draft',
    updatedAt: nowIso()
  }
}

function applyClassPayload(payload, current = null) {
  const courseId = cleanText(payload.courseId)
  return {
    classId: current?.classId || uid('class'),
    platformId: cleanText(payload.platformId) || 'demo-platform',
    externalId: cleanText(payload.externalId) || uid('external_class'),
    teachingCourseId: courseId,
    courseId,
    teacherId: cleanText(payload.teacherId),
    className: cleanText(payload.className) || '未命名班级',
    classCode: cleanText(payload.classCode),
    semester: cleanText(payload.semester),
    grade: cleanText(payload.grade),
    major: cleanText(payload.major),
    capacity: safeNumber(payload.capacity, 50),
    status: cleanText(payload.status) || 'active',
    updatedAt: nowIso()
  }
}

function applyEnrollmentPayload(payload, current = null) {
  const courseId = cleanText(payload.courseId)
  const classId = cleanText(payload.classId)
  return {
    enrollmentId: current?.enrollmentId || uid('enroll'),
    platformId: cleanText(payload.platformId) || 'demo-platform',
    externalId: cleanText(payload.externalId) || uid('external_enroll'),
    teachingCourseId: courseId,
    courseId,
    courseClassId: classId,
    classId,
    userId: cleanText(payload.userId),
    role: cleanText(payload.role) || 'student',
    status: cleanText(payload.status) || 'active',
    enrolledAt: current?.enrolledAt || nowIso(),
    updatedAt: nowIso()
  }
}

function ensureUserByExternalId(store, externalId, fallbackName = '新用户', role = 'teacher') {
  const match = store.platform.users.find((item) => item.externalId === externalId || item.userId === externalId)
  if (match) return match
  const user = {
    userId: uid('user'),
    platformId: 'demo-platform',
    externalId,
    username: externalId,
    displayName: fallbackName,
    role,
    status: 'active',
    orgCode: 'SCH-01',
    schoolName: '示例学校',
    major: '',
    grade: role === 'student' ? '未知年级' : '教师',
    classExternalId: '',
    className: '',
    email: '',
    phone: '',
    updatedAt: nowIso()
  }
  store.platform.users.unshift(user)
  return user
}

function handlePlatformSyncUser(store, options) {
  const body = parseJsonBody(options)
  const userInfo = body.userInfo || {}
  const externalId = cleanText(userInfo.userId) || uid('external_user')
  const role = cleanText(userInfo.role) || 'student'
  const existing = store.platform.users.find((item) => item.externalId === externalId || item.userId === externalId)

  const payload = {
    userId: existing?.userId || uid('user'),
    platformId: cleanText(body.platformId) || 'demo-platform',
    externalId,
    username: externalId,
    displayName: cleanText(userInfo.userName) || '未命名用户',
    role,
    status: 'active',
    orgCode: cleanText(userInfo.schoolId) || 'SCH-01',
    schoolName: cleanText(userInfo.schoolName) || '示例学校',
    major: cleanText(userInfo.major),
    grade: cleanText(userInfo.grade) || (role === 'teacher' ? '教师' : ''),
    classExternalId: cleanText(userInfo.classId),
    className: cleanText(userInfo.className),
    email: cleanText(userInfo.contactInfo?.email),
    phone: cleanText(userInfo.contactInfo?.phone),
    updatedAt: nowIso()
  }

  if (existing) {
    Object.assign(existing, payload)
  } else {
    store.platform.users.unshift(payload)
  }

  const linkedCourses = []
  if (payload.classExternalId || payload.className) {
    let classItem = store.platform.classes.find((item) => item.externalId === payload.classExternalId || item.className === payload.className)
    if (!classItem) {
      const firstCourse = store.platform.courses[0]
      classItem = {
        classId: uid('class'),
        platformId: payload.platformId,
        externalId: payload.classExternalId || uid('external_class'),
        teachingCourseId: firstCourse?.courseId || '',
        courseId: firstCourse?.courseId || '',
        teacherId: firstCourse?.teacherId || '',
        className: payload.className || '默认班级',
        classCode: '',
        semester: firstCourse?.semester || '',
        grade: payload.grade || '',
        major: payload.major || '',
        capacity: 50,
        status: 'active',
        updatedAt: nowIso()
      }
      store.platform.classes.unshift(classItem)
    }

    const existsEnrollment = store.platform.enrollments.find((item) => (
      item.userId === payload.userId
      && (item.classId === classItem.classId || item.courseClassId === classItem.classId)
    ))

    if (!existsEnrollment) {
      store.platform.enrollments.unshift({
        enrollmentId: uid('enroll'),
        platformId: payload.platformId,
        externalId: uid('external_enroll'),
        teachingCourseId: classItem.teachingCourseId,
        courseId: classItem.courseId,
        courseClassId: classItem.classId,
        classId: classItem.classId,
        userId: payload.userId,
        role,
        status: 'active',
        enrolledAt: nowIso(),
        updatedAt: nowIso()
      })
    }

    linkedCourses.push({
      courseId: classItem.courseId,
      className: classItem.className,
      role,
      externalClassId: classItem.externalId
    })
  }

  return ok({
    syncStatus: 'success',
    syncTime: nowIso(),
    internalUserId: payload.userId,
    authToken: `mock-token-${payload.userId}`,
    userProfile: payload,
    linkedCourses
  })
}

function handlePlatformSyncCourse(store, options) {
  const body = parseJsonBody(options)
  const courseInfo = body.courseInfo || {}
  const externalCourseId = cleanText(courseInfo.courseId) || uid('external_course')
  const teacherInfo = Array.isArray(courseInfo.teacherInfo) ? courseInfo.teacherInfo[0] : {}
  const teacherExternalId = cleanText(teacherInfo.teacherId) || uid('external_teacher')
  const teacher = ensureUserByExternalId(store, teacherExternalId, cleanText(teacherInfo.teacherName) || '联调教师', 'teacher')

  const existingCourse = store.platform.courses.find((item) => item.externalId === externalCourseId || item.courseId === externalCourseId)
  const coursePayload = {
    courseId: existingCourse?.courseId || uid('course'),
    platformId: cleanText(body.platformId) || 'demo-platform',
    externalId: externalCourseId,
    code: cleanText(courseInfo.courseCode) || cleanText(courseInfo.courseId) || 'COURSE-DEMO',
    title: cleanText(courseInfo.courseName) || '未命名课程',
    description: cleanText(courseInfo.description),
    teacherId: teacher.userId,
    orgCode: cleanText(courseInfo.schoolId) || 'SCH-01',
    schoolName: cleanText(courseInfo.schoolName) || '示例学校',
    semester: cleanText(courseInfo.term),
    credit: safeNumber(courseInfo.credit, 2),
    period: safeNumber(courseInfo.period, 32),
    status: 'active',
    updatedAt: nowIso()
  }

  if (existingCourse) {
    Object.assign(existingCourse, coursePayload)
  } else {
    store.platform.courses.unshift(coursePayload)
  }

  const classList = Array.isArray(courseInfo.classList) ? courseInfo.classList : []
  const classes = classList.map((item) => {
    const externalClassId = cleanText(item.classId) || uid('external_class')
    const existingClass = store.platform.classes.find((candidate) => candidate.externalId === externalClassId)
    const classPayload = {
      classId: existingClass?.classId || uid('class'),
      platformId: cleanText(body.platformId) || 'demo-platform',
      externalId: externalClassId,
      teachingCourseId: coursePayload.courseId,
      courseId: coursePayload.courseId,
      teacherId: teacher.userId,
      className: cleanText(item.className) || '默认班级',
      classCode: cleanText(item.classCode),
      semester: coursePayload.semester,
      grade: '',
      major: '',
      capacity: 50,
      status: 'active',
      updatedAt: nowIso()
    }
    if (existingClass) {
      Object.assign(existingClass, classPayload)
      return existingClass
    }
    store.platform.classes.unshift(classPayload)
    return classPayload
  })

  return ok({
    syncStatus: 'success',
    syncTime: nowIso(),
    internalCourseId: coursePayload.courseId,
    teacherCount: 1,
    enrollmentCount: store.platform.enrollments.filter((item) => item.courseId === coursePayload.courseId).length,
    courseMeta: coursePayload,
    teachers: [teacher],
    classes,
    classInfo: classes[0] || {}
  })
}

function handlePlatformRequest(store, pathname, searchParams, method, options) {
  if (pathname === '/api/v1/platform/overview' && method === 'GET') {
    return ok(platformOverview(store))
  }

  if (pathname === '/api/v1/platform/syncUser' && method === 'POST') {
    const result = handlePlatformSyncUser(store, options)
    persistMockStore()
    return result
  }

  if (pathname === '/api/v1/platform/syncCourse' && method === 'POST') {
    const result = handlePlatformSyncCourse(store, options)
    persistMockStore()
    return result
  }

  const segments = pathname.split('/').filter(Boolean)
  const entity = segments[3]
  const entityId = segments[4] ? decodeURIComponent(segments[4]) : ''
  const params = toPlainParams(searchParams)

  if (!['users', 'courses', 'classes', 'enrollments'].includes(entity)) {
    return null
  }

  if (!entityId && method === 'GET') {
    return ok(handlePlatformList(store, entity, params))
  }

  if (entityId && method === 'GET') {
    return ok(getPlatformDetail(store, entity, entityId))
  }

  if (entity === 'courses' && !entityId && method === 'POST') {
    const payload = applyCoursePayload(parseJsonBody(options))
    store.platform.courses.unshift(payload)
    persistMockStore()
    return ok(payload)
  }

  if (entity === 'courses' && entityId && method === 'PUT') {
    const current = store.platform.courses.find((item) => item.courseId === entityId)
    if (!current) return ok({})
    Object.assign(current, applyCoursePayload(parseJsonBody(options), current))
    persistMockStore()
    return ok(current)
  }

  if (entity === 'courses' && entityId && method === 'DELETE') {
    store.platform.courses = store.platform.courses.filter((item) => item.courseId !== entityId)
    const classIds = store.platform.classes.filter((item) => item.courseId === entityId || item.teachingCourseId === entityId).map((item) => item.classId)
    store.platform.classes = store.platform.classes.filter((item) => item.courseId !== entityId && item.teachingCourseId !== entityId)
    store.platform.enrollments = store.platform.enrollments.filter((item) => item.courseId !== entityId && item.teachingCourseId !== entityId && !classIds.includes(item.classId || item.courseClassId))
    persistMockStore()
    return ok({ removed: true })
  }

  if (entity === 'classes' && !entityId && method === 'POST') {
    const payload = applyClassPayload(parseJsonBody(options))
    store.platform.classes.unshift(payload)
    persistMockStore()
    return ok(payload)
  }

  if (entity === 'classes' && entityId && method === 'PUT') {
    const current = store.platform.classes.find((item) => item.classId === entityId)
    if (!current) return ok({})
    Object.assign(current, applyClassPayload(parseJsonBody(options), current))
    persistMockStore()
    return ok(current)
  }

  if (entity === 'classes' && entityId && method === 'DELETE') {
    store.platform.classes = store.platform.classes.filter((item) => item.classId !== entityId)
    store.platform.enrollments = store.platform.enrollments.filter((item) => (item.classId || item.courseClassId) !== entityId)
    persistMockStore()
    return ok({ removed: true })
  }

  if (entity === 'enrollments' && !entityId && method === 'POST') {
    const payload = applyEnrollmentPayload(parseJsonBody(options))
    store.platform.enrollments.unshift(payload)
    persistMockStore()
    return ok(payload)
  }

  if (entity === 'enrollments' && entityId && method === 'PUT') {
    const current = store.platform.enrollments.find((item) => item.enrollmentId === entityId)
    if (!current) return ok({})
    Object.assign(current, applyEnrollmentPayload(parseJsonBody(options), current))
    persistMockStore()
    return ok(current)
  }

  if (entity === 'enrollments' && entityId && method === 'DELETE') {
    store.platform.enrollments = store.platform.enrollments.filter((item) => item.enrollmentId !== entityId)
    persistMockStore()
    return ok({ removed: true })
  }

  return null
}

export function handleMockRequest(path, options = {}, originalError = null) {
  const { pathname, searchParams } = splitPath(path)
  const method = String(options?.method || 'GET').toUpperCase()
  const store = ensureMockStore()

  try {
    if (pathname.startsWith('/api/v1/teacher/coursewares')) {
      const response = handleTeacherCoursewareRequest(store, pathname, searchParams, method, options)
      if (response) return response
    }

    if (pathname === '/api/v1/teacher/recommend' && method === 'POST') {
      return handleRecommendRequest(options)
    }

    if (pathname.startsWith('/api/v1/teacher/iteration')) {
      const response = handleIterationRequest(store, pathname, method, options)
      if (response) return response
    }

    if (pathname.startsWith('/api/v1/platform/')) {
      const response = handlePlatformRequest(store, pathname, searchParams, method, options)
      if (response) return response
    }
  } catch (error) {
    console.warn('[MockBackend] fallback failed:', error)
    return null
  }

  if (originalError) {
    console.warn('[MockBackend] no route matched for', method, pathname, originalError)
  }
  return null
}

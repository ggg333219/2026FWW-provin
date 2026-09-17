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
          // 兼容旧版本 localStorage：补齐 S2/KB 新增字段
          if (!Array.isArray(mockStoreCache.materials)) {
            mockStoreCache.materials = buildDefaultMaterialStore()
          }
          if (!mockStoreCache.parseTasks || typeof mockStoreCache.parseTasks !== 'object') {
            mockStoreCache.parseTasks = {}
          }
          if (!Array.isArray(mockStoreCache.ragDocuments)) {
            mockStoreCache.ragDocuments = []
          }
          // 清理历史遗留的二进制乱码切片（旧版本曾把 PDF 按 UTF-8 解码进 content）
          sanitizeStoreChunks(mockStoreCache)
          persistMockStore()
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

function buildDefaultMaterialStore() {
  const materials = [
    {
      id: 'mat_001',
      title: '函数与导数基础',
      type: 'document',
      fileType: 'pdf',
      fileSize: 2457600,
      source: '教师上传',
      tags: ['函数', '导数', '基础'],
      parseStatus: 'done',
      uploadedAt: isoDaysAgo(3),
      chunks: [
        { chunkId: 'chunk_001', materialId: 'mat_001', content: '函数是数学中的基本概念，表示两个集合之间的对应关系。设A、B为非空集合，如果按照某种对应法则f，使得A中任意一个元素x，在B中都有唯一确定的元素y与之对应，则称f为从A到B的函数。', pageStart: 1, pageEnd: 1, seqIndex: 0, relevanceScore: 0.92 },
        { chunkId: 'chunk_002', materialId: 'mat_001', content: '函数的定义域是指自变量x的取值范围，值域是函数值y的取值范围。求定义域时需要注意：分母不为零、偶次根号内非负、对数真数大于零等限制条件。', pageStart: 2, pageEnd: 2, seqIndex: 1, relevanceScore: 0.88 },
        { chunkId: 'chunk_003', materialId: 'mat_001', content: '导数描述了函数在某一点的变化率。对于函数y=f(x)，其导数f\'(x)表示函数在x处的瞬时变化率。导数的几何意义是函数曲线在该点切线的斜率。', pageStart: 3, pageEnd: 3, seqIndex: 2, relevanceScore: 0.95 },
        { chunkId: 'chunk_004', materialId: 'mat_001', content: '常用导数公式：(x^n)\' = nx^(n-1)，(sin x)\' = cos x，(cos x)\' = -sin x，(e^x)\' = e^x，(ln x)\' = 1/x。掌握这些基本公式是求解导数题目的基础。', pageStart: 4, pageEnd: 4, seqIndex: 3, relevanceScore: 0.85 },
      ]
    },
    {
      id: 'mat_002',
      title: '排序算法动画演示',
      type: 'video',
      fileType: 'mp4',
      fileSize: 15728640,
      source: 'B站资源',
      tags: ['算法', '排序', '动画'],
      parseStatus: 'done',
      uploadedAt: isoDaysAgo(5),
      chunks: [
        { chunkId: 'chunk_005', materialId: 'mat_002', content: '冒泡排序（Bubble Sort）是一种简单的排序算法。它重复地遍历要排序的数列，一次比较两个元素，如果它们的顺序错误就把它们交换过来。遍历数列的工作是重复地进行直到没有再需要交换。', timeStart: 0, timeEnd: 45, seqIndex: 0, relevanceScore: 0.90 },
        { chunkId: 'chunk_006', materialId: 'mat_002', content: '快速排序（Quick Sort）通过一趟排序将待排记录分隔成独立的两部分，其中一部分记录的关键字均比另一部分的关键字小，则可分别对这两部分记录继续进行排序，以达到整个序列有序。', timeStart: 46, timeEnd: 120, seqIndex: 1, relevanceScore: 0.93 },
        { chunkId: 'chunk_007', materialId: 'mat_002', content: '快速排序的平均时间复杂度为O(n log n)，最坏情况为O(n²)。通过合理选择基准值（pivot），如三数取中法，可以有效避免最坏情况的发生。', timeStart: 121, timeEnd: 180, seqIndex: 2, relevanceScore: 0.87 },
      ]
    },
    {
      id: 'mat_003',
      title: '三角函数与图像',
      type: 'document',
      fileType: 'pptx',
      fileSize: 5242880,
      source: '校内资源',
      tags: ['三角函数', '图像', '变换'],
      parseStatus: 'parsing',
      uploadedAt: isoDaysAgo(1),
      chunks: []
    }
  ]
  return materials
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
    },
    materials: buildDefaultMaterialStore(),
    parseTasks: {},
    ragDocuments: [],
    genTasks: {},
    intentSessions: {},
    versionSnapshots: {},
    exportJobs: {}
  }
}

function ok(data) {
  return { code: 200, message: 'ok (mock)', data }
}

// ================================================================
// Mock 导出文件生成（PPTX / DOCX 最小可打开包，STORED ZIP）
// 让离线演示的「下载文件」真正产出可打开的 Office 文件，而不是 404。
// 生成逻辑独立验证：python-pptx / python-docx 均可解析。
// ================================================================

const MOCK_XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
const PPTX_MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

let _mockCrcTable = null
function mockCrc32(bytes) {
  if (!_mockCrcTable) {
    _mockCrcTable = new Uint32Array(256)
    for (let n = 0; n < 256; n += 1) {
      let c = n
      for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
      _mockCrcTable[n] = c >>> 0
    }
  }
  let crc = 0xffffffff
  for (let i = 0; i < bytes.length; i += 1) {
    crc = (crc >>> 8) ^ _mockCrcTable[(crc ^ bytes[i]) & 0xff]
  }
  return (crc ^ 0xffffffff) >>> 0
}

/** 最小 ZIP 打包器（method=0 STORED，无需压缩算法，浏览器可直接生成） */
function mockZipStore(entries) {
  const encoder = new TextEncoder()
  const chunks = []
  const central = []
  let offset = 0
  for (const entry of entries) {
    const name = encoder.encode(entry.name)
    const data = entry.data
    const crc = mockCrc32(data)
    const local = new DataView(new ArrayBuffer(30))
    local.setUint32(0, 0x04034b50, true)
    local.setUint16(4, 20, true)
    local.setUint16(6, 0x0800, true) // UTF-8 文件名
    local.setUint16(8, 0, true) // method = STORED
    local.setUint16(10, 0, true)
    local.setUint16(12, 0x21, true)
    local.setUint32(14, crc, true)
    local.setUint32(18, data.length, true)
    local.setUint32(22, data.length, true)
    local.setUint16(26, name.length, true)
    local.setUint16(28, 0, true)
    chunks.push(new Uint8Array(local.buffer), name, data)
    central.push({ name, crc, size: data.length, offset })
    offset += 30 + name.length + data.length
  }
  const cdStart = offset
  for (const c of central) {
    const h = new DataView(new ArrayBuffer(46))
    h.setUint32(0, 0x02014b50, true)
    h.setUint16(4, 20, true)
    h.setUint16(6, 20, true)
    h.setUint16(8, 0x0800, true)
    h.setUint16(10, 0, true)
    h.setUint16(12, 0, true)
    h.setUint16(14, 0x21, true)
    h.setUint32(16, c.crc, true)
    h.setUint32(20, c.size, true)
    h.setUint32(24, c.size, true)
    h.setUint16(28, c.name.length, true)
    h.setUint16(30, 0, true)
    h.setUint16(32, 0, true)
    h.setUint16(34, 0, true)
    h.setUint16(36, 0, true)
    h.setUint32(38, 0, true)
    h.setUint32(42, c.offset, true)
    chunks.push(new Uint8Array(h.buffer), c.name)
  }
  const cdSize = central.reduce((s, c) => s + 46 + c.name.length, 0)
  const eocd = new DataView(new ArrayBuffer(22))
  eocd.setUint32(0, 0x06054b50, true)
  eocd.setUint16(4, 0, true)
  eocd.setUint16(6, 0, true)
  eocd.setUint16(8, central.length, true)
  eocd.setUint16(10, central.length, true)
  eocd.setUint32(12, cdSize, true)
  eocd.setUint32(16, cdStart, true)
  eocd.setUint16(20, 0, true)
  chunks.push(new Uint8Array(eocd.buffer))
  const total = chunks.reduce((s, c) => s + c.length, 0)
  const out = new Uint8Array(total)
  let pos = 0
  for (const c of chunks) {
    out.set(c, pos)
    pos += c.length
  }
  return out
}

function mockEscXml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

const MOCK_CORE_PROPS = `${MOCK_XML_DECL}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>课件导出</dc:title><dc:creator>Teacher Frontend (Mock)</dc:creator><cp:lastModifiedBy>Teacher Frontend</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">2026-01-01T00:00:00Z</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">2026-01-01T00:00:00Z</dcterms:modified></cp:coreProperties>`

const MOCK_PPTX_THEME = `${MOCK_XML_DECL}<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office"><a:themeElements><a:clrScheme name="Office"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="44546A"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2><a:accent1><a:srgbClr val="4472C4"/></a:accent1><a:accent2><a:srgbClr val="ED7D31"/></a:accent2><a:accent3><a:srgbClr val="A5A5A5"/></a:accent3><a:accent4><a:srgbClr val="FFC000"/></a:accent4><a:accent5><a:srgbClr val="5B9BD5"/></a:accent5><a:accent6><a:srgbClr val="70AD47"/></a:accent6><a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme><a:fontScheme name="Office"><a:majorFont><a:latin typeface="Calibri Light" panose="020F0302020204030204"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Calibri" panose="020F0502020204030204"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme><a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="50000"/><a:satMod val="300000"/></a:schemeClr></a:gs><a:gs pos="35000"><a:schemeClr val="phClr"><a:tint val="37000"/><a:satMod val="300000"/></a:schemeClr></a:gs><a:gs pos="100000"><a:schemeClr val="phClr"><a:tint val="15000"/><a:satMod val="350000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="16200000" scaled="1"/></a:gradFill><a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:shade val="51000"/><a:satMod val="130000"/></a:schemeClr></a:gs><a:gs pos="80000"><a:schemeClr val="phClr"><a:shade val="93000"/><a:satMod val="130000"/></a:schemeClr></a:gs><a:gs pos="100000"><a:schemeClr val="phClr"><a:shade val="94000"/><a:satMod val="135000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="16200000" scaled="0"/></a:gradFill></a:fillStyleLst><a:lnStyleLst><a:ln w="6350" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln><a:ln w="12700" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln><a:ln w="19050" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"><a:tint val="95000"/><a:satMod val="170000"/></a:schemeClr></a:solidFill><a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="93000"/><a:satMod val="150000"/><a:shade val="98000"/><a:lumMod val="102000"/></a:schemeClr></a:gs><a:gs pos="50000"><a:schemeClr val="phClr"><a:tint val="98000"/><a:satMod val="130000"/><a:shade val="90000"/><a:lumMod val="103000"/></a:schemeClr></a:gs><a:gs pos="100000"><a:schemeClr val="phClr"><a:shade val="63000"/><a:satMod val="120000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="16200000" scaled="0"/></a:gradFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>`

/** 从 mock 版本快照（或生成任务）取导出节点 */
function mockExportNodesFrom(store, genId) {
  const snapshots = (store.versionSnapshots && store.versionSnapshots[genId]) || []
  const latest = snapshots[snapshots.length - 1]
  if (Array.isArray(latest?.nodes_snapshot)) return latest.nodes_snapshot
  const tasks = store.genTasks || {}
  for (const task of Object.values(tasks)) {
    if (task.generation_id === genId && Array.isArray(task.nodes) && task.nodes.length) return task.nodes
  }
  return []
}

function mockNormalizeNode(node, index) {
  return {
    title: node.title || node.node_title || `页面 ${index + 1}`,
    content: node.content || node.scriptText || node.script || node.summary || '',
    points: Array.isArray(node.key_points)
      ? node.key_points
      : Array.isArray(node.children)
        ? node.children
        : []
  }
}

function mockBuildPptxBytes(nodes) {
  const slides = (Array.isArray(nodes) && nodes.length ? nodes : [{ title: '课件', content: '（暂无内容）' }])
    .map((n, i) => mockNormalizeNode(n, i))

  const contentTypes = `${MOCK_XML_DECL}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/><Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/><Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>${slides.map((_, i) => `<Override PartName="/ppt/slides/slide${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>`).join('')}<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>`

  const rootRels = `${MOCK_XML_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>`

  const presentationRels = `${MOCK_XML_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>${slides.map((_, i) => `<Relationship Id="rId${i + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide${i + 1}.xml"/>`).join('')}</Relationships>`

  const presentation = `${MOCK_XML_DECL}<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>${slides.map((_, i) => `<p:sldId id="${256 + i}" r:id="rId${i + 2}"/>`).join('')}</p:sldIdLst><p:sldSz cx="12192000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/><p:defaultTextStyle/></p:presentation>`

  const slideMaster = `${MOCK_XML_DECL}<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>`

  const slideMasterRels = `${MOCK_XML_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>`

  const slideLayout = `${MOCK_XML_DECL}<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>`

  const slideLayoutRels = `${MOCK_XML_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>`

  const slideXmls = slides.map((s) => {
    const title = mockEscXml(s.title)
    const content = mockEscXml(s.content)
    const points = s.points.length
      ? `<a:p><a:r><a:rPr lang="zh-CN" sz="1600" dirty="0"><a:solidFill><a:srgbClr val="2F605A"/></a:solidFill><a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/></a:rPr><a:t>${s.points.map((p) => `• ${mockEscXml(p)}`).join('\n')}</a:t></a:r></a:p>`
      : ''
    return `${MOCK_XML_DECL}<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr><p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="457200" y="304800"/><a:ext cx="11277600" cy="1371600"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr wrap="none"/><a:lstStyle/><a:p><a:r><a:rPr lang="zh-CN" sz="4000" b="1" dirty="0"><a:solidFill><a:srgbClr val="2F605A"/></a:solidFill><a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/></a:rPr><a:t>${title}</a:t></a:r></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id="3" name="Content"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="457200" y="1828800"/><a:ext cx="11277600" cy="4525500"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr wrap="square"/><a:lstStyle/><a:p><a:r><a:rPr lang="zh-CN" sz="2000" dirty="0"><a:solidFill><a:srgbClr val="333333"/></a:solidFill><a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/></a:rPr><a:t>${content}</a:t></a:r></a:p>${points}</p:txBody></p:sp></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>`
  })

  const slideRels = slides.map(
    () => `${MOCK_XML_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>`
  )

  const appProps = `${MOCK_XML_DECL}<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Teacher Frontend (Mock)</Application><Slides>${slides.length}</Slides></Properties>`

  const encoder = new TextEncoder()
  const entries = [
    { name: '[Content_Types].xml', data: encoder.encode(contentTypes) },
    { name: '_rels/.rels', data: encoder.encode(rootRels) },
    { name: 'docProps/core.xml', data: encoder.encode(MOCK_CORE_PROPS) },
    { name: 'docProps/app.xml', data: encoder.encode(appProps) },
    { name: 'ppt/presentation.xml', data: encoder.encode(presentation) },
    { name: 'ppt/_rels/presentation.xml.rels', data: encoder.encode(presentationRels) },
    { name: 'ppt/slideMasters/slideMaster1.xml', data: encoder.encode(slideMaster) },
    { name: 'ppt/slideMasters/_rels/slideMaster1.xml.rels', data: encoder.encode(slideMasterRels) },
    { name: 'ppt/slideLayouts/slideLayout1.xml', data: encoder.encode(slideLayout) },
    { name: 'ppt/slideLayouts/_rels/slideLayout1.xml.rels', data: encoder.encode(slideLayoutRels) },
    { name: 'ppt/theme/theme1.xml', data: encoder.encode(MOCK_PPTX_THEME) }
  ]
  slides.forEach((_, i) => {
    entries.push({ name: `ppt/slides/slide${i + 1}.xml`, data: encoder.encode(slideXmls[i]) })
    entries.push({ name: `ppt/slides/_rels/slide${i + 1}.xml.rels`, data: encoder.encode(slideRels[i]) })
  })
  return mockZipStore(entries)
}

function mockBuildDocxBytes(nodes) {
  const encoder = new TextEncoder()
  const items = Array.isArray(nodes) && nodes.length ? nodes : [{ title: '课件', content: '（暂无内容）' }]
  const bodyXml = items
    .map((n, i) => {
      const title = mockEscXml(n.title || n.node_title || `页面 ${i + 1}`)
      const content = mockEscXml(n.content || n.scriptText || n.script || n.summary || '')
      const points = (Array.isArray(n.key_points) ? n.key_points : Array.isArray(n.children) ? n.children : [])
        .map((p) => `<w:p><w:r><w:t>• ${mockEscXml(p)}</w:t></w:r></w:p>`)
        .join('')
      return `<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>${title}</w:t></w:r></w:p><w:p><w:r><w:t>${content}</w:t></w:r></w:p>${points}`
    })
    .join('')

  const documentXml = `${MOCK_XML_DECL}<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${bodyXml}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>`
  const stylesXml = `${MOCK_XML_DECL}<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/><w:color w:val="2F605A"/></w:rPr></w:style></w:styles>`
  const contentTypes = `${MOCK_XML_DECL}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>`
  const rootRels = `${MOCK_XML_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>`
  const docRels = `${MOCK_XML_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`
  const appProps = `${MOCK_XML_DECL}<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Teacher Frontend (Mock)</Application><Pages>${items.length}</Pages></Properties>`

  return mockZipStore([
    { name: '[Content_Types].xml', data: encoder.encode(contentTypes) },
    { name: '_rels/.rels', data: encoder.encode(rootRels) },
    { name: 'docProps/core.xml', data: encoder.encode(MOCK_CORE_PROPS) },
    { name: 'docProps/app.xml', data: encoder.encode(appProps) },
    { name: 'word/document.xml', data: encoder.encode(documentXml) },
    { name: 'word/styles.xml', data: encoder.encode(stylesXml) },
    { name: 'word/_rels/document.xml.rels', data: encoder.encode(docRels) }
  ])
}

/** 按 job 缓存 Blob URL（会话内复用，避免轮询时重复创建造成内存泄漏） */
const _mockExportBlobCache = new Map()

/** 导出任务 → 可下载地址：浏览器环境返回 Blob URL（真实可打开文件），否则回退后端下载路径 */
function mockBuildExportDownloadUrl(store, job) {
  const fmt = job.format || 'pptx'
  const fallback = `/download/${job.job_id}.${fmt}`
  const canBlob = typeof URL !== 'undefined' && typeof Blob !== 'undefined' && typeof URL.createObjectURL === 'function'
  if (!canBlob) return fallback
  if (_mockExportBlobCache.has(job.job_id)) return _mockExportBlobCache.get(job.job_id)
  try {
    const nodes = mockExportNodesFrom(store, job.generation_id)
    const isDocx = fmt === 'docx'
    const bytes = isDocx ? mockBuildDocxBytes(nodes) : mockBuildPptxBytes(nodes)
    const blobUrl = URL.createObjectURL(new Blob([bytes], { type: isDocx ? DOCX_MIME : PPTX_MIME }))
    _mockExportBlobCache.set(job.job_id, blobUrl)
    return blobUrl
  } catch (error) {
    return fallback
  }
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

function buildGeneratedScript(courseTitle, page, nodes, evidence = null) {
  const parts = [
    `${courseTitle} · 第${page}页 AI 预制讲稿`,
    '',
    '开场：先用1分钟回顾上页关键点，并抛出本页目标。',
    ''
  ]
  // 如果有证据包，在生成讲稿时附加证据上下文提示
  if (evidence && evidence.synthesized_context) {
    parts.push(`📋 证据上下文：${evidence.synthesized_context}`)
    parts.push('')
  }
  if (evidence && Array.isArray(evidence.relevant_chunks) && evidence.relevant_chunks.length > 0) {
    parts.push('参考资料：')
    evidence.relevant_chunks.forEach((chunk, idx) => {
      const snippet = String(chunk.content || '').slice(0, 80)
      parts.push(`  [${idx + 1}] ${snippet}${chunk.content && chunk.content.length > 80 ? '...' : ''}`)
    })
    parts.push('')
  }
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
    const evidence = body.evidence
    const content = buildGeneratedScript(course.title, page, nodes, evidence)
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

// =============================================================================
// S2 多模态资料中心 + KB 知识库 RAG — Mock 处理器
// =============================================================================

const MATERIAL_TYPE_BY_EXT = {
  '.pdf': 'document',
  '.pptx': 'document',
  '.ppt': 'document',
  '.docx': 'document',
  '.doc': 'document',
  '.txt': 'document',
  '.md': 'document',
  '.mp4': 'video',
  '.avi': 'video',
  '.mov': 'video',
  '.mp3': 'audio',
  '.wav': 'audio',
  '.png': 'image',
  '.jpg': 'image',
  '.jpeg': 'image',
  '.gif': 'image',
  '.webp': 'image'
}

function fileExt(name) {
  const idx = String(name || '').lastIndexOf('.')
  return idx >= 0 ? String(name).slice(idx).toLowerCase() : ''
}

function materialSourceType(fileName) {
  const ext = fileExt(fileName)
  if (ext === '.mp4' || ext === '.avi' || ext === '.mov') return 'video'
  if (ext === '.mp3' || ext === '.wav') return 'audio'
  if (ext === '.png' || ext === '.jpg' || ext === '.jpeg' || ext === '.gif' || ext === '.webp') return 'image'
  if (ext === '.pdf') return 'pdf'
  if (ext === '.pptx' || ext === '.ppt') return 'pptx'
  if (ext === '.docx' || ext === '.doc') return 'docx'
  return 'text'
}

function seedChunksForFile(fileName, materialId) {
  const ext = fileExt(fileName)
  const baseName = String(fileName || '未命名资料').replace(/\.[^.]+$/, '')
  if (ext === '.mp4') {
    return [
      { chunkId: uid('chunk'), materialId, content: `【视频】${baseName} 第1段：概念引入与学习目标说明，适合课堂导入使用。`, timeStart: 0, timeEnd: 45, seqIndex: 0, relevanceScore: 0.9 },
      { chunkId: uid('chunk'), materialId, content: `【视频】${baseName} 第2段：核心知识点讲解，配合案例演示。`, timeStart: 46, timeEnd: 120, seqIndex: 1, relevanceScore: 0.88 },
      { chunkId: uid('chunk'), materialId, content: `【视频】${baseName} 第3段：例题演练与易错点总结。`, timeStart: 121, timeEnd: 180, seqIndex: 2, relevanceScore: 0.84 }
    ]
  }
  if (ext === '.mp3' || ext === '.wav') {
    return [
      { chunkId: uid('chunk'), materialId, content: `【音频】${baseName} 第1段：录音开场与背景介绍。`, timeStart: 0, timeEnd: 60, seqIndex: 0, relevanceScore: 0.82 },
      { chunkId: uid('chunk'), materialId, content: `【音频】${baseName} 第2段：核心内容讲解。`, timeStart: 61, timeEnd: 150, seqIndex: 1, relevanceScore: 0.86 }
    ]
  }
  if (ext === '.png' || ext === '.jpg' || ext === '.jpeg') {
    return [
      { chunkId: uid('chunk'), materialId, content: `【图片】${baseName}：整页图像，OCR 识别文本内容为示例图片说明文字。`, pageStart: 1, pageEnd: 1, seqIndex: 0, relevanceScore: 0.8 }
    ]
  }
  return [
    { chunkId: uid('chunk'), materialId, content: `${baseName} 第1部分：本节内容的引入与背景，介绍核心概念与学习目标。`, pageStart: 1, pageEnd: 1, seqIndex: 0, relevanceScore: 0.9 },
    { chunkId: uid('chunk'), materialId, content: `${baseName} 第2部分：核心知识点展开，配合具体示例说明，并给出关键结论。`, pageStart: 2, pageEnd: 3, seqIndex: 1, relevanceScore: 0.87 },
    { chunkId: uid('chunk'), materialId, content: `${baseName} 第3部分：本节小结与课后练习建议。`, pageStart: 4, pageEnd: 4, seqIndex: 2, relevanceScore: 0.83 }
  ]
}

function buildParseAssets(filePaths) {
  const list = Array.isArray(filePaths) ? filePaths : []
  return list.map((filePath, idx) => {
    const fileName = decodeURIComponent(String(filePath || '').split(/[\\/]/).pop() || `文件${idx + 1}`)
    const ext = fileExt(fileName)
    const mimeMap = {
      '.pdf': 'application/pdf',
      '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      '.ppt': 'application/vnd.ms-powerpoint',
      '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      '.mp4': 'video/mp4',
      '.mp3': 'audio/mpeg',
      '.png': 'image/png',
      '.jpg': 'image/jpeg'
    }
    const pageCountMap = { '.pdf': 12, '.pptx': 8, '.docx': 6 }
    const durationMap = { '.mp4': 180, '.mp3': 150 }
    return {
      asset_id: uid('asset'),
      file_name: fileName,
      source_type: materialSourceType(fileName),
      parse_status: 'uploaded',
      file_size: 51200 + (idx + 1) * 30720,
      page_count: pageCountMap[ext] ?? null,
      duration_sec: durationMap[ext] ?? null,
      mime_type: mimeMap[ext] || 'application/octet-stream',
      created_at: nowIso(),
      metadata: { ext, mock: true }
    }
  })
}

function getMaterialById(store, id) {
  return store.materials.find((item) => item.id === id)
}

/**
 * 用真实文件文本生成切片（Mock 端）。
 * 前端上传时通过 file_contents 附带文件头部文本，
 * 这里按段落切分、累加成 ~220 字/块的 ChunkSchema。
 * 文本过短或二进制乱码（PDF/PPTX/视频按 UTF-8 解码）时回退到种子内容。
 */
function isBinaryGarbage(text) {
  const limited = String(text || '')

  // 常见二进制文件头签名：PDF、ZIP(Office/PPTX/DOCX)、PNG/JPEG、GIF
  if (/^%PDF-/.test(limited)) return true
  if (/^PK[\x03\x04\x05\x07]/.test(limited)) return true
  if (/^\x89PNG/.test(limited)) return true
  if (/^\xFF\xD8\xFF/.test(limited)) return true
  if (/^GIF8/.test(limited)) return true

  // 可打印字符占比 + 控制字符检测：二进制解码后往往夹杂 NUL/控制字符
  let printable = 0
  let control = 0
  let total = 0
  for (const ch of limited) {
    total += 1
    const code = ch.codePointAt(0)
    if (code === 0 || (code < 32 && code !== 9 && code !== 10 && code !== 13)) control += 1
    if (code >= 32 || ch === '\n' || ch === '\t' || ch === '\r') printable += 1
  }
  if (total > 0 && control / total > 0.02) return true
  return total > 0 ? printable / total < 0.8 : true
}

/**
 * 清理历史遗留的二进制乱码切片：把含 PDF/ZIP 等二进制签名的 content
 * 用该文件的种子切片整体替换，保证列表/检索/预览显示正常文本。
 * 通过 _sanitized 标记只执行一次。
 */
function sanitizeStoreChunks(store) {
  if (!store || store._sanitized) return
  store._sanitized = true
  const isBad = (m) => (m.chunks || []).some((c) => isBinaryGarbage(c.content || ''))
  ;(store.materials || []).forEach((m) => {
    if (isBad(m)) {
      m.chunks = seedChunksForFileRich(m.title || m.fileName || '资料', m.id)
      m.parseStatus = 'done'
    }
  })
  ;(store.ragDocuments || []).forEach((doc) => {
    if ((doc.chunks || []).some((c) => isBinaryGarbage(c.content || ''))) {
      doc.chunks = seedChunksForFileRich(doc.file_name || '资料', doc.document_id || 'ragmat')
    }
  })
}

function chunkRealText(text, fileName, materialId) {
  const limited = String(text || '').slice(0, 200000)

  // 二进制乱码或文本过短 → 回退到种子内容
  if (isBinaryGarbage(limited) || limited.replace(/\s/g, '').length < 10) {
    return seedChunksForFileRich(fileName, materialId)
  }

  const paragraphs = limited
    .split(/\r?\n\s*\r?\n/)
    .map((p) => p.replace(/[ \t]+/g, ' ').trim())
    .filter((p) => p.length > 0)

  const chunks = []
  let current = ''
  let seq = 0
  const flush = () => {
    if (!current) return
    chunks.push({
      chunkId: uid('chunk'),
      materialId,
      content: current,
      seqIndex: seq,
      relevanceScore: Number((0.8 + ((current.length % 5) * 0.02)).toFixed(2))
    })
    seq += 1
    current = ''
  }

  for (const para of paragraphs) {
    if (current && current.length + para.length > 220) flush()
    current = current ? `${current}\n${para}` : para
  }
  flush()

  return chunks.length > 0 ? chunks : seedChunksForFileRich(fileName, materialId)
}

function normalizeTextForFile(text, fileName) {
  const ext = fileExt(fileName)
  const normalized = String(text || '').replace(/\r\n?/g, '\n').trim()
  if (!normalized) return ''
  if (ext === '.json') {
    try {
      return JSON.stringify(JSON.parse(normalized), null, 2)
    } catch {
      return normalized
    }
  }
  if (ext === '.csv') {
    return normalized
      .split('\n')
      .map((line) => line.replace(/[ \t]+$/g, ''))
      .filter((line) => line.trim().length > 0)
      .join('\n')
  }
  if (ext === '.html' || ext === '.htm' || ext === '.xml') {
    return normalized
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  }
  return normalized
}

/** 找到某 asset 对应的前端附带文本（按 file_paths 中的原始路径匹配） */
function contentForAsset(asset, task) {
  const paths = Array.isArray(task.file_paths) ? task.file_paths : []
  const idx = paths.findIndex((p) => {
    const name = decodeURIComponent(String(p).split(/[\\/]/).pop() || '')
    return name === asset.file_name
  })
  const raw = idx >= 0 ? task.file_contents?.[paths[idx]] || '' : task.file_contents?.[asset.file_name] || ''
  return normalizeTextForFile(raw, asset.file_name)
}

function handleS2MaterialRequest(store, pathname, searchParams, method, options) {
  // /api/v1/teacher/materials/...  保留旧路径的兼容（列表 + chunks + vector-search）
  const segments = pathname.split('/').filter(Boolean)
  if (segments.length < 4 || segments[2] !== 'teacher' || segments[3] !== 'materials') return null

  // 搜索（/api/v1/teacher/materials/search?keyword=...）
  if (segments.length === 5 && segments[4] === 'search' && method === 'GET') {
    const keyword = cleanText(searchParams.get('keyword'))
    const sessionId = cleanText(searchParams.get('session_id'))
    let list = deepClone(store.materials)
    if (sessionId) {
      list = list.filter((m) => cleanText(m.sessionId || m.session_id) === sessionId)
    }
    if (keyword) {
      const kw = keyword.toLowerCase()
      list = list.filter((m) => String(m.title || '').toLowerCase().includes(kw))
    }
    return ok(list)
  }

  // 全量列表
  if (segments.length === 4 && method === 'GET') {
    return ok(deepClone(store.materials))
  }

  const materialId = segments[4] ? decodeURIComponent(segments[4]) : ''
  const material = getMaterialById(store, materialId)

  if (segments.length === 5 && method === 'DELETE' && material) {
    store.materials = store.materials.filter((item) => item.id !== materialId)
    persistMockStore()
    return ok({ removed: true, materialId })
  }

  if (segments.length === 5 && method === 'PUT' && material) {
    const body = parseJsonBody(options)
    Object.assign(material, {
      title: cleanText(body.title) || material.title,
      tags: Array.isArray(body.tags) ? body.tags : material.tags
    })
    material.updatedAt = nowIso()
    persistMockStore()
    return ok(material)
  }

  if (segments.length === 6 && segments[5] === 'chunks' && method === 'GET' && material) {
    return ok({ chunks: deepClone(material.chunks || []) })
  }

  return null
}

function handleParseRequest(store, pathname, method, options) {
  if (pathname === '/api/v1/parse/process' && method === 'POST') {
    const body = parseJsonBody(options)
    const filePaths = Array.isArray(body.file_paths) ? body.file_paths : []
    const sessionId = cleanText(body.session_id)
    const taskId = uid('ptask')

    const task = {
      task_id: taskId,
      status: 'parsing',
      assets: buildParseAssets(filePaths),
      file_paths: filePaths,
      file_contents: (typeof body.file_contents === 'object' && body.file_contents) || {},
      session_id: sessionId,
      materialIds: [],
      created_at: nowIso(),
      updated_at: nowIso()
    }
    store.parseTasks[taskId] = task

    // 异步模拟：解析完成后把 chunks 写回材料库
    if (typeof window !== 'undefined') {
      setTimeout(() => {
        const current = store.parseTasks[taskId]
        if (!current) return
        current.status = 'done'
        current.updated_at = nowIso()

        const materialIds = []
        current.assets.forEach((asset) => {
          const materialId = uid('mat')
          const fileText = contentForAsset(asset, current)
          // 有真实文本 → 按实际内容切片；否则回退到种子内容
          const chunks = fileText
            ? chunkRealText(normalizeTextForFile(fileText, asset.file_name), asset.file_name, materialId)
            : seedChunksForFileRich(asset.file_name, materialId)
          store.materials.unshift({
            id: materialId,
            sessionId: current.session_id,
            title: asset.file_name,
            type: MATERIAL_TYPE_BY_EXT[fileExt(asset.file_name)] || 'document',
            fileType: String(asset.file_name).split('.').pop() || 'file',
            fileSize: asset.file_size,
            source: '本次上传',
            tags: [],
            parseStatus: 'done',
            uploadedAt: nowIso(),
            chunks
          })
          materialIds.push(materialId)
        })
        current.materialIds = materialIds
        persistMockStore()
      }, 1800)
    }
    return ok({ task_id: taskId, status: 'processing', assets: deepClone(task.assets) })
  }

  if (pathname.startsWith('/api/v1/parse/status/') && method === 'GET') {
    const taskId = decodeURIComponent(pathname.split('/').pop() || '')
    const task = store.parseTasks[taskId]
    if (!task) {
      return ok({ task_id: taskId, status: 'done', chunks: [], error: null })
    }
    const chunks = task.materialIds && task.materialIds.length > 0
      ? task.materialIds.flatMap((mid) => {
          const material = getMaterialById(store, mid)
          return material ? (material.chunks || []) : []
        })
      : []
    return ok({
      task_id: task.task_id,
      status: task.status,
      chunks: deepClone(chunks),
      materialIds: Array.isArray(task.materialIds) ? [...task.materialIds] : [],
      error: task.error || null
    })
  }

  if (pathname === '/api/v1/parse/video' && method === 'POST') {
    const body = parseJsonBody(options)
    const filePath = cleanText(body.file_path)
    const sessionId = cleanText(body.session_id)
    const taskId = uid('vtask')
    const task = {
      task_id: taskId,
      status: 'processing',
      assets: buildParseAssets([filePath]),
      file_paths: [filePath],
      session_id: sessionId,
      materialIds: [],
      created_at: nowIso(),
      updated_at: nowIso()
    }
    store.parseTasks[taskId] = task
    if (typeof window !== 'undefined') {
      setTimeout(() => {
        const current = store.parseTasks[taskId]
        if (!current) return
        current.status = 'done'
        current.updated_at = nowIso()
        const fileName = decodeURIComponent(String(filePath || '').split(/[\\/]/).pop() || '视频素材.mp4')
        const materialId = uid('mat')
        store.materials.unshift({
          id: materialId,
          sessionId: current.session_id,
          title: fileName,
          type: 'video',
          fileType: 'mp4',
          fileSize: current.assets[0]?.file_size || 0,
          source: '视频解析',
          tags: [],
          parseStatus: 'done',
          uploadedAt: nowIso(),
          chunks: seedChunksForFileRich(fileName, materialId)
        })
        current.materialIds = [materialId]
        persistMockStore()
      }, 1800)
    }
    return ok({ task_id: taskId, status: 'processing', assets: deepClone(task.assets) })
  }

  return null
}

function handleKnowledgeUploadRequest(store, options) {
  const body = parseJsonBody(options)
  const sessionId = cleanText(body.session_id)
  const files = Array.isArray(body.files) ? body.files : []

  let chunkCount = 0
  if (files.length > 0) {
    files.forEach((filePath) => {
      const fileName = decodeURIComponent(String(filePath || '').split(/[\\/]/).pop() || '资料')
      // 同名文件视为同一文档：已索引则跳过，避免重复入库
      const existing = store.ragDocuments.find(
        (d) => d.file_name === fileName && d.source_type === materialSourceType(fileName)
      )
      if (existing) {
        chunkCount += existing.chunk_count
        return
      }
      const chunks = seedChunksForFileRich(fileName, uid('ragmat')).map((c) => ({
        ...c,
        metadata: { ...(c.metadata || {}), file_name: fileName, type: 'knowledge' }
      }))
      chunkCount += chunks.length
      store.ragDocuments.push({
        document_id: uid('doc'),
        file_name: fileName,
        source_type: materialSourceType(fileName),
        chunk_count: chunks.length,
        chunks,
        created_at: nowIso()
      })
    })
  } else {
    // 没有 files 时，从该 session 最近完成的解析材料中收集 chunks
    const collected = store.materials.filter((m) => m.parseStatus === 'done').flatMap((m) => m.chunks || [])
    if (collected.length > 0) {
      const docName = `会话${sessionId || '默认'}资料合集`
      const existing = store.ragDocuments.find((d) => d.file_name === docName)
      if (existing) {
        // 幂等合并：仅把新增切片补进已有合集，避免重复点击“索引知识库”产生重复文档
        const seen = new Set(existing.chunks.map((c) => c.chunkId))
        const fresh = collected.filter((c) => !seen.has(c.chunkId))
        existing.chunks = existing.chunks.concat(fresh)
        existing.chunk_count = existing.chunks.length
        existing.created_at = nowIso()
        chunkCount = fresh.length
      } else {
        chunkCount = collected.length
        store.ragDocuments.push({
          document_id: uid('doc'),
          file_name: docName,
          source_type: 'mixed',
          chunk_count: collected.length,
          chunks: collected,
          created_at: nowIso()
        })
      }
    }
  }
  persistMockStore()
  return ok({
    task_id: uid('kbtask'),
    status: 'done',
    chunk_count: chunkCount,
    document_id: store.ragDocuments[store.ragDocuments.length - 1]?.document_id || ''
  })
}

/**
 * 解析切片来源名：
 * 1. 索引入库的 KB 切片直接携带 file_name（metadata.file_name）；
 * 2. 素材切片通过 materialId 反查素材标题；
 * 3. 均未命中则按知识库/素材兜底。
 */
function resolveChunkSourceName(store, c) {
  if (c.metadata?.file_name) return c.metadata.file_name
  if (c.materialId) {
    const material = getMaterialById(store, c.materialId)
    if (material?.title) return material.title
  }
  const ownerDoc = store.ragDocuments.find((d) => (d.chunks || []).some((ch) => ch.chunkId === c.chunkId))
  if (ownerDoc?.file_name) return ownerDoc.file_name
  return c.metadata?.type === 'knowledge' ? '知识库' : '素材'
}

function handleRagSearchRequest(store, options) {
  const body = parseJsonBody(options)
  const query = cleanText(body.query)
  if (!query) return ok({ results: [], total_chunks: 0 })

  const topK = Math.max(1, safeNumber(body.top_k, 5))
  const minScore = safeNumber(body.min_score, 0.6)

  // 候选池：知识库文档 + 已解析材料
  const candidates = []
  store.ragDocuments.forEach((doc) => {
    ;(doc.chunks || []).forEach((c) => candidates.push(c))
  })
  store.materials.forEach((m) => {
    ;(m.chunks || []).forEach((c) => candidates.push(c))
  })

  const seen = new Set()
  const uniqueCandidates = candidates.filter((c) => {
    if (seen.has(c.chunkId)) return false
    seen.add(c.chunkId)
    return true
  })

  const normalizedQuery = query.toLowerCase()
  const keywordLexicon = [
    '快速排序', '冒泡排序', '复杂度', '定义域', '值域', '三角函数',
    '函数', '导数', '排序', '算法', '图像', '概念'
  ]
  const queryKeywords = keywordLexicon.filter((keyword) => normalizedQuery.includes(keyword))
  const asciiTokens = normalizedQuery.match(/[a-z0-9]{2,}/g) || []
  const queryTokens = [...new Set([...queryKeywords, ...asciiTokens])]

  const scored = uniqueCandidates
    .map((c) => {
      const content = String(c.content || '')
      const normalizedContent = content.toLowerCase()
      let score = normalizedContent.includes(normalizedQuery) ? 0.95 : 0
      if (score === 0 && queryTokens.length > 0) {
        const matched = queryTokens.filter((token) => normalizedContent.includes(token)).length
        if (matched > 0) {
          score = 0.62 + Math.min(0.28, matched * 0.09)
        }
      }
      return {
        chunk_id: c.chunkId,
        content,
        score: Number(score.toFixed(3)),
        source: {
          file_name: resolveChunkSourceName(store, c),
          page: c.pageStart || c.pageEnd || null,
          url: ''
        },
        metadata: {
          type: c.metadata?.type || (c.materialId ? 'material' : 'knowledge'),
          node_ref: ''
        }
      }
    })
    .filter((item) => item.score >= minScore)
    .sort((a, b) => b.score - a.score)
    .slice(0, topK)

  return ok({ results: scored, total_chunks: uniqueCandidates.length })
}

function handleRagEvidenceRequest(store, options) {
  const body = parseJsonBody(options)
  const query = cleanText(body.query)
  const search = handleRagSearchRequest(store, {
    body: JSON.stringify({ query, top_k: 5, min_score: 0.5 })
  })
  const results = search.data.results || []
  return ok({
    evidence_packet: {
      query,
      relevant_chunks: results.map((item) => ({
        chunk_id: item.chunk_id,
        content: item.content,
        source_type: item.metadata?.type === 'material' ? materialSourceType(item.source?.file_name) : 'text',
        page_ref: item.source?.page || 0,
        seq_index: 0
      })),
      synthesized_context: results.length
        ? `基于检索到的 ${results.length} 段相关资料，综合整理出与“${query}”相关的内容要点，可作为生成环节的参考上下文。`
        : '未检索到足够相关资料，建议先上传并解析素材后再进行证据融合。',
      citations: results.map((item) => ({
        chunk_id: item.chunk_id,
        text_snippet: String(item.content).slice(0, 60),
        source_ref: item.source?.file_name || ''
      }))
    }
  })
}

function seedChunksForFileRich(fileName, materialId) {
  const ext = fileExt(fileName)
  const baseName = String(fileName || '未命名资料').replace(/\.[^.]+$/, '')

  if (ext === '.pdf') {
    return [
      { chunkId: uid('chunk'), materialId, content: `【PDF】${baseName} 第1页：标题与目录，提取为页面导读切片。`, pageStart: 1, pageEnd: 1, seqIndex: 0, relevanceScore: 0.91 },
      { chunkId: uid('chunk'), materialId, content: `【PDF】${baseName} 第2页：正文内容与公式/表格信息，适合知识点讲解。`, pageStart: 2, pageEnd: 2, seqIndex: 1, relevanceScore: 0.89 },
      { chunkId: uid('chunk'), materialId, content: `【PDF】${baseName} 第3页：总结与练习建议，可直接用于课件引用。`, pageStart: 3, pageEnd: 3, seqIndex: 2, relevanceScore: 0.87 }
    ]
  }

  if (ext === '.pptx' || ext === '.ppt') {
    return [
      { chunkId: uid('chunk'), materialId, content: `【PPT】${baseName} 幻灯片1：课程导入与学习目标。`, pageStart: 1, pageEnd: 1, seqIndex: 0, relevanceScore: 0.92 },
      { chunkId: uid('chunk'), materialId, content: `【PPT】${baseName} 幻灯片2：核心知识点展开与示例说明。`, pageStart: 2, pageEnd: 2, seqIndex: 1, relevanceScore: 0.9 },
      { chunkId: uid('chunk'), materialId, content: `【PPT】${baseName} 幻灯片3：课堂小结与互动提问。`, pageStart: 3, pageEnd: 3, seqIndex: 2, relevanceScore: 0.88 }
    ]
  }

  if (ext === '.docx' || ext === '.doc') {
    return [
      { chunkId: uid('chunk'), materialId, content: `【DOC】${baseName} 第1节：章节概述、背景与教学目标。`, pageStart: 1, pageEnd: 1, seqIndex: 0, relevanceScore: 0.91 },
      { chunkId: uid('chunk'), materialId, content: `【DOC】${baseName} 第2节：正文与案例说明，适合作为课堂讲义。`, pageStart: 2, pageEnd: 2, seqIndex: 1, relevanceScore: 0.89 },
      { chunkId: uid('chunk'), materialId, content: `【DOC】${baseName} 第3节：总结、练习与延伸阅读。`, pageStart: 3, pageEnd: 3, seqIndex: 2, relevanceScore: 0.87 }
    ]
  }

  if (ext === '.mp4') {
    return [
      { chunkId: uid('chunk'), materialId, content: `【视频】${baseName} 第1段：概念引入与学习目标说明，适合课堂导入使用。`, timeStart: 0, timeEnd: 45, seqIndex: 0, relevanceScore: 0.9 },
      { chunkId: uid('chunk'), materialId, content: `【视频】${baseName} 第2段：核心知识点讲解，配合案例演示。`, timeStart: 46, timeEnd: 120, seqIndex: 1, relevanceScore: 0.88 },
      { chunkId: uid('chunk'), materialId, content: `【视频】${baseName} 第3段：例题演练与易错点总结。`, timeStart: 121, timeEnd: 180, seqIndex: 2, relevanceScore: 0.84 }
    ]
  }

  if (ext === '.mp3' || ext === '.wav') {
    return [
      { chunkId: uid('chunk'), materialId, content: `【音频】${baseName} 第1段：录音开场与背景介绍。`, timeStart: 0, timeEnd: 60, seqIndex: 0, relevanceScore: 0.82 },
      { chunkId: uid('chunk'), materialId, content: `【音频】${baseName} 第2段：核心内容讲解。`, timeStart: 61, timeEnd: 150, seqIndex: 1, relevanceScore: 0.86 }
    ]
  }

  if (ext === '.png' || ext === '.jpg' || ext === '.jpeg') {
    return [
      { chunkId: uid('chunk'), materialId, content: `【图片】${baseName}：整页图像，OCR 识别文本内容为示例图片说明文字。`, pageStart: 1, pageEnd: 1, seqIndex: 0, relevanceScore: 0.8 }
    ]
  }

  return [
    { chunkId: uid('chunk'), materialId, content: `${baseName} 第1部分：本节内容的引入与背景，介绍核心概念与学习目标。`, pageStart: 1, pageEnd: 1, seqIndex: 0, relevanceScore: 0.9 },
    { chunkId: uid('chunk'), materialId, content: `${baseName} 第2部分：核心知识点展开，配合具体示例说明，并给出关键结论。`, pageStart: 2, pageEnd: 3, seqIndex: 1, relevanceScore: 0.87 },
    { chunkId: uid('chunk'), materialId, content: `${baseName} 第3部分：本节小结与课后练习建议。`, pageStart: 4, pageEnd: 4, seqIndex: 2, relevanceScore: 0.83 }
  ]
}

// ================================================================
// S1 意图理解 Mock（与 ai_engine/intent/service.py 行为对齐的规则版）
// ================================================================

const INTENT_CORE_FIELDS = ['topic', 'duration_minutes']
const INTENT_QUALITY_FIELDS = ['style', 'target_student', 'knowledge_points']
const INTENT_WEIGHTS = { topic: 25, duration_minutes: 25, style: 15, target_student: 15, knowledge_points: 20 }
const INTENT_FOLLOWUP_QUESTIONS = {
  topic: '这节课最想讲清楚的主题是什么？',
  duration_minutes: '这节课计划安排多少分钟？',
  style: '你更偏好案例驱动、讲练结合，还是项目式教学？',
  target_student: '这节课主要面向哪个年级、专业或基础层次的学生？',
  knowledge_points: '希望重点覆盖哪些知识点？列出 2–5 个即可。'
}

function parseIntentFromMessages(messages = []) {
  const teacherText = (messages || [])
    .filter((m) => m && m.role === 'teacher')
    .map((m) => String(m.content || ''))
    .join('\n')
    .trim()
  const summary = {
    topic: '',
    duration_minutes: null,
    style: '',
    target_student: '',
    knowledge_points: [],
    output_format: ['ppt'],
    with_interactive: false,
    key_difficulties: [],
    expected_outcomes: [],
    missing_fields: []
  }
  if (!teacherText) return summary

  // 主题：优先「主题：X」/「课程主题：X」契约，否则取首句去掉语气词前缀并按标点截断
  let topic = ''
  const topicMatch = teacherText.match(/(?:课程)?主题[:：]\s*([^\n；;。]+)/)
  if (topicMatch) {
    topic = topicMatch[1].trim()
  } else {
    const firstLine = teacherText.split('\n').map((s) => s.trim()).filter(Boolean)[0] || ''
    topic = firstLine
      .replace(/^(请|帮我|我想|这节课)?(讲|讲解|讲授|做|制(作)?|生成|设计|做一个|一份|一节)?/, '')
      .split(/[，。；;,]/)[0]
      .trim()
      .slice(0, 30)
  }
  summary.topic = topic

  // 授课时长
  const dur = teacherText.match(/(\d{1,3})\s*(分钟|min|课时)/i)
  summary.duration_minutes = dur ? Math.min(Number(dur[1]), 240) : null

  // 教学风格（兼容「教学风格：X」契约与风格关键词）
  const styleContract = teacherText.match(/教学风格[:：]\s*([^\n；;。]+)/)
  const styleKeyword = teacherText.match(/(案例驱动|讲练结合|项目式|项目制|理论为主|启发式|互动式)/)
  summary.style = styleContract ? styleContract[1].trim() : (styleKeyword ? styleKeyword[1] : '')

  // 授课对象（兼容「授课对象：X」契约与「面向X」自然表述）
  const stuContract = teacherText.match(/(?:授课对象|面向)\s*[:：]?\s*([^\n；;。，,]{2,20})/)
  summary.target_student = stuContract ? stuContract[1].trim().replace(/(学生|年级|专业)?$/, '') : ''

  // 知识点
  let kps = []
  const kpMatch = teacherText.match(/知识点[:：]\s*([^\n]+)/)
  if (kpMatch) kps = kpMatch[1].split(/[、，,；;]/)
  if (!kps.length) {
    kps = teacherText.split('\n').map((s) => s.trim()).filter((s) => /(重点|知识点|掌握)/.test(s))
  }
  summary.knowledge_points = kps.map((k) => String(k).trim()).filter((k) => k && k.length <= 30).slice(0, 5)

  // 互动 / 难点 / 成果
  const interactiveContract = teacherText.match(/互动设计[:：]\s*(需要|不需要|是|否)/)
  summary.with_interactive = interactiveContract
    ? /需要|是/.test(interactiveContract[1])
    : /互动|测验|投票|讨论/.test(teacherText)
  const diff = teacherText.match(/难点[:：]\s*([^\n]+)/)
  if (diff) summary.key_difficulties = diff[1].split(/[、，,；;]/).map((k) => k.trim()).filter(Boolean).slice(0, 5)
  const out = teacherText.match(/成果[:：]\s*([^\n]+)/)
  if (out) summary.expected_outcomes = out[1].split(/[、，,；;]/).map((k) => k.trim()).filter(Boolean).slice(0, 5)

  return summary
}

function inferIntentMissingFields(summary) {
  return [...INTENT_CORE_FIELDS, ...INTENT_QUALITY_FIELDS].filter((field) => {
    const value = summary[field]
    return Array.isArray(value) ? value.length === 0 : (value === null || String(value || '').trim() === '')
  })
}

function intentCompletionPct(summary) {
  return Object.entries(INTENT_WEIGHTS).reduce((total, [field, weight]) => {
    const value = summary[field]
    const empty = Array.isArray(value) ? value.length === 0 : (value === null || String(value || '').trim() === '')
    return total + (empty ? 0 : weight)
  }, 0)
}

function renderIntentHumanSummary(summary) {
  const parts = []
  if (summary.topic) parts.push(`主题：${summary.topic}`)
  if (summary.duration_minutes) parts.push(`时长：${summary.duration_minutes}分钟`)
  if (summary.style) parts.push(`风格：${summary.style}`)
  if (summary.target_student) parts.push(`对象：${summary.target_student}`)
  if (summary.knowledge_points.length) parts.push(`知识点：${summary.knowledge_points.join('、')}`)
  parts.push(`互动：${summary.with_interactive ? '需要' : '不需要'}`)
  return parts.join('；')
}

function handleIntentExtractRequest(store, options) {
  const body = parseJsonBody(options)
  const sessionId = cleanText(body.session_id)
  store.intentSessions = store.intentSessions || {}
  const previous = store.intentSessions[sessionId] || { summary: null, turn_count: 0 }
  const teacherTurns = Math.max(previous.turn_count || 0, (body.messages || []).filter((m) => m && m.role === 'teacher').length)

  // 增量补全：合并历史摘要与本次解析，避免多轮对话丢失已收集字段
  const parsed = parseIntentFromMessages(body.messages)
  const prev = previous.summary || {}
  const merged = {
    topic: parsed.topic || prev.topic || '',
    duration_minutes: parsed.duration_minutes ?? prev.duration_minutes ?? null,
    style: parsed.style || prev.style || '',
    target_student: parsed.target_student || prev.target_student || '',
    knowledge_points: [...(prev.knowledge_points || []), ...parsed.knowledge_points].filter((v, i, arr) => v && arr.indexOf(v) === i),
    output_format: parsed.output_format,
    with_interactive: parsed.with_interactive || Boolean(prev.with_interactive),
    key_difficulties: parsed.key_difficulties.length ? parsed.key_difficulties : (prev.key_difficulties || []),
    expected_outcomes: parsed.expected_outcomes.length ? parsed.expected_outcomes : (prev.expected_outcomes || []),
    missing_fields: []
  }
  merged.missing_fields = inferIntentMissingFields(merged)

  const maxTurns = 8
  const coreMissing = merged.missing_fields.filter((f) => INTENT_CORE_FIELDS.includes(f))
  const canConfirm = coreMissing.length === 0
  let status
  if (canConfirm || teacherTurns >= maxTurns) status = 'confirming'
  else if (teacherTurns <= 1) status = 'collecting'
  else status = 'clarifying'

  const followups = [...INTENT_CORE_FIELDS, ...INTENT_QUALITY_FIELDS]
    .filter((f) => merged.missing_fields.includes(f))
    .slice(0, 2)
    .map((f) => INTENT_FOLLOWUP_QUESTIONS[f] || '请补充一下相关信息。')
  const response = followups.length
    ? `我已经更新了教学意图，请补充：${followups[0]}`
    : '教学意图已经完整，我已整理成右侧方案卡。确认后即可进入资料融合。'

  store.intentSessions[sessionId] = {
    summary: merged,
    status,
    turn_count: teacherTurns,
    updated_at: nowIso()
  }
  persistMockStore()

  return ok({
    session_id: sessionId,
    intent_summary: merged,
    session_status: status,
    response,
    need_followup: followups.length > 0,
    followup_questions: followups,
    human_summary: renderIntentHumanSummary(merged),
    completion_pct: intentCompletionPct(merged),
    turn_count: teacherTurns,
    max_turns: maxTurns,
    can_confirm: canConfirm,
    engine: 'rule',
    used_fallback: false
  })
}

function handleIntentConfirmRequest(store, options) {
  const body = parseJsonBody(options)
  const sessionId = cleanText(body.session_id)
  store.intentSessions = store.intentSessions || {}
  const session = store.intentSessions[sessionId]
  const intentId = `intent_${String(sessionId || '').replace(/[^a-z0-9]/gi, '').slice(0, 12)}_${Date.now().toString(36)}`

  if (!session || !session.summary) {
    // 无会话仍返回确认状态，保证演示环境 S1→S2 不被阻塞
    return ok({
      session_id: sessionId,
      intent_id: intentId,
      confirmed: true,
      intent_summary: { topic: '', missing_fields: ['topic'] },
      session_status: 'confirmed',
      completion_pct: 20,
      next_step: 'material_upload'
    })
  }

  const summary = session.summary || {}
  session.status = 'confirmed'
  session.intent_id = intentId
  store.intentSessions[sessionId] = session
  persistMockStore()

  return ok({
    session_id: sessionId,
    intent_id: intentId,
    confirmed: true,
    intent_summary: summary,
    session_status: 'confirmed',
    completion_pct: 100,
    next_step: 'material_upload'
  })
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

    if (pathname.startsWith('/api/v1/teacher/materials')) {
      const response = handleS2MaterialRequest(store, pathname, searchParams, method, options)
      if (response) return response
    }

    if (pathname.startsWith('/api/v1/parse')) {
      const response = handleParseRequest(store, pathname, method, options)
      if (response) return response
    }

    if (pathname === '/api/v1/knowledge/upload' && method === 'POST') {
      return handleKnowledgeUploadRequest(store, options)
    }

    if (pathname === '/api/v1/rag/search' && method === 'POST') {
      return handleRagSearchRequest(store, options)
    }

    if (pathname === '/api/v1/rag/evidence' && method === 'POST') {
      return handleRagEvidenceRequest(store, options)
    }

    if (pathname === '/api/v1/intent/extract' && method === 'POST') {
      return handleIntentExtractRequest(store, options)
    }

    if (pathname === '/api/v1/intent/confirm' && method === 'POST') {
      return handleIntentConfirmRequest(store, options)
    }

    // ================================================================
    // 预览渲染（与后端 ai_engine/gen/preview.py 保持一致的 JS 镜像）
    // ================================================================

    const TYPE_ALIASES = {
      cover: 'cover', title: 'cover',
      section: 'section', divider: 'section', toc: 'section', chapter: 'section',
      quiz: 'quiz', qa: 'quiz', interactive: 'quiz', question: 'quiz',
      summary: 'summary', recap: 'summary',
      content: 'content', slide: 'content'
    }

    function escHtml(value) {
      return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[ch]))
    }

    function resolveType(node) {
      let raw = node.type
      if (raw === undefined || raw === null || String(raw).trim() === '') raw = node.node_type
      if (raw === undefined || raw === null || String(raw).trim() === '') return 'content'
      return TYPE_ALIASES[String(raw).trim().toLowerCase()] || 'content'
    }

    function toList(value) {
      if (Array.isArray(value)) return value.map((v) => String(v).trim()).filter(Boolean)
      if (typeof value === 'string' && value.trim()) {
        return value.split('\n').map((s) => s.trim()).filter(Boolean)
      }
      return []
    }

    function extractKeyPoints(node) {
      for (const key of ['key_points', 'core_points', 'key_difficulties', 'expected_outcomes']) {
        const pts = toList(node[key])
        if (pts.length) return pts
      }
      const content = String(node.content || node.script || node.summary || '').trim()
      if (!content) return []
      const lines = content.split('\n').map((s) => s.trim().replace(/^[•\-*#·]+\s*/, '')).filter(Boolean)
      if (lines.length >= 2) return lines.slice(0, 8)
      return content.split(/[。；;！？!?]\s*/).filter(Boolean).slice(0, 8)
    }

    function renderKeyPoints(points, cls, withIndex) {
      return points.slice(0, 10).map((p, i) => {
        const idx = withIndex ? `<span class="kp-idx">${i + 1}</span>` : ''
        return `<li>${idx}${escHtml(p)}</li>`
      }).join('')
    }

    function renderKnowledgeCard(kc) {
      if (!kc || typeof kc !== 'object') return ''
      const term = escHtml(String(kc.term || '知识卡片'))
      const def = String(kc.definition || '').trim()
        ? `<p class="kc-def">${escHtml(kc.definition)}</p>` : ''
      const formula = String(kc.formula || '').trim()
        ? `<pre class="kc-formula">${escHtml(kc.formula)}</pre>` : ''
      const tags = Array.isArray(kc.tags) && kc.tags.length
        ? `<div class="kc-tags">${kc.tags.map(escHtml).map((t) => `<span>${t}</span>`).join('')}</div>` : ''
      if (!def && !formula && !tags) return ''
      return `<div class="knowledge-card"><strong class="kc-term">📘 ${term}</strong>${def}${formula}${tags}</div>`
    }

    function renderSegments(node) {
      const segs = Array.isArray(node.segments) ? node.segments : []
      const items = []
      for (const s of segs) {
        if (!s || typeof s !== 'object') continue
        const text = String(s.text || '').trim()
        if (!text) continue
        const segType = String(s.segment_type || '').trim().toLowerCase()
        const badge = segType ? `<span class="seg-badge seg-badge-${escHtml(segType)}">${escHtml(segType)}</span>` : ''
        const dur = s.estimated_seconds ? `<span class="seg-dur">⏱ ${s.estimated_seconds}s</span>` : ''
        const diff = String(s.difficulty || '').trim().toLowerCase()
        const diffHtml = diff ? `<span class="seg-diff diff-${escHtml(diff)}">${escHtml(diff)}</span>` : ''
        const hint = String(s.interaction_hint || '').trim()
        const hintHtml = hint ? `<p class="seg-hint">💬 ${escHtml(hint)}</p>` : ''
        items.push(`<li class="seg-item">${badge}${dur}${diffHtml}<p class="seg-text">${escHtml(text)}</p>${hintHtml}${renderKnowledgeCard(s.knowledge_card)}</li>`)
      }
      if (!items.length) return ''
      return `<section class="segments-block"><h4>讲授分段</h4><ol class="segments">${items.join('')}</ol></section>`
    }

    function renderSlide(node, index) {
      const type = resolveType(node)
      const title = escHtml(node.title || `第${index}页`)
      const points = extractKeyPoints(node)
      const num = `<div class="slide-num">${index}</div>`

      if (type === 'cover') {
        const sub = escHtml(String(node.subtitle || node.content || node.summary || '').trim())
        const inner = `<div class="cover-inner"><h1>${title}</h1>${sub ? `<p class="subtitle">${sub}</p>` : ''}${points.length ? `<ul class="cover-points">${renderKeyPoints(points, 'cover-points', false)}</ul>` : ''}</div>`
        return `<div class="slide cover-slide">${num}${inner}</div>`
      }
      if (type === 'section') {
        const children = toList(node.children)
        const items = children.length ? children : points
        const sub = escHtml(String(node.content || node.summary || '').trim())
        const inner = `<div class="section-inner"><h2>${title}</h2><div class="divider"></div>${sub ? `<p class="section-sub">${sub}</p>` : ''}${items.length ? `<ul class="section-list">${renderKeyPoints(items, 'section-list', true)}</ul>` : ''}</div>`
        return `<div class="slide section-slide">${num}${inner}</div>`
      }
      if (type === 'quiz') {
        let qs = toList(node.questions || node.interactive_questions)
        if (!qs.length) qs = points.length ? points : extractKeyPoints(node)
        return `<div class="slide quiz-slide">${num}<h2>💡 ${title}</h2><ol class="questions">${qs.map((q) => `<li class="q-item">${escHtml(q)}</li>`).join('')}</ol></div>`
      }
      if (type === 'summary') {
        return `<div class="slide summary-slide">${num}<h2>📌 ${title}</h2><ul class="key-points">${renderKeyPoints(points.slice(0, 10), 'key-points', false)}</ul>${renderSegments(node)}</div>`
      }
      // content（通用）
      const bodyParts = []
      for (const key of ['content', 'script', 'summary']) {
        const val = node[key]
        if (typeof val === 'string' && val.trim()) bodyParts.push(`<p>${escHtml(val)}</p>`)
        else if (Array.isArray(val) && val.length) {
          bodyParts.push(`<ul>${val.map((v) => `<li>${escHtml(v)}</li>`).join('')}</ul>`)
        }
      }
      return `<div class="slide content-slide">${num}<h2>${title}</h2>${points.length ? `<ul class="key-points">${renderKeyPoints(points, 'key-points', false)}</ul>` : ''}${bodyParts.length ? `<div class="body">${bodyParts.join('')}</div>` : ''}${renderSegments(node)}</div>`
    }

    const PREVIEW_CSS = `
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f0f2f5; color: #1a1a2e; padding: 20px; }
  .presentation { max-width: 1100px; margin: 0 auto; }
  .slide { background: #fff; border-radius: 14px; box-shadow: 0 2px 14px rgba(0,0,0,0.08); padding: 44px 52px 48px; margin-bottom: 24px; position: relative; min-height: 320px; overflow: hidden; }
  .slide-num { position: absolute; top: 16px; right: 20px; z-index: 2; font-size: 13px; color: rgba(0,0,0,0.4); background: rgba(0,0,0,0.06); padding: 2px 10px; border-radius: 999px; }
  .slide h1, .slide h2 { padding-right: 52px; }
  h1 { font-size: 34px; line-height: 1.3; }
  h2 { font-size: 24px; margin-bottom: 16px; color: #1a1a2e; line-height: 1.4; }
  .cover-slide, .title-slide { background: linear-gradient(135deg, #4361ee 0%, #7209b7 100%); color: #fff; display: flex; align-items: center; justify-content: center; text-align: center; }
  .cover-slide .slide-num, .title-slide .slide-num { color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.16); }
  .cover-inner { max-width: 720px; margin: 0 auto; }
  .cover-slide h1, .title-slide h1 { color: #fff; margin-bottom: 18px; }
  .cover-slide .subtitle, .title-slide .subtitle { font-size: 19px; color: rgba(255,255,255,0.85); }
  .cover-points { list-style: none; margin: 28px auto 0; display: grid; gap: 10px; max-width: 520px; }
  .cover-points li { background: rgba(255,255,255,0.14); border-radius: 10px; padding: 10px 18px; font-size: 15px; line-height: 1.6; }
  .section-slide { background: linear-gradient(135deg, #f72585 0%, #b5179e 100%); color: #fff; }
  .section-slide .slide-num { color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.16); }
  .section-inner { max-width: 720px; margin: 0 auto; }
  .section-slide h2 { color: #fff; }
  .section-slide .divider { width: 60px; height: 4px; background: rgba(255,255,255,0.9); margin: 20px 0; border-radius: 2px; }
  .section-sub { font-size: 16px; color: rgba(255,255,255,0.85); margin-bottom: 18px; line-height: 1.6; }
  .section-list { list-style: none; display: grid; gap: 10px; margin-top: 8px; }
  .section-list li { display: flex; align-items: center; gap: 12px; background: rgba(255,255,255,0.14); border-radius: 10px; padding: 10px 16px; font-size: 15px; line-height: 1.5; }
  .section-list .kp-idx { flex-shrink: 0; width: 24px; height: 24px; border-radius: 50%; background: #fff; color: #b5179e; font-weight: 700; font-size: 12px; display: flex; align-items: center; justify-content: center; }
  .quiz-slide { border-left: 5px solid #f72585; background: linear-gradient(180deg, #fff, #fff5f9); }
  .questions { list-style: none; counter-reset: q; margin-top: 8px; display: grid; gap: 12px; }
  .questions .q-item { counter-increment: q; position: relative; padding: 14px 18px 14px 52px; background: #fff; border: 1px solid #f0d7e6; border-radius: 12px; font-size: 15px; line-height: 1.6; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
  .questions .q-item::before { content: counter(q); position: absolute; left: 16px; top: 14px; width: 24px; height: 24px; border-radius: 50%; background: #f72585; color: #fff; font-weight: 700; font-size: 13px; display: flex; align-items: center; justify-content: center; }
  .summary-slide { border-left: 5px solid #4361ee; background: linear-gradient(180deg, #f8f9ff, #fff); }
  .key-points { list-style: none; display: grid; gap: 10px; margin-top: 12px; }
  .key-points li { position: relative; padding: 10px 16px 10px 40px; background: #eef1ff; border-radius: 10px; font-size: 15px; line-height: 1.6; }
  .key-points li::before { content: "\\2713"; position: absolute; left: 14px; top: 10px; color: #4361ee; font-weight: 700; }
  .body { font-size: 15px; line-height: 1.85; color: #333; margin-top: 10px; }
  .body p { margin-bottom: 8px; }
  .body ul { padding-left: 22px; }
  .body li { margin-bottom: 4px; }
  .segments-block { margin-top: 20px; padding-top: 16px; border-top: 1px dashed #d4d9e4; }
  .segments-block h4 { font-size: 14px; color: #5f6c84; margin-bottom: 10px; letter-spacing: 0.02em; }
  .segments { list-style: none; display: grid; gap: 10px; }
  .seg-item { padding: 12px 16px; background: #f6f8fb; border-radius: 10px; border-left: 3px solid #a9b4c8; }
  .seg-badge { display: inline-block; font-size: 11px; padding: 2px 10px; border-radius: 999px; font-weight: 600; text-transform: capitalize; }
  .seg-badge-opening { background: #e3f2fd; color: #1565c0; }
  .seg-badge-explanation { background: #f3e5f5; color: #7b1fa2; }
  .seg-badge-example { background: #e8f5e9; color: #2e7d32; }
  .seg-badge-interaction { background: #fff3e0; color: #e65100; }
  .seg-badge-transition { background: #fce4ec; color: #c62828; }
  .seg-badge-summary { background: #e8eaf6; color: #283593; }
  .seg-dur { display: inline-block; font-size: 12px; color: #667; margin-left: 8px; }
  .seg-diff { display: inline-block; font-size: 11px; padding: 1px 8px; border-radius: 999px; margin-left: 6px; text-transform: capitalize; }
  .diff-easy { background: #e8f5e9; color: #2e7d32; }
  .diff-medium { background: #fff8e1; color: #f57f17; }
  .diff-hard { background: #ffebee; color: #c62828; }
  .seg-text { margin-top: 6px; font-size: 14px; line-height: 1.7; color: #2b3140; }
  .seg-hint { margin-top: 6px; font-size: 12px; color: #7a5b00; background: #fff8e1; display: inline-block; padding: 3px 10px; border-radius: 8px; }
  .knowledge-card { margin-top: 8px; padding: 10px 12px; background: #fff; border: 1px solid #dfe6f0; border-radius: 10px; }
  .kc-term { font-size: 13px; color: #2f5d8f; display: block; margin-bottom: 4px; }
  .kc-def { font-size: 13px; color: #445; line-height: 1.6; }
  .kc-formula { font-size: 12px; background: #f4f6fa; padding: 6px 10px; border-radius: 6px; overflow-x: auto; margin-top: 4px; }
  .kc-tags { display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
  .kc-tags span { font-size: 11px; background: #eef3fa; color: #445; padding: 1px 8px; border-radius: 999px; }
  .empty-state { text-align: center; padding: 60px 20px; color: #94a3b8; font-size: 15px; }
`

    function renderPreviewHtml(nodes, courseName) {
      const slides = (Array.isArray(nodes) ? nodes : []).map(renderSlide).join('\n')
        || '<div class="empty-state">暂无节点数据，请先完成 S3 讲稿生成。</div>'
      return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${escHtml(courseName || '课件预览')}</title>
<style>
${PREVIEW_CSS}
</style>
</head>
<body>
<div class="presentation">
${slides}
</div>
</body>
</html>`
    }

    // ================================================================
    // gen API（S3 生成 + 修改 + 预览）
    // ================================================================

    if (pathname === '/api/v1/gen/create' && method === 'POST') {
      const body = parseJsonBody(options)
      const taskId = uid('gentask')
      const genId = uid('gen')
      const courseId = cleanText(body.course_id) || store.teacher.coursewares?.[0]?.id || 'demo_course'
      // 存入生成任务，模拟异步生成
      store.genTasks = store.genTasks || {}
      store.genTasks[taskId] = {
        task_id: taskId,
        generation_id: genId,
        status: 'processing',
        progress: 0,
        stage_text: '正在构建大纲…',
        nodes: [],
        // 回显 S1 意图 / S2 证据（供测试断言 S1→S4 链路透传）
        intent: body.intent || null,
        evidence_packet: body.evidence_packet || null,
        created_at: nowIso()
      }

      // 预创建版本快照（供 S4 版本/导出 mock 使用）
      store.versionSnapshots = store.versionSnapshots || {}
      store.versionSnapshots[genId] = store.versionSnapshots[genId] || []
      store.versionSnapshots[genId].push({
        version_number: 1,
        id: uid('ver'),
        nodes_snapshot: [],
        summary: '初始版本',
        locked: false,
        created_at: nowIso()
      })

      // 异步模拟完成
      if (typeof window !== 'undefined') {
        setTimeout(() => {
          const task = store.genTasks[taskId]
          if (!task) return
          task.status = 'completed'
          task.progress = 1
          task.stage_text = '生成完成'
          task.nodes = [
            { node_id: 'node_001', title: '课程导入', node_type: 'cover', summary: '概念引入与学习目标', subtitle: 'AI-PPT 课件演示', content: '本节课我们将学习核心概念，了解其在实际中的应用场景。', status: 'completed', key_points: ['掌握核心概念', '了解应用场景', '完成课堂练习'] },
            { node_id: 'node_002', title: '核心知识点', node_type: 'section', summary: '通过示例讲解核心知识点', content: '核心知识点包括定义、性质和常见应用，下面通过具体案例来说明。', status: 'completed', children: ['定义与性质', '典型示例', '易错提醒'] },
            { node_id: 'node_003', title: '练习与总结', node_type: 'summary', summary: '做题演练并总结易错点', content: '通过两道练习题巩固所学内容，并总结常见易错点。', status: 'completed', core_points: ['易错点一：单位换算', '易错点二：符号混淆', '解题思路三步走'], segments: [{ segment_id: 'seg_1', text: '先回顾上节概念，进入练习环节。', node_id: 'node_003', segment_type: 'opening', estimated_seconds: 25, difficulty: 'easy', interaction_hint: '提问：上节课的关键公式是什么？', knowledge_card: { term: '易错提醒', definition: '计算时注意单位统一', formula: '', tags: ['exam'] } }] }
          ]
          // 同步更新版本快照（供 S4 版本管理/导出使用）
          if (store.versionSnapshots?.[genId]?.length > 0) {
            const latest = store.versionSnapshots[genId][store.versionSnapshots[genId].length - 1]
            latest.nodes_snapshot = deepClone(task.nodes)
          }
          persistMockStore()
        }, 3000)
      }

      return ok({
        task_id: taskId,
        generation_id: genId,
        status: 'processing',
        progress: 0,
        stage_text: '正在构建大纲…'
      })
    }

    if (pathname.startsWith('/api/v1/gen/status/') && method === 'GET') {
      const taskId = decodeURIComponent(pathname.split('/').pop() || '')
      store.genTasks = store.genTasks || {}
      const task = store.genTasks[taskId]
      if (!task) {
        return ok({ status: 'unknown', error: '任务不存在' })
      }
      return ok({
        task_id: task.task_id,
        generation_id: task.generation_id,
        status: task.status,
        progress: task.progress,
        stage_text: task.stage_text,
        nodes: task.nodes || [],
        intent: task.intent || null,
        evidence_packet: task.evidence_packet || null,
        error: task.error || null
      })
    }

    if (pathname === '/api/v1/gen/preview' && method === 'POST') {
      const body = parseJsonBody(options)
      const genId = cleanText(body.gen_id)
      const courseName = cleanText(body.course_name) || '课件预览'
      let nodes = Array.isArray(body.nodes) ? body.nodes : []
      let versionNumber = null
      let snapshotSummary = ''

      // 版本快照预览：按 gen_id 从 mock 版本快照恢复节点（缺省最新版）
      if (genId && !nodes.length) {
        const snapshots = (store.versionSnapshots && store.versionSnapshots[genId]) || []
        const target = body.version
          ? snapshots.find((s) => s.version_number === Number(body.version))
          : snapshots[snapshots.length - 1]
        if (target) {
          nodes = Array.isArray(target.nodes_snapshot) ? deepClone(target.nodes_snapshot) : []
          versionNumber = target.version_number
          snapshotSummary = target.summary || ''
        }
      }

      const html = renderPreviewHtml(nodes, snapshotSummary && snapshotSummary !== '初始版本' ? snapshotSummary : courseName)
      return ok({
        html,
        node_count: nodes.length,
        generation_id: genId || null,
        version_number: versionNumber,
        nodes
      })
    }

    if (pathname === '/api/v1/gen/modify' && method === 'POST') {
      const body = parseJsonBody(options)
      const commands = Array.isArray(body.commands) ? body.commands : []
      const nodes = Array.isArray(body.nodes) ? deepClone(body.nodes) : []

      commands.forEach((cmd) => {
        if (cmd.type === 'update_node' && cmd.node_id) {
          const target = nodes.find(n => n.node_id === cmd.node_id || n.id === cmd.node_id)
          if (target) {
            if (cmd.patch) {
              Object.assign(target, cmd.patch)
            } else {
              target.content = cmd.content || target.content
              target.title = cmd.title || target.title
              target.summary = cmd.summary || target.summary
            }
          }
        }
        if (cmd.type === 'add_node' && cmd.after_node_id) {
          const idx = nodes.findIndex(n => n.node_id === cmd.after_node_id)
          const newNode = { node_id: uid('node'), title: cmd.title || '新节点', content: cmd.content || '', summary: cmd.summary || '', status: 'completed' }
          if (idx >= 0) nodes.splice(idx + 1, 0, newNode)
          else nodes.push(newNode)
        }
        if (cmd.type === 'delete_node' && cmd.node_id) {
          const idx = nodes.findIndex(n => n.node_id === cmd.node_id)
          if (idx >= 0) nodes.splice(idx, 1)
        }
        if (cmd.type === 'swap_nodes' && Array.isArray(cmd.node_ids) && cmd.node_ids.length >= 2) {
          const [a, b] = cmd.node_ids
          const ia = nodes.findIndex(n => n.node_id === a)
          const ib = nodes.findIndex(n => n.node_id === b)
          if (ia >= 0 && ib >= 0) [nodes[ia], nodes[ib]] = [nodes[ib], nodes[ia]]
        }
      })

      return ok({ nodes, commands_applied: commands.length })
    }

    if (pathname === '/api/v1/teacher/recommend' && method === 'POST') {
      return handleRecommendRequest(options)
    }

    // ================================================================
    // version API（S4 版本管理）
    // ================================================================

    if (pathname.startsWith('/api/v1/version/') && method === 'GET') {
      // /api/v1/version/{gen_id}/history
      // /api/v1/version/{gen_id}/diff?v1=1&v2=2
      // /api/v1/version/{gen_id}?v=N
      const segments = pathname.split('/').filter(Boolean)
      const genId = segments[3] || ''
      const action = segments[4] || ''

      if (action === 'history') {
        const snapshots = store.versionSnapshots?.[genId] || []
        return ok({
          versions: snapshots.map(s => ({
            version_number: s.version_number,
            id: s.id,
            summary: s.summary,
            locked: s.locked || false,
            created_at: s.created_at
          }))
        })
      }

      if (action === 'diff') {
        const v1 = parseInt(searchParams.get('v1') || '0', 10)
        const v2 = parseInt(searchParams.get('v2') || '0', 10)
        const snapshots = store.versionSnapshots?.[genId] || []
        const s1 = snapshots.find(s => s.version_number === v1)
        const s2 = snapshots.find(s => s.version_number === v2)
        return ok({
          v1: { version_number: v1, nodes_count: s1?.nodes_snapshot?.length || 0 },
          v2: { version_number: v2, nodes_count: s2?.nodes_snapshot?.length || 0 },
          changes: [],
          summary: `${v1} → ${v2} 对比`
        })
      }

      if (!action) {
        // 加载指定版本 /api/v1/version/{gen_id}
        const v = parseInt(searchParams.get('v') || '0', 10)
        const snapshots = store.versionSnapshots?.[genId] || []
        const snap = v ? snapshots.find(s => s.version_number === v) : snapshots[snapshots.length - 1]
        if (!snap) return ok({ version_number: 1, id: uid('ver'), nodes_snapshot: [], summary: '初始版本', locked: false, created_at: nowIso() })
        return ok({
          version_number: snap.version_number,
          id: snap.id,
          nodes_snapshot: snap.nodes_snapshot || [],
          summary: snap.summary,
          locked: snap.locked || false,
          created_at: snap.created_at
        })
      }
    }

    if (pathname.startsWith('/api/v1/version/') && method === 'POST') {
      const segments = pathname.split('/').filter(Boolean)
      const genId = segments[3] || ''
      const action = segments[4] || ''

      if (action === 'rollback') {
        const body = parseJsonBody(options)
        const targetVersion = body.target_version || 1
        store.versionSnapshots = store.versionSnapshots || {}
        store.versionSnapshots[genId] = store.versionSnapshots[genId] || []
        const snapshots = store.versionSnapshots[genId]
        const target = snapshots.find(s => s.version_number === targetVersion)
        if (!target) return ok({ current_version: targetVersion, status: 'done' })
        // 回滚：创建新版本，内容来自目标版本
        const newVer = {
          version_number: snapshots.length + 1,
          id: uid('ver'),
          nodes_snapshot: deepClone(target.nodes_snapshot || []),
          summary: `回滚到版本 ${targetVersion}`,
          locked: false,
          created_at: nowIso()
        }
        snapshots.push(newVer)
        persistMockStore()
        return ok({ current_version: newVer.version_number, status: 'done' })
      }

      if (action === 'lock') {
        store.versionSnapshots = store.versionSnapshots || {}
        store.versionSnapshots[genId] = store.versionSnapshots[genId] || []
        const snapshots = store.versionSnapshots[genId]
        if (snapshots.length > 0) {
          snapshots[snapshots.length - 1].locked = true
        }
        persistMockStore()
        return ok({ version: snapshots.length, locked: true })
      }
    }

    // ================================================================
    // export API（S4 异步导出）
    // ================================================================

    if (pathname.startsWith('/api/v1/export/') && method === 'POST') {
      const segments = pathname.split('/').filter(Boolean)
      const genId = segments[3] || ''
      const body = parseJsonBody(options)
      const jobId = uid('exp')

      store.exportJobs = store.exportJobs || {}
      store.exportJobs[jobId] = {
        job_id: jobId,
        generation_id: genId,
        format: body.format || 'pptx',
        status: 'pending',
        download_url: '',
        error: null,
        created_at: nowIso()
      }

      // 模拟异步完成；下载文件在 status 轮询时按需生成（Blob URL，刷新后自动重建，不持久化死链）
      if (typeof window !== 'undefined') {
        setTimeout(() => {
          const job = store.exportJobs[jobId]
          if (!job) return
          job.status = 'done'
          persistMockStore()
        }, 2000)
      }

      persistMockStore()
      return ok({
        job_id: jobId,
        status: 'pending',
        download_url: null,
        error: null
      })
    }

    if (pathname.startsWith('/api/v1/export/status/') && method === 'GET') {
      const jobId = decodeURIComponent(pathname.split('/').pop() || '')
      const job = store.exportJobs?.[jobId]
      if (!job) {
        return ok({
          job_id: jobId,
          status: 'failed',
          download_url: null,
          error: '导出任务不存在'
        })
      }
      // 完成时按需生成真实可下载文件（浏览器返回 Blob URL；无 Blob 环境回退后端下载路径）
      const downloadUrl = job.status === 'done' ? mockBuildExportDownloadUrl(store, job) : ''
      return ok({
        job_id: job.job_id,
        status: job.status,
        download_url: downloadUrl,
        error: job.error || null
      })
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

<template>
  <section class="platform-panel">
    <div class="platform-toolbar">
      <div>
        <div class="toolbar-label">平台工作台</div>
        <h3>用户、课程、班级与选课统一管理</h3>
      </div>
      <div class="toolbar-actions">
        <button class="ghost-btn" :disabled="syncState.submitting" @click="openSyncForm('user')">
          同步用户
        </button>
        <button class="ghost-btn" :disabled="syncState.submitting" @click="openSyncForm('course')">
          同步课程
        </button>
        <button class="ghost-btn" :disabled="refreshing" @click="refreshCurrentView">
          {{ refreshing ? '刷新中...' : '刷新数据' }}
        </button>
      </div>
    </div>

    <div v-if="feedback.message" class="feedback-banner" :class="feedback.type">
      {{ feedback.message }}
    </div>

    <div v-if="syncState.visible" class="form-shell sync-shell">
      <div class="form-head">
        <h4>{{ syncState.type === 'user' ? '同步平台用户' : '同步平台课程' }}</h4>
        <button class="text-btn" @click="closeSyncForm">收起</button>
      </div>

      <div v-if="syncState.type === 'user'" class="form-grid">
        <label>
          <span>平台标识</span>
          <input v-model="syncState.payload.platformId" class="text-input" placeholder="demo-platform" />
        </label>
        <label>
          <span>外部用户ID</span>
          <input v-model="syncState.payload.userId" class="text-input" placeholder="teacher-001 / student-001" />
        </label>
        <label>
          <span>用户名称</span>
          <input v-model="syncState.payload.userName" class="text-input" placeholder="请输入姓名" />
        </label>
        <label>
          <span>角色</span>
          <select v-model="syncState.payload.role" class="select-input">
            <option value="student">student</option>
            <option value="teacher">teacher</option>
            <option value="assistant">assistant</option>
          </select>
        </label>
        <label>
          <span>学校编码</span>
          <input v-model="syncState.payload.schoolId" class="text-input" placeholder="SCH-01" />
        </label>
        <label>
          <span>学校名称</span>
          <input v-model="syncState.payload.schoolName" class="text-input" placeholder="请输入学校名称" />
        </label>
        <label>
          <span>专业</span>
          <input v-model="syncState.payload.major" class="text-input" placeholder="学生可填专业" />
        </label>
        <label>
          <span>年级</span>
          <input v-model="syncState.payload.grade" class="text-input" placeholder="2026 / 教师" />
        </label>
        <label>
          <span>班级外部ID</span>
          <input v-model="syncState.payload.classId" class="text-input" placeholder="学生可选填" />
        </label>
        <label>
          <span>班级名称</span>
          <input v-model="syncState.payload.className" class="text-input" placeholder="学生可选填" />
        </label>
        <label>
          <span>邮箱</span>
          <input v-model="syncState.payload.email" class="text-input" placeholder="user@example.com" />
        </label>
        <label>
          <span>手机号</span>
          <input v-model="syncState.payload.phone" class="text-input" placeholder="13800000000" />
        </label>
      </div>

      <div v-else class="form-grid">
        <label>
          <span>平台标识</span>
          <input v-model="syncState.payload.platformId" class="text-input" placeholder="demo-platform" />
        </label>
        <label>
          <span>外部课程ID</span>
          <input v-model="syncState.payload.courseId" class="text-input" placeholder="course-001" />
        </label>
        <label>
          <span>课程名称</span>
          <input v-model="syncState.payload.courseName" class="text-input" placeholder="请输入课程名称" />
        </label>
        <label>
          <span>教师外部ID</span>
          <input v-model="syncState.payload.teacherExternalId" class="text-input" placeholder="teacher-001" />
        </label>
        <label>
          <span>教师姓名</span>
          <input v-model="syncState.payload.teacherName" class="text-input" placeholder="联调教师" />
        </label>
        <label>
          <span>学校编码</span>
          <input v-model="syncState.payload.schoolId" class="text-input" placeholder="SCH-01" />
        </label>
        <label>
          <span>学校名称</span>
          <input v-model="syncState.payload.schoolName" class="text-input" placeholder="请输入学校名称" />
        </label>
        <label>
          <span>学期</span>
          <input v-model="syncState.payload.term" class="text-input" placeholder="2026-Spring" />
        </label>
        <label>
          <span>学分</span>
          <input v-model.number="syncState.payload.credit" type="number" min="0" step="0.5" class="text-input" />
        </label>
        <label>
          <span>学时</span>
          <input v-model.number="syncState.payload.period" type="number" min="0" class="text-input" />
        </label>
        <label>
          <span>班级外部ID</span>
          <input v-model="syncState.payload.classId" class="text-input" placeholder="class-001" />
        </label>
        <label>
          <span>班级名称</span>
          <input v-model="syncState.payload.className" class="text-input" placeholder="默认班级" />
        </label>
      </div>

      <div class="form-actions">
        <button class="ghost-btn" :disabled="syncState.submitting" @click="closeSyncForm">取消</button>
        <button class="primary-btn" :disabled="syncState.submitting" @click="submitSyncForm">
          {{ syncState.submitting ? '同步中...' : '开始同步' }}
        </button>
      </div>
    </div>

    <div class="view-switcher">
      <button
        v-for="view in views"
        :key="view.key"
        class="switch-btn"
        :class="{ active: activeView === view.key }"
        @click="changeView(view.key)"
      >
        {{ view.label }}
      </button>
    </div>

    <div v-if="activeView === 'overview'" class="overview-board">
      <div class="stats-grid">
        <article v-for="card in overviewCards" :key="card.key" class="stat-card stat-card-action" @click="openOverviewList(card.key)">
          <span class="stat-label">{{ card.label }}</span>
          <strong class="stat-value">{{ card.value }}</strong>
          <span class="stat-hint">{{ card.hint }}</span>
        </article>
      </div>

      <div class="recent-grid">
        <article class="recent-card">
          <div class="card-head">
            <h4>最近用户</h4>
            <span>{{ overview.recentUsers.length }}</span>
          </div>
          <div v-if="overview.recentUsers.length" class="recent-list">
            <button
              v-for="user in overview.recentUsers"
              :key="user.userId"
              class="recent-item"
              @click="openOverviewDetail('users', user.userId)"
            >
              <strong>{{ displayText(user.displayName || user.externalId || user.userId, '未命名用户') }}</strong>
              <span>{{ displayText(user.role, 'unknown') }} · {{ displayText(user.orgCode, '未分配组织') }}</span>
            </button>
          </div>
          <div v-else class="empty-tip">暂无用户数据</div>
        </article>

        <article class="recent-card">
          <div class="card-head">
            <h4>最近课程</h4>
            <span>{{ overview.recentCourses.length }}</span>
          </div>
          <div v-if="overview.recentCourses.length" class="recent-list">
            <button
              v-for="course in overview.recentCourses"
              :key="course.courseId"
              class="recent-item"
              @click="openOverviewDetail('courses', course.courseId)"
            >
              <strong>{{ displayText(course.title || course.externalId || course.courseId, '未命名课程') }}</strong>
              <span>{{ displayText(course.status, 'unknown') }} · {{ displayText(course.semester, '未设学期') }}</span>
            </button>
          </div>
          <div v-else class="empty-tip">暂无课程数据</div>
        </article>

        <article class="recent-card">
          <div class="card-head">
            <h4>最近班级</h4>
            <span>{{ overview.recentClasses.length }}</span>
          </div>
          <div v-if="overview.recentClasses.length" class="recent-list">
            <button
              v-for="classItem in overview.recentClasses"
              :key="classItem.classId"
              class="recent-item"
              @click="openOverviewDetail('classes', classItem.classId)"
            >
              <strong>{{ displayText(classItem.className || classItem.externalId || classItem.classId, '未命名班级') }}</strong>
              <span>{{ displayText(classItem.status, 'unknown') }} · {{ displayText(classItem.semester, '未设学期') }}</span>
            </button>
          </div>
          <div v-else class="empty-tip">暂无班级数据</div>
        </article>

        <article class="recent-card">
          <div class="card-head">
            <h4>最近选课</h4>
            <span>{{ overview.recentEnrollments.length }}</span>
          </div>
          <div v-if="overview.recentEnrollments.length" class="recent-list">
            <button
              v-for="enrollment in overview.recentEnrollments"
              :key="enrollment.enrollmentId"
              class="recent-item"
              @click="openOverviewDetail('enrollments', enrollment.enrollmentId)"
            >
              <strong>{{ displayText(enrollment.externalId || enrollment.enrollmentId, '未命名选课') }}</strong>
              <span>{{ displayText(enrollment.role, 'unknown') }} · {{ displayText(enrollment.status, 'unknown') }}</span>
            </button>
          </div>
          <div v-else class="empty-tip">暂无选课数据</div>
        </article>
      </div>
    </div>

    <div v-else class="entity-board">
      <div v-if="activeView === 'users'" class="contract-note">
        当前用户页以平台同步结果为准，暂不提供前端直接新建/编辑/删除用户。可通过上方“同步用户”入口补录教师或学生。
      </div>

      <div class="entity-toolbar">
        <div class="filter-row">
          <input v-model="activeFilters.keyword" class="text-input" placeholder="关键词搜索" @keyup.enter="searchCurrentView" />

          <select v-if="activeView === 'users'" v-model="activeFilters.role" class="select-input" @change="searchCurrentView">
            <option value="">全部角色</option>
            <option value="student">学生</option>
            <option value="teacher">教师</option>
            <option value="assistant">助教</option>
          </select>

          <select v-if="activeView === 'courses' || activeView === 'classes' || activeView === 'enrollments'" v-model="activeFilters.status" class="select-input" @change="searchCurrentView">
            <option value="">全部状态</option>
            <option value="active">active</option>
            <option value="inactive">inactive</option>
            <option value="draft">draft</option>
            <option value="archived">archived</option>
            <option value="completed">completed</option>
          </select>

          <select v-if="activeView === 'enrollments'" v-model="activeFilters.role" class="select-input" @change="searchCurrentView">
            <option value="">全部身份</option>
            <option value="student">student</option>
            <option value="teacher">teacher</option>
            <option value="assistant">assistant</option>
          </select>

          <input v-if="activeView === 'users' || activeView === 'courses'" v-model="activeFilters.orgCode" class="text-input narrow" placeholder="组织编码" @keyup.enter="searchCurrentView" />

          <select v-if="activeView === 'courses' || activeView === 'classes'" v-model="activeFilters.teacherId" class="select-input" @change="searchCurrentView">
            <option value="">全部教师</option>
            <option v-for="teacher in teacherLookup" :key="teacher.userId" :value="teacher.userId">{{ displayText(teacher.displayName || teacher.externalId, '未命名教师') }}</option>
          </select>

          <select v-if="activeView === 'classes' || activeView === 'enrollments'" v-model="activeFilters.courseId" class="select-input" @change="searchCurrentView">
            <option value="">全部课程</option>
            <option v-for="course in courseLookup" :key="course.courseId" :value="course.courseId">{{ displayText(course.title || course.externalId, '未命名课程') }}</option>
          </select>

          <select v-if="activeView === 'enrollments'" v-model="activeFilters.classId" class="select-input" @change="searchCurrentView">
            <option value="">全部班级</option>
            <option v-for="classItem in classLookup" :key="classItem.classId" :value="classItem.classId">{{ displayText(classItem.className || classItem.externalId, '未命名班级') }}</option>
          </select>

          <select v-if="activeView === 'enrollments'" v-model="activeFilters.userId" class="select-input" @change="searchCurrentView">
            <option value="">全部用户</option>
            <option v-for="user in userLookup" :key="user.userId" :value="user.userId">{{ displayText(user.displayName || user.externalId, '未命名用户') }}</option>
          </select>
        </div>

        <div class="action-row">
          <button class="ghost-btn" :disabled="loading" @click="searchCurrentView">查询</button>
          <button class="ghost-btn" :disabled="loading" @click="resetCurrentFilters">重置</button>
          <button v-if="activeView !== 'users'" class="primary-btn" @click="openCreateForm">新建{{ activeLabel }}</button>
        </div>
      </div>

      <div v-if="formState.visible" class="form-shell">
        <div class="form-head">
          <h4>{{ formState.mode === 'create' ? '新建' : '编辑' }}{{ activeLabel }}</h4>
          <button class="text-btn" @click="closeForm">收起</button>
        </div>

        <div v-if="activeView === 'courses'" class="form-grid">
          <label>
            <span>平台标识</span>
            <input v-model="formState.payload.platformId" class="text-input" placeholder="demo-platform" />
          </label>
          <label>
            <span>外部课程ID</span>
            <input v-model="formState.payload.externalId" class="text-input" placeholder="course-xxx" />
          </label>
          <label>
            <span>课程编码</span>
            <input v-model="formState.payload.code" class="text-input" placeholder="COURSE-001" />
          </label>
          <label>
            <span>课程标题</span>
            <input v-model="formState.payload.title" class="text-input" placeholder="请输入课程标题" />
          </label>
          <label class="wide">
            <span>课程描述</span>
            <textarea v-model="formState.payload.description" class="text-area" placeholder="请输入课程描述"></textarea>
          </label>
          <label>
            <span>授课教师</span>
            <select v-model="formState.payload.teacherId" class="select-input">
              <option value="">请选择教师</option>
              <option v-for="teacher in teacherLookup" :key="teacher.userId" :value="teacher.userId">{{ displayText(teacher.displayName || teacher.externalId, '未命名教师') }}</option>
            </select>
          </label>
          <label>
            <span>组织编码</span>
            <input v-model="formState.payload.orgCode" class="text-input" placeholder="SCH-01" />
          </label>
          <label>
            <span>学校名称</span>
            <input v-model="formState.payload.schoolName" class="text-input" placeholder="请输入学校名称" />
          </label>
          <label>
            <span>学期</span>
            <input v-model="formState.payload.semester" class="text-input" placeholder="2026-Spring" />
          </label>
          <label>
            <span>学分</span>
            <input v-model.number="formState.payload.credit" type="number" min="0" step="0.5" class="text-input" />
          </label>
          <label>
            <span>学时</span>
            <input v-model.number="formState.payload.period" type="number" min="0" class="text-input" />
          </label>
          <label>
            <span>状态</span>
            <select v-model="formState.payload.status" class="select-input">
              <option value="draft">draft</option>
              <option value="active">active</option>
              <option value="inactive">inactive</option>
              <option value="archived">archived</option>
            </select>
          </label>
        </div>

        <div v-else-if="activeView === 'classes'" class="form-grid">
          <label>
            <span>平台标识</span>
            <input v-model="formState.payload.platformId" class="text-input" placeholder="demo-platform" />
          </label>
          <label>
            <span>外部班级ID</span>
            <input v-model="formState.payload.externalId" class="text-input" placeholder="class-xxx" />
          </label>
          <label>
            <span>所属课程</span>
            <select v-model="formState.payload.courseId" class="select-input">
              <option value="">请选择课程</option>
              <option v-for="course in courseLookup" :key="course.courseId" :value="course.courseId">{{ course.title || course.externalId }}</option>
            </select>
          </label>
          <label>
            <span>授课教师</span>
            <select v-model="formState.payload.teacherId" class="select-input">
              <option value="">请选择教师</option>
              <option v-for="teacher in teacherLookup" :key="teacher.userId" :value="teacher.userId">{{ displayText(teacher.displayName || teacher.externalId, '未命名教师') }}</option>
            </select>
          </label>
          <label>
            <span>班级名称</span>
            <input v-model="formState.payload.className" class="text-input" placeholder="请输入班级名称" />
          </label>
          <label>
            <span>班级编码</span>
            <input v-model="formState.payload.classCode" class="text-input" placeholder="CLASS-001" />
          </label>
          <label>
            <span>学期</span>
            <input v-model="formState.payload.semester" class="text-input" placeholder="2026-Spring" />
          </label>
          <label>
            <span>年级</span>
            <input v-model="formState.payload.grade" class="text-input" placeholder="2026" />
          </label>
          <label>
            <span>专业</span>
            <input v-model="formState.payload.major" class="text-input" placeholder="请输入专业" />
          </label>
          <label>
            <span>容量</span>
            <input v-model.number="formState.payload.capacity" type="number" min="0" class="text-input" />
          </label>
          <label>
            <span>状态</span>
            <select v-model="formState.payload.status" class="select-input">
              <option value="active">active</option>
              <option value="inactive">inactive</option>
              <option value="archived">archived</option>
            </select>
          </label>
        </div>

        <div v-else-if="activeView === 'enrollments'" class="form-grid">
          <label>
            <span>平台标识</span>
            <input v-model="formState.payload.platformId" class="text-input" placeholder="demo-platform" />
          </label>
          <label>
            <span>外部选课ID</span>
            <input v-model="formState.payload.externalId" class="text-input" placeholder="enrollment-xxx" />
          </label>
          <label>
            <span>所属课程</span>
            <select v-model="formState.payload.courseId" class="select-input">
              <option value="">请选择课程</option>
              <option v-for="course in courseLookup" :key="course.courseId" :value="course.courseId">{{ displayText(course.title || course.externalId, '未命名课程') }}</option>
            </select>
          </label>
          <label>
            <span>所属班级</span>
            <select v-model="formState.payload.classId" class="select-input">
              <option value="">请选择班级</option>
              <option v-for="classItem in classLookup" :key="classItem.classId" :value="classItem.classId">{{ displayText(classItem.className || classItem.externalId, '未命名班级') }}</option>
            </select>
          </label>
          <label>
            <span>用户</span>
            <select v-model="formState.payload.userId" class="select-input">
              <option value="">请选择用户</option>
              <option v-for="user in userLookup" :key="user.userId" :value="user.userId">{{ displayText(user.displayName || user.externalId, '未命名用户') }}</option>
            </select>
          </label>
          <label>
            <span>角色</span>
            <select v-model="formState.payload.role" class="select-input">
              <option value="student">student</option>
              <option value="teacher">teacher</option>
              <option value="assistant">assistant</option>
            </select>
          </label>
          <label>
            <span>状态</span>
            <select v-model="formState.payload.status" class="select-input">
              <option value="active">active</option>
              <option value="inactive">inactive</option>
              <option value="completed">completed</option>
              <option value="archived">archived</option>
            </select>
          </label>
        </div>

        <div class="form-actions">
          <button class="ghost-btn" :disabled="saving" @click="closeForm">取消</button>
          <button class="primary-btn" :disabled="saving" @click="submitForm">
            {{ saving ? '提交中...' : (formState.mode === 'create' ? '确认创建' : '保存修改') }}
          </button>
        </div>
      </div>

      <div class="entity-layout">
        <div class="list-pane">
          <div class="list-head">
            <div>
              <h4>{{ activeLabel }}列表</h4>
              <p>共 {{ currentPagination.total }} 条，当前第 {{ currentPagination.page }} / {{ Math.max(currentPagination.totalPages, 1) }} 页</p>
            </div>
          </div>

          <div v-if="loading" class="empty-tip">正在加载{{ activeLabel }}数据...</div>
          <div v-else-if="currentItems.length === 0" class="empty-tip">当前筛选条件下没有{{ activeLabel }}数据</div>
          <div v-else class="entity-list">
            <article
              v-for="item in currentItems"
              :key="getEntityKey(item)"
              class="entity-item"
              :class="{ selected: selectedEntityKey === getEntityKey(item) }"
              @click="selectEntity(item)"
            >
              <div class="entity-main">
                <div class="entity-title-row">
                  <strong>{{ getEntityTitle(item) }}</strong>
                  <span class="entity-badge">{{ getEntityBadge(item) }}</span>
                </div>
                <p>{{ getEntitySubtitle(item) }}</p>
                <div class="entity-meta">
                  <span v-for="meta in getEntityMeta(item)" :key="meta">{{ meta }}</span>
                </div>
              </div>
              <div v-if="activeView !== 'users'" class="entity-actions">
                <button class="mini-btn" @click.stop="openEditForm(item)">编辑</button>
                <button class="mini-btn danger" @click.stop="removeEntity(item)">删除</button>
              </div>
            </article>
          </div>

          <div class="pager" v-if="currentPagination.totalPages > 1">
            <button class="ghost-btn" :disabled="currentPagination.page <= 1 || loading" @click="changePage(currentPagination.page - 1)">上一页</button>
            <span>第 {{ currentPagination.page }} 页</span>
            <button class="ghost-btn" :disabled="currentPagination.page >= currentPagination.totalPages || loading" @click="changePage(currentPagination.page + 1)">下一页</button>
          </div>
        </div>

        <aside class="detail-pane">
          <div class="list-head">
            <div>
              <h4>{{ activeLabel }}详情</h4>
              <p>{{ detailLoading ? '正在加载详情...' : (detailSections.length ? '已加载详情' : '请选择左侧记录查看详情') }}</p>
            </div>
          </div>

          <div v-if="detailLoading" class="empty-tip">详情加载中...</div>
          <div v-else-if="!detailSections.length" class="empty-tip">暂无详情内容</div>
          <div v-else class="detail-sections">
            <section v-for="section in detailSections" :key="section.title" class="detail-card">
              <div class="card-head">
                <h5>{{ section.title }}</h5>
                <span v-if="section.count !== undefined">{{ section.count }}</span>
              </div>
              <div v-if="section.type === 'pairs'" class="pair-grid">
                <div v-for="pair in section.items" :key="pair.label" class="pair-item">
                  <span>{{ pair.label }}</span>
                  <strong>{{ pair.value }}</strong>
                </div>
              </div>
              <div v-else class="simple-list">
                <div v-for="row in section.items" :key="row.key" class="simple-row">
                  <strong>{{ row.title }}</strong>
                  <span>{{ row.subtitle }}</span>
                </div>
              </div>
            </section>
          </div>
        </aside>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { teacherV1Api } from '../../services/v1'

const emit = defineEmits(['summary-change'])

const views = [
  { key: 'overview', label: '平台总览' },
  { key: 'users', label: '平台用户' },
  { key: 'courses', label: '平台课程' },
  { key: 'classes', label: '平台班级' },
  { key: 'enrollments', label: '平台选课' }
]

const activeView = ref('overview')
const loading = ref(false)
const refreshing = ref(false)
const saving = ref(false)
const detailLoading = ref(false)
const feedback = reactive({ type: '', message: '' })
const overview = reactive({
  counts: { users: 0, courses: 0, classes: 0, enrollments: 0 },
  recentUsers: [],
  recentCourses: [],
  recentClasses: [],
  recentEnrollments: []
})

const items = reactive({
  users: [],
  courses: [],
  classes: [],
  enrollments: []
})

const pagination = reactive({
  users: { page: 1, pageSize: 20, total: 0, totalPages: 0 },
  courses: { page: 1, pageSize: 20, total: 0, totalPages: 0 },
  classes: { page: 1, pageSize: 20, total: 0, totalPages: 0 },
  enrollments: { page: 1, pageSize: 20, total: 0, totalPages: 0 }
})

const filters = reactive({
  users: { keyword: '', role: '', orgCode: '', page: 1, pageSize: 20 },
  courses: { keyword: '', status: '', orgCode: '', teacherId: '', page: 1, pageSize: 20 },
  classes: { keyword: '', status: '', teacherId: '', courseId: '', page: 1, pageSize: 20 },
  enrollments: { keyword: '', status: '', role: '', userId: '', classId: '', courseId: '', page: 1, pageSize: 20 }
})

const selectedEntityKey = ref('')
const detailState = ref(null)
const formState = reactive({
  visible: false,
  mode: 'create',
  entityKey: '',
  payload: {}
})
const syncState = reactive({
  visible: false,
  type: 'user',
  submitting: false,
  payload: {}
})

const activeLabel = computed(() => views.find((item) => item.key === activeView.value)?.label.replace('平台', '') || '平台')
const activeFilters = computed(() => filters[activeView.value] || {})
const currentItems = computed(() => items[activeView.value] || [])
const currentPagination = computed(() => pagination[activeView.value] || { page: 1, total: 0, totalPages: 0 })

const userLookup = computed(() => items.users)
const teacherLookup = computed(() => items.users.filter((item) => item.role === 'teacher' || item.role === 'assistant'))
const courseLookup = computed(() => items.courses)
const classLookup = computed(() => items.classes)

const overviewCards = computed(() => [
  { key: 'users', label: '平台用户', value: overview.counts.users || 0, hint: '查看用户列表与详情' },
  { key: 'courses', label: '平台课程', value: overview.counts.courses || 0, hint: '查看课程运营状态' },
  { key: 'classes', label: '平台班级', value: overview.counts.classes || 0, hint: '查看班级与成员分布' },
  { key: 'enrollments', label: '平台选课', value: overview.counts.enrollments || 0, hint: '查看选课关系明细' }
])

const detailSections = computed(() => buildDetailSections(activeView.value, detailState.value))

watch(activeView, async (view) => {
  formState.visible = false
  detailState.value = null
  selectedEntityKey.value = ''
  if (view === 'overview') {
    await loadOverview()
    return
  }
  await ensureLookupData(view)
  await loadList(view)
})

onMounted(async () => {
  await loadOverview()
  await ensureLookupData('courses')
})

async function changeView(view) {
  activeView.value = view
}

async function openOverviewList(view) {
  if (!view || view === 'overview') {
    return
  }
  activeView.value = view
}

async function refreshCurrentView() {
  refreshing.value = true
  try {
    if (activeView.value === 'overview') {
      await loadOverview()
      return
    }
    await ensureLookupData(activeView.value, true)
    await loadList(activeView.value)
  } catch (error) {
    setFeedback('error', `刷新失败：${error.message}`)
  } finally {
    refreshing.value = false
  }
}

async function searchCurrentView() {
  try {
    if (activeView.value === 'overview') {
      await loadOverview()
      return
    }
    activeFilters.value.page = 1
    await loadList(activeView.value)
  } catch (error) {
    setFeedback('error', `查询失败：${error.message}`)
  }
}

async function changePage(page) {
  try {
    activeFilters.value.page = page
    await loadList(activeView.value)
  } catch (error) {
    setFeedback('error', `翻页失败：${error.message}`)
  }
}

async function resetCurrentFilters() {
  try {
    const defaults = defaultFilters(activeView.value)
    Object.assign(activeFilters.value, defaults)
    await loadList(activeView.value)
  } catch (error) {
    setFeedback('error', `重置筛选失败：${error.message}`)
  }
}

async function loadOverview() {
  try {
    const response = await teacherV1Api.platform.getOverview()
    const data = response.data || {}
    overview.counts = {
      users: Number(data.counts?.users || 0),
      courses: Number(data.counts?.courses || 0),
      classes: Number(data.counts?.classes || 0),
      enrollments: Number(data.counts?.enrollments || 0)
    }
    overview.recentUsers = data.recentUsers || []
    overview.recentCourses = data.recentCourses || []
    overview.recentClasses = data.recentClasses || []
    overview.recentEnrollments = data.recentEnrollments || []
    emit('summary-change', overview.counts)
  } catch (error) {
    setFeedback('error', `平台总览加载失败：${error.message}`)
    throw error
  }
}

async function loadList(view) {
  loading.value = true
  try {
    const response = await getListHandler(view)(sanitizeParams(activeFilters.value))
    const data = response.data || {}
    items[view] = data.items || []
    pagination[view] = {
      page: Number(data.pagination?.page || activeFilters.value.page || 1),
      pageSize: Number(data.pagination?.pageSize || activeFilters.value.pageSize || 20),
      total: Number(data.pagination?.total || 0),
      totalPages: Number(data.pagination?.totalPages || 0)
    }
    if (currentItems.value.length === 0 && activeView.value === view) {
      setFeedback('info', `${views.find((item) => item.key === view)?.label || '数据'}为空，可调整筛选条件或执行同步/新建操作。`)
    } else {
      clearFeedback()
    }
  } catch (error) {
    items[view] = []
    pagination[view] = { page: 1, pageSize: 20, total: 0, totalPages: 0 }
    setFeedback('error', `${views.find((item) => item.key === view)?.label || '数据'}加载失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

async function ensureLookupData(view, force = false) {
  const tasks = []
  if ((view === 'courses' || view === 'classes' || view === 'enrollments') && (force || items.users.length === 0)) {
    tasks.push(loadLookup('users', { page: 1, pageSize: 100 }))
  }
  if ((view === 'classes' || view === 'enrollments') && (force || items.courses.length === 0)) {
    tasks.push(loadLookup('courses', { page: 1, pageSize: 100 }))
  }
  if (view === 'enrollments' && (force || items.classes.length === 0)) {
    tasks.push(loadLookup('classes', { page: 1, pageSize: 100 }))
  }
  if (tasks.length > 0) {
    await Promise.all(tasks)
  }
}

async function loadLookup(view, params) {
  try {
    const response = await getListHandler(view)(params)
    items[view] = response.data?.items || []
  } catch (error) {
    items[view] = []
    if (activeView.value === view) {
      setFeedback('error', `${views.find((item) => item.key === view)?.label || '数据'}引用数据加载失败：${error.message}`)
    }
  }
}

async function selectEntity(item) {
  const key = getEntityKey(item)
  selectedEntityKey.value = key
  detailLoading.value = true
  try {
    const response = await getDetailHandler(activeView.value)(getEntityId(item))
    detailState.value = response.data || null
  } catch (error) {
    detailState.value = null
    setFeedback('error', `详情加载失败：${error.message}`)
  } finally {
    detailLoading.value = false
  }
}

function openSyncForm(type) {
  syncState.visible = true
  syncState.type = type
  syncState.payload = buildDefaultSyncPayload(type)
  clearFeedback()
}

function closeSyncForm() {
  syncState.visible = false
}

async function openOverviewDetail(view, id) {
  try {
    activeView.value = view
    await ensureLookupData(view)
    await loadList(view)
    const target = (items[view] || []).find((item) => getEntityId(item) === id)
    if (target) {
      await selectEntity(target)
    } else {
      selectedEntityKey.value = id
      detailLoading.value = true
      try {
        const response = await getDetailHandler(view)(id)
        detailState.value = response.data || null
      } finally {
        detailLoading.value = false
      }
    }
  } catch (error) {
    setFeedback('error', `跳转详情失败：${error.message}`)
  }
}

function openCreateForm() {
  formState.visible = true
  formState.mode = 'create'
  formState.entityKey = ''
  formState.payload = buildDefaultPayload(activeView.value)
}

function openEditForm(item) {
  formState.visible = true
  formState.mode = 'edit'
  formState.entityKey = getEntityId(item)
  formState.payload = buildPayloadFromItem(activeView.value, item)
}

function closeForm() {
  formState.visible = false
}

async function submitForm() {
  const validationError = validateEntityForm(activeView.value, formState.payload)
  if (validationError) {
    setFeedback('error', validationError)
    return
  }

  saving.value = true
  try {
    let response
    if (activeView.value === 'courses') {
      response = formState.mode === 'create'
        ? await teacherV1Api.platform.createCourse(trimPayload(formState.payload))
        : await teacherV1Api.platform.updateCourse(formState.entityKey, trimPayload(formState.payload))
    } else if (activeView.value === 'classes') {
      response = formState.mode === 'create'
        ? await teacherV1Api.platform.createClass(trimPayload(formState.payload))
        : await teacherV1Api.platform.updateClass(formState.entityKey, trimPayload(formState.payload))
    } else if (activeView.value === 'enrollments') {
      response = formState.mode === 'create'
        ? await teacherV1Api.platform.createEnrollment(trimPayload(formState.payload))
        : await teacherV1Api.platform.updateEnrollment(formState.entityKey, trimPayload(formState.payload))
    }

    formState.visible = false
    await loadOverview()
    await ensureLookupData(activeView.value, true)
    await loadList(activeView.value)
    const responseData = response?.data || {}
    detailState.value = responseData
    setFeedback('success', `${formState.mode === 'create' ? '创建' : '更新'}成功`)
  } catch (error) {
    setFeedback('error', `提交失败：${error.message}`)
  } finally {
    saving.value = false
  }
}

async function submitSyncForm() {
  const validationError = validateSyncPayload(syncState.type, syncState.payload)
  if (validationError) {
    setFeedback('error', validationError)
    return
  }

  syncState.submitting = true
  try {
    let response
    if (syncState.type === 'user') {
      response = await teacherV1Api.platform.syncUser(buildSyncUserRequest(syncState.payload))
      await ensureLookupData('courses', true)
    } else {
      response = await teacherV1Api.platform.syncCourse(buildSyncCourseRequest(syncState.payload))
      await ensureLookupData('classes', true)
    }
    await loadOverview()
    if (activeView.value !== 'overview') {
      await ensureLookupData(activeView.value, true)
      await loadList(activeView.value)
    }
    syncState.visible = false
    await revealSyncResult(syncState.type, response?.data || {})
    setFeedback('success', `${syncState.type === 'user' ? '用户' : '课程'}同步成功`)
  } catch (error) {
    setFeedback('error', `同步失败：${error.message}`)
  } finally {
    syncState.submitting = false
  }
}

async function removeEntity(item) {
  const title = getEntityTitle(item)
  if (!window.confirm(`确定删除${title}吗？`)) {
    return
  }
  try {
    if (activeView.value === 'courses') {
      await teacherV1Api.platform.deleteCourse(getEntityId(item))
    } else if (activeView.value === 'classes') {
      await teacherV1Api.platform.deleteClass(getEntityId(item))
    } else if (activeView.value === 'enrollments') {
      await teacherV1Api.platform.deleteEnrollment(getEntityId(item))
    }
    detailState.value = null
    selectedEntityKey.value = ''
    await loadOverview()
    await ensureLookupData(activeView.value, true)
    await loadList(activeView.value)
    setFeedback('success', '删除成功')
  } catch (error) {
    setFeedback('error', `删除失败：${error.message}`)
  }
}

function setFeedback(type, message) {
  feedback.type = type
  feedback.message = message
}

function clearFeedback() {
  feedback.type = ''
  feedback.message = ''
}

function getListHandler(view) {
  if (view === 'users') return teacherV1Api.platform.listUsers
  if (view === 'courses') return teacherV1Api.platform.listCourses
  if (view === 'classes') return teacherV1Api.platform.listClasses
  return teacherV1Api.platform.listEnrollments
}

function getDetailHandler(view) {
  if (view === 'users') return teacherV1Api.platform.getUserDetail
  if (view === 'courses') return teacherV1Api.platform.getCourseDetail
  if (view === 'classes') return teacherV1Api.platform.getClassDetail
  return teacherV1Api.platform.getEnrollmentDetail
}

function defaultFilters(view) {
  if (view === 'users') return { keyword: '', role: '', orgCode: '', page: 1, pageSize: 20 }
  if (view === 'courses') return { keyword: '', status: '', orgCode: '', teacherId: '', page: 1, pageSize: 20 }
  if (view === 'classes') return { keyword: '', status: '', teacherId: '', courseId: '', page: 1, pageSize: 20 }
  if (view === 'enrollments') return { keyword: '', status: '', role: '', userId: '', classId: '', courseId: '', page: 1, pageSize: 20 }
  return {}
}

function sanitizeParams(params) {
  return Object.fromEntries(Object.entries(params).filter(([, value]) => value !== ''))
}

function trimPayload(payload) {
  return Object.fromEntries(Object.entries(payload).map(([key, value]) => {
    if (typeof value === 'string') {
      return [key, value.trim()]
    }
    return [key, value]
  }).filter(([, value]) => value !== ''))
}

function buildDefaultPayload(view) {
  if (view === 'courses') {
    return {
      platformId: 'demo-platform',
      externalId: '',
      code: '',
      title: '',
      description: '',
      teacherId: teacherLookup.value[0]?.userId || '',
      orgCode: '',
      schoolName: '',
      semester: '',
      credit: 2,
      period: 32,
      status: 'draft'
    }
  }
  if (view === 'classes') {
    return {
      platformId: 'demo-platform',
      externalId: '',
      courseId: courseLookup.value[0]?.courseId || '',
      teacherId: teacherLookup.value[0]?.userId || '',
      className: '',
      classCode: '',
      semester: '',
      grade: '',
      major: '',
      capacity: 50,
      status: 'active'
    }
  }
  return {
    platformId: 'demo-platform',
    externalId: '',
    courseId: courseLookup.value[0]?.courseId || '',
    classId: classLookup.value[0]?.classId || '',
    userId: userLookup.value[0]?.userId || '',
    role: 'student',
    status: 'active'
  }
}

function buildDefaultSyncPayload(type) {
  if (type === 'user') {
    return {
      platformId: 'demo-platform',
      userId: '',
      userName: '',
      role: 'student',
      schoolId: 'SCH-01',
      schoolName: '',
      major: '',
      grade: '',
      classId: '',
      className: '',
      email: '',
      phone: ''
    }
  }

  return {
    platformId: 'demo-platform',
    courseId: '',
    courseName: '',
    teacherExternalId: '',
    teacherName: '',
    schoolId: 'SCH-01',
    schoolName: '',
    term: '',
    credit: 2,
    period: 32,
    classId: '',
    className: ''
  }
}

function buildPayloadFromItem(view, item) {
  if (view === 'courses') {
    return {
      platformId: item.platformId || 'demo-platform',
      externalId: item.externalId || '',
      code: item.code || '',
      title: item.title || '',
      description: item.description || '',
      teacherId: item.teacherId || '',
      orgCode: item.orgCode || '',
      schoolName: item.schoolName || '',
      semester: item.semester || '',
      credit: Number(item.credit || 0),
      period: Number(item.period || 0),
      status: item.status || 'draft'
    }
  }
  if (view === 'classes') {
    return {
      platformId: item.platformId || 'demo-platform',
      externalId: item.externalId || '',
      courseId: item.teachingCourseId || item.courseId || '',
      teacherId: item.teacherId || '',
      className: item.className || '',
      classCode: item.classCode || '',
      semester: item.semester || '',
      grade: item.grade || '',
      major: item.major || '',
      capacity: Number(item.capacity || 0),
      status: item.status || 'active'
    }
  }
  return {
    platformId: item.platformId || 'demo-platform',
    externalId: item.externalId || '',
    courseId: item.teachingCourseId || item.courseId || '',
    classId: item.courseClassId || item.classId || '',
    userId: item.userId || '',
    role: item.role || 'student',
    status: item.status || 'active'
  }
}

function getEntityKey(item) {
  return `${activeView.value}:${getEntityId(item)}`
}

function getEntityId(item) {
  if (activeView.value === 'users') return item.userId
  if (activeView.value === 'courses') return item.courseId
  if (activeView.value === 'classes') return item.classId
  return item.enrollmentId
}

function getEntityTitle(item) {
  if (activeView.value === 'users') return displayText(item.displayName || item.externalId || item.userId, '未命名用户')
  if (activeView.value === 'courses') return displayText(item.title || item.externalId || item.courseId, '未命名课程')
  if (activeView.value === 'classes') return displayText(item.className || item.externalId || item.classId, '未命名班级')
  return displayText(item.externalId || item.enrollmentId, '未命名选课')
}

function getEntitySubtitle(item) {
  if (activeView.value === 'users') return joinDisplayParts([item.externalId, item.orgCode], '未配置扩展信息')
  if (activeView.value === 'courses') return joinDisplayParts([item.code, item.schoolName], '未配置课程说明')
  if (activeView.value === 'classes') return joinDisplayParts([item.classCode, item.major], '未配置班级说明')
  return joinDisplayParts([item.userId, item.teachingCourseId], '未配置选课说明')
}

function getEntityBadge(item) {
  if (activeView.value === 'users') return displayText(item.role, 'user')
  return displayText(item.status, 'unknown')
}

function getEntityMeta(item) {
  if (activeView.value === 'users') return compactDisplayList([item.schoolName, item.className, item.email])
  if (activeView.value === 'courses') return compactDisplayList([item.semester, item.teacherId, item.orgCode])
  if (activeView.value === 'classes') return compactDisplayList([item.semester, item.teacherId, item.capacity ? `容量 ${item.capacity}` : ''])
  return compactDisplayList([item.role, item.status, item.courseClassId])
}

function buildDetailSections(view, detail) {
  if (!detail) {
    return []
  }
  if (detail.syncStatus) {
    return buildSyncResultSections(detail)
  }
  if (view === 'users') {
    return [
      createPairSection('用户档案', detail.profile),
      createPairSection('汇总信息', detail.summary),
      createListSection('关联课程', detail.courses, (item) => ({ key: item.courseId, title: displayText(item.title || item.externalId, '未命名课程'), subtitle: joinDisplayParts([item.status, item.semester], '未配置课程信息') })),
      createListSection('关联班级', detail.classes, (item) => ({ key: item.classId, title: displayText(item.className || item.externalId, '未命名班级'), subtitle: joinDisplayParts([item.status, item.semester], '未配置班级信息') })),
      createListSection('选课关系', detail.enrollments, (item) => ({ key: item.enrollmentId, title: displayText(item.externalId || item.enrollmentId, '未命名选课'), subtitle: joinDisplayParts([item.role, item.status], '未配置选课信息') }))
    ].filter(Boolean)
  }
  if (view === 'courses') {
    return [
      createPairSection('课程信息', detail.courseInfo),
      createPairSection('课程汇总', detail.summary),
      createPairSection('授课教师', detail.teacher),
      createListSection('班级列表', detail.classes, (item) => ({ key: item.classId, title: displayText(item.className || item.externalId, '未命名班级'), subtitle: joinDisplayParts([item.status, item.semester], '未配置班级信息') })),
      createListSection('成员列表', detail.members, (item) => ({ key: item.userId, title: displayText(item.displayName || item.externalId, '未命名用户'), subtitle: joinDisplayParts([item.role, item.className], '未配置成员信息') }))
    ].filter(Boolean)
  }
  if (view === 'classes') {
    return [
      createPairSection('班级信息', detail.classInfo),
      createPairSection('班级汇总', detail.summary),
      createPairSection('所属课程', detail.course),
      createPairSection('授课教师', detail.teacher),
      createListSection('成员名单', detail.members, (item) => ({ key: item.userId, title: displayText(item.displayName || item.externalId, '未命名用户'), subtitle: joinDisplayParts([item.role, item.major, item.grade], '未配置成员信息') }))
    ].filter(Boolean)
  }
  return [
    createPairSection('选课信息', detail.enrollmentInfo),
    createPairSection('用户摘要', detail.user),
    createPairSection('课程摘要', detail.course),
    createPairSection('班级摘要', detail.class)
  ].filter(Boolean)
}

function createPairSection(title, data) {
  if (!data || typeof data !== 'object') {
    return null
  }
  const items = Object.entries(data)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([label, value]) => ({ label: formatDetailLabel(label), value: formatDetailValue(value) }))
  if (items.length === 0) {
    return null
  }
  return { title, type: 'pairs', items }
}

function createListSection(title, list, mapper) {
  if (!Array.isArray(list) || list.length === 0) {
    return null
  }
  return { title, type: 'list', count: list.length, items: list.map(mapper) }
}

function validateEntityForm(view, payload) {
  if (view === 'courses') {
    if (!String(payload.title || '').trim()) return '课程标题不能为空'
    if (!String(payload.teacherId || '').trim()) return '请选择授课教师'
    return ''
  }
  if (view === 'classes') {
    if (!String(payload.courseId || '').trim()) return '请选择所属课程'
    if (!String(payload.className || '').trim()) return '班级名称不能为空'
    return ''
  }
  if (view === 'enrollments') {
    if (!String(payload.courseId || '').trim()) return '请选择所属课程'
    if (!String(payload.userId || '').trim()) return '请选择用户'
    return ''
  }
  return ''
}

function validateSyncPayload(type, payload) {
  if (type === 'user') {
    if (!String(payload.userId || '').trim()) return '同步用户时必须填写外部用户ID'
    if (!String(payload.userName || '').trim()) return '同步用户时必须填写用户名称'
    if (!String(payload.schoolId || '').trim()) return '同步用户时建议至少填写学校编码'
    return ''
  }
  if (!String(payload.courseId || '').trim()) return '同步课程时必须填写外部课程ID'
  if (!String(payload.courseName || '').trim()) return '同步课程时必须填写课程名称'
  if (!String(payload.teacherExternalId || '').trim()) return '同步课程时必须填写教师外部ID'
  if (!String(payload.teacherName || '').trim()) return '同步课程时必须填写教师姓名'
  return ''
}

function buildSyncUserRequest(payload) {
  return {
    platformId: payload.platformId,
    userInfo: {
      userId: payload.userId,
      userName: payload.userName,
      role: payload.role,
      schoolId: payload.schoolId,
      schoolName: payload.schoolName,
      major: payload.major,
      grade: payload.grade,
      classId: payload.classId,
      className: payload.className,
      contactInfo: {
        email: payload.email,
        phone: payload.phone
      }
    }
  }
}

function buildSyncCourseRequest(payload) {
  return {
    platformId: payload.platformId,
    courseInfo: {
      courseId: payload.courseId,
      courseName: payload.courseName,
      schoolId: payload.schoolId,
      schoolName: payload.schoolName,
      term: payload.term,
      credit: Number(payload.credit || 0),
      period: Number(payload.period || 0),
      teacherInfo: [{
        teacherId: payload.teacherExternalId,
        teacherName: payload.teacherName
      }],
      classList: payload.className || payload.classId ? [{
        classId: payload.classId,
        className: payload.className || `${payload.courseName}默认班级`
      }] : []
    }
  }
}

async function revealSyncResult(type, data) {
  detailState.value = data
  if (type === 'user' && data.internalUserId) {
    activeView.value = 'users'
    await loadList('users')
    const target = items.users.find((item) => item.userId === data.internalUserId || item.externalId === syncState.payload.userId)
    if (target) {
      await selectEntity(target)
    }
    return
  }

  if (type === 'course' && data.internalCourseId) {
    activeView.value = 'courses'
    await ensureLookupData('courses', true)
    await loadList('courses')
    const target = items.courses.find((item) => item.courseId === data.internalCourseId || item.externalId === syncState.payload.courseId)
    if (target) {
      await selectEntity(target)
    }
  }
}

function buildSyncResultSections(detail) {
  return [
    createPairSection('同步结果', {
      syncStatus: detail.syncStatus,
      syncTime: detail.syncTime,
      internalUserId: detail.internalUserId,
      internalCourseId: detail.internalCourseId,
      enrollmentCount: detail.enrollmentCount,
      teacherCount: detail.teacherCount,
      authToken: detail.authToken
    }),
    createPairSection('用户摘要', detail.userProfile),
    createPairSection('课程摘要', detail.courseMeta),
    createPairSection('默认班级', detail.classInfo),
    createListSection('关联课程', detail.linkedCourses, (item) => ({ key: item.courseId || item.externalCourseId, title: displayText(item.className || item.externalCourseId, '未命名课程关系'), subtitle: joinDisplayParts([item.role, item.externalClassId], '未配置关系信息') })),
    createListSection('同步教师', detail.teachers, (item) => ({ key: item.userId || item.externalId, title: displayText(item.displayName || item.externalId, '未命名教师'), subtitle: displayText(item.userId || item.externalId, '未配置教师信息') })),
    createListSection('同步班级', detail.classes, (item) => ({ key: item.classId || item.externalClassId, title: displayText(item.className || item.externalClassId, '未命名班级'), subtitle: joinDisplayParts([item.semester, item.major], '未配置班级信息') }))
  ].filter(Boolean)
}

function formatDetailValue(value) {
  if (Array.isArray(value)) {
    const normalized = compactDisplayList(value)
    return normalized.length ? normalized.join(', ') : '未填写'
  }
  if (value && typeof value === 'object') {
    return Object.keys(value).length ? JSON.stringify(value) : '未填写'
  }
  return displayText(value)
}

function formatDetailLabel(label) {
  const labelMap = {
    syncStatus: '同步状态',
    syncTime: '同步时间',
    internalUserId: '内部用户ID',
    internalCourseId: '内部课程ID',
    enrollmentCount: '选课数量',
    teacherCount: '教师数量',
    authToken: '认证令牌',
    userId: '用户ID',
    platformId: '平台标识',
    externalId: '外部ID',
    username: '用户名',
    displayName: '显示名称',
    role: '角色',
    status: '状态',
    orgCode: '组织编码',
    schoolName: '学校名称',
    major: '专业',
    grade: '年级',
    classExternalId: '班级外部ID',
    className: '班级名称',
    email: '邮箱',
    phone: '手机号',
    updatedAt: '更新时间',
    courseCount: '课程数量',
    classCount: '班级数量',
    roleDistribution: '角色分布',
    statusDistribution: '状态分布',
    enrollmentInfo: '选课信息',
    courseId: '课程ID',
    code: '课程编码',
    title: '标题',
    description: '描述',
    teacherId: '教师ID',
    semester: '学期',
    credit: '学分',
    period: '学时',
    coverUrl: '封面地址',
    classId: '班级ID',
    teachingCourseId: '教学课程ID',
    classCode: '班级编码',
    capacity: '容量',
    memberCount: '成员数量',
    enrolledAt: '选课时间',
    courseClassId: '班级关联ID'
  }
  if (labelMap[label]) {
    return labelMap[label]
  }
  return label
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/^./, (char) => char.toUpperCase())
}

function compactDisplayList(values) {
  return (values || []).map((item) => cleanDisplayText(item)).filter(Boolean)
}

function joinDisplayParts(values, fallback = '未填写') {
  const parts = compactDisplayList(values)
  return parts.length ? parts.join(' · ') : fallback
}

function displayText(value, fallback = '未填写') {
  const normalized = cleanDisplayText(value)
  return normalized || fallback
}

function cleanDisplayText(value) {
  if (value === undefined || value === null) {
    return ''
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  const text = String(value).replace(/<nil>/gi, '').trim()
  if (!text || /^\?+$/.test(text)) {
    return ''
  }
  if (!text.replace(/[?？\-_/\\\s]+/g, '')) {
    return ''
  }
  return text
}
</script>

<style scoped>
.platform-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 22px;
  gap: 18px;
  overflow: auto;
}

.platform-toolbar,
.entity-toolbar,
.form-shell,
.list-pane,
.detail-pane,
.recent-card,
.stat-card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.94) 100%);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 18px 32px rgba(15, 23, 42, 0.06);
}

.platform-toolbar,
.sync-shell,
.form-shell,
.list-pane,
.detail-pane,
.recent-card,
.stat-card {
  border-radius: 24px;
}

.feedback-banner,
.contract-note {
  padding: 12px 16px;
  border-radius: 18px;
  font-size: 13px;
  font-weight: 600;
}

.feedback-banner.info,
.contract-note {
  background: rgba(14, 165, 233, 0.08);
  border: 1px solid rgba(14, 165, 233, 0.18);
  color: #075985;
}

.feedback-banner.success {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.2);
  color: #047857;
}

.feedback-banner.error {
  background: rgba(244, 63, 94, 0.08);
  border: 1px solid rgba(244, 63, 94, 0.18);
  color: #be123c;
}

.platform-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 20px 22px;
}

.toolbar-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #0f766e;
}

.platform-toolbar h3,
.list-head h4,
.card-head h4,
.form-head h4 {
  margin: 6px 0 0;
  color: #0f172a;
}

.toolbar-actions,
.action-row,
.form-actions,
.pager,
.entity-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.view-switcher {
  display: flex;
  gap: 10px;
  overflow-x: auto;
}

.switch-btn,
.ghost-btn,
.primary-btn,
.mini-btn,
.text-btn {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  padding: 10px 16px;
  cursor: pointer;
  font: inherit;
  transition: all 0.2s ease;
}

.switch-btn,
.ghost-btn,
.mini-btn,
.text-btn {
  background: rgba(255, 255, 255, 0.86);
  color: #334155;
}

.switch-btn.active,
.primary-btn {
  color: #fff;
  background: linear-gradient(90deg, #0f766e 0%, #0284c7 100%);
  box-shadow: 0 14px 24px rgba(2, 132, 199, 0.18);
  border-color: transparent;
}

.mini-btn.danger {
  color: #be123c;
  background: #fff1f2;
  border-color: #fecdd3;
}

.text-btn {
  padding-inline: 0;
  border: none;
  background: transparent;
  color: #0284c7;
}

.stats-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.recent-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr)); /* 只修改这一行，从2列改为4列 */
}

.entity-layout,
.form-grid {
  display: grid;
  gap: 16px;
}

.stats-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.stat-card {
  padding: 18px 20px;
}

.stat-card-action {
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.stat-card-action:hover {
  transform: translateY(-1px);
  border-color: rgba(14, 165, 233, 0.34);
  box-shadow: 0 14px 26px rgba(2, 132, 199, 0.1);
}

.stat-label {
  display: block;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.stat-value {
  display: block;
  margin-top: 12px;
  font-size: 30px;
  color: #0f172a;
}

.stat-hint {
  display: block;
  margin-top: 10px;
  font-size: 12px;
  color: #64748b;
}

.recent-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.recent-card,
.list-pane,
.detail-pane,
.form-shell,
.entity-toolbar {
  padding: 18px 20px;
}

.card-head,
.list-head,
.form-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.card-head span,
.list-head p,
.form-head span,
.simple-row span,
.pair-item span,
.entity-main p,
.entity-meta span,
.empty-tip {
  color: #64748b;
}

.recent-list,
.entity-list,
.detail-sections,
.simple-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.recent-item,
.entity-item,
.simple-row {
  width: 100%;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.88) 0%, rgba(255, 255, 255, 0.98) 100%);
  border-radius: 18px;
  padding: 14px 16px;
  text-align: left;
}

.recent-item,
.entity-item {
  cursor: pointer;
}

.recent-item strong,
.entity-title-row strong,
.simple-row strong,
.pair-item strong {
  color: #0f172a;
}

.recent-item span {
  display: block;
  margin-top: 6px;
}

.entity-toolbar {
  border-radius: 24px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.filter-row {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.text-input,
.select-input,
.text-area {
  width: 100%;
  min-height: 42px;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.26);
  background: rgba(255, 255, 255, 0.92);
  font: inherit;
  box-sizing: border-box;
}

.text-input.narrow {
  max-width: 180px;
}

.text-area {
  min-height: 92px;
  resize: vertical;
}

.form-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.form-grid label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}

.form-grid label.wide {
  grid-column: 1 / -1;
}

.entity-layout {
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.9fr);
}

.entity-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.entity-item:hover,
.recent-item:hover {
  transform: translateY(-1px);
  border-color: rgba(14, 165, 233, 0.34);
  box-shadow: 0 12px 22px rgba(15, 23, 42, 0.05);
}

.entity-item.selected {
  border-color: #0284c7;
  box-shadow: 0 14px 26px rgba(2, 132, 199, 0.14);
}

.entity-main {
  min-width: 0;
}

.entity-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.entity-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.1);
  color: #0369a1;
  font-size: 12px;
  font-weight: 700;
}

.entity-main p {
  margin: 8px 0;
}

.entity-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.detail-card {
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.9);
  padding: 16px;
}

.pair-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.pair-item,
.simple-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.empty-tip {
  padding: 28px 12px;
  text-align: center;
  border: 1px dashed rgba(148, 163, 184, 0.3);
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.8);
}

@media (max-width: 1200px) {
 
  .entity-layout,
  .form-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 860px) {
  .platform-toolbar,
  .entity-toolbar,
  .form-head,
  .list-head,
  .card-head,
  .entity-item {
    flex-direction: column;
  }

  .platform-panel {
    padding: 14px;
  }
}
</style>
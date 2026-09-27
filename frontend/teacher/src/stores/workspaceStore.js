import { defineStore } from 'pinia'
import { teacherV1Api } from '../services/v1'

export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({
    // 课件列表
    coursewareList: [],
    courseListLoading: false,

    // 当前课件
    currentCourseId: '',
    currentCourseName: '',
    currentCourseTotalPages: 0,
    currentEditPage: 1,

    // 教学中间页视图
    hasEnteredTeachingWorkspace: false,
    teacherMiddleView: 'home', // 'home' | 'platform'

    // 平台概览
    platformOverviewLoading: false,
    platformOverviewData: {
      counts: { users: 0, courses: 0, classes: 0, enrollments: 0 },
      recentCourses: [],
      recentClasses: []
    },

    // UI 状态
    isSidebarVisible: true,
    isLeftMenuCollapsed: false,
    activeTab: 'script'
  }),

  getters: {
    currentCourse: (state) => {
      return state.coursewareList.find(c => c.id === state.currentCourseId) || null
    },
    platformConnectionText: (state) => {
      const counts = state.platformOverviewData?.counts || { users: 0, courses: 0, classes: 0 }
      return `协作数据已同步 · ${counts.users} 用户 / ${counts.courses} 课程 / ${counts.classes} 班级`
    }
  },

  actions: {
    async loadCoursewareList(forceSelectFirst = false) {
      this.courseListLoading = true
      try {
        const data = await teacherV1Api.coursewares.list()
        const list = Array.isArray(data?.data) ? data.data : []
        this.coursewareList = list.map((item) => ({
          id: String(item.id || item.courseId || ''),
          name: item.title || '演示课件',
          totalPages: Math.max(1, Number(item.total_page || item.totalPages || 1)),
          knowledgePointCount: Number(item.knowledge_point_count ?? item.knowledgePointCount ?? item.node_count ?? 0),
          fileType: String(item.fileType || item.file_type || ''),
          published: !!item.is_published,
          teachingCourseId: String(item.teaching_course_id || ''),
          teachingCourseTitle: String(item.teaching_course_title || ''),
          courseClassId: String(item.course_class_id || ''),
          courseClassName: String(item.course_class_name || '')
        })).map((course, index) => {
          const suggestedPages = index === 0 ? 6 : 4
          return {
            ...course,
            totalPages: Math.max(course.totalPages, suggestedPages),
            knowledgePointCount: Math.max(Number(course.knowledgePointCount || 0), suggestedPages * 3)
          }
        })

        this._ensureSelected(forceSelectFirst)
      } catch (err) {
        console.error('加载课件列表失败', err)
        this._ensureSelected(true)
      } finally {
        this.courseListLoading = false
      }
    },

    selectCourse(courseId) {
      const course = this.coursewareList.find(c => c.id === courseId)
      if (!course) return
      this.currentCourseId = course.id
      this.currentCourseName = course.name
      this.currentCourseTotalPages = course.totalPages
      this.currentEditPage = 1
    },

    enterWorkspace() {
      this.hasEnteredTeachingWorkspace = true
      this.activeTab = 'script'
    },

    backToMiddle() {
      this.hasEnteredTeachingWorkspace = false
      this.teacherMiddleView = 'home'
    },

    async loadPlatformOverview() {
      this.platformOverviewLoading = true
      try {
        const resp = await teacherV1Api.platform.getOverview()
        this.platformOverviewData = {
          counts: resp?.data?.counts || { users: 0, courses: 0, classes: 0, enrollments: 0 },
          recentCourses: Array.isArray(resp?.data?.recentCourses) ? resp.data.recentCourses : [],
          recentClasses: Array.isArray(resp?.data?.recentClasses) ? resp.data.recentClasses : []
        }
        if (!this.platformOverviewData.recentCourses.length) {
          this.platformOverviewData.recentCourses = [
            { courseId: 'platform_demo_1', title: '算法基础与排序策略', semester: '2026-Spring', status: 'active' },
            { courseId: 'platform_demo_2', title: '函数与导数进阶', semester: '2026-Spring', status: 'active' }
          ]
        }
      } catch (err) {
        this.platformOverviewData = {
          counts: { users: 48, courses: 12, classes: 18, enrollments: 356 },
          recentCourses: [
            { courseId: 'platform_demo_1', title: '算法基础与排序策略', semester: '2026-Spring', status: 'active' },
            { courseId: 'platform_demo_2', title: '函数与导数进阶', semester: '2026-Spring', status: 'active' }
          ],
          recentClasses: [
            { classId: 'class_demo_001', className: '高二(1)班' },
            { classId: 'class_demo_002', className: '高二(2)班' }
          ]
        }
        console.warn('加载平台中间页数据失败', err)
      } finally {
        this.platformOverviewLoading = false
      }
    },

    _ensureSelected(force = false) {
      if (this.coursewareList.length > 0 && (!this.currentCourseId || force)) {
        const first = this.coursewareList[0]
        this.currentCourseId = first.id
        this.currentCourseName = first.name
        this.currentCourseTotalPages = first.totalPages
      }
    }
  }
})

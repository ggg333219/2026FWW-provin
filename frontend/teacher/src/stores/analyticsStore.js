import { defineStore } from 'pinia'
import { teacherV1Api } from '../services/v1'

/**
 * 学情统计 Store
 *
 * 对应学情分析与统计模块的状态管理，包括：
 * - 学情总览数据
 * - 提问记录与统计
 * - 掌握度雷达图
 * - 班级趋势
 */
export const useAnalyticsStore = defineStore('analytics', {
  state: () => ({
    /** 学情统计数据 */
    studentStats: {
      totalQuestions: 0,
      activeSessions: 0,
      avgTurnsPerSession: 0,
      hotPages: [],
      keyDifficulties: '暂无',
      nodeStats: [],
      mappingCoverage: { coveredNodeCount: 0, uncoveredNodeCount: 0, uncoveredNodeIds: [] },
      nodeHeatmap: [],
      masteryRadar: { indicators: [], values: [], avgMastery: 0 },
      classTrend: [],
      learningInsights: { reteachNodes: [], prerequisiteGaps: [], summary: '' }
    },

    /** 卡片数据 */
    cardData: [],
    // cardData[i] 结构参考：
    // { page, 提问量, 停留时长, 需重讲, 卡点指数 }

    /** 提问记录 */
    questionRecords: [],
    // questionRecords[i] 结构参考：
    // {
    //   id, studentId, page, nodeId, nodeTitle,
    //   content, answer, time
    // }

    /** 筛选 */
    filterPage: '',

    /** 统计子标签 */
    statsSubTab: 'overview',

    loading: false,
    error: ''
  }),

  getters: {
    filteredQuestions: (state) => {
      if (!state.filterPage) return state.questionRecords
      return state.questionRecords.filter(q => q.page === Number(state.filterPage))
    },
    nodeInsights: (state) => {
      const stats = state.studentStats?.nodeStats
      if (!Array.isArray(stats)) return {}
      const map = {}
      stats.forEach((row) => {
        const id = String(row?.nodeId || '').trim()
        if (!id) return
        map[id] = {
          mastery: Math.round(Number(row?.masteryScore ?? row?.mastery ?? 0)),
          card: Math.round(Number(row?.cardScore ?? row?.bottleneckScore ?? 0) * 10) / 10
        }
      })
      return map
    }
  },

  actions: {
    async loadStats(courseId) {
      if (!courseId) return
      this.loading = true
      try {
        const data = await teacherV1Api.analytics.getStats(courseId)
        const payload = data?.data || {}
        this.studentStats = {
          totalQuestions: payload.totalQuestions || 0,
          activeSessions: payload.activeSessions || 0,
          avgTurnsPerSession: payload.avgTurnsPerSession || 0,
          hotPages: (payload.pageStats || []).map(item => item.page).slice(0, 3),
          keyDifficulties: payload.keyDifficulties || '暂无',
          nodeStats: payload.nodeStats || [],
          mappingCoverage: payload.mappingCoverage || { uncoveredNodeIds: [] },
          nodeHeatmap: payload.nodeHeatmap || [],
          masteryRadar: payload.masteryRadar || { indicators: [], values: [], avgMastery: 0 },
          classTrend: payload.classTrend || [],
          learningInsights: payload.learningInsights || { reteachNodes: [], prerequisiteGaps: [], summary: '' }
        }
      } catch (err) {
        console.warn('加载学情统计失败', err)
      } finally {
        this.loading = false
      }
    },

    async loadCardData(courseId) {
      if (!courseId) return
      try {
        const data = await teacherV1Api.analytics.getCardData(courseId)
        const pageStats = data?.data?.pageStats || []
        this.cardData = pageStats.map(item => ({
          page: item.page,
          提问量: item.questionCount,
          停留时长: item.stayTime,
          需重讲: item.reteachCount || 0,
          卡点指数: item.cardIndex
        }))
      } catch (err) {
        console.warn('加载卡片数据失败', err)
      }
    },

    async loadQuestionRecords(courseId, page = 1, pageSize = 100) {
      if (!courseId) return
      try {
        const data = await teacherV1Api.analytics.getQuestionRecords(courseId, page, pageSize)
        const list = data?.data?.list || []
        this.questionRecords = list.map(item => ({
          id: item.id,
          studentId: item.user_id || item.userId || '未知',
          page: item.page_index || item.pageIndex || 1,
          nodeId: item.nodeId || '',
          nodeTitle: item.nodeTitle || '',
          content: item.question || '',
          answer: item.answer || '',
          time: item.created_at ? new Date(item.created_at).toLocaleString() : ''
        }))
      } catch (err) {
        console.warn('加载提问记录失败', err)
      }
    },

    setFilterPage(page) {
      this.filterPage = page
    },

    setStatsSubTab(tab) {
      this.statsSubTab = tab
    },

    reset() {
      this.studentStats = {
        totalQuestions: 0,
        activeSessions: 0,
        avgTurnsPerSession: 0,
        hotPages: [],
        keyDifficulties: '暂无',
        nodeStats: [],
        mappingCoverage: { coveredNodeCount: 0, uncoveredNodeCount: 0, uncoveredNodeIds: [] },
        nodeHeatmap: [],
        masteryRadar: { indicators: [], values: [], avgMastery: 0 },
        classTrend: [],
        learningInsights: { reteachNodes: [], prerequisiteGaps: [], summary: '' }
      }
      this.cardData = []
      this.questionRecords = []
      this.filterPage = ''
    }
  }
})

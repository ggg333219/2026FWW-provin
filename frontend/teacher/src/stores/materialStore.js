import { defineStore } from 'pinia'

/**
 * S2 素材管理 Store
 *
 * 对应素材选择与切片模块的状态管理，包括：
 * - 素材列表与选择
 * - ChunkSchema 结构映射
 * - 素材与知识点关联
 */
export const useMaterialStore = defineStore('material', {
  state: () => ({
    /** 素材列表 */
    materials: [],
    // materials[i] 结构参考：
    // {
    //   id: string,
    //   title: string,
    //   type: 'video' | 'document' | 'image' | 'audio' | 'link',
    //   url: string,
    //   source: string,          // 来源
    //   tags: string[],          // 标签
    //   chunks: [],              // ChunkSchema 切片
    //   selected: boolean,
    //  关联知识点
    //   knowledgePoints: []
    // }

    /** 当前选中的素材 */
    selectedMaterials: [],

    /** 素材切片列表 (ChunkSchema) */
    chunks: [],
    // chunks[i] 结构参考：
    // {
    //   chunkId: string,
    //   materialId: string,
    //   content: string,         // 切片内容/文本
    //   pageStart: number,
    //   pageEnd: number,
    //   timeStart: number,       // 视频起始时间(秒)
    //   timeEnd: number,         // 视频结束时间(秒)
    //   embedding: [],           // 向量嵌入（可选）
    //   metadata: {},            // 额外元数据
    //   relevanceScore: number   // 与当前意图的相关性(0-1)
    // }

    /** 素材加载状态 */
    loading: false,

    /** 错误信息 */
    error: '',

    /** 检索结果缓存 */
    searchCache: {}
  }),

  getters: {
    selectedCount: (state) => state.selectedMaterials.length,
    hasSelection: (state) => state.selectedMaterials.length > 0,
    selectedChunks: (state) => state.chunks.filter(c => state.selectedMaterials.includes(c.materialId))
  },

  actions: {
    setMaterials(list) {
      this.materials = list
    },

    toggleMaterial(id) {
      const idx = this.selectedMaterials.indexOf(id)
      if (idx >= 0) {
        this.selectedMaterials.splice(idx, 1)
      } else {
        this.selectedMaterials.push(id)
      }
    },

    selectMaterial(id) {
      if (!this.selectedMaterials.includes(id)) {
        this.selectedMaterials.push(id)
      }
    },

    deselectMaterial(id) {
      const idx = this.selectedMaterials.indexOf(id)
      if (idx >= 0) {
        this.selectedMaterials.splice(idx, 1)
      }
    },

    setChunks(chunks) {
      this.chunks = chunks
    },

    addChunks(chunks) {
      this.chunks.push(...chunks)
    },

    setLoading(loading) {
      this.loading = loading
    },

    setError(error) {
      this.error = error
    },

    reset() {
      this.materials = []
      this.selectedMaterials = []
      this.chunks = []
      this.error = ''
    }
  }
})

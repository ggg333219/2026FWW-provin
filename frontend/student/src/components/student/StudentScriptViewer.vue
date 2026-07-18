<template>
  <div class="student-script-viewer">
    <!-- 当没有脚本时显示占位符 -->
    <div v-if="!scriptContent && !isLoading" class="script-empty">
      <p>还没有课程讲稿</p>
    </div>

    <!-- 加载中状态 -->
    <div v-if="isLoading" class="script-loading">
      <el-skeleton animated>
        <template #default>
          <el-skeleton-item variant="p" style="width: 100%" />
          <el-skeleton-item variant="p" style="width: 80%; margin-top: 10px" />
          <el-skeleton-item variant="p" style="width: 90%; margin-top: 10px" />
        </template>
      </el-skeleton>
    </div>

    <!-- 使用统一的 UnifiedMdRenderer 渲染脚本 -->
    <UnifiedMdRenderer
      v-if="scriptContent && !isLoading"
      :md-text="scriptContent"
      @render-error="handleRenderError"
      @rendered="handleRendered"
    />
  </div>
</template>

<script setup>
/* eslint-disable no-undef */
import { ElSkeleton, ElSkeletonItem } from 'element-plus'
import UnifiedMdRenderer from '@/components/common/UnifiedMdRenderer.vue'

defineProps({
  scriptContent: {
    type: String,
    default: ''
  },
  isLoading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['error', 'warning'])

/**
 * 处理渲染错误
 */
function handleRenderError(errors) {
  console.error('[StudentScriptViewer] 渲染错误:', errors)
  emit('error', errors)
}

/**
 * 处理渲染警告
 */
function handleRenderWarning(warnings) {
  console.warn('[StudentScriptViewer] 渲染警告:', warnings)
  emit('warning', warnings)
}

function handleRendered(payload) {
  if (payload?.warnings?.length) {
    handleRenderWarning(payload.warnings)
  }
}
</script>

<style scoped>
.student-script-viewer {
  width: 100%;
  background-color: #fff;
  border-radius: 6px;
  padding: 16px;
  min-height: 100px;
}

.script-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: #999;
  font-size: 14px;
  border: 1px dashed #ddd;
  border-radius: 4px;
  background-color: #fafafa;
}

.script-loading {
  padding: 16px;
}

/* 确保 UnifiedMdRenderer 在这个容器中正确显示 */
:deep(.unified-md-renderer) {
  width: 100%;
}
</style>

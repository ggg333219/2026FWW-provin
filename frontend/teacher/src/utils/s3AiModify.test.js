// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import OutlineRevisionDialog from '../components/teacher/OutlineRevisionDialog.vue'
import ModifyPanel from '../components/teacher/ModifyPanel.vue'
import { useModifyStore } from '../stores/modifyStore'
import { useGenerationStore } from '../stores/generationStore'

let app
let host
afterEach(() => { app?.unmount(); host?.remove(); app = null; vi.restoreAllMocks() })

function mount(component, props = {}) {
  host = document.createElement('div')
  document.body.appendChild(host)
  const pinia = createPinia()
  setActivePinia(pinia)
  app = createApp({ render: () => h(component, props) })
  app.use(pinia)
  app.mount(host)
}

describe('S3 按需 AI 修改', () => {
  it('大纲窗口默认隐藏，打开后显示整份大纲与快捷建议', async () => {
    const onSubmit = vi.fn()
    mount(OutlineRevisionDialog, { visible: false, message: '', onSubmit })
    expect(host.querySelector('[role="dialog"]')).toBeNull()
    app.unmount()
    app = null
    host.remove()
    mount(OutlineRevisionDialog, { visible: true, message: '补充案例', onSubmit })
    expect(host.textContent).toContain('当前对象：整份课程大纲')
    expect(host.textContent).toContain('增加课堂练习')
    expect(host.textContent).toContain('后端可能立即保存新的草稿版本')
    ;[...host.querySelectorAll('button')].find(button => button.textContent.includes('提交并生成草稿')).click()
    await nextTick()
    expect(onSubmit).toHaveBeenCalledOnce()
  })

  it('大纲候选预览说明关闭不撤销后端草稿，加载期间不能关闭', () => {
    mount(OutlineRevisionDialog, { visible: true, pendingNodes: [{ node_id: 'n1', title: '绪论' }] })
    expect(host.textContent).toContain('关闭查看（不撤销后端草稿）')
    expect(host.textContent).toContain('采用此版后继续调整')
    app.unmount()
    app = null
    host.remove()
    mount(OutlineRevisionDialog, { visible: true, loading: true, message: '调整顺序' })
    expect(host.querySelector('button[aria-label="关闭"]').disabled).toBe(true)
  })

  it('本页提交固定目标节点，失败后保留输入以便重试', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useModifyStore()
    const generation = useGenerationStore()
    store.projectId = 'project_1'
    store.inputText = '精简本页文字'
    generation.setNodes([{ node_id: 'page_node_2', title: '第二页', content: '原文' }])
    const send = vi.spyOn(store, 'sendModify').mockImplementation(async () => {
      expect(store.activeNodeId).toBe('page_node_2')
      store.inputText = ''
      store.error = '服务暂不可用'
      store.lastFailedInstruction = '精简本页文字'
    })
    host = document.createElement('div')
    document.body.appendChild(host)
    app = createApp({ render: () => h(ModifyPanel, { scope: 'page', targetNodeId: 'page_node_2' }) })
    app.use(pinia)
    app.mount(host)
    expect(host.textContent).toContain('提交并立即应用')
    expect(host.querySelector('.active-page-bar')).toBeNull()
    host.querySelector('.send-btn').click()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(send).toHaveBeenCalledOnce()
    expect(store.inputText).toBe('精简本页文字')
    store.pendingTaskId = 'task_running'
    await nextTick()
    expect(host.querySelector('.send-btn').disabled).toBe(true)
    host.querySelector('.send-btn').click()
    expect(send).toHaveBeenCalledOnce()
  })
})

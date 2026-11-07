// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import StepNav from './StepNav.vue'
import AppToast from './AppToast.vue'
import LoadingState from './LoadingState.vue'
import EmptyState from './EmptyState.vue'
import ErrorState from './ErrorState.vue'

const routeNames = ['S1Intent', 'S2Material', 'S3Studio', 'S4Version', 'Middle']

function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: routeNames.map(name => ({
      path: `/${name.toLowerCase()}`,
      name,
      component: { render: () => h('div') }
    }))
  })
}

const mounted = []

async function mount(Component, props = {}) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const router = createTestRouter()
  await router.push('/s1intent')
  await router.isReady()
  const app = createApp({ render: () => h(Component, props) })
  app.use(router)
  app.mount(host)
  await nextTick()
  const handle = {
    host,
    router,
    unmount() {
      app.unmount()
      host.remove()
    }
  }
  mounted.push(handle)
  return handle
}

afterEach(() => {
  while (mounted.length) mounted.pop().unmount()
  document.body.innerHTML = ''
})

describe('StepNav · 统一流程导航', () => {
  it('主流程只呈现 S1 → S3 → S4 三步，S2 是可选补充入口', async () => {
    const { host } = await mount(StepNav, { current: 's1', projectId: 'p1' })
    const items = host.querySelectorAll('.step-nav__item')
    expect(items.length).toBe(3)
    expect(host.querySelector('.step-nav__rail').textContent).toContain('意图理解')
    expect(host.querySelector('.step-nav__rail').textContent).toContain('课件生成')
    expect(host.querySelector('.step-nav__rail').textContent).toContain('版本与导出')
    expect(host.querySelector('.step-nav__rail').textContent).not.toContain('资料上传')
    expect(host.querySelector('.step-nav__optional').textContent).toContain('补充资料（可选）')
    expect(host.querySelector('.step-nav__back').textContent).toContain('返回中间页')
  })

  it('当前步有 aria-current，已完成步有 is-done', async () => {
    const { host } = await mount(StepNav, { current: 's3' })
    const items = [...host.querySelectorAll('.step-nav__item')]
    expect(items[1].getAttribute('aria-current')).toBe('step')
    expect(items[0].classList.contains('is-done')).toBe(true)
    expect(items[2].classList.contains('is-done')).toBe(false)
  })

  it('ready=false 时非当前步不可点击，并标注 aria-disabled', async () => {
    const { host } = await mount(StepNav, { current: 's1', ready: false })
    const disabled = host.querySelectorAll('.step-nav__rail [aria-disabled="true"]')
    expect(disabled.length).toBe(2)
    expect(host.querySelector('.step-nav__optional').getAttribute('aria-disabled')).toBe('true')
  })

  it('overrides 能保留 S4 页带 generation_id 的跳转参数', async () => {
    const { host } = await mount(StepNav, {
      current: 's4',
      projectId: 'p1',
      overrides: { s3: { name: 'S3Studio', query: { project_id: 'p1', generation_id: 'g9' } } }
    })
    const s3 = [...host.querySelectorAll('.step-nav__rail a')].find(a => a.textContent.includes('课件生成'))
    expect(s3.getAttribute('href')).toContain('generation_id=g9')
  })

  it('actionKeys 渲染为按钮，只发 step-action 不触发路由跳转', async () => {
    const onStepAction = vi.fn()
    const { host, router } = await mount(StepNav, {
      current: 's2',
      actionKeys: ['s3'],
      onStepAction
    })
    const button = host.querySelector('.step-nav__link--button')
    expect(button).not.toBeNull()
    expect(button.textContent).toContain('课件生成')
    button.click()
    await nextTick()
    expect(onStepAction).toHaveBeenCalledWith('s3')
    expect(router.currentRoute.value.name).toBe('S1Intent')
  })

  it('普通步骤点击只发 step-click 通知，不劫持路由', async () => {
    const onStepClick = vi.fn()
    const { host } = await mount(StepNav, { current: 's1', onStepClick })
    const link = [...host.querySelectorAll('.step-nav__rail a')].find(a => a.textContent.includes('课件生成'))
    link.click()
    await nextTick()
    expect(onStepClick).toHaveBeenCalledWith('s3')
  })
})

describe('AppToast · 全局反馈', () => {
  it('按类型渲染语义与文案', () => {
    return mount(AppToast, { visible: true, message: '保存成功', type: 'error', onDismiss: vi.fn() })
      .then(() => {
        const toast = document.querySelector('.app-toast')
        expect(toast).not.toBeNull()
        expect(toast.textContent).toContain('保存成功')
        expect(toast.getAttribute('role')).toBe('alert')
        expect(toast.classList.contains('app-toast--error')).toBe(true)
      })
  })

  it('空文案不渲染，关闭按钮可发 dismiss', async () => {
    const onDismiss = vi.fn()
    await mount(AppToast, { visible: true, message: '', onDismiss })
    expect(document.querySelector('.app-toast')).toBeNull()
    await mount(AppToast, { visible: true, message: '提示', onDismiss })
    document.querySelector('.app-toast__close').click()
    expect(onDismiss).toHaveBeenCalled()
  })
})

describe('统一状态组件', () => {
  it('LoadingState 三态都有正确的无障碍语义', async () => {
    const loading = await mount(LoadingState, { type: 'loading', text: '加载中' })
    expect(loading.host.querySelector('[role="status"]')).not.toBeNull()
    loading.unmount()
    mounted.pop()

    const error = await mount(LoadingState, { type: 'error', text: '加载失败' })
    expect(error.host.querySelector('[role="alert"]')).not.toBeNull()
    error.unmount()
    mounted.pop()

    const empty = await mount(LoadingState, { type: 'empty', text: '暂无数据' })
    expect(empty.host.querySelector('[role]')).toBeNull()
    expect(empty.host.textContent).toContain('暂无数据')
  })

  it('EmptyState 转发标题 / 说明 / 动作事件', async () => {
    const onAction = vi.fn()
    const { host } = await mount(EmptyState, {
      title: '还没有课件',
      description: '开始创建第一份课件',
      actionText: '新建课件',
      onAction
    })
    expect(host.textContent).toContain('还没有课件')
    expect(host.textContent).toContain('开始创建第一份课件')
    host.querySelector('.loading-state__action').click()
    expect(onAction).toHaveBeenCalled()
  })

  it('ErrorState 把重试动作映射为 retry 事件', async () => {
    const onRetry = vi.fn()
    const { host } = await mount(ErrorState, {
      title: '课件加载失败',
      description: '网络异常',
      retryText: '重试加载',
      onRetry
    })
    expect(host.textContent).toContain('课件加载失败')
    host.querySelector('.loading-state__action').click()
    expect(onRetry).toHaveBeenCalled()
  })
})

// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, reactive } from 'vue'
import S3StageNav from '../components/teacher/S3StageNav.vue'

let app
let host
afterEach(() => { app?.unmount(); host?.remove(); app = null })

function mountNav(initial) {
  const state = reactive(initial)
  const onSelect = vi.fn(phase => { state.phase = phase })
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(S3StageNav, { ...state, onSelect }) })
  app.mount(host)
  return { state, onSelect, buttons: () => [...host.querySelectorAll('button')] }
}

describe('S3 三阶段导航', () => {
  it('首次只开放大纲，确认后开放内容', async () => {
    const nav = mountNav({ phase: 'outline', outlineConfirmed: false, reviewReady: false })
    expect(nav.buttons().map(button => button.textContent)).toEqual(['大纲', '内容', '审阅'])
    expect(nav.buttons()[1].disabled).toBe(true)
    expect(nav.buttons()[2].disabled).toBe(true)
    nav.state.outlineConfirmed = true
    await nextTick()
    nav.buttons()[1].click()
    await nextTick()
    expect(nav.onSelect).toHaveBeenCalledWith('content')
    expect(nav.buttons()[1].getAttribute('aria-current')).toBe('step')
  })

  it('有实际可预览内容才开放审阅，并能返回内容', async () => {
    const nav = mountNav({ phase: 'content', outlineConfirmed: true, reviewReady: false })
    nav.buttons()[2].click()
    expect(nav.onSelect).not.toHaveBeenCalled()
    nav.state.reviewReady = true
    await nextTick()
    nav.buttons()[2].click()
    await nextTick()
    expect(nav.state.phase).toBe('review')
    nav.buttons()[1].click()
    expect(nav.state.phase).toBe('content')
  })
})

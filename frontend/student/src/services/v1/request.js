import { API_BASE } from '../../config/api'

export async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || (typeof payload.code !== 'undefined' && payload.code !== 200)) {
    throw new Error(payload.message || `请求失败: ${response.status}`)
  }
  return payload
}

export async function requestSSE(path, body, handlers = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })

  if (!response.ok || !response.body) {
    throw new Error(`请求失败: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  const emitFrame = (frame) => {
    const lines = frame.split('\n').map(line => line.trim()).filter(Boolean)
    let eventName = 'message'
    let dataLine = ''
    lines.forEach((line) => {
      if (line.startsWith('event:')) eventName = line.slice(6).trim()
      if (line.startsWith('data:')) dataLine += line.slice(5).trim()
    })
    if (!dataLine) return
    let payload = {}
    try {
      payload = JSON.parse(dataLine)
    } catch (error) {
      payload = { text: dataLine }
    }
    const handler = handlers[eventName]
    if (typeof handler === 'function') handler(payload)
  }

  let doneReading = false
  while (!doneReading) {
    const { value, done } = await reader.read()
    doneReading = done
    if (doneReading) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    frames.forEach(emitFrame)
  }

  if (buffer.trim()) emitFrame(buffer)
}

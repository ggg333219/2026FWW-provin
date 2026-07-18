import { requestJson } from './request'

export const studentKnowledgeApi = {
  parse: (body) => requestJson('/api/v1/ai/parse-knowledge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
}

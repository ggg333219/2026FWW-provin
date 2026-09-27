const clean = (value) => String(value ?? '').trim()

const list = (value) => (Array.isArray(value) ? value : [])
  .map(clean)
  .filter(Boolean)

/** 将 S1 结构化意图收敛为稳定、可复现的全课件检索查询。 */
export function buildIntentEvidenceQuery(intent = {}) {
  const segments = [
    clean(intent.topic),
    ...list(intent.knowledge_points),
    ...list(intent.key_difficulties),
    ...list(intent.expected_outcomes),
    clean(intent.target_student),
  ].filter(Boolean)
  return [...new Set(segments)].join('；')
}

export function evidenceIds(packet) {
  if (!packet || typeof packet !== 'object') return []
  const values = [
    ...(packet.citations || []),
    ...(packet.relevant_chunks || []),
  ].map((item) => clean(item?.chunk_id || item?.id)).filter(Boolean)
  return [...new Set(values)]
}

/** 识别旧版空 Markdown 生成的单节点占位大纲，避免其跨项目缓存后继续复用。 */
export function isPlaceholderOutline(nodes = []) {
  if (!Array.isArray(nodes) || nodes.length !== 1) return false
  const node = nodes[0] || {}
  const text = [node.title, node.summary, node.content, ...(node.key_points || [])].join(' ')
  return text.includes('当前课件仅含标题')
    || text.includes('未提供可切分正文')
    || text.includes('未提供正文')
}

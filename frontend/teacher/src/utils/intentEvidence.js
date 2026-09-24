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

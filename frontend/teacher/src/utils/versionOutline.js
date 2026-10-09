const EDITABLE_TYPES = new Set(['content', 'section', 'quiz', 'interactive', 'summary'])

export function shouldAutoGenerateOutline({ allowAutoGenerate, ready, outlineId, nodeCount, intentSummary }) {
  return Boolean(allowAutoGenerate && ready && !outlineId && nodeCount === 0 && intentSummary)
}

function outlineType(node) {
  if (node?.interactive_plan?.kind === 'flashcard') return 'interactive'
  const raw = String(node?.node_type || node?.type || '').toLowerCase()
  if (EDITABLE_TYPES.has(raw)) return raw
  if (raw === 'divider' || raw === 'agenda') return 'section'
  return 'content'
}

/** Build a new editable outline from the selected version, never from the latest project draft. */
export function outlineFromVersion(outline, contentNodes = [], title = '') {
  const original = Array.isArray(outline?.nodes) && outline.nodes.length
    ? outline.nodes
    : (Array.isArray(contentNodes) ? contentNodes : []).filter((node) =>
      node?.node_id && !String(node.node_id).startsWith('__auto_'))
  const nodes = original.map((node, index) => ({
    node_id: String(node.node_id || `version_node_${index + 1}`),
    order: index + 1,
    title: String(node.title || `第 ${index + 1} 页`),
    summary: String(node.summary || ''),
    node_type: outlineType(node),
    key_points: Array.isArray(node.key_points) ? [...node.key_points]
      : (Array.isArray(node.core_points) ? [...node.core_points] : []),
    estimated_duration_minutes: Number(node.estimated_duration_minutes) > 0
      ? Number(node.estimated_duration_minutes) : 5,
    source_chunk_ids: Array.isArray(node.source_chunk_ids) ? [...node.source_chunk_ids] : [],
    interactive_plan: node.interactive_plan || null,
  }))
  return {
    title: String(outline?.title || title || ''),
    session_id: String(outline?.session_id || ''),
    intent_id: String(outline?.intent_id || ''),
    nodes,
  }
}

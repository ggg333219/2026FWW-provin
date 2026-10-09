/** Drop pages sourced from outline nodes that were explicitly deleted. */
export function filterDeletedOutlineNodes(nodes, deletedIds = []) {
  const removed = new Set((deletedIds || []).map(String))
  if (!removed.size) return Array.isArray(nodes) ? nodes : []
  return (Array.isArray(nodes) ? nodes : []).filter((node) =>
    !removed.has(String(node?.node_id || ''))
    && !removed.has(String(node?.source_node_id || '')))
}

/** Identify an old generated page without removing intentionally added pages automatically. */
export function isGeneratedPageOutsideOutline(page, outlineNodes = []) {
  if (!Array.isArray(outlineNodes) || !outlineNodes.length || !page?.node_id) return false
  if (String(page.node_id).startsWith('__auto_')) return false
  const active = new Set(outlineNodes.map((node) => String(node.node_id || '')))
  return !active.has(String(page.node_id))
    && !active.has(String(page.source_node_id || ''))
}

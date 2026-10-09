/** 将大纲中的翻卡规划补到版本内容；旧版本可能完全缺少互动节点。 */
export function withOutlineInteractivePlans(nodes = [], outlineNodes = []) {
  const outline = (Array.isArray(outlineNodes) ? outlineNodes : [])
    .filter((node) => node?.node_id && node?.interactive_plan?.kind)
  const byId = new Map(outline.map((node) => [String(node.node_id), node]))
  const content = Array.isArray(nodes) ? nodes : []
  const seen = new Set(content.map((node) => String(node?.node_id || node?.nodeId || '')))
  const merged = content.map((node) => {
    const source = byId.get(String(node?.node_id || node?.nodeId || ''))
    if (!source) return node
    if (source.interactive_plan.kind === 'flashcard') {
      return {
        ...node,
        node_type: 'interactive', type: 'interactive',
        interactive_plan: source.interactive_plan,
        key_points: node.key_points?.length ? node.key_points : (source.key_points || []),
        summary: node.summary || source.summary || '',
      }
    }
    return node?.interactive_plan?.kind ? node : { ...node, interactive_plan: source.interactive_plan }
  })
  for (const node of outline) {
    if (node.interactive_plan.kind !== 'flashcard' || seen.has(String(node.node_id))) continue
    merged.push({ ...node, node_type: 'interactive', type: 'interactive' })
    seen.add(String(node.node_id))
  }
  return merged
}

/** S3 生成成功后把素材放进实际保存的内容节点，而不只放在临时互动 store。 */
export function withGeneratedInteractiveAsset(nodes = [], outlineNode = {}, asset = {}) {
  const nodeId = String(outlineNode?.node_id || '')
  if (!nodeId) return Array.isArray(nodes) ? nodes : []
  const items = Array.isArray(asset?.items) ? asset.items : []
  const cardMode = outlineNode?.interactive_plan?.kind === 'flashcard'
  const content = Array.isArray(nodes) ? nodes : []
  const apply = (node) => ({
    ...node,
    ...(cardMode ? { node_type: 'interactive', type: 'interactive' } : {}),
    interactive_plan: outlineNode.interactive_plan || node.interactive_plan || null,
    interactive_items: items,
    metadata: {
      ...(node.metadata || {}),
      interactive_asset: { ...asset, items },
      interactive_entry_url: asset.entry_url || asset.file_url || '',
    },
  })
  let matched = false
  const merged = content.map((node) => {
    if (String(node?.node_id || node?.nodeId || '') !== nodeId) return node
    matched = true
    return apply(node)
  })
  if (!matched) merged.push(apply({ ...outlineNode, node_id: nodeId }))
  return merged
}

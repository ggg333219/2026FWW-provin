import { describe, expect, it } from 'vitest'
import { withGeneratedInteractiveAsset, withOutlineInteractivePlans } from './interactiveExport'

describe('HTML5 导出旧版本翻卡规划', () => {
  it('按节点 ID 从已保存大纲补回翻卡规划', () => {
    const nodes = [{ node_id: 'n1', title: '排序算法' }, { node_id: 'n2', title: '普通页' }]
    const outline = [{ node_id: 'n1', interactive_plan: { kind: 'flashcard' } }]
    const result = withOutlineInteractivePlans(nodes, outline)
    expect(result[0].interactive_plan.kind).toBe('flashcard')
    expect(result[1].interactive_plan).toBeUndefined()
    expect(nodes[0].interactive_plan).toBeUndefined()
  })

  it('保留节点上更新过的互动规划，不被旧大纲覆盖', () => {
    const nodes = [{ node_id: 'n1', interactive_plan: { kind: 'quiz' } }]
    const outline = [{ node_id: 'n1', interactive_plan: { kind: 'flashcard' } }]
    expect(withOutlineInteractivePlans(nodes, outline)[0].interactive_plan.kind).toBe('flashcard')
  })

  it('adds a missing flashcard outline node to an old version export', () => {
    const nodes = [{ node_id: 'content_1', title: 'Course content' }]
    const outline = [{ node_id: 'card_1', title: 'Quick sort', summary: 'Divide and conquer', interactive_plan: { kind: 'flashcard' } }]
    const result = withOutlineInteractivePlans(nodes, outline)
    expect(result).toHaveLength(2)
    expect(result[1]).toMatchObject({ node_id: 'card_1', type: 'interactive', summary: 'Divide and conquer' })
  })

  it('stores generated flashcards in the version content even when the node was missing', () => {
    const card = { type: 'flashcard', front: 'Quick sort', back: 'Divide and conquer' }
    const outlineNode = { node_id: 'card_1', title: 'Quick sort', interactive_plan: { kind: 'flashcard' } }
    const asset = { interactive_asset_id: 'asset_1', status: 'done', items: [card] }
    const result = withGeneratedInteractiveAsset([{ node_id: 'content_1' }], outlineNode, asset)
    expect(result).toHaveLength(2)
    expect(result[1].metadata.interactive_asset.items).toEqual([card])
    expect(result[1].interactive_items).toEqual([card])
    expect(result[1].type).toBe('interactive')
  })

  it('replaces stale quiz items on the matching saved node', () => {
    const card = { type: 'flashcard', front: 'Partition', back: 'Split by pivot' }
    const nodes = [{ node_id: 'card_1', type: 'quiz', interactive_items: [{ type: 'quiz' }] }]
    const outlineNode = { node_id: 'card_1', interactive_plan: { kind: 'flashcard' } }
    const result = withGeneratedInteractiveAsset(nodes, outlineNode, { status: 'done', items: [card] })
    expect(result).toHaveLength(1)
    expect(result[0].interactive_items).toEqual([card])
    expect(result[0].type).toBe('interactive')
  })
})

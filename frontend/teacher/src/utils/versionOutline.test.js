import { describe, expect, it } from 'vitest'
import { outlineFromVersion, shouldAutoGenerateOutline } from './versionOutline'

describe('version outline reuse', () => {
  it('never auto-generates for a version fork, even before the snapshot arrives', () => {
    expect(shouldAutoGenerateOutline({ allowAutoGenerate: false, ready: true, outlineId: '', nodeCount: 0, intentSummary: { topic: 'Sorting' } })).toBe(false)
    expect(shouldAutoGenerateOutline({ allowAutoGenerate: true, ready: true, outlineId: '', nodeCount: 0, intentSummary: { topic: 'Sorting' } })).toBe(true)
  })
  it('preserves the selected version outline instead of rebuilding from content', () => {
    const selected = { title: 'Sorting', nodes: [
      { node_id: 'a', title: 'Bubble sort', summary: 'Adjacent swap', node_type: 'content', order: 9 },
      { node_id: 'b', title: 'Quick sort', summary: 'Divide and conquer', node_type: 'interactive', interactive_plan: { kind: 'flashcard' } },
    ] }
    const result = outlineFromVersion(selected, [{ node_id: 'old', title: 'Wrong content' }])
    expect(result.nodes.map((node) => node.node_id)).toEqual(['a', 'b'])
    expect(result.nodes.map((node) => node.order)).toEqual([1, 2])
    expect(result.nodes[1].interactive_plan.kind).toBe('flashcard')
  })

  it('reconstructs a legacy version without an outline and skips generated pages', () => {
    const result = outlineFromVersion(null, [
      { node_id: '__auto_cover', title: 'Cover', type: 'cover' },
      { node_id: 'n1', title: 'Quick sort', type: 'slide', summary: 'Partition', core_points: ['Pivot'] },
    ], 'Sorting')
    expect(result.title).toBe('Sorting')
    expect(result.nodes).toMatchObject([{ node_id: 'n1', order: 1, node_type: 'content', key_points: ['Pivot'] }])
  })
})

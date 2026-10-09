import { describe, expect, it } from 'vitest'
import { filterDeletedOutlineNodes, isGeneratedPageOutsideOutline } from './outlineDeletion'

describe('outline deletion', () => {
  it('removes the deleted page and generated children without touching other pages', () => {
    const pages = [
      { node_id: 'n1', title: '保留' },
      { node_id: 'n2', title: '删除' },
      { node_id: 'child', source_node_id: 'n2', title: '删除的续页' },
      { node_id: '__auto_cover__', title: '封面' },
    ]
    expect(filterDeletedOutlineNodes(pages, ['n2']).map((node) => node.node_id))
      .toEqual(['n1', '__auto_cover__'])
  })

  it('leaves the generated pages intact when nothing was deleted', () => {
    const pages = [{ node_id: 'n1' }]
    expect(filterDeletedOutlineNodes(pages)).toBe(pages)
  })

  it('shows old pages outside the outline without flagging generated children or auto pages', () => {
    const outline = [{ node_id: 'n1' }]
    expect(isGeneratedPageOutsideOutline({ node_id: 'n2' }, outline)).toBe(true)
    expect(isGeneratedPageOutsideOutline({ node_id: 'child', source_node_id: 'n1' }, outline)).toBe(false)
    expect(isGeneratedPageOutsideOutline({ node_id: '__auto_cover__' }, outline)).toBe(false)
  })
})

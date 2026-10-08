import { describe, expect, it } from 'vitest'
import { resolveSavedProjectVersion } from './coursewareVersion'

describe('resolveSavedProjectVersion', () => {
  it('uses the persisted project version instead of the independent AI counter', () => {
    expect(resolveSavedProjectVersion({ version_no: 1 }, 2)).toBe(1)
  })

  it('supports legacy generation-only saves', () => {
    expect(resolveSavedProjectVersion(null, 3)).toBe(3)
  })
})

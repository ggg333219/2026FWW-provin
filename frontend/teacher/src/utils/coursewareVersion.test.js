import { describe, expect, it } from 'vitest'
import { resolveSavedProjectVersion } from './coursewareVersion'

describe('resolveSavedProjectVersion', () => {
  it('prefers the persisted project version number', () => {
    expect(resolveSavedProjectVersion({ version_no: 4 }, 2)).toBe(4)
    expect(resolveSavedProjectVersion({ version: 5 }, 2)).toBe(5)
  })

  it('falls back to the generation version when project data has no version', () => {
    expect(resolveSavedProjectVersion({}, 3)).toBe(3)
  })
})

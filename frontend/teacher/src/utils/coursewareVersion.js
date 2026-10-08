export function resolveSavedProjectVersion(projectVersion, generationVersion = 0) {
  const persistedVersion = Number(projectVersion?.version_no ?? projectVersion?.version ?? 0)
  return persistedVersion > 0 ? persistedVersion : Number(generationVersion) || 0
}

const STORAGE_KEY = 'teacher-local-auth-users'

function isStorageLike(storage) {
  return Boolean(storage && typeof storage.getItem === 'function' && typeof storage.setItem === 'function')
}

export function getLocalAuthStore(storage = window.localStorage) {
  if (!storage) return {}
  try {
    const raw = storage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export function saveLocalAuthStore(store, storage = window.localStorage) {
  if (!storage) return
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(store))
  } catch {
    // noop
  }
}

export function registerLocalUser(username, password, storage = window.localStorage) {
  const normalizedUsername = String(username || '').trim().toLowerCase()
  if (!normalizedUsername || !String(password || '').trim()) {
    throw new Error('用户名和密码不能为空')
  }

  const store = getLocalAuthStore(storage)
  const user = {
    username: normalizedUsername,
    password: String(password || '').trim(),
    role: 'teacher'
  }
  store[normalizedUsername] = user
  saveLocalAuthStore(store, storage)
  return { username: user.username, role: user.role }
}

export function authenticateLocalUser(username, password, storage = window.localStorage) {
  const normalizedUsername = String(username || '').trim().toLowerCase()
  const normalizedPassword = String(password || '').trim()
  const store = getLocalAuthStore(storage)
  const user = store[normalizedUsername]

  if (!user || user.password !== normalizedPassword || user.role === 'student') {
    throw new Error('账号或密码错误')
  }

  return { username: user.username, role: 'teacher' }
}

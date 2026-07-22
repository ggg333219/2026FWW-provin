import test from 'node:test'
import assert from 'node:assert/strict'
import { registerLocalUser, authenticateLocalUser } from './authFallback.js'

test('registerLocalUser stores a user for later login', () => {
  const storage = {}
  const user = registerLocalUser('demo', '1234', 'teacher', storage)

  assert.equal(user.username, 'demo')
  assert.equal(user.role, 'teacher')
  assert.equal(storage.localAuthUsers.demo.password, '1234')
})

test('authenticateLocalUser accepts a registered local account', () => {
  const storage = {}
  registerLocalUser('demo', '1234', 'student', storage)
  const result = authenticateLocalUser('demo', '1234', storage)

  assert.deepEqual(result, { username: 'demo', role: 'student' })
})

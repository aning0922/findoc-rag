import assert from 'node:assert/strict'
import test from 'node:test'

import {
  canChangeDocument,
  canStartRequest,
  createRequestSnapshot,
  isCurrentRequest,
  isRequestDocumentReady,
  type RequestSnapshot,
} from '../src/requestOwnership.ts'

test('活动请求在 React 重渲染前也阻止重复提交', () => {
  const request = createRequestSnapshot(1, 'document-a', '查询2025年度营业收入')

  assert.equal(canStartRequest(null), true)
  assert.equal(canStartRequest(request), false)
})

test('pending 时文档切换同时受实际入口守卫保护', () => {
  const request = createRequestSnapshot(1, 'document-a', '查询2025年度营业收入')

  assert.equal(canChangeDocument(request), false)
  assert.equal(canChangeDocument(null), true)
})

test('相同文档和问题的迟到请求仍按本地请求身份丢弃', () => {
  const oldRequest = createRequestSnapshot(1, 'document-a', '查询2025年度营业收入')
  const currentRequest = createRequestSnapshot(2, 'document-a', '查询2025年度营业收入')

  assert.equal(isCurrentRequest(currentRequest, oldRequest), false)
  assert.equal(isCurrentRequest(currentRequest, currentRequest), true)
})

test('文档消失或失去 ready 会使提交快照失效', () => {
  const request = createRequestSnapshot(1, 'document-a', '查询2025年度营业收入')

  assert.equal(isRequestDocumentReady([
    { document_id: 'document-a', status: 'ready' },
  ], request), true)
  assert.equal(isRequestDocumentReady([
    { document_id: 'document-a', status: 'indexing' },
  ], request), false)
  assert.equal(isRequestDocumentReady([
    { document_id: 'document-b', status: 'ready' },
  ], request), false)
})

test('旧 finally 不能清除新请求拥有的 pending', () => {
  const oldRequest = createRequestSnapshot(1, 'document-a', '查询2025年度营业收入')
  const newRequest = createRequestSnapshot(2, 'document-b', '查询2024年度净利润')
  let activeRequest: RequestSnapshot | null = newRequest

  if (isCurrentRequest(activeRequest, oldRequest)) {
    activeRequest = null
  }

  assert.equal(activeRequest, newRequest)
})

test('请求快照拒绝空身份和非法请求号', () => {
  assert.throws(
    () => createRequestSnapshot(0, 'document-a', '查询2025年度营业收入'),
    /请求号/,
  )
  assert.throws(
    () => createRequestSnapshot(1, '   ', '查询2025年度营业收入'),
    /文档 ID/,
  )
  assert.throws(
    () => createRequestSnapshot(1, 'document-a', '   '),
    /问题/,
  )
})

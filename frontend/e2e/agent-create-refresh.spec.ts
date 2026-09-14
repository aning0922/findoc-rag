import { expect, test } from '@playwright/test'


const CONTROLLED_DOCUMENT_ID = 'controlled-synthetic-document'
const CONTROLLED_SOURCE_FILE = 'controlled-synthetic-finance.pdf'

test('创建 answered Run 后刷新只用 GET 恢复同一结果', async ({ page }) => {
  /**
   * 输入：受控 ready 文档、2025 年和营业收入。
   * 输出：页面展示一次创建所得的 answered、金额、引用和 Run 身份。
   * 边界：刷新必须从同一浏览器 context 经 GET 读回，禁止 mock API 或再次 POST。
   */
  const runCreateRequests: string[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (request.method() === 'POST' && url.pathname === '/api/agent/runs') {
      runCreateRequests.push(request.url())
    }
  })

  const documentsResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return response.request().method() === 'GET' && url.pathname === '/api/documents'
  })
  await page.goto('/')
  const documentsResponse = await documentsResponsePromise
  expect(documentsResponse.status()).toBe(200)
  const documents = await documentsResponse.json() as Array<Record<string, unknown>>
  expect(documents).toContainEqual(expect.objectContaining({
    document_id: CONTROLLED_DOCUMENT_ID,
    source_file: CONTROLLED_SOURCE_FILE,
    status: 'ready',
  }))

  await page.getByRole('radio', { name: new RegExp(CONTROLLED_SOURCE_FILE) }).check()
  await page.getByRole('button', { name: 'Agent 有限任务' }).click()
  await page.getByLabel('年份').fill('2025')
  await page.getByLabel('指标').selectOption('营业收入')

  const createResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname === '/api/agent/runs'
  })
  await page.getByRole('button', { name: '创建并执行 Agent Run' }).click()
  const createResponse = await createResponsePromise
  expect(createResponse.status()).toBe(201)
  const created = await createResponse.json() as Record<string, unknown>
  const runId = created.run_id
  expect(typeof runId).toBe('string')
  expect(runId).not.toBe('')
  expect(created).toMatchObject({
    document_id: CONTROLLED_DOCUMENT_ID,
    user_result: { status: 'answered' },
  })

  const resultCard = page.locator('.result-card')
  await expect(resultCard.getByText('answered', { exact: true })).toBeVisible()
  await expect(resultCard).toContainText('120万元')
  await expect(resultCard).toContainText(CONTROLLED_SOURCE_FILE)
  await expect(resultCard).toContainText('第 1 页')
  await expect(resultCard).toContainText(String(runId))
  expect(runCreateRequests).toHaveLength(1)

  const resultPath = `/api/agent/runs/${encodeURIComponent(String(runId))}`
  const restoredResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === resultPath
      && response.status() === 200
  })
  await page.reload()
  const restoredResponse = await restoredResponsePromise
  const restored = await restoredResponse.json() as Record<string, unknown>
  expect(restored).toMatchObject({
    run_id: runId,
    document_id: CONTROLLED_DOCUMENT_ID,
    user_result: { status: 'answered' },
  })

  const restoredResultCard = page.locator('.result-card')
  await expect(restoredResultCard.getByText('answered', { exact: true })).toBeVisible()
  await expect(restoredResultCard).toContainText('120万元')
  await expect(restoredResultCard).toContainText(CONTROLLED_SOURCE_FILE)
  await expect(restoredResultCard).toContainText(String(runId))
  expect(runCreateRequests).toHaveLength(1)
})

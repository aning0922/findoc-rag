import { consumeSSEStream } from './sse'
import type { ChangeEvent } from 'react'
import { useEffect, useState } from 'react'

type ChatViewStatus =
  | 'idle' //尚未提问
  | 'streaming' //请求已经开始，但还没有可信终态
  | 'success' //收到合法答案，引用以及 done(success)
  | 'refusal' //收到正常拒答以及 done(refusal)
  | 'error' //HTTP错误，系统失败或流协议不完整

interface CitationView {
  number: number
  source_file: string
  page: number
  chunk_id: string
}

interface ChatViewState {
  status: ChatViewStatus
  answer: string | null
  citations: CitationView[]
  refusalReason: string | null
  errorMessage: string | null
}

const INITIAL_CHAT_VIEW: ChatViewState = {
  status: 'idle',
  answer: null,
  citations: [],
  refusalReason: null,
  errorMessage: null,
}

type DocumentStatus =
  | 'queued'
  | 'parsing'
  | 'indexing'
  | 'ready'
  | 'failed'

type FailureStage = 'queued' | 'parsing' | 'indexing'

interface DocumentRecord {
  document_id: string
  source_file: string
  status: DocumentStatus
  failed_stage: FailureStage | null
  error_code: string | null
  safe_error_message: string | null
  created_at: string
  updated_at: string
}

/**
 * 确认 SSE data 是可以按字段读取的普通 JSON 对象。
 *
 * @param data - JSON.parse 返回的未经信任数据。
 * @returns 可以通过字符串键读取的普通对象。
 * @throws data 不是对象、为 null 或为数组时抛出 Error。
 */
function requireDataObject(data: unknown): Record<string, unknown> {
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    throw new Error('SSE data 必须是 JSON 对象')
  }
  return data as Record<string, unknown>
}

/**
 * 展示PDF上传、文档状态轮询和可信SSE问答的单页薄壳。
 *
 * @returns 包含文档选择、问题提交和可信终态展示的React页面。
 * @remarks 只在收到匹配的done后提交答案或拒答；网络和协议失败显示安全错误。
 */
function App() {
  // 保存后端返回的文档列表
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  // 表示文档列表请求是否仍在进行，用于控制加载提示和按钮
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true)
  // 保存可以展示给用户的安全错误消息，null 表示当前没有错误
  const [documentError, setDocumentError] = useState<string | null>(null)
  // 保存用户当前选择的 ready 文档身份；null 表示尚未选择
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null)
  // 保存用户从文件选择框中选中的 PDF；null 表示尚未选中
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  // 表示 PDF 上传请求是否正在进行，用于防止重复提交
  const [isUploading, setIsUploading] = useState(false)
  // 保存可以展示给用户的安全上传错误；null 表示当前没有错误
  const [uploadError, setUploadError] = useState<string | null>(null)
  // 保存上传请求成功后的业务提示；null 表示当前没有提示
  const [uploadMessage, setUploadMessage] = useState<string | null>(null)
  // 保存用户针对当前 ready 文档输入的问题；空字符串表示尚未输入
  const [query, setQuery] = useState('')
  // 保存一次聊天请求当前可展示的可信页面状态
  const [chatView, setChatView] = useState<ChatViewState>(INITIAL_CHAT_VIEW)

  /**
   * 从后端加载固定 workspace 的文档列表
   *
   * 输入：无
   * 输出：Promise<void>，数据通过 React 状态保存，不直接返回
   * 失败：网络异常或非 2xx 响应时保存安全错误信息
   */
  async function loadDocuments(): Promise<void> {
    try {
      const response = await fetch(`/api/documents`)
      if (!response.ok) {
        throw new Error('Failed to load documents')
      }
      const data = (await response.json()) as DocumentRecord[]
      setDocumentError(null)
      setDocuments(data)
    }
    catch {
      setDocumentError('无法加载文档，请稍后重试')
    } finally {
      setIsLoadingDocuments(false)
    }
  }
  /**
   * 响应用户的重新加载操作，并恢复请求前的页面状态
   *
   * 输入：无
   * 输出：void 请求由 loadDocuments 异步执行
   * 失败：具体失败状态由 loadDocuments 统一处理
   */
  function handleReloadDocuments(): void {
    setIsLoadingDocuments(true)
    setDocumentError(null)
    void loadDocuments()
  }

  /**
   * 读取文件输入框当前选中的第一个文件并保存到 React 状态
   *
   * @param event - 文件输入框产生的 change 事件
   * @returns void 选中的 File 通过 React 保存
   * 边界：用户取消选择或文件列表为空时保存 null
   */
  function handleFileChange(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.currentTarget.files?.[0] ?? null
    setSelectedFile(file)
  }

  /**
   * 把用户选中的 PDF 作为 multipart/form-data 请求提交到后端
   *
   * 输入：无，文件从 selectedFile 状态读取
   * 输出：Promise<void>，成功后刷新文档列表并更新可见提示
   * 失败：未选择文件，网络异常或非 2xx 响应时保存安全错误
   */
  async function uploadSelectedDocument(): Promise<void> {
    if (selectedFile === null) {
      setUploadError("请先选择 PDF 文件")
      return
    }

    setIsUploading(true)
    setUploadError(null)
    setUploadMessage(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      const response = await fetch('/api/documents', {
        method: 'POST',
        body: formData
      })
      if (!response.ok) {
        throw new Error('Failed to upload document')
      }
      setUploadMessage('上传已提交，等待处理')
      await loadDocuments()
    }
    catch {
      setUploadError('上传失败，请稍后重试')
    } finally {
      setIsUploading(false)
    }
  }


  /**
   * 把聊天文本框的最新内容保存到 React 状态
   *
   * @param event - textarea 产生的 change 事件
   * 输出：void，问题文本通过 React 状态保存
   * 边界：允许用户编辑为空字符串，提交时再禁止空问题
   */
  function handleQueryChange(event: ChangeEvent<HTMLTextAreaElement>): void {
    setQuery(event.currentTarget.value)
  }


  useEffect(() => {
    // 初次挂载需要同步外部文档服务；状态只会在等待网络响应后更新
    // oxlint-disable-next-line react/set-state-in-effect
    void loadDocuments()
  }, [])

  useEffect(() => {
    // 只有存在处理中且列表请求正常的文档时，才安排下一次刷新
    const hasProcessingDocuments = documents.some(
      (document) =>
        document.status === 'queued' ||
        document.status === 'parsing' ||
        document.status === 'indexing',
    )

    if (!hasProcessingDocuments || documentError !== null) {
      return
    }

    // 使用一次性定时器，避免上一轮请求未完成时启动下一轮
    const timerId = window.setTimeout(() => {
      void loadDocuments()
    }, 1500)

    return () => {
      window.clearTimeout(timerId)
    }
  }, [documents, documentError])

  const selectedReadyDocument =
    documents.find(
      (document) =>
        document.document_id === selectedDocumentId && document.status === 'ready'
    ) ?? null

  /**
   * 向当前 ready 文档提交问题并消费可信 SSE 终态
   *
   * 输入：selectedReadyDocument 和 query 和当前 React 状态
   * 输出：Promise<void>，最终结果通过 chatView 展示
   * 失败：HTTP 错误，流中断，字段非法或终态不匹配时显示安全错误
   */
  async function submitQuestion(): Promise<void> {
    const trimmedQuery = query.trim()
    if (selectedReadyDocument === null || trimmedQuery.length === 0) {
      return
    }

    setChatView({ ...INITIAL_CHAT_VIEW, status: 'streaming' })

    let streamedAnswer: string | null = null
    const streamedCitations: CitationView[] = []
    let refusalReason: string | null = null
    let safeErrorMessage: string | null = null
    let doneOutcome: 'success' | 'refusal' | 'error' | null = null

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          document_id: selectedReadyDocument.document_id,
          query: trimmedQuery,
        })
      })
      if (!response.ok) {
        throw new Error('无法开始聊天请求')
      }
      if (response.body === null) {
        throw new Error('聊天响应缺少可读流')
      }

      await consumeSSEStream(response.body, (event) => {
        const data = requireDataObject(event.data)

        switch (event.event) {
          case 'status':
            // 读取 refused 的 reason
            if (data.phase === 'refused') {
              if (typeof data.reason !== 'string') {
                throw new Error('refused 状态缺少 reason')
              }
              refusalReason = data.reason
            }
            break

          case 'final_answer':
            // 验证并保存 content
            if (typeof data.content !== 'string') {
              throw new Error('final_answer 缺少 content')
            }
            streamedAnswer = data.content
            break

          case 'citation':
            // 验证并追加四个引用字段
            if (
              typeof data.number !== 'number' ||
              typeof data.source_file !== 'string' ||
              typeof data.page !== 'number' ||
              typeof data.chunk_id !== 'string'
            ) {
              throw new Error('citation 字段非法')
            }
            streamedCitations.push({
              number: data.number,
              source_file: data.source_file,
              page: data.page,
              chunk_id: data.chunk_id,
            })
            break

          case 'usage':
            // 当前没有真实 usage 展示需求
            break

          case 'error':
            // 验证并保存安全 message 不存在 raw_error 字段
            if (typeof data.code !== 'string' || typeof data.message !== 'string') {
              throw new Error('error 事件字段非法')
            }
            safeErrorMessage = data.message
            break

          case 'done':
            //验证并保存 success/refusal/error outcome
            if (data.outcome !== 'success' && data.outcome !== 'refusal' && data.outcome !== 'error') {
              throw new Error('done outcome 非法')
            }
            doneOutcome = data.outcome
            break
        }
      })
      if (doneOutcome === 'success') {
        if (streamedAnswer === null) {
          throw new Error('成功终态缺少 final_answer')
        }

        setChatView({
          status: 'success',
          answer: streamedAnswer,
          citations: streamedCitations,
          refusalReason: null,
          errorMessage: null,
        })
        return
      }
      if (doneOutcome === 'refusal') {
        if (refusalReason === null) {
          throw new Error('拒答终态缺少 reason')
        }

        setChatView({
          status: 'refusal',
          answer: null,
          citations: [],
          refusalReason: refusalReason,
          errorMessage: null,
        })
        return
      }
      if (doneOutcome === 'error' && safeErrorMessage !== null) {

        setChatView({
          status: 'error',
          answer: null,
          citations: [],
          refusalReason: null,
          errorMessage: safeErrorMessage,
        })
        return
      }
      throw new Error('SSE 终态与事件内容不匹配')
    } catch {
      setChatView({
        status: 'error',
        answer: null,
        citations: [],
        refusalReason: null,
        errorMessage: '问答失败或响应流未完整结束',
      })
    }
  }

  return (
    <main>
      <h1>FinDoc 可信问答</h1>

      <section>
        <h2>上传 PDF</h2>

        <label htmlFor="pdf-file">选择文本型 PDF</label>
        <input
          id="pdf-file"
          type="file"
          accept="application/pdf"
          onChange={handleFileChange}
        />

        {selectedFile !== null && (
          <p>已选择：{selectedFile.name}</p>
        )}

        <button
          type="button"
          disabled={selectedFile === null || isUploading}
          onClick={() => void uploadSelectedDocument()}
        >
          {isUploading ? '正在上传……' : '上传 PDF'}
        </button>
        {uploadError !== null && (
          <p role="alert">{uploadError}</p>
        )}
        {uploadMessage !== null && (
          <p role="status">{uploadMessage}</p>
        )}
      </section>

      <p>当前共有 {documents.length} 篇文档</p>
      {/* 请求尚未结束时，只显示加载提示 */}
      {isLoadingDocuments && (<p>正在加载文档……</p>)}

      {/* 请求结束并且存在错误时，显示安全错误消息和重试按钮 */}
      {!isLoadingDocuments && documentError !== null && (
        <section>
          <p role="alert">{documentError}</p>
          <button type="button"
            onClick={handleReloadDocuments}
          >
            重新加载
          </button>
        </section>
      )}
      {/* 请求成功但没有文档时，显示空状态 */}
      {!isLoadingDocuments && documentError === null && documents.length === 0 && (<p>还没有上传文档</p>)}

      {/* 请求成功且存在文档时，把每条记录转换为一个列表项 */}
      {!isLoadingDocuments && documentError === null && documents.length > 0 && (
        <ul>
          {documents.map((document) => (
            <li key={document.document_id}>
              <label>
                <input
                  type="radio"
                  name="selected-document"
                  value={document.document_id}
                  checked={selectedDocumentId === document.document_id}
                  disabled={document.status !== 'ready'}
                  onChange={() => setSelectedDocumentId(document.document_id)}
                />
                <span>{document.source_file}</span>
                <span>状态：{document.status}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
      {selectedDocumentId !== null && (
        <p>已选择文档：{selectedDocumentId}</p>
      )}
      <section>
        <h2>向文档提问</h2>

        {selectedReadyDocument === null && (
          <p>请先选择一篇 ready 文档</p>
        )}

        <label htmlFor="chat-query">问题</label>
        <textarea
          id="chat-query"
          value={query}
          onChange={handleQueryChange}
          disabled={selectedReadyDocument === null}
          rows={4}
        />
        <button
          type="button"
          disabled={
            selectedReadyDocument === null || query.trim().length === 0 || chatView.status === 'streaming'
          }
          onClick={() => void submitQuestion()}
        >
          发送问题
        </button>

        {chatView.status === 'streaming' && (
          <p>正在查询并验证答案……</p>
        )}

        {chatView.status === 'success' && chatView.answer !== null && (
          <section>
            <h3>答案</h3>
            <p>{chatView.answer}</p>

            <h3>引用</h3>
            {chatView.citations.length === 0 ? (
              <p>没有引用</p>
            ) : (
              <ol>
                {chatView.citations.map((citation) => (
                  <li key={citation.number}>
                    {citation.source_file}，第 {citation.page} 页，chunk：{citation.chunk_id}
                  </li>
                ))}
              </ol>
            )}
          </section>
        )}

        {chatView.status === 'refusal' && (
          <p>无法基于当前文档回答：{chatView.refusalReason}</p>
        )}

        {chatView.status === 'error' && (
          <p role="alert">{chatView.errorMessage}</p>
        )}
      </section>
    </main>
  )
}

export default App

import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent, MutableRefObject } from 'react'

import { api, getStoredToken } from '../api/client'
import type { ChatServerEvent } from '../stores/chatStore'
import { useChatStore } from '../stores/chatStore'

type SpeechRecognitionInstance = {
  lang: string
  interimResults: boolean
  start: () => void
  onresult: ((event: { results: { 0: { transcript: string } }[] }) => void) | null
}

type AttachmentKind = 'image' | 'spreadsheet'

interface PendingAttachment {
  id: string
  file: File
  kind: AttachmentKind
}

function wsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/chat`
}

function sendJson(socketRef: MutableRefObject<WebSocket | null>, payload: unknown) {
  if (socketRef.current?.readyState === WebSocket.OPEN) {
    socketRef.current.send(JSON.stringify(payload))
    return true
  }

  return false
}

function buildAttachmentPrompt(fileId: string, kind: AttachmentKind) {
  return kind === 'image'
    ? `我上传了课表图片 file_id=${fileId}，请解析并展示确认卡片。`
    : `我上传了课表文件 file_id=${fileId}，请解析并展示确认卡片。`
}

function buildAttachmentConfirmation(kind: AttachmentKind, count: number) {
  return kind === 'image' ? `已发送 ${count} 张课表图片` : '已发送 1 个课表文件'
}

function detectAttachmentKind(file: File): AttachmentKind | null {
  const name = file.name.toLowerCase()
  if (
    file.type === 'image/png' ||
    file.type === 'image/jpeg' ||
    file.type === 'image/jpg' ||
    file.type === 'image/webp' ||
    /\.(png|jpe?g|webp)$/i.test(name)
  ) {
    return 'image'
  }
  if (
    file.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
    file.type === 'application/vnd.ms-excel' ||
    /\.(xls|xlsx)$/i.test(name)
  ) {
    return 'spreadsheet'
  }
  return null
}

export function ChatPage() {
  const socketRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef(0)
  const reconnectTimerRef = useRef<number | null>(null)
  const { answerAsk, appendUserMessage, applyServerEvent, error, isSending, messages, pendingAsk, progress } =
    useChatStore()
  const [draft, setDraft] = useState('')
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([])
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const hasSpeech = typeof window !== 'undefined' && 'webkitSpeechRecognition' in window

  useEffect(() => {
    let closed = false

    function connect() {
      const token = getStoredToken()
      if (!token || closed) {
        return
      }
      const socket = new WebSocket(wsUrl())
      socketRef.current = socket
      socket.onopen = () => {
        reconnectRef.current = 0
        socket.send(JSON.stringify({ token }))
      }
      socket.onmessage = (event) => {
        applyServerEvent(JSON.parse(event.data) as ChatServerEvent)
      }
      socket.onclose = () => {
        if (closed) {
          return
        }
        const delay = Math.min(30000, 1000 * 2 ** reconnectRef.current)
        reconnectRef.current += 1
        reconnectTimerRef.current = window.setTimeout(connect, delay)
      }
    }

    connect()
    return () => {
      closed = true
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current)
      }
      socketRef.current?.close()
    }
  }, [applyServerEvent])

  async function submit(event: FormEvent) {
    event.preventDefault()
    const message = draft.trim()
    const attachments = pendingAttachments

    if (attachments.length > 0 && message) {
      setAttachmentError('文字草稿和附件不能一起发送，请分开发送。')
      return
    }

    if (attachments.length > 0) {
      try {
        const uploadResponse = await api.uploadSchedule(attachments.map((item) => item.file))
        const sent = sendJson(socketRef, { message: buildAttachmentPrompt(uploadResponse.file_id, uploadResponse.kind) })
        if (!sent) {
          setAttachmentError('聊天连接不可用，请稍后重试')
          return
        }
        appendUserMessage(buildAttachmentConfirmation(uploadResponse.kind, uploadResponse.source_file_count))
        setPendingAttachments([])
        setAttachmentError(null)
      } catch (error) {
        setAttachmentError(error instanceof Error ? error.message : '课表上传失败')
      }
      return
    }

    if (!message) {
      return
    }

    appendUserMessage(message)
    sendJson(socketRef, { message })
    setDraft('')
  }

  function submitAnswer(answer: string) {
    answerAsk(answer)
    sendJson(socketRef, { answer })
  }

  function addPendingAttachments(files: File[]) {
    if (files.length === 0) {
      return
    }

    const kinds = files.map(detectAttachmentKind)
    if (kinds.some((kind) => kind === null)) {
      setAttachmentError('暂不支持该附件类型，仅支持 png、jpg、jpeg、webp、xls、xlsx')
      return
    }

    const nextKind = kinds[0]
    if (kinds.some((kind) => kind !== nextKind)) {
      setAttachmentError('不能同时添加图片和表格')
      return
    }

    const existingKind = pendingAttachments[0]?.kind ?? null
    if (existingKind && existingKind !== nextKind) {
      setAttachmentError('不能同时添加图片和表格')
      return
    }

    if (nextKind === 'image' && pendingAttachments.filter((attachment) => attachment.kind === 'image').length + files.length > 3) {
      setAttachmentError('最多只能添加 3 张图片')
      return
    }

    if (
      nextKind === 'spreadsheet' &&
      pendingAttachments.filter((attachment) => attachment.kind === 'spreadsheet').length + files.length > 1
    ) {
      setAttachmentError('最多只能添加 1 个表格')
      return
    }

    setPendingAttachments((current) => [
      ...current,
      ...files.map((file) => ({
        id: crypto.randomUUID(),
        file,
        kind: nextKind,
      })),
    ])
    setAttachmentError(null)
  }

  function uploadSchedule(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files ?? [])
    addPendingAttachments(files)
    event.currentTarget.value = ''
  }

  function removeAttachment(id: string) {
    setPendingAttachments((current) => current.filter((attachment) => attachment.id !== id))
    setAttachmentError(null)
  }

  function startSpeech() {
    const SpeechRecognition = (window as unknown as { webkitSpeechRecognition: new () => SpeechRecognitionInstance })
      .webkitSpeechRecognition
    const recognition = new SpeechRecognition()
    recognition.lang = 'zh-CN'
    recognition.interimResults = false
    recognition.onresult = (event) => {
      setDraft(event.results[0][0].transcript)
    }
    recognition.start()
  }

  return (
    <main className="page chat-page">
      <div className="message-list">
        {messages.map((message) => (
          <div className={`message message--${message.role}`} key={message.id}>
            {message.content}
          </div>
        ))}
        {progress.length > 0 ? (
          <section className="progress-card" aria-label="处理进度">
            <strong>{isSending ? '正在处理...' : '处理完成'}</strong>
            {progress.map((item) => (
              <div key={item.name}>{item.status === 'done' ? '✓' : '…'} {item.label}</div>
            ))}
          </section>
        ) : null}
        {pendingAsk ? (
          <section className="ask-card" aria-label="需要确认">
            <p>{pendingAsk.question}</p>
            {pendingAsk.data ? <pre>{JSON.stringify(pendingAsk.data, null, 2)}</pre> : null}
            {pendingAsk.answered ? (
              <p>已选择：{pendingAsk.answered}</p>
            ) : (
              <div className="ask-card__actions">
                {(pendingAsk.options.length > 0 ? pendingAsk.options : ['确认', '取消']).map((option) => (
                  <button type="button" key={option} onClick={() => submitAnswer(option)}>
                    {option}
                  </button>
                ))}
              </div>
            )}
          </section>
        ) : null}
        {error ? <p role="alert">{error}</p> : null}
      </div>

      {pendingAttachments.length > 0 ? (
        <section className="attachment-tray" aria-label="待发送附件">
          <strong>待发送附件 {pendingAttachments.length}</strong>
          <div className="attachment-tray__items">
            {pendingAttachments.map((attachment) => (
              <div className="attachment-tray__item" key={attachment.id}>
                <span>{attachment.file.name}</span>
                <button type="button" onClick={() => removeAttachment(attachment.id)}>
                  移除 {attachment.file.name}
                </button>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {attachmentError ? <p role="alert">{attachmentError}</p> : null}

      <form className="chat-input" onSubmit={submit}>
        <label className="icon-button">
          附件
          <input
            aria-label="上传课表"
            type="file"
            accept="image/*,.xls,.xlsx"
            capture="environment"
            multiple
            onChange={uploadSchedule}
          />
        </label>
        <button type="button" className="icon-button" onClick={startSpeech} disabled={!hasSpeech}>
          语音
        </button>
        <input aria-label="输入消息" value={draft} onChange={(event) => setDraft(event.target.value)} />
        <button type="submit" className="primary-button">
          发送
        </button>
      </form>
    </main>
  )
}

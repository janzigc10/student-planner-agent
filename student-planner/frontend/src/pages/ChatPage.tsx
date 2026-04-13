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

function wsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/chat`
}

function sendJson(socketRef: MutableRefObject<WebSocket | null>, payload: unknown) {
  if (socketRef.current?.readyState === WebSocket.OPEN) {
    socketRef.current.send(JSON.stringify(payload))
  }
}

export function ChatPage() {
  const socketRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef(0)
  const reconnectTimerRef = useRef<number | null>(null)
  const { answerAsk, appendUserMessage, applyServerEvent, error, isSending, messages, pendingAsk, progress } =
    useChatStore()
  const [draft, setDraft] = useState('')
  const [uploading, setUploading] = useState(false)
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

  function submit(event: FormEvent) {
    event.preventDefault()
    const message = draft.trim()
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

  async function uploadSchedule(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    setUploading(true)
    try {
      const result = await api.uploadSchedule(file)
      const message = `我上传了课表文件，file_id=${result.file_id}，kind=${result.kind}，请解析并让我确认导入。`
      appendUserMessage(message)
      sendJson(socketRef, { message })
    } finally {
      setUploading(false)
      event.target.value = ''
    }
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
      <form className="chat-input" onSubmit={submit}>
        <label className="icon-button">
          附件
          <input
            aria-label="上传课表"
            type="file"
            accept="image/*,.xls,.xlsx"
            capture="environment"
            onChange={uploadSchedule}
            disabled={uploading}
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

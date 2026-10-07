import { useEffect, useRef, useState } from "react"
import { useLocation, useNavigate, useParams } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

export default function Chat() {
    const { jobId } = useParams()
    const location = useLocation()
    const navigate = useNavigate()
    const token = localStorage.getItem("token") || ""
    const me = JSON.parse(localStorage.getItem("user") || "null")
    const [job, setJob] = useState(location.state?.job || null)
    const [messages, setXabarlar] = useState([])
    const [text, setText] = useState("")
    const [receiverId, setReceiverId] = useState(
        String(location.state?.job?.worker_id || location.state?.job?.user_id || "")
    )
    const [notice, setNotice] = useState("")
    const [otherOnline, setOtherOnline] = useState(false)
    const [otherLastSeen, setOtherLastSeen] = useState("")
    const [otherTyping, setOtherTyping] = useState(false)
    const [otherName, setOtherName] = useState("Foydalanuvchi")
    const [otherUsername, setOtherUsername] = useState("")
    const [file, setFile] = useState(null)
    const fileInputRef = useRef(null)
    const bottomRef = useRef(null)
    const typingTimerRef = useRef(null)

    const formatLastSeen = (value) => {
        const lastSeen = new Date(value)
        if (Number.isNaN(lastSeen.getTime())) return ""

        const diffMs = Math.max(0, Date.now() - lastSeen.getTime())
        const diffMinutes = Math.floor(diffMs / 60000)

        if (diffMinutes < 60) return `${diffMinutes} daqiqa oldin`

        const diffHours = Math.floor(diffMinutes / 60)
        if (diffHours < 24) return `${diffHours} soat oldin`

        const diffDays = Math.floor(diffHours / 24)
        if (diffDays < 30) return `${diffDays} kun oldin`

        const diffMonths = Math.floor(diffDays / 30)
        if (diffMonths < 12) return `${diffMonths} oy oldin`

        const diffYears = Math.floor(diffDays / 365)
        return `${diffYears} yil oldin`
    }

    const loadXabarlar = async () => {
        if (document.hidden) return
        const result = await api(`/messages/${jobId}`, { token })
        if (Array.isArray(result)) setXabarlar(result)
    }

    const loadPresence = async () => {
        if (!receiverId) return
        const result = await api(`/presence/${receiverId}`, { token })
        if (result?.ok) {
            setOtherOnline(Boolean(result.online))
            setOtherLastSeen(result.last_seen_at || "")
        }
    }

    const loadTyping = async () => {
        const result = await api(`/typing/${jobId}`, { token })
        if (result?.ok) setOtherTyping(Boolean(result.typing))
    }

    const sendTypingState = async (active) => {
        await api(`/typing/${jobId}`, {
            method: "POST",
            body: { typing: active },
            token
        })
    }

    const loadJob = async () => {
        const jobData = await api(`/jobs/${jobId}`, { token })
        if (jobData?.id) {
            setJob(jobData)
            const targetId = String(jobData.user_id === me?.id ? jobData.worker_id : jobData.user_id)
            const targetName = jobData.user_id === me?.id
                ? ([jobData.worker_first, jobData.worker_last].filter(Boolean).join(" ") || jobData.worker_username)
                : ([jobData.creator_first, jobData.creator_last].filter(Boolean).join(" ") || jobData.creator_username)
            const targetUsername = jobData.user_id === me?.id ? jobData.worker_username : jobData.creator_username
            if (targetName) setOtherName(targetName)
            if (targetUsername) setOtherUsername(targetUsername)
            if (targetId && targetId !== "null" && targetId !== "undefined") {
                setReceiverId(targetId)
            }
        }
    }

    useEffect(() => {
        loadXabarlar()
        if (!location.state?.job) {
            loadJob()
        }

        const interval = setInterval(loadXabarlar, 3000)
        const presenceInterval = setInterval(loadPresence, 5000)
        const typingInterval = setInterval(loadTyping, 1500)
        const heartbeat = setInterval(() => api("/presence", { method: "POST", token }), 30000)
        loadPresence()
        api("/presence", { method: "POST", token })
        const handleVisibilityChange = () => {
            if (!document.hidden) {
                loadXabarlar()
                loadPresence()
                loadTyping()
            }
        }
        document.addEventListener("visibilitychange", handleVisibilityChange)

        return () => {
            clearInterval(interval)
            clearInterval(presenceInterval)
            clearInterval(typingInterval)
            clearInterval(heartbeat)
            clearTimeout(typingTimerRef.current)
            sendTypingState(false)
            document.removeEventListener("visibilitychange", handleVisibilityChange)
        }
    }, [jobId, receiverId])

    useEffect(() => {
        if (location.state?.job) {
            const currentJob = location.state.job
            setJob(currentJob)
            const targetId = String(currentJob.user_id === me?.id ? currentJob.worker_id : currentJob.user_id)
            const targetName = currentJob.user_id === me?.id
                ? ([currentJob.worker_first, currentJob.worker_last].filter(Boolean).join(" ") || currentJob.worker_username)
                : ([currentJob.creator_first, currentJob.creator_last].filter(Boolean).join(" ") || currentJob.creator_username)
            const targetUsername = currentJob.user_id === me?.id ? currentJob.worker_username : currentJob.creator_username
            if (targetName) setOtherName(targetName)
            if (targetUsername) setOtherUsername(targetUsername)
            if (targetId && targetId !== "null" && targetId !== "undefined") {
                setReceiverId(targetId)
            }
        }
    }, [location.state])

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [messages])

    const send = async (e) => {
        e.preventDefault()
        if (!text.trim() && !file) return

        const body = new FormData()
        body.append("receiver_id", String(Number(receiverId) || ""))
        body.append("job_id", String(Number(jobId)))
        body.append("message", text)
        if (file) body.append("file", file)

        const result = await api("/message", {
            method: "POST",
            body,
            token
        })

        if (result?.msg === "ok" || result?.msg === "sent") {
            setText("")
            setFile(null)
            if (fileInputRef.current) fileInputRef.current.value = ""
            clearTimeout(typingTimerRef.current)
            await sendTypingState(false)
            const res = await api(`/messages/${jobId}`, { token })
            if (Array.isArray(res)) setXabarlar(res)
        } else {
            setNotice(result?.msg || "Xabar yuborilmadi")
        }
    }

    return (
        <AppLayout
            title="Suhbat"
            subtitle={`Ish #${jobId} bo‘yicha suhbat`}
        >
            {notice && <div className="notice warn" style={{ marginBottom: 16 }}>{notice}</div>}

            <div style={{ width: "100%" }}>
                <section className="card chat-wrap" style={{ width: "100%", maxWidth: "100%" }}>
                    <div className="section-toolbar" style={{ marginBottom: 0 }}>
                        <div className="page-head">
                            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                <span className="profile-online-dot" style={{ opacity: otherOnline || otherTyping ? 1 : 0.35 }} />
                                <div>
                                    <button
                                        type="button"
                                        onClick={() => otherUsername && navigate(`/profile/${otherUsername}`)}
                                        disabled={!otherUsername}
                                        style={{
                                            margin: 0,
                                            padding: 0,
                                            border: 0,
                                            background: "transparent",
                                            font: "inherit",
                                            fontWeight: 700,
                                            color: "inherit",
                                            cursor: otherUsername ? "pointer" : "default",
                                            textAlign: "left"
                                        }}
                                    >
                                        {otherName}
                                    </button>
                                    <p className="muted" style={{ margin: 0 }}>
                                        {otherTyping ? "Yozmoqda..." : otherOnline ? "Online" : otherLastSeen ? `Offline · Oxirgi faollik: ${formatLastSeen(otherLastSeen)}` : "Offline"}
                                    </p>
                                </div>
                            </div>
                            <p className="muted" style={{ margin: "4px 0 0 30px" }}>
                                {job?.title || `Ish #${jobId}`}
                            </p>
                        </div>
                        <div className="actions">
                            <button className="btn btn-secondary" onClick={() => navigate(-1)}>Orqaga</button>
                        </div>
                    </div>

                    <div className="message-list" style={{ minHeight: "400px" }}>
                        {messages.map((message, index) => {
                            const myName = `${me?.first_name || ""} ${me?.last_name || ""}`.trim() || me?.username
                            const mine = message.sender_name === myName || String(message.sender_id) === String(me?.id)

                            return (
                                <div key={index} className={`message ${mine ? "me" : "them"}`}>
                                    <div className="message-meta">
                                        {mine ? "Siz" : (message.sender_name || "Foydalanuvchi")} • {message.sent_at}
                                    </div>
                                    {message.message && <div>{message.message}</div>}
                                    {message.attachment_url && (
                                        <div style={{ marginTop: message.message ? 8 : 0 }}>
                                            {message.attachment_type === "image" ? (
                                                <a href={message.attachment_url} target="_blank" rel="noreferrer">
                                                    <img src={message.attachment_url} alt={message.attachment_name || "Fayl"} style={{ maxWidth: "260px", maxHeight: "260px", borderRadius: 10, display: "block" }} />
                                                </a>
                                            ) : (
                                                <a href={message.attachment_url} target="_blank" rel="noreferrer" className="btn btn-secondary">
                                                    📎 {message.attachment_name || "Faylni ochish"}
                                                </a>
                                            )}
                                        </div>
                                    )}
                                    {mine && <small className="muted" style={{ display: "block", marginTop: 4 }}>{message.read_at ? "✓✓ Ko‘rildi" : "✓ Yuborildi"}</small>}
                                </div>
                            )
                        })}
                        <div ref={bottomRef} />
                        {!messages.length && <div className="empty-state">Hozircha xabar yo‘q.</div>}
                    </div>

                    {file && <div className="notice" style={{ marginTop: 14 }}>Tanlangan fayl: {file.name}</div>}
                    <form onSubmit={send} className="actions" style={{ marginTop: 14 }}>
                        <input
                            ref={fileInputRef}
                            type="file"
                            style={{ display: "none" }}
                            accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.zip"
                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                        />
                        <button type="button" className="btn btn-secondary" onClick={() => fileInputRef.current?.click()}>
                            Fayl
                        </button>
                        <input
                            className="input"
                            style={{ flex: 1 }}
                            placeholder="Xabar yozing..."
                            value={text}
                            onChange={(e) => {
                                const value = e.target.value
                                setText(value)
                                clearTimeout(typingTimerRef.current)
                                sendTypingState(Boolean(value.trim()))
                                if (value.trim()) {
                                    typingTimerRef.current = setTimeout(() => sendTypingState(false), 1200)
                                }
                            }}
                        />
                        <button className="btn btn-primary">Yuborish</button>
                    </form>
                </section>
            </div>
        </AppLayout>
    )
}

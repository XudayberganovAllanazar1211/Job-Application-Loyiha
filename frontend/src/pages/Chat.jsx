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
    const [otherAvatarUrl, setOtherAvatarUrl] = useState("")
    const meAvatarUrl = me?.avatar_url || ""
    const [file, setFile] = useState(null)
    const [reportingMessageId, setReportingMessageId] = useState(null)
    const fileInputRef = useRef(null)
    const bottomRef = useRef(null)
    const typingTimerRef = useRef(null)
    const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:5000").replace(/\/$/, "")

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
        if (result?.ok === false && Number(result.status) === 403) {
            navigate("/conversations", {
                replace: true,
                state: { notice: "Bu suhbat mavjud emas yoki siz uning ishtirokchisi emassiz." }
            })
            return
        }
        if (Array.isArray(result)) {
            setXabarlar(result)
            const otherMessage = result.find((message) => String(message.sender_id) !== String(me?.id))
            if (otherMessage?.sender_avatar_url !== undefined) {
                setOtherAvatarUrl(otherMessage.sender_avatar_url || "")
            }
        }
    }

    const loadOtherProfile = async (username) => {
        if (!username) return
        const profile = await api(`/profiles/${encodeURIComponent(username)}`, { token })
        if (profile?.id && profile.username === username) {
            setOtherAvatarUrl(profile.avatar_url || "")
        }
    }

    const loadPresence = async () => {
        if (!receiverId) return
        const result = await api(`/presence/${receiverId}?job_id=${encodeURIComponent(jobId)}`, { token })
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
        if (jobData?.ok === false && Number(jobData.status) === 404) {
            navigate("/conversations", {
                replace: true,
                state: { notice: "Bu ish yoki suhbat topilmadi." }
            })
            return
        }
        if (jobData?.id) {
            setJob(jobData)
            const targetId = String(jobData.user_id === me?.id ? jobData.worker_id : jobData.user_id)
            const targetName = jobData.user_id === me?.id
                ? ([jobData.worker_first, jobData.worker_last].filter(Boolean).join(" ") || jobData.worker_username)
                : ([jobData.creator_first, jobData.creator_last].filter(Boolean).join(" ") || jobData.creator_username)
            const targetUsername = jobData.user_id === me?.id ? jobData.worker_username : jobData.creator_username
            if (targetName) setOtherName(targetName)
            if (targetUsername) {
                setOtherUsername(targetUsername)
                await loadOtherProfile(targetUsername)
            }
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
            if (targetUsername) {
                setOtherUsername(targetUsername)
                loadOtherProfile(targetUsername)
            }
            if (targetId && targetId !== "null" && targetId !== "undefined") {
                setReceiverId(targetId)
            }
        }
    }, [location.state])

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [messages])

    const openAttachment = async (url) => {
        try {
            const response = await fetch(API_BASE + url, { headers: { Authorization: `Bearer ${token}` } })
            if (!response.ok) throw new Error("Faylni ochib bo‘lmadi")
            const blob = await response.blob()
            const objectUrl = URL.createObjectURL(blob)
            window.open(objectUrl, "_blank", "noopener,noreferrer")
            setTimeout(() => URL.revokeObjectURL(objectUrl), 60000)
        } catch (error) {
            setNotice(error.message || "Faylni ochib bo‘lmadi")
        }
    }

    const reportMessage = async (message) => {
        if (!message?.id || !message.sender_id || String(message.sender_id) === String(me?.id)) return

        const reasons = [
            "Spam",
            "Haqorat / tahqirlash",
            "Firibgarlik",
            "Nomaqbul kontent",
            "Tahdid",
            "Reklama",
            "Shaxsiy ma’lumot tarqatish",
            "Boshqa sabab"
        ]
        const choice = window.prompt(
            "Xabarni report qilish sababini tanlang:\n\n" +
            reasons.map((item, index) => `${index + 1}. ${item}`).join("\n") +
            "\n\nRaqamini kiriting:"
        )
        if (choice === null) return

        const index = Number(choice) - 1
        if (!Number.isInteger(index) || index < 0 || index >= reasons.length) {
            setNotice("Noto‘g‘ri report turi tanlandi.")
            return
        }

        let reason = reasons[index]
        let details = ""

        if (reason === "Boshqa sabab") {
            reason = window.prompt("Boshqa sababni yozing:") || ""
            if (!reason.trim()) return
            reason = reason.trim()
        }

        setReportingMessageId(message.id)

        const result = await api("/report", {
            method: "POST",
            body: {
                job_id: Number(jobId),
                message_id: Number(message.id),
                reported_user_id: Number(message.sender_id),
                reason,
                details
            },
            token
        })

        setReportingMessageId(null)
        setNotice(result?.msg || "Shikoyat yuborildi.")
    }
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
                                {otherAvatarUrl ? (
                                    <img
                                        className="chat-header-avatar"
                                        src={getAvatarSrc(otherAvatarUrl, API_BASE)}
                                        alt={otherName}
                                    />
                                ) : (
                                    <div className="chat-header-avatar chat-header-avatar-fallback">
                                        {getInitials(otherName)}
                                    </div>
                                )}
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
                            const messageDate = getMessageDateKey(message.sent_at)
                            const previousDate = index > 0 ? getMessageDateKey(messages[index - 1].sent_at) : null
                            const showDate = messageDate !== previousDate
                            const senderAvatar = mine ? meAvatarUrl : (message.sender_avatar_url || otherAvatarUrl)

                            return (
                                <div key={message.id || index}>
                                    {showDate && (
                                        <div className="chat-date-divider">
                                            <span>{formatMessageDate(message.sent_at)}</span>
                                        </div>
                                    )}
                                    <div className={`chat-message-row ${mine ? "mine" : "theirs"}`}>
                                        {!mine && (
                                            senderAvatar ? (
                                                <img className="chat-avatar" src={getAvatarSrc(senderAvatar, API_BASE)} alt="" />
                                            ) : (
                                                <div className="chat-avatar chat-avatar-fallback">{getInitials(message.sender_name || otherName)}</div>
                                            )
                                        )}
                                        <div className={`message ${mine ? "me" : "them"}`}>
                                            <div className="message-meta">
                                                {mine ? "Siz" : (message.sender_name || "Foydalanuvchi")} • {formatMessageTime(message.sent_at)}
                                            </div>
                                            {message.message && <div>{message.message}</div>}
                                            {message.attachment_url && (
                                                <div style={{ marginTop: message.message ? 8 : 0 }}>
                                                    {message.attachment_type === "image" ? (
                                                        <ChatImage
                                                            url={message.attachment_url}
                                                            name={message.attachment_name || "Rasm"}
                                                            apiBase={API_BASE}
                                                            token={token}
                                                            onOpen={openAttachment}
                                                        />
                                                    ) : (
                                                        <button
                                                            type="button"
                                                            className="btn btn-secondary"
                                                            onClick={() => openAttachment(message.attachment_url)}
                                                        >
                                                            Fayl: {message.attachment_name || "Faylni ochish"}
                                                        </button>
                                                    )}
                                                </div>
                                            )}
                                            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                                                {mine && <small className="muted">{message.read_at ? "✓✓ Ko‘rildi" : "✓ Yuborildi"}</small>}
                                                {!mine && (
                                                    <button
                                                        type="button"
                                                        className="btn btn-secondary"
                                                        style={{ padding: "3px 8px", fontSize: 12 }}
                                                        disabled={reportingMessageId === message.id}
                                                        onClick={() => reportMessage(message)}
                                                    >
                                                        {reportingMessageId === message.id ? "Yuborilmoqda..." : "Report"}
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                        {mine && (
                                            senderAvatar ? (
                                                <img className="chat-avatar" src={getAvatarSrc(senderAvatar, API_BASE)} alt="" />
                                            ) : (
                                                <div className="chat-avatar chat-avatar-fallback">{getInitials(myName || "Siz")}</div>
                                            )
                                        )}
                                    </div>
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

function getMessageDateKey(value) {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ""
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, "0")
    const day = String(date.getDate()).padStart(2, "0")
    return `${year}-${month}-${day}`
}

function formatMessageTime(value) {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return "--:--"
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })
}

function formatMessageDate(value) {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return "Sana noma'lum"
    const today = new Date()
    const yesterday = new Date()
    yesterday.setDate(today.getDate() - 1)

    if (getMessageDateKey(date) === getMessageDateKey(today)) return "Bugun"
    if (getMessageDateKey(date) === getMessageDateKey(yesterday)) return "Kecha"
    return date.toLocaleDateString("uz-UZ", { day: "2-digit", month: "long", year: "numeric" })
}

function getAvatarSrc(url, apiBase) {
    if (!url) return ""
    return url.startsWith("http://") || url.startsWith("https://") ? url : apiBase + url
}

function getInitials(name) {
    const parts = String(name || "").trim().split(/\\s+/).filter(Boolean)
    return parts.slice(0, 2).map((part) => part[0].toUpperCase()).join("") || "?"
}

function ChatImage({ url, name, apiBase, token, onOpen }) {
    const [src, setSrc] = useState("")
    const [error, setError] = useState(false)

    useEffect(() => {
        let objectUrl = ""

        const load = async () => {
            try {
                const response = await fetch(apiBase + url, {
                    headers: { Authorization: `Bearer ${token}` }
                })
                if (!response.ok) throw new Error("Rasmni yuklab bo‘lmadi")
                const blob = await response.blob()
                objectUrl = URL.createObjectURL(blob)
                setSrc(objectUrl)
            } catch {
                setError(true)
            }
        }

        load()

        return () => {
            if (objectUrl) URL.revokeObjectURL(objectUrl)
        }
    }, [apiBase, token, url])

    if (error) {
        return (
            <button type="button" className="btn btn-secondary" onClick={() => onOpen(url)}>
                Rasmni ochish: {name}
            </button>
        )
    }

    if (!src) {
        return <div className="notice" style={{ display: "inline-block" }}>Rasm yuklanmoqda...</div>
    }

    return (
        <button
            type="button"
            onClick={() => onOpen(url)}
            style={{
                display: "block",
                padding: 0,
                border: 0,
                background: "transparent",
                cursor: "pointer",
                maxWidth: "min(420px, 100%)",
                borderRadius: 12,
                overflow: "hidden"
            }}
            aria-label={`Rasmni kattalashtirish: ${name}`}
        >
            <img
                src={src}
                alt={name}
                style={{
                    display: "block",
                    width: "100%",
                    maxWidth: 420,
                    maxHeight: 420,
                    objectFit: "contain",
                    borderRadius: 12
                }}
            />
        </button>
    )
}

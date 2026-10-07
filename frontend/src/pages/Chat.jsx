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
    const bottomRef = useRef(null)
    const typingTimerRef = useRef(null)

    const loadXabarlar = async () => {
        // Skip polling if the browser tab is hidden to save bandwidth and battery
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
                ? (jobData.worker_name || jobData.worker_username)
                : (jobData.user_name || jobData.user_username)
            if (targetName) setOtherName(targetName)
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

        // Smart polling: poll every 3 seconds, and immediately refresh when user returns to tab
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
                ? (currentJob.worker_name || currentJob.worker_username)
                : (currentJob.user_name || currentJob.user_username)
            if (targetName) setOtherName(targetName)
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
        if (!text.trim()) return

        const result = await api("/message", {
            method: "POST",
            body: {
                receiver_id: Number(receiverId) || undefined,
                job_id: Number(jobId),
                message: text
            },
            token
        })

        if (result?.msg === "ok" || result?.msg === "sent") {
            setText("")
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
                                    <h2 style={{ margin: 0 }}>{otherName}</h2>
                                    <p className="muted" style={{ margin: 0 }}>
                                        {otherTyping ? "Yozmoqda..." : otherOnline ? "Online" : otherLastSeen ? `Offline · Oxirgi faollik: ${new Date(otherLastSeen).toLocaleString("uz-UZ", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}` : "Offline"}
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
                                    <div>{message.message}</div>
                                    {mine && <small className="muted" style={{ display: "block", marginTop: 4 }}>{message.read_at ? "✓✓ Ko‘rildi" : "✓ Yuborildi"}</small>}
                                </div>
                            )
                        })}
                        <div ref={bottomRef} />
                        {!messages.length && <div className="empty-state">Hozircha xabar yo‘q.</div>}
                    </div>

                    <form onSubmit={send} className="actions" style={{ marginTop: 14 }}>
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

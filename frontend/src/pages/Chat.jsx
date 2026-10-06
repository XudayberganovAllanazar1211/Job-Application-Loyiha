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
    const bottomRef = useRef(null)

    const loadXabarlar = async () => {
        // Skip polling if the browser tab is hidden to save bandwidth and battery
        if (document.hidden) return
        const result = await api(`/messages/${jobId}`, { token })
        if (Array.isArray(result)) setXabarlar(result)
    }

    const loadJob = async () => {
        const jobData = await api(`/jobs/${jobId}`, { token })
        if (jobData?.id) {
            setJob(jobData)
            const targetId = String(jobData.user_id === me?.id ? jobData.worker_id : jobData.user_id)
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
        const handleVisibilityChange = () => {
            if (!document.hidden) {
                loadXabarlar()
            }
        }
        document.addEventListener("visibilitychange", handleVisibilityChange)

        return () => {
            clearInterval(interval)
            document.removeEventListener("visibilitychange", handleVisibilityChange)
        }
    }, [jobId])

    useEffect(() => {
        if (location.state?.job) {
            const currentJob = location.state.job
            setJob(currentJob)
            const targetId = String(currentJob.user_id === me?.id ? currentJob.worker_id : currentJob.user_id)
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
                    <div className="topbar" style={{ marginBottom: 0 }}>
                        <div className="page-head">
                            <h2 style={{ margin: 0 }}>Xabarlar</h2>
                            <p className="muted" style={{ margin: 0 }}>
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
                            onChange={(e) => setText(e.target.value)}
                        />
                        <button className="btn btn-primary">Yuborish</button>
                    </form>
                </section>
            </div>
        </AppLayout>
    )
}

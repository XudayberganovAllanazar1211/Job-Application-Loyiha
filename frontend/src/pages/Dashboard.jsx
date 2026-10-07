import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

function formatTimeAgo(dateString) {
    if (!dateString) return "Vaqt noma'lum"

    const created = new Date(String(dateString).replace(" ", "T"))
    if (Number.isNaN(created.getTime())) return "Vaqt noma'lum"

    const seconds = Math.max(0, Math.floor((Date.now() - created.getTime()) / 1000))
    if (seconds < 60) return "Hozirgina"

    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes} daqiqa oldin`

    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours} soat oldin`

    const days = Math.floor(hours / 24)
    if (days < 7) return `${days} kun oldin`

    const weeks = Math.floor(days / 7)
    if (days < 30) return `${weeks} hafta oldin`

    const months = Math.floor(days / 30)
    if (days < 365) return `${months} oy oldin`

    const years = Math.floor(days / 365)
    return `${years} yil oldin`
}

export default function Dashboard() {
    const [jobs, setJobs] = useState([])
    const [services, setServices] = useState([])
    const [messages, setMessages] = useState([])
    const [selectedJob, setSelectedJob] = useState(null)
    const [search, setSearch] = useState("")
    const [notice, setNotice] = useState("")
    const [noticeType, setNoticeType] = useState("ok")
    const token = localStorage.getItem("token") || ""
    const user = JSON.parse(localStorage.getItem("user") || localStorage.getItem("foydalanuvchi") || "null")
    const navigate = useNavigate()


    const serviceMap = useMemo(
        () => Object.fromEntries(services.map((service) => [String(service.id), service.name])),
        [services]
    )

    const load = async () => {
        const [jobResult, serviceResult, profileResult] = await Promise.all([
            api("/jobs", { token }),
            api("/services", { token }),
            api("/profile", { token })
        ])

        if (Array.isArray(jobResult)) {
            setJobs(jobResult)
            if (!selectedJob && jobResult[0]) {
                const firstJob = jobResult[0]
                setSelectedJob(firstJob)
                const participant =
                    String(firstJob.user_id) === String(user?.id) ||
                    String(firstJob.worker_id) === String(user?.id)
                if (participant) {
                    loadMessages(firstJob)
                }
            }
        }

        if (Array.isArray(serviceResult)) setServices(serviceResult)

        if (profileResult?.id) {
            localStorage.setItem("foydalanuvchi", JSON.stringify(profileResult))
        }
    }

    const loadMessages = async (job) => {
        if (!job) return

        const participant =
            String(job.user_id) === String(user?.id) ||
            String(job.worker_id) === String(user?.id)

        if (!participant) {
            setMessages([])
            return
        }

        const result = await api(`/messages/${job.id}`, { token })
        setMessages(Array.isArray(result) ? result : [])
    }

    useEffect(() => {
        load()
    }, [])

    const selectJob = async (job) => {
        setSelectedJob(job)
        await loadMessages(job)
    }

    const acceptJob = async (job) => {
        const result = await api("/accept_job", {
            method: "POST",
            body: { job_id: job.id },
            token
        })
        const accepted = result?.msg === "ok"
        setNoticeType(accepted ? "ok" : "warn")
        setNotice(accepted ? "Ish qabul qilindi" : (result?.msg || "Xato"))
        load()
    }

    // Ish beruvchi uchun finish funksiyasi
    const finishJobSeeker = async (job) => {
        const result = await api("/finish_job", {
            method: "POST",
            body: { job_id: job.id },
            token
        })
        const waiting = result?.msg === "waiting"
        const completed = result?.msg === "ok"
        setNoticeType((waiting || completed) ? "ok" : "warn")
        setNotice(
            completed
                ? "Ish yakunlandi. To‘lov bajaruvchiga o‘tkazildi."
                : waiting
                    ? "Siz ishni yakunladingiz. Ikkinchi tomonning ham «Yakunlash» tugmasini bosishini kuting."
                    : (result?.msg || "Xato")
        )
        load()
    }

    const cancelWorker = async (job) => {
        const workerName = ((job.worker_first || "") + " " + (job.worker_last || "")).trim() || job.worker_username || "bajaruvchi"
        const confirmed = window.confirm(
            '"' + job.title + '" ishidan "' + workerName + '"ni olib tashlamoqchimisiz? Ish yana barcha foydalanuvchilar uchun ochiladi.'
        )
        if (!confirmed) return

        const result = await api("/cancel_worker", {
            method: "POST",
            body: { job_id: job.id },
            token
        })
        const cancelled = result?.msg === "ok"
        setNoticeType(cancelled ? "ok" : "warn")
        setNotice(
            cancelled
                ? "Bajaruvchi bekor qilindi. Ish yana barcha uchun ochiq."
                : (result?.msg || "Xatolik yuz berdi")
        )
        load()
    }

    const filtered = useMemo(() => {
        return jobs.filter((job) => {
            const text = `${job.title || ""} ${job.description || ""} ${job.location || ""}`.toLowerCase()
            return text.includes(search.toLowerCase())
        })
    }, [jobs, search])

    return (
        <AppLayout
            title="Boshqaruv paneli"
            subtitle={`Xush kelibsiz, ${user?.first_name || user?.username || "foydalanuvchi"}!`}
        >
            {notice && <div className={`notice ${noticeType === "ok" ? "ok" : "warn"}`} style={{ marginBottom: 16 }}>{notice}</div>}

            <div className="stat-grid" style={{ marginBottom: 18 }}>
                <div className="stat-card">
                    <div className="stat-card-icon">01</div>
                    <div className="stat-card-kicker">Ish maydoni</div>
                    <div className="stat-label">Faol ishlar</div>
                    <div className="stat-value">{jobs.filter((job) => String(job.status || "").trim().toLowerCase() === "active").length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-card-icon">02</div>
                    <div className="stat-card-kicker">Katalog</div>
                    <div className="stat-label">Xizmatlar</div>
                    <div className="stat-value">{services.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-card-icon">03</div>
                    <div className="stat-card-kicker">Platform</div>
                    <div className="stat-label">Tizim rejimi</div>
                    <div className="stat-value" style={{ fontSize: 22, color: "#10b981" }}>
                        Ko‘p yo‘nalishli bitta profil
                    </div>
                </div>
            </div>

            <div className="grid-2">
                <section className="card">
                    <div className="topbar" style={{ marginBottom: 16 }}>
                        <div className="page-head">
                            <h2 style={{ margin: 0 }}>Mening ish maydonim</h2>
                            <p className="muted" style={{ margin: 0 }}>
                                Faol e’lonlar hamda siz yaratgan yoki qabul qilgan ishlar shu yerda ko‘rinadi.
                            </p>
                        </div>
                        <div className="actions">
                            <input
                                className="input"
                                style={{ minWidth: 220 }}
                                placeholder="Qidirish..."
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                            />
                            <button className="btn btn-primary" onClick={() => navigate("/create")}>
                                Ish yaratish
                            </button>
                        </div>
                    </div>

                    <div className="job-grid">
                        {filtered.map((job) => {
                            const status = String(job.status || "").trim().toLowerCase()
                            const isMyJob = String(job.user_id) === String(user?.id)
                            const isIAccepted = String(job.worker_id) === String(user?.id)
                            const isParticipant = isMyJob || isIAccepted
                            const canAccept = status === "active" && !isMyJob && job.worker_id == null
                            const canFinish = status === "accepted" && ((isMyJob && !job.owner_finished) || (isIAccepted && !job.worker_finished))
                            const statusLabel = {
                                active: "Faol",
                                accepted: "Qabul qilingan",
                                pending_finish: "Tasdiqlash kutilmoqda",
                                finished: "Yakunlangan"
                            }[status] || status

                            return (
                                <article
                                    key={job.id}
                                     className={`card job-card ${selectedJob?.id === job.id ? "selected" : ""}`}
                                    style={{ cursor: "pointer" }}
                                    onClick={() => selectJob(job)}
                                >
                                    <h3 className="job-title">{job.title}</h3>
                                    <p className="job-desc">{job.description || "Tavsif kiritilmagan"}</p>
                                    <div className="meta" style={{ marginBottom: 12 }}>
                                        <span className="chip job-time-chip">🕒 {formatTimeAgo(job.created_at)}</span>
                                        <span className="chip">💰 {job.price ?? "-"} {job.currency || "UZS"}</span>
                                        <span className="chip">📍 {job.location || "-"}</span>
                                        <span className="chip job-service-chip">🧩 {job.service_name || serviceMap[String(job.service_id)] || job.service_id || "Noma’lum"}</span>
                                        <span className={`chip status-chip status-${status}`}><span className="status-dot" />{statusLabel}</span>
                                    </div>

                                    <div className="actions">
                                        {isParticipant && (
                                            <button
                                                className="btn btn-secondary"
                                                onClick={(e) => {
                                                    e.stopPropagation()
                                                    navigate(`/chat/${job.id}`, { state: { job } })
                                                }}
                                            >
                                                Suhbat
                                            </button>
                                        )}
                                        {isParticipant && status === "finished" && (
                                            <button
                                                className="btn btn-secondary"
                                                onClick={(e) => {
                                                    e.stopPropagation()
                                                    navigate(`/rating/${job.id}`, { state: { job } })
                                                }}
                                            >
                                                Baho
                                            </button>
                                        )}

                                        {/* --- ACCEPT TUGMASI (Mening ishim bo'lmaganda hamma uchun) --- */}
                                        {canAccept && (
                                            <button
                                                className="btn btn-primary"
                                                onClick={(e) => {
                                                    e.stopPropagation()
                                                    acceptJob(job)
                                                }}
                                            >
                                                Qabul qilish
                                            </button>
                                        )}

                                        {/* --- SIZ QABUL QILGANSIS CHIP --- */}
                                        {isIAccepted && status === "accepted" && (
                                            <span className="chip" style={{ background: "rgba(34, 197, 94, 0.2)", color: "#4ade80" }}>
                                                ✅ Qabul qilgansiz
                                            </span>
                                        )}

                                        {/* --- ISHCHINI BEKOR QILISH (Ish beruvchi uchun) --- */}
                                        {isMyJob && canFinish && (
                                            <button
                                                className="btn btn-warn"
                                                onClick={(e) => {
                                                    e.stopPropagation()
                                                    cancelWorker(job)
                                                }}
                                            >
                                                Ishchini almashtirish
                                            </button>
                                        )}

                                        {/* --- FINISH TUGMASI (Ish beruvchi uchun) --- */}
                                        {isMyJob && canFinish && (
                                            <button
                                                className="btn btn-success"
                                                onClick={(e) => {
                                                    e.stopPropagation()
                                                    finishJobSeeker(job)
                                                }}
                                            >
                                                Yakunlash
                                            </button>
                                        )}

                                        {/* --- FINISH TUGMASI (Bajaruvchi uchun) --- */}
                                        {isIAccepted && canFinish && (
                                            <button
                                                className="btn btn-success"
                                                onClick={(e) => {
                                                    e.stopPropagation()
                                                    finishJobSeeker(job)
                                                }}
                                            >
                                                Yakunlash
                                            </button>
                                        )}

                                        {isParticipant && status === "accepted" && (job.owner_finished || job.worker_finished) && (
                                            <span className="chip">
                                                ⏳ Ikkinchi tomonning yakunlashini kutmoqda
                                            </span>
                                        )}
                                    </div>
                                </article>
                            )
                        })}

                        {!filtered.length && <div className="empty-state">Hozircha ishlar yo‘q.</div>}
                    </div>
                </section>

                <aside className="card chat-wrap">
                    <div className="topbar" style={{ marginBottom: 0 }}>
                        <div className="page-head">
                            <h2 style={{ margin: 0 }}>Suhbat ko‘rinishi</h2>
                            <p className="muted" style={{ margin: 0 }}>
                                Tanlangan ish bo‘yicha oxirgi xabarlar.
                            </p>
                        </div>
                        <button
                            className="btn btn-secondary"
                            disabled={!selectedJob}
                            onClick={() => selectedJob && navigate(`/chat/${selectedJob.id}`, { state: { job: selectedJob } })}
                        >
                            Suhbatni ochish
                        </button>
                    </div>

                    {selectedJob ? (
                        <>
                            <div className="card" style={{ padding: 16, background: "rgba(255,255,255,.03)" }}>
                                <div className="helper">Tanlangan ish</div>
                                <div style={{ fontWeight: 800, fontSize: 18, marginTop: 6 }}>{selectedJob.title}</div>
                                <div className="meta" style={{ marginTop: 10 }}>
                                    <span className="chip">💰 {selectedJob.price ?? "-"} UZS</span>
                                    <span className="chip">📍 {selectedJob.location || "-"}</span>
                                </div>
                            </div>

                            <div className="message-list">
                                {messages.map((message, index) => {
                                    const mine = String(message.sender_id) === String(user?.id)
                                    return (
                                        <div className={`message ${mine ? "me" : "them"}`} key={index}>
                                            <div className="message-meta">{mine ? "Siz" : (message.sender_name || "Foydalanuvchi")} • {message.sent_at}</div>
                                            <div>{message.message}</div>
                                        </div>
                                    )
                                })}
                                {!messages.length && <div className="empty-state">Hozircha xabar yo‘q.</div>}
                            </div>
                        </>
                    ) : (
                        <div className="empty-state">Suhbatni ko‘rish uchun ish tanlang.</div>
                    )}
                </aside>
            </div>
        </AppLayout>
    )
}
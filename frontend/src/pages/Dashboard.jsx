import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

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

    const [activeConfirmJobId, setActiveConfirmJobId] = useState(null)
    const [adminContactJobId, setAdminContactJobId] = useState(null)

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
        const requested = result?.msg === "ok"
        setNoticeType(requested ? "ok" : "warn")
        setNotice(requested ? "Yakunlash so'rovi yuborildi. Bajaruvchi tasdiqlashi kutilmoqda." : (result?.msg || "Xato"))
        load()
    }

    // Ish bajaruvchi uchun panelni ochish
    const openConfirmPanel = (jobId) => {
        setActiveConfirmJobId(jobId)
    }

    const handleConfirmFinish = async (jobId, choice) => {
        const result = await api("/confirm_finish", {
            method: "POST",
            body: { job_id: jobId, choice },
            token
        })

        if (result?.msg === "ok") {
            setNoticeType("ok")
            setNotice("Ish muvaffaqiyatli yakunlandi va yopildi")
            setAdminContactJobId(null)
            setActiveConfirmJobId(null)
        } else if (result?.msg === "rejected") {
            setNoticeType("warn")
            setNotice("Siz rad etdingiz. Ish o'z joyida faol holatda qoldi.")
            setAdminContactJobId(jobId)
            setActiveConfirmJobId(null)
        } else {
            setNoticeType("warn")
            setNotice(result?.msg || "Xatolik yuz berdi")
        }
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
                                        <span className="chip">💰 {job.price ?? "-"} {job.currency || "UZS"}</span>
                                        <span className="chip">📍 {job.location || "-"}</span>
                                        <span className="chip">🧩 {serviceMap[String(job.service_id)] || job.service_name || job.service_id || "Noma’lum"}</span>
                                        <span className={`chip status-chip status-${status}`}><span className="status-dot" />{statusLabel}</span>
                                    </div>

                                    {/* --- IJROCHI TASDIQLASH SINOVI OYNASI --- */}
                                    {isIAccepted && activeConfirmJobId === job.id && (
                                        <div style={{
                                            background: "rgba(245, 158, 11, 0.1)",
                                            border: "1px solid rgba(245, 158, 11, 0.3)",
                                            padding: "12px",
                                            borderRadius: "8px",
                                            marginBottom: "12px"
                                        }} onClick={(e) => e.stopPropagation()}>
                                            <strong style={{ color: "#f59e0b", display: "block", marginBottom: 6, fontSize: 13 }}>
                                                Ishni tugatib, to'lovni qabul qildingizmi?
                                            </strong>
                                            <div style={{ display: "flex", gap: "8px" }}>
                                                <button className="btn btn-success" style={{ padding: "2px 10px", fontSize: 12 }} onClick={() => handleConfirmFinish(job.id, "yes")}>
                                                    Ha
                                                </button>
                                                <button className="btn btn-warn" style={{ padding: "2px 10px", fontSize: 12, background: "#ef4444" }} onClick={() => handleConfirmFinish(job.id, "no")}>
                                                    Yo'q
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {/* --- ADMIN BILAN BOG'LANISH OGOHLANTIRISHI --- */}
                                    {adminContactJobId === job.id && (
                                        <div className="notice warn" style={{ marginBottom: 12, fontSize: 12 }} onClick={(e) => e.stopPropagation()}>
                                            ⚠️ Muammo bormi? administrator bilan bog‘laning: <strong>@admin_support</strong>
                                        </div>
                                    )}

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

                                        {/* --- FINISH TUGMASI (Ish beruvchi uchun) --- */}
                                        {isMyJob && status === "accepted" && (
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
                                        {isIAccepted && status === "pending_finish" && activeConfirmJobId !== job.id && (
                                            <button
                                                className="btn btn-success"
                                                style={{ background: "#f59e0b" }}
                                                onClick={(e) => {
                                                    e.stopPropagation()
                                                    openConfirmPanel(job.id)
                                                }}
                                            >
                                                Yakunlash
                                            </button>
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
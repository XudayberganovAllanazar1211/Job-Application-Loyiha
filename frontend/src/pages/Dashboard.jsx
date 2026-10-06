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
    const token = localStorage.getItem("token") || ""
    const user = JSON.parse(localStorage.getItem("user") || "null")
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
            localStorage.setItem("user", JSON.stringify(profileResult))
        }
    }

    const loadMessages = async (job) => {
        if (!job) return
        const result = await api(`/messages/${job.id}`, { token })
        if (Array.isArray(result)) setMessages(result)
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
        setNotice(result?.msg === "ok" ? "Job qabul qilindi ✅" : (result?.msg || "Xato"))
        load()
    }

    // Ish beruvchi uchun finish funksiyasi
    const finishJobSeeker = async (job) => {
        const result = await api("/finish_job", {
            method: "POST",
            body: { job_id: job.id },
            token
        })
        setNotice(result?.msg === "ok" ? "Yakunlash so'rovi yuborildi. Bajaruvchi tasdiqlashi kutilmoqda." : (result?.msg || "Xato"))
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
            setNotice("Ish muvaffaqiyatli yakunlandi va yopildi ✅")
            setAdminContactJobId(null)
            setActiveConfirmJobId(null)
        } else if (result?.msg === "rejected") {
            setNotice("Siz rad etdingiz. Ish o'z joyida faol holatda qoldi.")
            setAdminContactJobId(jobId)
            setActiveConfirmJobId(null)
        } else {
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
            title="Dashboard"
            subtitle={`Xush kelibsiz, ${user?.first_name || user?.username || "user"}!`}
        >
            {notice && <div className="notice ok" style={{ marginBottom: 16 }}>{notice}</div>}

            <div className="stat-grid" style={{ marginBottom: 18 }}>
                <div className="stat-card">
                    <div className="stat-label">Active jobs</div>
                    <div className="stat-value">{jobs.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Services</div>
                    <div className="stat-value">{services.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">System Mode</div>
                    <div className="stat-value" style={{ fontSize: 22, color: "#10b981" }}>
                        Multi-talent (All-in-One)
                    </div>
                </div>
            </div>

            <div className="grid-2">
                <section className="card">
                    <div className="topbar" style={{ marginBottom: 16 }}>
                        <div className="page-head">
                            <h2 style={{ margin: 0 }}>My Workspace</h2>
                            <p className="muted" style={{ margin: 0 }}>
                                Siz yaratgan yoki siz qabul qilgan barcha faol ishlar ro'yxati.
                            </p>
                        </div>
                        <div className="actions">
                            <input
                                className="input"
                                style={{ minWidth: 220 }}
                                placeholder="Search..."
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                            />
                            <button className="btn btn-primary" onClick={() => navigate("/create")}>
                                Create Job
                            </button>
                        </div>
                    </div>

                    <div className="job-grid">
                        {filtered.map((job) => {
                            const workerName = `${job.worker_first || ""} ${job.worker_last || ""}`.trim() || job.worker_username;
                            const status = String(job.status || "").trim().toLowerCase()
                            const isMyJob = String(job.user_id) === String(user?.id)
                            const isIAccepted = String(job.worker_id) === String(user?.id)
                            const isParticipant = isMyJob || isIAccepted
                            const canAccept = status === "active" && !isMyJob && job.worker_id == null

                            return (
                                <article
                                    key={job.id}
                                    className="card job-card"
                                    style={{
                                        cursor: "pointer",
                                        outline: selectedJob?.id === job.id ? "2px solid rgba(96,165,250,.45)" : "none"
                                    }}
                                    onClick={() => selectJob(job)}
                                >
                                    <h3 className="job-title">{job.title}</h3>
                                    <p className="job-desc">{job.description || "No description"}</p>
                                    <div className="meta" style={{ marginBottom: 12 }}>
                                        <span className="chip">💰 {job.price ?? "-"} UZS</span>
                                        <span className="chip">📍 {job.location || "-"}</span>
                                        <span className="chip">🧩 {serviceMap[String(job.service_id)] || job.service_name || job.service_id || "Unknown"}</span>
                                        <span className="chip" style={{
                                            background: job.status === "pending_finish" ? "rgba(245, 158, 11, 0.2)" : "rgba(255,255,255,0.05)",
                                            color: job.status === "pending_finish" ? "#f59e0b" : "#fff"
                                        }}>
                                            Status: {status === "pending_finish" ? "Kutilmoqda" : status}
                                        </span>
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
                                            ⚠️ Muammo bormi? Admin bilan bog'laning: <strong>@admin_support</strong>
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
                                                Chat
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
                                                Rating
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
                                                Accept
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
                                                Finish
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
                                                Finish
                                            </button>
                                        )}
                                    </div>
                                </article>
                            )
                        })}

                        {!filtered.length && <div className="empty-state">Hozircha job yo‘q.</div>}
                    </div>
                </section>

                <aside className="card chat-wrap">
                    <div className="topbar" style={{ marginBottom: 0 }}>
                        <div className="page-head">
                            <h2 style={{ margin: 0 }}>Chat preview</h2>
                            <p className="muted" style={{ margin: 0 }}>
                                Tanlangan job bo‘yicha oxirgi xabarlar.
                            </p>
                        </div>
                        <button
                            className="btn btn-secondary"
                            disabled={!selectedJob}
                            onClick={() => selectedJob && navigate(`/chat/${selectedJob.id}`, { state: { job: selectedJob } })}
                        >
                            Open chat
                        </button>
                    </div>

                    {selectedJob ? (
                        <>
                            <div className="card" style={{ padding: 16, background: "rgba(255,255,255,.03)" }}>
                                <div className="helper">Selected job</div>
                                <div style={{ fontWeight: 800, fontSize: 18, marginTop: 6 }}>{selectedJob.title}</div>
                                <div className="meta" style={{ marginTop: 10 }}>
                                    <span className="chip">💰 {selectedJob.price ?? "-"} UZS</span>
                                    <span className="chip">📍 {selectedJob.location || "-"}</span>
                                </div>
                            </div>

                            <div className="message-list">
                                {messages.map((message, index) => (
                                    <div className="message them" key={index}>
                                        <div className="message-meta">{message.sender_name} • {message.sent_at}</div>
                                        <div>{message.message}</div>
                                    </div>
                                ))}
                                {!messages.length && <div className="empty-state">Hozircha xabar yo‘q.</div>}
                            </div>
                        </>
                    ) : (
                        <div className="empty-state">Chat ko‘rish uchun job tanla.</div>
                    )}
                </aside>
            </div>
        </AppLayout>
    )
}
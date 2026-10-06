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

export default function Jobs() {
    const [jobs, setJobs] = useState([])
    const [services, setServices] = useState([])
    const [search, setSearch] = useState("")
    const [notice, setNotice] = useState("")
    const [noticeType, setNoticeType] = useState("ok")
    const token = localStorage.getItem("token") || ""
    const user = JSON.parse(localStorage.getItem("user") || "null")
    const navigate = useNavigate()

    // Bajaruvchi uchun tasdiqlash so'rovi oynasini ochish/yopish holati
    const [activeConfirmJobId, setActiveConfirmJobId] = useState(null)
    // Bajaruvchi "Yo'q" tugmasini bossa, ekranda chiqadigan admin xabari
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

        if (Array.isArray(jobResult)) setJobs(jobResult)
        if (Array.isArray(serviceResult)) setServices(serviceResult)

        if (profileResult?.id) {
            localStorage.setItem("user", JSON.stringify(profileResult))
        }
    }

    useEffect(() => {
        load()
    }, [])

    const filtered = useMemo(() => {
        return jobs.filter((job) => {
            const text = `${job.title || ""} ${job.description || ""} ${job.location || ""}`.toLowerCase()
            return text.includes(search.toLowerCase())
        })
    }, [jobs, search])

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

    // Ish beruvchi uchun ishni tugatish so'rovi
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

    // Ish bajaruvchi "Yakunlash" tugmasini bosganda tasdiqlash panelini ochish
    const openConfirmPanel = (jobId) => {
        setActiveConfirmJobId(jobId)
    }

    // Tasdiqlash natijasini yuborish (Ha yoki Yo'q)
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

    return (
        <AppLayout
            title="Ishlar"
            subtitle="Tizimdagi faol e’lonlar va siz yaratgan yoki qabul qilgan ishlar."
        >
            <div className="card" style={{ marginBottom: 18 }}>
                <div className="topbar" style={{ marginBottom: 0 }}>
                    <div className="page-head">
                        <h2 style={{ margin: 0 }}>Mavjud ishlar</h2>
                        <p className="muted" style={{ margin: 0 }}>
                            Ishlarni qidirish, qabul qilish va boshqarish bo‘limi.
                        </p>
                    </div>
                    <div className="actions">
                        <input
                            className="input"
                            style={{ minWidth: 260 }}
                            placeholder="Ish qidirish..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />
                        <button className="btn btn-secondary" onClick={load}>Yangilash</button>
                        <button className="btn btn-primary" onClick={() => navigate("/create")}>
                            Ish yaratish
                        </button>
                    </div>
                </div>
                {notice && <div className={`notice ${noticeType === "ok" ? "ok" : "warn"}`} style={{ marginTop: 14 }}>{notice}</div>}
            </div>

            <div className="job-grid">
                {filtered.map((job) => {
                    const workerName = `${job.worker_first || ""} ${job.worker_last || ""}`.trim() || job.worker_username;
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
                        <article className="card job-card" key={job.id}>
                            <h3 className="job-title">{job.title}</h3>
                            <p className="job-desc">{job.description || "Tavsif kiritilmagan"}</p>
                            <div className="meta" style={{ marginBottom: 12 }}>
                                <span className="chip job-time-chip">🕒 {formatTimeAgo(job.created_at)}</span>
                                <span className="chip">💰 {job.price ?? "-"} {job.currency || "UZS"}</span>
                                <span className="chip">📍 {job.location || "-"}</span>
                                <span className="chip job-service-chip">🧩 {job.service_name || serviceMap[String(job.service_id)] || job.service_id || "Noma’lum"}</span>
                                <span className={`chip status-chip status-${status}`}><span className="status-dot" />{statusLabel}</span>

                                {isMyJob && (
                                    <span className="chip" style={{ background: "rgba(255,255,255,0.05)", color: "#9ca3af" }}>
                                        👤 Bajaruvchi: {job.worker_id ? workerName : "Hali qabul qilinmagan"}
                                    </span>
                                )}
                            </div>

                            {/* --- IJROCHI TASDIQLASH SINOVI OYNASI --- */}
                            {isIAccepted && activeConfirmJobId === job.id && (
                                <div style={{
                                    background: "rgba(245, 158, 11, 0.1)",
                                    border: "1px solid rgba(245, 158, 11, 0.3)",
                                    padding: "14px",
                                    borderRadius: "8px",
                                    marginBottom: "14px"
                                }}>
                                    <strong style={{ color: "#f59e0b", display: "block", marginBottom: 6 }}>
                                        Siz ishni bajarib bo'ldingizmi va to'lovni qabul qildingizmi?
                                    </strong>
                                    <div style={{ display: "flex", gap: "8px" }}>
                                        <button className="btn btn-success" style={{ padding: "4px 14px" }} onClick={() => handleConfirmFinish(job.id, "yes")}>
                                            Ha
                                        </button>
                                        <button className="btn btn-warn" style={{ padding: "4px 14px", background: "#ef4444" }} onClick={() => handleConfirmFinish(job.id, "no")}>
                                            Yo'q
                                        </button>
                                    </div>
                                </div>
                            )}

                            {/* --- ADMIN BILAN BOG'LANISH OGOHLANTIRISHI --- */}
                            {adminContactJobId === job.id && (
                                <div className="notice warn" style={{ marginBottom: 14, fontSize: 13 }}>
                                    ⚠️ To'lov yoki ish bo'yicha muammo mavjud. Iltimos, administratorlarimiz bilan bog‘laning: <strong>@admin_support</strong>
                                </div>
                            )}

                            <div className="actions">
                                {isParticipant && (
                                    <button className="btn btn-secondary" onClick={() => navigate(`/chat/${job.id}`, { state: { job } })}>
                                        Suhbat
                                    </button>
                                )}
                                {isParticipant && status === "finished" && (
                                    <button className="btn btn-secondary" onClick={() => navigate(`/rating/${job.id}`, { state: { job } })}>
                                        Baho
                                    </button>
                                )}

                                {/* --- ACCEPT TUGMASI (Mening ishim bo'lmasa va bo'sh bo'lsa hamma ko'ra oladi) --- */}
                                {canAccept && (
                                    <button className="btn btn-primary" onClick={() => acceptJob(job)}>
                                        Ishni qabul qilish
                                    </button>
                                )}

                                {/* --- SIZ QABUL QILGANSIS CHIP --- */}
                                {isIAccepted && status === "accepted" && (
                                    <span className="chip" style={{ background: "rgba(34, 197, 94, 0.2)", color: "#4ade80" }}>
                                        ✅ Siz qabul qilgansiz
                                    </span>
                                )}

                                {/* --- ISHCHINI BEKOR QILISH (Ish egasi uchun) --- */}
                                {isMyJob && (status === "accepted" || status === "pending_finish") && (
                                    <button className="btn btn-warn" onClick={() => cancelWorker(job)}>
                                        Ishchini almashtirish
                                    </button>
                                )}

                                {/* --- FINISH TUGMASI (Ish egasi uchun) --- */}
                                {isMyJob && status === "accepted" && (
                                    <button className="btn btn-success" onClick={() => finishJobSeeker(job)}>
                                        Yakunlash
                                    </button>
                                )}

                                {/* --- FINISH TUGMASI (Bajaruvchi uchun) --- */}
                                {isIAccepted && status === "pending_finish" && activeConfirmJobId !== job.id && (
                                    <button className="btn btn-success" style={{ background: "#f59e0b" }} onClick={() => openConfirmPanel(job.id)}>
                                        Yakunlash
                                    </button>
                                )}
                            </div>
                        </article>
                    )
                })}

                {!filtered.length && <div className="empty-state">Ish topilmadi.</div>}
            </div>
        </AppLayout>
    )
}
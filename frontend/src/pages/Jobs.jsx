import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

export default function Jobs() {
    const [jobs, setJobs] = useState([])
    const [services, setServices] = useState([])
    const [search, setSearch] = useState("")
    const [notice, setNotice] = useState("")
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
        setNotice(result?.msg === "ok" ? "Job qabul qilindi ✅" : (result?.msg || "Xato"))
        load()
    }

    // Ish beruvchi uchun ishni tugatish so'rovi
    const finishJobSeeker = async (job) => {
        const result = await api("/finish_job", {
            method: "POST",
            body: { job_id: job.id },
            token
        })
        setNotice(result?.msg === "ok" ? "Yakunlash so'rovi yuborildi. Bajaruvchi tasdiqlashi kutilmoqda." : (result?.msg || "Xato"))
        load()
    }

    // Ish bajaruvchi "Finish" tugmasini bosganda tasdiqlash panelini ochish
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

    return (
        <AppLayout
            title="Jobs"
            subtitle="Tizimdagi barcha faol e'lonlar va siz qabul qilgan ishlar."
        >
            <div className="card" style={{ marginBottom: 18 }}>
                <div className="topbar" style={{ marginBottom: 0 }}>
                    <div className="page-head">
                        <h2 style={{ margin: 0 }}>Available jobs</h2>
                        <p className="muted" style={{ margin: 0 }}>
                            Ishlarni qidirish, qabul qilish va boshqarish paneli.
                        </p>
                    </div>
                    <div className="actions">
                        <input
                            className="input"
                            style={{ minWidth: 260 }}
                            placeholder="Search job..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />
                        <button className="btn btn-secondary" onClick={load}>Refresh</button>
                        <button className="btn btn-primary" onClick={() => navigate("/create")}>
                            Create Job
                        </button>
                    </div>
                </div>
                {notice && <div className="notice ok" style={{ marginTop: 14 }}>{notice}</div>}
            </div>

            <div className="job-grid">
                {filtered.map((job) => {
                    const workerName = `${job.worker_first || ""} ${job.worker_last || ""}`.trim() || job.worker_username;
                    const isMyJob = String(job.user_id) === String(user?.id); // Men yaratgan ishmi?
                    const isIAccepted = String(job.worker_id) === String(user?.id); // Men qabul qilgan ishmi?

                    return (
                        <article className="card job-card" key={job.id}>
                            <h3 className="job-title">{job.title}</h3>
                            <p className="job-desc">{job.description || "No description"}</p>
                            <div className="meta" style={{ marginBottom: 12 }}>
                                <span className="chip">💰 {job.price ?? "-"} {job.currency || "UZS"}</span>
                                <span className="chip">📍 {job.location || "-"}</span>
                                <span className="chip">🧩 {serviceMap[String(job.service_id)] || job.service_name || job.service_id || "Unknown"}</span>
                                <span className="chip" style={{
                                    background: job.status === "pending_finish" ? "rgba(245, 158, 11, 0.2)" : "rgba(255,255,255,0.05)",
                                    color: job.status === "pending_finish" ? "#f59e0b" : "#fff"
                                }}>
                                    Status: {job.status === "pending_finish" ? "Tasdiqlanish kutilmoqda" : job.status}
                                </span>

                                {isMyJob && (
                                    <span className="chip" style={{ background: "rgba(255,255,255,0.05)", color: "#9ca3af" }}>
                                        👤 Bajaruvchi: {job.worker_id ? workerName : "Hozircha qabul qilinmagan"}
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
                                    ⚠️ To'lov yoki ish bo'yicha muammo mavjud. Iltimos, adminlarimiz bilan bog'laning: <strong>@admin_support</strong>
                                </div>
                            )}

                            <div className="actions">
                                <button className="btn btn-secondary" onClick={() => navigate(`/chat/${job.id}`, { state: { job } })}>
                                    Chat
                                </button>
                                <button className="btn btn-secondary" onClick={() => navigate(`/rating/${job.id}`, { state: { job } })}>
                                    Rating
                                </button>

                                {/* --- ACCEPT TUGMASI (Mening ishim bo'lmasa va bo'sh bo'lsa hamma ko'ra oladi) --- */}
                                {!isMyJob && String(job.status).toLowerCase() === "active" && (
                                    <button className="btn btn-primary" onClick={() => acceptJob(job)}>
                                        Accept job
                                    </button>
                                )}

                                {/* --- SIZ QABUL QILGANSIS CHIP --- */}
                                {isIAccepted && job.status === "accepted" && (
                                    <span className="chip" style={{ background: "rgba(34, 197, 94, 0.2)", color: "#4ade80" }}>
                                        ✅ Siz qabul qilgansiz
                                    </span>
                                )}

                                {/* --- FINISH TUGMASI (Ish egasi uchun) --- */}
                                {isMyJob && job.status === "accepted" && (
                                    <button className="btn btn-success" onClick={() => finishJobSeeker(job)}>
                                        Finish
                                    </button>
                                )}

                                {/* --- FINISH TUGMASI (Bajaruvchi uchun) --- */}
                                {isIAccepted && job.status === "pending_finish" && activeConfirmJobId !== job.id && (
                                    <button className="btn btn-success" style={{ background: "#f59e0b" }} onClick={() => openConfirmPanel(job.id)}>
                                        Finish
                                    </button>
                                )}
                            </div>
                        </article>
                    )
                })}

                {!filtered.length && <div className="empty-state">Job topilmadi.</div>}
            </div>
        </AppLayout>
    )
}
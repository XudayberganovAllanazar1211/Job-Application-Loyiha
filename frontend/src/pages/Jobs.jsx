import { useEffect, useMemo, useRef, useState } from "react"
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
    const [serviceSearch, setServiceSearch] = useState("")
    const [selectedServices, setSelectedServices] = useState([])
    const [showServiceMenu, setShowServiceMenu] = useState(false)
    const [showFilters, setShowFilters] = useState(false)
    const [minPrice, setMinPrice] = useState("")
    const [maxPrice, setMaxPrice] = useState("")
    const [timeFilter, setTimeFilter] = useState("all")
    const [locationFilter, setLocationFilter] = useState("")
    const [profileSkills, setProfileSkills] = useState([])
    const [notice, setNotice] = useState("")
    const [noticeType, setNoticeType] = useState("ok")
    const token = localStorage.getItem("token") || ""
    const user = JSON.parse(localStorage.getItem("user") || "null")
    const navigate = useNavigate()
    const serviceSearchRef = useRef(null)
    const filterRef = useRef(null)

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
            const skills = Array.isArray(profileResult.skills)
                ? profileResult.skills
                : typeof profileResult.skills === "string"
                    ? profileResult.skills.split(",")
                    : []
            setProfileSkills(skills.map((skill) => String(skill).trim()).filter(Boolean))
        }
    }

    useEffect(() => {
        load()
    }, [])

    const availableServices = useMemo(() => {
        const leafServices = services
            .filter((service) => !services.some((item) => String(item.parent_id) === String(service.id)))
            .map((service) => String(service.name).trim())
            .filter(Boolean)

        const jobServices = jobs
            .flatMap((job) => String(job.service_name || serviceMap[String(job.service_id)] || "").split(","))
            .map((name) => name.trim())
            .filter(Boolean)

        return [...new Set([...leafServices, ...jobServices])]
            .sort((a, b) => a.localeCompare(b, "uz"))
    }, [services, jobs, serviceMap])

    const matchingServices = useMemo(() => {
        const query = serviceSearch.trim().toLowerCase()
        return availableServices.filter((service) => {
            return !selectedServices.includes(service) && (!query || service.toLowerCase().includes(query))
        }).slice(0, 30)
    }, [availableServices, serviceSearch, selectedServices])

    const filtered = useMemo(() => {
        const query = search.trim().toLowerCase()
        const locationQuery = locationFilter.trim().toLowerCase()
        const min = minPrice === "" ? null : Number(minPrice)
        const max = maxPrice === "" ? null : Number(maxPrice)
        const now = Date.now()
        const timeLimits = { today: 1, three_days: 3, week: 7, month: 30 }

        return jobs.filter((job) => {
            const text = `${job.title || ""} ${job.description || ""} ${job.location || ""}`.toLowerCase()
            const jobServices = String(job.service_name || serviceMap[String(job.service_id)] || "")
                .split(",")
                .map((name) => name.trim())
                .filter(Boolean)

            const price = Number(job.price)
            const priceMatches = (min === null || (!Number.isNaN(price) && price >= min)) && (max === null || (!Number.isNaN(price) && price <= max))
            const locationMatches = !locationQuery || String(job.location || "").toLowerCase().includes(locationQuery)
            const days = timeLimits[timeFilter]
            const created = new Date(String(job.created_at || "").replace(" ", "T")).getTime()
            const timeMatches = !days || (!Number.isNaN(created) && created <= now && now - created <= days * 24 * 60 * 60 * 1000)
            const textMatches = !query || text.includes(query)
            const serviceMatches = !selectedServices.length || selectedServices.some((service) => jobServices.includes(service))

            return textMatches && serviceMatches && priceMatches && timeMatches && locationMatches
        })
    }, [jobs, search, selectedServices, serviceMap, minPrice, maxPrice, timeFilter, locationFilter])

    const recommendationData = useMemo(() => {
        const normalizedSkills = profileSkills.map((skill) => skill.toLowerCase().trim()).filter(Boolean)
        const scored = filtered.map((job) => {
            const jobServices = String(job.service_name || serviceMap[String(job.service_id)] || "")
                .split(",")
                .map((name) => name.trim().toLowerCase())
                .filter(Boolean)
            const jobText = (job.title || "") + " " + (job.description || "") + " " + jobServices.join(" ")
            let score = 0
            const matchedSkills = []
            normalizedSkills.forEach((skill) => {
                if (jobServices.some((service) => service === skill)) {
                    score += 100
                    matchedSkills.push(skill)
                } else if (jobServices.some((service) => service.includes(skill) || skill.includes(service))) {
                    score += 60
                    matchedSkills.push(skill)
                } else if (jobText.toLowerCase().includes(skill)) {
                    score += 25
                    matchedSkills.push(skill)
                }
            })
            return { job, score, matchedSkills }
        })
        scored.sort((a, b) => b.score - a.score || new Date(String(b.job.created_at || "").replace(" ", "T")).getTime() - new Date(String(a.job.created_at || "").replace(" ", "T")).getTime())
        return {
            recommended: scored.filter((item) => item.score > 0).slice(0, 6),
            ranked: scored
        }
    }, [filtered, profileSkills, serviceMap])

    useEffect(() => {
        if (!showServiceMenu && !showFilters) return

        const handleOutsideClick = (event) => {
            if (showServiceMenu && serviceSearchRef.current && !serviceSearchRef.current.contains(event.target)) setShowServiceMenu(false)
            if (showFilters && filterRef.current && !filterRef.current.contains(event.target)) setShowFilters(false)
        }

        document.addEventListener("mousedown", handleOutsideClick)
        document.addEventListener("touchstart", handleOutsideClick)

        return () => {
            document.removeEventListener("mousedown", handleOutsideClick)
            document.removeEventListener("touchstart", handleOutsideClick)
        }
    }, [showServiceMenu, showFilters])

    const addServiceFilter = (service) => {
        setSelectedServices([...selectedServices, service])
        setServiceSearch("")
        setShowServiceMenu(true)
    }

    const removeServiceFilter = (service) => {
        setSelectedServices(selectedServices.filter((item) => item !== service))
    }

    const clearAllFilters = () => {
        setSelectedServices([])
        setServiceSearch("")
        setMinPrice("")
        setMaxPrice("")
        setTimeFilter("all")
        setLocationFilter("")
        setShowServiceMenu(false)
        setShowFilters(false)
    }

    const clearServiceFilters = () => {
        setSelectedServices([])
        setServiceSearch("")
        setShowServiceMenu(false)
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
                    <div className="actions jobs-toolbar">
                        <input
                            className="input jobs-search-input"
                            placeholder="Ish qidirish..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />

                        <div className="jobs-service-search" ref={serviceSearchRef}>
                            <div className="jobs-service-input-wrap">
                                <input
                                    className="input"
                                    placeholder="Soha bo‘yicha qidirish..."
                                    value={serviceSearch}
                                    onFocus={() => setShowServiceMenu(true)}
                                    onChange={(e) => {
                                        setServiceSearch(e.target.value)
                                        setShowServiceMenu(true)
                                    }}
                                />
                                {selectedServices.length > 0 && (
                                    <span className="jobs-service-count">{selectedServices.length}</span>
                                )}
                            </div>

                            {showServiceMenu && (
                                <div className="jobs-service-menu">
                                    {selectedServices.length > 0 && (
                                        <div className="jobs-selected-services">
                                            {selectedServices.map((service) => (
                                                <button
                                                    type="button"
                                                    className="jobs-selected-chip"
                                                    key={service}
                                                    onClick={() => removeServiceFilter(service)}
                                                    title="Olib tashlash"
                                                >
                                                    {service} ×
                                                </button>
                                            ))}
                                            <button type="button" className="jobs-clear-services" onClick={clearServiceFilters}>
                                                Tozalash
                                            </button>
                                        </div>
                                    )}

                                    <div className="jobs-service-results">
                                        {matchingServices.map((service) => (
                                            <button
                                                type="button"
                                                className="jobs-service-option"
                                                key={service}
                                                onClick={() => addServiceFilter(service)}
                                            >
                                                <span>{service}</span>
                                                <span>+</span>
                                            </button>
                                        ))}
                                        {!matchingServices.length && (
                                            <div className="jobs-service-empty">Mos soha topilmadi.</div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="jobs-filter-wrap" ref={filterRef}>
                            <button className="btn btn-secondary" type="button" onClick={() => setShowFilters(!showFilters)}>Filtrlash</button>
                            {showFilters && (
                                <div className="jobs-filter-panel">
                                    <div className="jobs-filter-title">Ishlarni filtrlash</div>
                                    <div className="jobs-filter-grid">
                                        <label><span>Minimal narx</span><input className="input" type="number" min="0" placeholder="Masalan: 100000" value={minPrice} onChange={(e) => setMinPrice(e.target.value)} /></label>
                                        <label><span>Maksimal narx</span><input className="input" type="number" min="0" placeholder="Masalan: 500000" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} /></label>
                                        <label><span>Joylashuv</span><input className="input" placeholder="Masalan: Toshkent" value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)} /></label>
                                        <label><span>Vaqt</span><select className="input" value={timeFilter} onChange={(e) => setTimeFilter(e.target.value)}><option value="all">Barchasi</option><option value="today">Bugun</option><option value="three_days">Oxirgi 3 kun</option><option value="week">Oxirgi hafta</option><option value="month">Oxirgi oy</option></select></label>
                                    </div>
                                    <button className="btn btn-secondary" type="button" onClick={clearAllFilters}>Filtrlarni tozalash</button>
                                </div>
                            )}
                        </div>

                        <button className="btn btn-secondary" onClick={load}>Yangilash</button>
                        <button className="btn btn-primary" onClick={() => navigate("/create")}>
                            Ish yaratish
                        </button>
                    </div>
                </div>
                <div className="jobs-filter-note">
                    {selectedServices.length
                        ? <><strong>{selectedServices.length}</strong> ta soha tanlangan • <strong>{filtered.length}</strong> ta ish ko‘rsatilmoqda</>
                        : <><strong>{filtered.length}</strong> ta ish ko‘rsatilmoqda</>}
                </div>

                {notice && <div className={`notice ${noticeType === "ok" ? "ok" : "warn"}`} style={{ marginTop: 14 }}>{notice}</div>}
            </div>

            {recommendationData.recommended.length > 0 && (
                <section className="jobs-recommendations card">
                    <div className="jobs-recommendations-head">
                        <div>
                            <span className="jobs-recommendations-kicker">Siz uchun</span>
                            <h2>Profilingizga mos ishlar</h2>
                            <p>Profilingizdagi sohalarga mos keladigan ishlar.</p>
                        </div>
                        <span className="jobs-recommendations-count">{recommendationData.recommended.length} ta mos ish</span>
                    </div>
                    <div className="job-grid jobs-recommendation-grid">
                        {recommendationData.recommended.map(({ job, matchedSkills }) => (
                            <article className="card job-card job-recommended-card" key={job.id}>
                                <div className="job-recommended-label">★ Sizga mos</div>
                                <h3 className="job-title">{job.title}</h3>
                                <p className="job-desc">{job.description || "Tavsif kiritilmagan"}</p>
                                <div className="meta" style={{ marginBottom: 12 }}>
                                    <span className="chip job-time-chip">🕒 {formatTimeAgo(job.created_at)}</span>
                                    <span className="chip">💰 {job.price ?? "-"} {job.currency || "UZS"}</span>
                                    <span className="chip">📍 {job.location || "-"}</span>
                                    <span className="chip job-service-chip">🧩 {job.service_name || serviceMap[String(job.service_id)] || job.service_id || "Noma’lum"}</span>
                                </div>
                                <div className="job-recommended-skills">Mos sohalar: {matchedSkills.join(", ")}</div>
                            </article>
                        ))}
                    </div>
                </section>
            )}

            <div className="jobs-results-heading">
                <div>
                    <h2>Barcha ishlar</h2>
                    <p>Filtrlaringizga mos barcha mavjud ishlar.</p>
                </div>
                {profileSkills.length > 0 && recommendationData.recommended.length === 0 && (
                    <span className="jobs-profile-note">Profil sohalaringizga mos yangi ish hozircha topilmadi.</span>
                )}
            </div>

            <div className="job-grid">
                {recommendationData.ranked.map(({ job }) => {
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
                                    <span className="chip job-worker-chip">
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
                                    ⚠️ To‘lov yoki ish bo‘yicha muammo mavjud. Iltimos, administrator bilan bog‘laning.
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
                                    <span className="chip job-accepted-chip">
                                        ✅ Siz qabul qilgansiz
                                    </span>
                                )}

                                {/* --- ISHCHINI BEKOR QILISH (Ish egasi uchun) --- */}
                                {isMyJob && status === "accepted" && (
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
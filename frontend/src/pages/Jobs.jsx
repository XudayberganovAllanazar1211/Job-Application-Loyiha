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
    const [favoriteJobIds, setFavoriteJobIds] = useState([])
    const [savedOnly, setSavedOnly] = useState(false)
    const [showServiceMenu, setShowServiceMenu] = useState(false)
    const [showFilters, setShowFilters] = useState(false)
    const [minPrice, setMinPrice] = useState("")
    const [maxPrice, setMaxPrice] = useState("")
    const [timeFilter, setTimeFilter] = useState("all")
    const [locationFilter, setLocationFilter] = useState("")
    const [profileSkills, setProfileSkills] = useState([])
    const [notice, setNotice] = useState("")
    const [noticeType, setNoticeType] = useState("ok")
    const [loading, setLoading] = useState(true)
    const [actionJobId, setActionJobId] = useState(null)
    const token = localStorage.getItem("token") || ""
    const user = JSON.parse(localStorage.getItem("user") || "null")
    const navigate = useNavigate()
    const serviceSearchRef = useRef(null)
    const filterRef = useRef(null)

    const [reportJobId, setReportJobId] = useState(null)
    const [reportReason, setReportReason] = useState("")
    const [reportDetails, setReportDetails] = useState("")
    const [pageSize, setPageSize] = useState(10)
    const [currentPage, setCurrentPage] = useState(1)
    const [selectedJob, setSelectedJob] = useState(null)
    const [jobDetails, setJobDetails] = useState(null)
    const [jobDetailsLoading, setJobDetailsLoading] = useState(false)
    const [proposals, setProposals] = useState([])
    const [proposalLoading, setProposalLoading] = useState(false)
    const [proposalModalJob, setProposalModalJob] = useState(null)
    const [proposalPrice, setProposalPrice] = useState("")
    const [proposalDeadline, setProposalDeadline] = useState("")
    const [proposalMessage, setProposalMessage] = useState("")
    const [proposalActionId, setProposalActionId] = useState(null)

    const serviceMap = useMemo(
        () => Object.fromEntries(services.map((service) => [String(service.id), service.name])),
        [services]
    )

    const load = async () => {
        setLoading(true)
        try {
            const [jobResult, serviceResult, profileResult, favoriteResult] = await Promise.all([
                api("/jobs", { token }),
                api("/services", { token }),
                api("/profile", { token }),
                api("/favorites?target_type=job", { token })
            ])

            if (Array.isArray(jobResult)) setJobs(jobResult)
            if (Array.isArray(serviceResult)) setServices(serviceResult)
            if (Array.isArray(favoriteResult)) {
                setFavoriteJobIds(
                    favoriteResult
                        .filter((item) => item.target_type === "job")
                        .map((item) => Number(item.target_id))
                        .filter((id) => Number.isFinite(id))
                )
            }

            if (profileResult?.id) {
                localStorage.setItem("user", JSON.stringify(profileResult))
                const skills = Array.isArray(profileResult.skills)
                    ? profileResult.skills
                    : typeof profileResult.skills === "string"
                        ? profileResult.skills.split(",")
                        : []
                setProfileSkills(skills.map((skill) => String(skill).trim()).filter(Boolean))
            }
        } catch {
            setNoticeType("warn")
            setNotice("Ma'lumotlarni yuklashda xatolik yuz berdi.")
        } finally {
            setLoading(false)
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
            const savedMatches = !savedOnly || favoriteJobIds.includes(Number(job.id))

            return textMatches && serviceMatches && priceMatches && timeMatches && locationMatches && savedMatches
        })
    }, [jobs, search, selectedServices, serviceMap, minPrice, maxPrice, timeFilter, locationFilter, savedOnly, favoriteJobIds])

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

    const totalPages = Math.max(1, Math.ceil(recommendationData.ranked.length / pageSize))
    const pagedRanked = useMemo(() => {
        const start = (currentPage - 1) * pageSize
        return recommendationData.ranked.slice(start, start + pageSize)
    }, [recommendationData.ranked, currentPage, pageSize])

    useEffect(() => {
        setCurrentPage(1)
    }, [search, selectedServices, minPrice, maxPrice, timeFilter, locationFilter, savedOnly, pageSize])

    useEffect(() => {
        if (currentPage > totalPages) setCurrentPage(totalPages)
    }, [currentPage, totalPages])

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

    const selectJob = (job) => {
        setSelectedJob(job)
        setJobDetails(null)
    }

    const activeJobDetails = jobDetails || selectedJob

    useEffect(() => {
        if (!activeJobDetails?.id) {
            setProposals([])
            return
        }

        let cancelled = false
        setProposalLoading(true)
        const loadProposals = async () => {
            const result = await api(`/jobs/${activeJobDetails.id}/proposals`, { token })
            if (!cancelled) {
                setProposals(Array.isArray(result) ? result : [])
                setProposalLoading(false)
            }
        }
        loadProposals()

        return () => {
            cancelled = true
        }
    }, [activeJobDetails?.id, token])

    useEffect(() => {
        if (!selectedJob?.id) return

        let cancelled = false
        setJobDetailsLoading(true)

        const loadSelectedJobDetails = async () => {
            try {
                const result = await api(`/jobs/${selectedJob.id}`, { token })
                if (!cancelled && result?.id) {
                    setJobDetails(result)
                }
            } catch {
                if (!cancelled) setJobDetails(null)
            } finally {
                if (!cancelled) setJobDetailsLoading(false)
            }
        }

        loadSelectedJobDetails()

        return () => {
            cancelled = true
        }
    }, [selectedJob?.id, token])

    const activeJobDetails = jobDetails || selectedJob

    useEffect(() => {
        if (!selectedJob?.id && pagedRanked.length > 0) {
            setSelectedJob(pagedRanked[0].job)
        }
    }, [pagedRanked, selectedJob?.id])

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
        setSavedOnly(false)
        setShowServiceMenu(false)
        setShowFilters(false)
    }

    const clearServiceFilters = () => {
        setSelectedServices([])
        setServiceSearch("")
        setShowServiceMenu(false)
    }

    const activeFilterCount =
        selectedServices.length +
        (minPrice !== "" ? 1 : 0) +
        (maxPrice !== "" ? 1 : 0) +
        (timeFilter !== "all" ? 1 : 0) +
        (locationFilter.trim() ? 1 : 0) +
        (savedOnly ? 1 : 0)

    const hasSearchOrFilters = Boolean(search.trim() || serviceSearch.trim() || activeFilterCount)
    
    const toggleFavoriteJob = async (jobId) => {
        const id = Number(jobId)
        if (!Number.isFinite(id)) return
        const isFavorite = favoriteJobIds.includes(id)
        const result = await api("/favorites", {
            method: isFavorite ? "DELETE" : "POST",
            token,
            body: { target_type: "job", target_id: id }
        })
        if (!result?.ok) {
            setNoticeType("warn")
            setNotice(result?.msg || "Saqlanganlar yangilanmadi.")
            return
        }
        setFavoriteJobIds((current) => isFavorite ? current.filter((item) => item !== id) : [...current, id])
    }

    // Ish beruvchi uchun ishni tugatish so'rovi
    const finishJobSeeker = async (job) => {
        if (actionJobId) return
        setActionJobId(job.id)
        try {
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
            await load()
        } finally {
            setActionJobId(null)
        }
    }

    const finishJobWorker = async (jobId) => {
        if (actionJobId) return
        setActionJobId(jobId)
        try {
            const result = await api("/finish_job", {
                method: "POST",
                body: { job_id: jobId },
                token
            })
            const waiting = result?.msg === "waiting"
            const finished = result?.msg === "ok"
            setNoticeType((waiting || finished) ? "ok" : "warn")
            setNotice(
                finished
                    ? "Ish yakunlandi. To‘lov bajaruvchiga o‘tkazildi."
                    : waiting
                        ? "Siz ishni yakunladingiz. Ikkinchi tomonning ham «Yakunlash» tugmasini bosishini kuting."
                        : "Ishni yakunlashda xatolik yuz berdi."
            )
            await load()
        } finally {
            setActionJobId(null)
        }
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

    const submitReport = async (job) => {
        const reportedUserId = String(job.user_id) === String(user?.id) ? job.worker_id : job.user_id

        if (!reportedUserId) {
            setNoticeType("warn")
            setNotice("Shikoyat qilish uchun ishda boshqa ishtirokchi bo‘lishi kerak.")
            return
        }

        if (!reportReason) {
            setNoticeType("warn")
            setNotice("Shikoyat sababini tanlang.")
            return
        }

        try {
            const result = await api("/report", {
                method: "POST",
                body: {
                    job_id: job.id,
                    reported_user_id: Number(reportedUserId),
                    reason: reportReason,
                    details: reportDetails.trim()
                },
                token
            })

            if (result?.msg === "Shikoyatingiz qabul qilindi.") {
                setNoticeType("ok")
                setNotice("Shikoyatingiz yuborildi.")
                setReportJobId(null)
                setReportReason("")
                setReportDetails("")
            } else {
                setNoticeType("warn")
                setNotice(result?.msg || "Shikoyat yuborishda xatolik yuz berdi.")
            }
        } catch {
            setNoticeType("warn")
            setNotice("Shikoyat yuborishda xatolik yuz berdi.")
        }
    }


    const openProposalModal = (job) => {
        setProposalModalJob(job)
        setProposalPrice(String(job.price || ""))
        setProposalDeadline("")
        setProposalMessage("")
    }

    const submitProposal = async (event) => {
        event.preventDefault()
        if (!proposalModalJob) return

        const price = Number(proposalPrice)
        if (!Number.isFinite(price) || price <= 0) {
            setNoticeType("warn")
            setNotice("Taklif narxini to‘g‘ri kiriting.")
            return
        }
        if (!proposalDeadline.trim()) {
            setNoticeType("warn")
            setNotice("Taklif muddatini kiriting.")
            return
        }

        const result = await api(`/jobs/${proposalModalJob.id}/proposals`, {
            method: "POST",
            token,
            body: {
                price,
                deadline: proposalDeadline.trim(),
                message: proposalMessage.trim()
            }
        })

        if (result?.ok) {
            setNoticeType("ok")
            setNotice("Taklif muvaffaqiyatli yuborildi.")
            setProposalModalJob(null)
            const refreshed = await api(`/jobs/${proposalModalJob.id}/proposals`, { token })
            setProposals(Array.isArray(refreshed) ? refreshed : [])
            await load()
        } else {
            setNoticeType("warn")
            setNotice(result?.msg || "Taklif yuborilmadi.")
        }
    }

    const updateProposal = async (proposal, action) => {
        if (proposalActionId) return
        setProposalActionId(proposal.id)
        const result = await api(`/proposals/${proposal.id}`, {
            method: "PATCH",
            token,
            body: { action }
        })
        setProposalActionId(null)

        if (result?.ok) {
            setNoticeType("ok")
            setNotice(result?.msg || "Taklif yangilandi.")
            const refreshed = await api(`/jobs/${proposal.job_id}/proposals`, { token })
            setProposals(Array.isArray(refreshed) ? refreshed : [])
            await load()
        } else {
            setNoticeType("warn")
            setNotice(result?.msg || "Taklifni yangilab bo‘lmadi.")
        }
    }

    const withdrawProposal = async (proposal) => {
        if (proposalActionId) return
        setProposalActionId(proposal.id)
        const result = await api(`/proposals/${proposal.id}`, {
            method: "DELETE",
            token
        })
        setProposalActionId(null)

        if (result?.ok) {
            setNoticeType("ok")
            setNotice(result?.msg || "Taklif bekor qilindi.")
            const refreshed = await api(`/jobs/${proposal.job_id}/proposals`, { token })
            setProposals(Array.isArray(refreshed) ? refreshed : [])
            await load()
        } else {
            setNoticeType("warn")
            setNotice(result?.msg || "Taklifni bekor qilib bo‘lmadi.")
        }
    }

    const detailStatus = String(activeJobDetails?.status || "").trim().toLowerCase()
    const detailIsMyJob = String(activeJobDetails?.user_id) === String(user?.id)
    const detailIsWorker = String(activeJobDetails?.worker_id) === String(user?.id)
    const detailIsParticipant = detailIsMyJob || detailIsWorker
    const detailCanPropose = detailStatus === "active" && !detailIsMyJob && activeJobDetails?.worker_id == null
    const myProposal = proposals.find((item) => String(item.worker_id) === String(user?.id))
    const detailCanFinish = detailStatus === "accepted" && ((detailIsMyJob && !activeJobDetails?.owner_finished) || (detailIsWorker && !activeJobDetails?.worker_finished))
    const detailCanReport = detailIsParticipant && activeJobDetails?.worker_id != null && ["accepted", "pending_finish"].includes(detailStatus)
    const detailStatusLabel = {
        active: "Faol",
        payment_pending: "To‘lov kutilmoqda",
        accepted: "Qabul qilingan",
        pending_finish: "Tasdiqlash kutilmoqda",
        finished: "Yakunlangan"
    }[detailStatus] || detailStatus

    return (
        <AppLayout
            title="Ishlar"
            subtitle="Tizimdagi ishlarni qidiring, tanlang va to‘liq ma’lumotlarini ko‘ring."
        >
            <div className="card" style={{ marginBottom: 18 }}>
                <div className="section-toolbar" style={{ marginBottom: 0 }}>
                    <div className="page-head">
                        <h2 style={{ margin: 0 }}>Mavjud ishlar</h2>
                        <p className="muted" style={{ margin: 0 }}>Ishlarni qidirish, filtrlash va boshqarish bo‘limi.</p>
                    </div>
                    <div className="actions jobs-toolbar">
                        <input className="input jobs-search-input" placeholder="Ish qidirish..." value={search} onChange={(e) => setSearch(e.target.value)} />
                        <div className="jobs-service-search" ref={serviceSearchRef}>
                            <div className="jobs-service-input-wrap">
                                <input className="input" placeholder="Soha bo‘yicha qidirish..." value={serviceSearch} onFocus={() => setShowServiceMenu(true)} onChange={(e) => { setServiceSearch(e.target.value); setShowServiceMenu(true) }} />
                                {selectedServices.length > 0 && <span className="jobs-service-count">{selectedServices.length}</span>}
                            </div>
                            {showServiceMenu && (
                                <div className="jobs-service-menu">
                                    {selectedServices.length > 0 && (
                                        <div className="jobs-selected-services">
                                            {selectedServices.map((service) => (
                                                <button type="button" className="jobs-selected-chip" key={service} onClick={() => removeServiceFilter(service)}>{service} ×</button>
                                            ))}
                                            <button type="button" className="jobs-clear-services" onClick={clearServiceFilters}>Tozalash</button>
                                        </div>
                                    )}
                                    <div className="jobs-service-results">
                                        {matchingServices.map((service) => (
                                            <button type="button" className="jobs-service-option" key={service} onClick={() => addServiceFilter(service)}>
                                                <span>{service}</span><span>+</span>
                                            </button>
                                        ))}
                                        {!matchingServices.length && <div className="jobs-service-empty">Mos soha topilmadi.</div>}
                                    </div>
                                </div>
                            )}
                        </div>
                        <div className="jobs-filter-wrap" ref={filterRef}>
                            <button className="btn btn-secondary jobs-filter-button" type="button" onClick={() => setShowFilters((value) => !value)}>
                                <span>Filtrlash</span>{activeFilterCount > 0 && <b>{activeFilterCount}</b>}
                            </button>
                            {showFilters && (
                                <div className="jobs-filter-panel">
                                    <div className="jobs-filter-title">Ishlarni filtrlash</div>
                                    <div className="jobs-filter-grid">
                                        <label><span>Minimal narx</span><input className="input" type="number" min="0" value={minPrice} onChange={(e) => setMinPrice(e.target.value)} /></label>
                                        <label><span>Maksimal narx</span><input className="input" type="number" min="0" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} /></label>
                                        <label><span>Joylashuv</span><input className="input" placeholder="Masalan: Toshkent" value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)} /></label>
                                        <label style={{ gridColumn: "1 / -1" }}>
                                            <span>Saqlangan ishlar</span>
                                            <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
                                                <input type="checkbox" checked={savedOnly} onChange={(e) => setSavedOnly(e.target.checked)} />
                                                <span>Faqat ★ bilan saqlangan ishlarni ko‘rsatish</span>
                                            </label>
                                        </label>
                                        <label>
                                            <span>Vaqt</span>
                                            <select className="input" value={timeFilter} onChange={(e) => setTimeFilter(e.target.value)}>
                                                <option value="all">Barchasi</option>
                                                <option value="today">Bugun</option>
                                                <option value="three_days">Oxirgi 3 kun</option>
                                                <option value="week">Oxirgi hafta</option>
                                                <option value="month">Oxirgi oy</option>
                                            </select>
                                        </label>
                                    </div>
                                    <button className="btn btn-secondary" type="button" onClick={clearAllFilters}>Filtrlarni tozalash</button>
                                </div>
                            )}
                        </div>
                        <button className="btn btn-secondary" onClick={load} disabled={loading}>{loading ? "Yangilanmoqda..." : "Yangilash"}</button>
                        <button className="btn btn-primary" onClick={() => navigate("/create")}>Ish yaratish</button>
                    </div>
                </div>
                <div className="jobs-filter-note">
                    <span><strong>{filtered.length}</strong> ta ish ko‘rsatilmoqda</span>
                    {activeFilterCount > 0 && <span className="jobs-active-filter-label">{activeFilterCount} ta filtr faol</span>}
                    {hasSearchOrFilters && <button type="button" className="jobs-clear-inline" onClick={clearAllFilters}>Hammasini tozalash</button>}
                </div>
                {notice && <div className={`notice ${noticeType === "ok" ? "ok" : "warn"}`} style={{ marginTop: 14 }}>{notice}</div>}
            </div>

            <div
                style={{
                    display: "grid",
                    gridTemplateColumns: "minmax(0, 1fr) minmax(420px, 520px)",
                    gap: 20,
                    alignItems: "start",
                    width: "100%"
                }}
            >
                <section style={{ minWidth: 0 }}>
                    {loading ? (
                        <div className="jobs-loading-grid">
                            {Array.from({ length: 6 }).map((_, index) => (
                                <div className="card job-card jobs-skeleton-card" key={index}>
                                    <div className="skeleton skeleton-line skeleton-title" />
                                    <div className="skeleton skeleton-line" />
                                    <div className="skeleton skeleton-line short" />
                                    <div className="skeleton-row">
                                        <div className="skeleton skeleton-chip" />
                                        <div className="skeleton skeleton-chip" />
                                        <div className="skeleton skeleton-chip" />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <>
                            {recommendationData.recommended.length > 0 && (
                                <section className="jobs-recommendations card" style={{ marginBottom: 18 }}>
                                    <div className="jobs-recommendations-head">
                                        <div>
                                            <span className="jobs-recommendations-kicker">Siz uchun</span>
                                            <h2>Profilingizga mos ishlar</h2>
                                            <p>Profilingizdagi sohalarga mos keladigan ishlar.</p>
                                        </div>
                                        <span className="jobs-recommendations-count">{recommendationData.recommended.length} ta mos ish</span>
                                    </div>
                                    <div className="job-grid" style={{ gridTemplateColumns: "1fr" }}>
                                        {recommendationData.recommended.map(({ job, matchedSkills }) => (
                                            <article className={`card job-card job-recommended-card ${selectedJob?.id === job.id ? "selected" : ""}`} key={job.id} onClick={() => selectJob(job)} style={{ cursor: "pointer" }}>
                                                <div className="job-recommended-label">★ Sizga mos</div>
                                                <h3 className="job-title">{job.title}</h3>
                                                <p className="job-desc">{job.description || "Tavsif kiritilmagan"}</p>
                                                <div className="meta">
                                                    <span className="chip">💰 {job.price ?? "-"} {job.currency || "UZS"}</span>
                                                    <span className="chip">📍 {job.location || "-"}</span>
                                                    <span className="chip">🧩 {job.service_name || serviceMap[String(job.service_id)] || "Noma’lum"}</span>
                                                </div>
                                                <div className="job-recommended-skills">Mos sohalar: {matchedSkills.join(", ")}</div>
                                            </article>
                                        ))}
                                    </div>
                                </section>
                            )}

                            <section className="card">
                                <div className="jobs-results-heading">
                                    <div><h2>Barcha ishlar</h2><p>Filtrlaringizga mos barcha ishlar.</p></div>
                                </div>
                                <div className="job-grid" style={{ gridTemplateColumns: "1fr" }}>
                                    {pagedRanked.map(({ job }) => (
                                        <article
                                            className={`card job-card ${selectedJob?.id === job.id ? "selected" : ""}`}
                                            key={job.id}
                                            onClick={() => selectJob(job)}
                                            style={{ cursor: "pointer" }}
                                        >
                                            <div style={{ display: "flex", gap: 10, alignItems: "flex-start", justifyContent: "space-between" }}>
                                                <h3 className="job-title" style={{ margin: 0 }}>{job.title}</h3>
                                                <button
                                                    type="button"
                                                    className="btn btn-secondary"
                                                    style={{ minWidth: 44, padding: "8px 10px" }}
                                                    aria-label={favoriteJobIds.includes(Number(job.id)) ? "Saqlangan ishni olib tashlash" : "Ishni saqlash"}
                                                    onClick={(event) => { event.stopPropagation(); toggleFavoriteJob(job.id) }}
                                                >
                                                    {favoriteJobIds.includes(Number(job.id)) ? "★" : "☆"}
                                                </button>
                                            </div>
                                            <p className="job-desc">{job.description || "Tavsif kiritilmagan"}</p>
                                            <div className="meta">
                                                <span className="chip">🕒 {formatTimeAgo(job.created_at)}</span>
                                                <span className="chip">💰 {job.price ?? "-"} {job.currency || "UZS"}</span>
                                                <span className="chip">📍 {job.location || "-"}</span>
                                                <span className="chip">🧩 {job.service_name || serviceMap[String(job.service_id)] || "Noma’lum"}</span>
                                                <span className={`chip status-chip status-${String(job.status || "").toLowerCase()}`}>
                                                    <span className="status-dot" />
                                                    {({ active: "Faol", payment_pending: "To‘lov kutilmoqda", accepted: "Qabul qilingan", pending_finish: "Tasdiqlash kutilmoqda", finished: "Yakunlangan" })[String(job.status || "").toLowerCase()] || job.status}
                                                </span>
                                                <span className="chip">📅 {job.created_at || "Sana noma’lum"}</span>
                                                <span className="chip job-worker-chip">
                                                    👤 Yaratuvchi:
                                                    <button type="button" className="profile-link-button" onClick={(e) => { e.stopPropagation(); if (job.creator_username) navigate(`/profiles/${job.creator_username}`) }}>
                                                        {(`${job.creator_first || ""} ${job.creator_last || ""}`).trim() || job.creator_username || "Noma’lum"}
                                                    </button>
                                                </span>
                                                <span className="chip job-worker-chip">
                                                    👤 Bajaruvchi:
                                                    {job.worker_id ? (
                                                        <button type="button" className="profile-link-button" onClick={(e) => { e.stopPropagation(); if (job.worker_username) navigate(`/profiles/${job.worker_username}`) }}>
                                                            {(`${job.worker_first || ""} ${job.worker_last || ""}`).trim() || job.worker_username || "Noma’lum"}
                                                        </button>
                                                    ) : " Hali qabul qilinmagan"}
                                                </span>
                                            </div>
                                        </article>
                                    ))}
                                    {!pagedRanked.length && (
                                        <div className="empty-state jobs-empty-state">
                                            <strong>{hasSearchOrFilters ? "Sizning mezonlaringiz bo‘yicha ish topilmadi." : "Hozircha faol ishlar yo‘q."}</strong>
                                            <span>{hasSearchOrFilters ? "Qidiruv yoki filtrlarni o‘zgartirib ko‘ring." : "Yangi e’lonlar paydo bo‘lishi bilan shu yerda ko‘rinadi."}</span>
                                            {hasSearchOrFilters && <button className="btn btn-secondary" type="button" onClick={clearAllFilters}>Filtrlarni tozalash</button>}
                                        </div>
                                    )}
                                </div>
                                {filtered.length > 0 && (
                                    <div className="jobs-pagination">
                                        <div className="jobs-page-size">
                                            <span>Bir sahifada</span>
                                            <select className="input" value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>
                                                <option value="5">5 ta</option>
                                                <option value="10">10 ta</option>
                                                <option value="20">20 ta</option>
                                                <option value="50">50 ta</option>
                                            </select>
                                            <span>job</span>
                                        </div>
                                        <div className="jobs-page-summary">{filtered.length} ta ish • {currentPage} / {totalPages} sahifa</div>
                                        <div className="jobs-page-controls">
                                            <button className="btn btn-secondary" disabled={currentPage === 1} onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}>‹</button>
                                            <input className="input jobs-page-number" type="number" min="1" max={totalPages} value={currentPage} aria-label="Sahifa raqami" onChange={(e) => { const page = Number(e.target.value); if (Number.isFinite(page)) setCurrentPage(Math.min(totalPages, Math.max(1, page))) }} />
                                            <span className="jobs-page-total">/ {totalPages}</span>
                                            <button className="btn btn-secondary" disabled={currentPage === totalPages} onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}>›</button>
                                        </div>
                                    </div>
                                )}
                            </section>
                        </>
                    )}
                </section>

                <aside
                    className="card jobs-detail-panel"
                    style={{ minWidth: 0, width: "100%" }}
                >
                    <div className="dashboard-panel-head">
                        <div>
                            <span className="profile-eyebrow">ISH MA'LUMOTI</span>
                            <h2>To‘liq ma’lumot</h2>
                            <p>Tanlangan jobning barcha tafsilotlari va amallari.</p>
                        </div>
                    </div>

                    {jobDetailsLoading ? (
                        <div className="empty-state">To‘liq ma’lumot backenddan yuklanmoqda...</div>
                    ) : !activeJobDetails ? (
                        <div className="empty-state">Jobni tanlang.</div>
                    ) : (
                        <div className="dashboard-job-detail-body">
                            <div>
                                <span className="helper">ISH NOMI</span>
                                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                                    <h2 className="dashboard-job-detail-title" style={{ marginBottom: 0 }}>{activeJobDetails.title}</h2>
                                    <button
                                        type="button"
                                        className="btn btn-secondary"
                                        onClick={() => toggleFavoriteJob(activeJobDetails.id)}
                                        aria-label={favoriteJobIds.includes(Number(activeJobDetails.id)) ? "Saqlangan ishni olib tashlash" : "Ishni saqlash"}
                                    >
                                        {favoriteJobIds.includes(Number(activeJobDetails.id)) ? "★ Saqlangan" : "☆ Saqlash"}
                                    </button>
                                </div>
                            </div>
                            <div className="dashboard-job-detail-section">
                                <span className="helper">TAVSIF</span>
                                <p>{activeJobDetails.description || "Tavsif kiritilmagan."}</p>
                            </div>
                            <div className="dashboard-job-detail-facts">
                                <div><span>Narx</span><strong>{activeJobDetails.price ?? "-"} {activeJobDetails.currency || "UZS"}</strong></div>
                                <div><span>Joylashuv</span><strong>{activeJobDetails.location || "—"}</strong></div>
                                <div><span>Soha</span><strong>{activeJobDetails.service_name || serviceMap[String(activeJobDetails.service_id)] || "Noma’lum"}</strong></div>
                                <div><span>Yaratilgan</span><strong>{activeJobDetails.created_at || "—"}</strong></div>
                                <div><span>Holat</span><strong>{detailStatusLabel}</strong></div>
                                <div>
                                    <span>Yaratuvchi</span>
                                    <strong>
                                        <button type="button" className="profile-link-button" disabled={!activeJobDetails.creator_username} onClick={() => activeJobDetails.creator_username && navigate(`/profiles/${activeJobDetails.creator_username}`)}>
                                            {(`${activeJobDetails.creator_first || ""} ${activeJobDetails.creator_last || ""}`).trim() || activeJobDetails.creator_username || "Noma’lum"}
                                        </button>
                                    </strong>
                                </div>
                                <div>
                                    <span>Bajaruvchi</span>
                                    <strong>
                                        {activeJobDetails.worker_id ? (
                                            <button type="button" className="profile-link-button" onClick={() => activeJobDetails.worker_username && navigate(`/profiles/${activeJobDetails.worker_username}`)}>
                                                {(`${activeJobDetails.worker_first || ""} ${activeJobDetails.worker_last || ""}`).trim() || activeJobDetails.worker_username || "Noma’lum"}
                                            </button>
                                        ) : "Hali qabul qilinmagan"}
                                    </strong>
                                </div>
                                {detailStatus === "accepted" && (
                                    <>
                                        <div><span>Yaratuvchi yakunladi</span><strong>{activeJobDetails.owner_finished ? "Ha" : "Yo‘q"}</strong></div>
                                        <div><span>Bajaruvchi yakunladi</span><strong>{activeJobDetails.worker_finished ? "Ha" : "Yo‘q"}</strong></div>
                                    </>
                                )}
                            </div>

                            {detailStatus === "active" && (detailIsMyJob || myProposal) && (
                                <div className="dashboard-job-detail-section" style={{ marginTop: 16 }}>
                                    <span className="helper">TAKLIFLAR</span>
                                    {proposalLoading ? (
                                        <div className="muted" style={{ marginTop: 8 }}>Takliflar yuklanmoqda...</div>
                                    ) : !proposals.length ? (
                                        <div className="empty-state" style={{ marginTop: 10, padding: 16 }}>
                                            <strong>Hali taklif yo‘q.</strong>
                                            <span>Ijrochilar bu ish uchun o‘z narxi va muddatini yuborishi mumkin.</span>
                                        </div>
                                    ) : (
                                        <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
                                            {proposals.map((proposal) => (
                                                <div key={proposal.id} className="card" style={{ margin: 0, padding: 14, border: "1px solid var(--border, #e5e7eb)" }}>
                                                    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                                                        <div>
                                                            <strong>{(`${proposal.first_name || ""} ${proposal.last_name || ""}`).trim() || proposal.username}</strong>
                                                            <div className="muted">@{proposal.username} · {Number(proposal.average_rating || 0).toFixed(1)} ★</div>
                                                        </div>
                                                        <strong>{Number(proposal.price || 0).toLocaleString("uz-UZ")} UZS</strong>
                                                    </div>
                                                    <div className="meta" style={{ marginTop: 8 }}>
                                                        <span className="chip">Muddat: {proposal.deadline}</span>
                                                        <span className="chip">Holat: {({ pending: "Kutilmoqda", accepted: "Qabul qilindi", rejected: "Rad etildi", withdrawn: "Bekor qilindi" })[proposal.status] || proposal.status}</span>
                                                    </div>
                                                    {proposal.message && <p style={{ margin: "10px 0 0" }}>{proposal.message}</p>}
                                                    {detailIsMyJob && proposal.status === "pending" && (
                                                        <div className="actions" style={{ marginTop: 10 }}>
                                                            <button className="btn btn-primary" disabled={proposalActionId === proposal.id} onClick={() => updateProposal(proposal, "accept")}>
                                                                {proposalActionId === proposal.id ? "Saqlanmoqda..." : "Taklifni qabul qilish"}
                                                            </button>
                                                            <button className="btn btn-secondary" disabled={proposalActionId === proposal.id} onClick={() => updateProposal(proposal, "reject")}>
                                                                Rad etish
                                                            </button>
                                                            <button className="btn btn-secondary" onClick={() => proposal.username && navigate(`/profiles/${proposal.username}`)}>
                                                                Profil
                                                            </button>
                                                        </div>
                                                    )}
                                                    {!detailIsMyJob && String(proposal.worker_id) === String(user?.id) && proposal.status === "pending" && (
                                                        <div className="actions" style={{ marginTop: 10 }}>
                                                            <button className="btn btn-secondary" disabled={proposalActionId === proposal.id} onClick={() => withdrawProposal(proposal)}>
                                                                Bekor qilish
                                                            </button>
                                                        </div>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}

                            <div className="dashboard-job-detail-section">
                                <span className="helper">AMALLAR</span>
                                <div className="actions" style={{ marginTop: 10 }}>
                                    {detailIsParticipant && <button className="btn btn-secondary" onClick={() => navigate(`/chat/${activeJobDetails.id}`, { state: { job: activeJobDetails } })}>Suhbat</button>}
                                    {detailIsParticipant && detailStatus === "finished" && <button className="btn btn-secondary" onClick={() => navigate(`/rating/${activeJobDetails.id}`, { state: { job: activeJobDetails } })}>Baho</button>}
                                    {detailCanPropose && <button className="btn btn-primary" onClick={() => openProposalModal(activeJobDetails)}>{myProposal?.status === "pending" ? "Taklifingizni ko‘rish" : "Taklif yuborish"}</button>}
                                    {detailIsMyJob && detailStatus === "payment_pending" && <button className="btn btn-primary" onClick={() => navigate(`/payments/job/${activeJobDetails.id}`)}>💳 To‘lovni amalga oshirish</button>}
                                    {detailCanReport && <button className="btn btn-secondary" onClick={() => setReportJobId(reportJobId === activeJobDetails.id ? null : activeJobDetails.id)}>⚑ Shikoyat</button>}
                                    {detailIsMyJob && detailCanFinish && <button className="btn btn-warn" onClick={() => cancelWorker(activeJobDetails)}>Ishchini almashtirish</button>}
                                    {detailCanFinish && detailIsParticipant && <button className="btn btn-success" disabled={actionJobId === activeJobDetails.id} onClick={() => detailIsWorker ? finishJobWorker(activeJobDetails.id) : finishJobSeeker(activeJobDetails)}>{actionJobId === activeJobDetails.id ? "Yakunlanmoqda..." : "Yakunlash"}</button>}
                                    {detailIsWorker && detailStatus === "payment_pending" && <span className="chip job-accepted-chip">⏳ Ish egasining to‘lovi kutilmoqda</span>}
                                    {detailIsWorker && detailStatus === "accepted" && <span className="chip job-accepted-chip">✅ Siz qabul qilgansiz</span>}
                                    {detailIsParticipant && detailStatus === "accepted" && (activeJobDetails.owner_finished || activeJobDetails.worker_finished) && <span className="chip">⏳ Ikkinchi tomonning yakunlashini kutmoqda</span>}
                                </div>

                                {reportJobId === activeJobDetails.id && detailCanReport && (
                                    <div className="report-panel" style={{ marginTop: 12 }}>
                                        <strong>{detailIsMyJob ? "Bajaruvchi haqida shikoyat" : "Ish egasi haqida shikoyat"}</strong>
                                        <select className="select" value={reportReason} onChange={(e) => setReportReason(e.target.value)}>
                                            <option value="">Sababni tanlang</option>
                                            <option value="Firibgarlik yoki aldov">Firibgarlik yoki aldov</option>
                                            <option value="Noto‘g‘ri yoki yolg‘on e’lon">Noto‘g‘ri yoki yolg‘on e’lon</option>
                                            <option value="Haqorat yoki nomaqbul xatti-harakat">Haqorat yoki nomaqbul xatti-harakat</option>
                                            <option value="Spam">Spam</option>
                                            <option value="Boshqa">Boshqa</option>
                                        </select>
                                        <textarea className="textarea" maxLength={2000} placeholder="Qo‘shimcha tafsilot..." value={reportDetails} onChange={(e) => setReportDetails(e.target.value)} />
                                        <div className="actions">
                                            <button type="button" className="btn btn-danger" disabled={!reportReason} onClick={() => submitReport(activeJobDetails)}>Yuborish</button>
                                            <button type="button" className="btn btn-secondary" onClick={() => setReportJobId(null)}>Bekor qilish</button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </aside>
            </div>

            {proposalModalJob && (
                <div
                    style={{
                        position: "fixed",
                        inset: 0,
                        zIndex: 1200,
                        background: "rgba(15, 23, 42, 0.58)",
                        display: "grid",
                        placeItems: "center",
                        padding: 18
                    }}
                    onMouseDown={(event) => {
                        if (event.target === event.currentTarget) setProposalModalJob(null)
                    }}
                >
                    <div className="card" style={{ width: "min(560px, 100%)", margin: 0, maxHeight: "90vh", overflow: "auto" }}>
                        <div className="section-toolbar">
                            <div className="page-head">
                                <span className="profile-eyebrow">TAKLIF YUBORISH</span>
                                <h2>{proposalModalJob.title}</h2>
                                <p className="muted">Narxingiz, bajarish muddatingiz va qisqa izohni kiriting.</p>
                            </div>
                            <button className="btn btn-secondary" type="button" onClick={() => setProposalModalJob(null)}>×</button>
                        </div>
                        <form onSubmit={submitProposal} className="form">
                            <label className="field">
                                <span>Taklif narxi (UZS)</span>
                                <input className="input" type="number" min="1" step="1" value={proposalPrice} onChange={(event) => setProposalPrice(event.target.value)} required />
                                <small className="muted">E’lon byudjeti: {Number(proposalModalJob.price || 0).toLocaleString("uz-UZ")} UZS</small>
                            </label>
                            <label className="field">
                                <span>Bajarish muddati</span>
                                <input className="input" type="date" value={proposalDeadline} onChange={(event) => setProposalDeadline(event.target.value)} required />
                            </label>
                            <label className="field">
                                <span>Taklif izohi</span>
                                <textarea className="textarea" maxLength={3000} rows={5} placeholder="Nima qilishingiz va qanday topshirishingizni qisqacha yozing..." value={proposalMessage} onChange={(event) => setProposalMessage(event.target.value)} />
                            </label>
                            <div className="actions">
                                <button className="btn btn-secondary" type="button" onClick={() => setProposalModalJob(null)}>Bekor qilish</button>
                                <button className="btn btn-primary" type="submit">Taklifni yuborish</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </AppLayout>
    )
}

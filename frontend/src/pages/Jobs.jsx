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
    const detailPanelRef = useRef(null)
    const jobsRequestRef = useRef(0)

    const [reportJobId, setReportJobId] = useState(null)
    const [reportReason, setReportReason] = useState("")
    const [reportDetails, setReportDetails] = useState("")
    const [pageSize, setPageSize] = useState(10)
    const [currentPage, setCurrentPage] = useState(1)
    const [totalItems, setTotalItems] = useState(0)
    const [serverTotalPages, setServerTotalPages] = useState(1)
    const [savedSearches, setSavedSearches] = useState([])
    const [selectedSavedSearch, setSelectedSavedSearch] = useState("")
    const [recentlyViewed, setRecentlyViewed] = useState([])
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
    const [proposalSubmitting, setProposalSubmitting] = useState(false)
    const [proposalModalExisting, setProposalModalExisting] = useState(null)
    const [isMobile, setIsMobile] = useState(() => window.matchMedia("(max-width: 760px)").matches)

    const serviceMap = useMemo(
        () => Object.fromEntries(services.map((service) => [String(service.id), service.name])),
        [services]
    )

    const loadJobs = async (requestedPage = currentPage) => {
        const requestId = jobsRequestRef.current + 1
        jobsRequestRef.current = requestId
        setLoading(true)
        try {
            const query = new URLSearchParams()
            query.set("page", String(requestedPage))
            query.set("page_size", String(pageSize))
            if (search.trim()) query.set("search", search.trim())
            if (locationFilter.trim()) query.set("location", locationFilter.trim())
            if (minPrice !== "") query.set("min_price", minPrice)
            if (maxPrice !== "") query.set("max_price", maxPrice)
            if (timeFilter !== "all") query.set("time_filter", timeFilter)
            if (savedOnly) query.set("saved_only", "1")
            const selectedIds = services
                .filter((service) => selectedServices.includes(String(service.name).trim()))
                .map((service) => Number(service.id))
                .filter((id) => Number.isFinite(id))
            if (selectedIds.length) query.set("service_ids", [...new Set(selectedIds)].join(","))

            const jobResult = await api("/jobs?" + query.toString(), { token })
            if (requestId !== jobsRequestRef.current) return
            if (jobResult?.items && Array.isArray(jobResult.items)) {
                setJobs(jobResult.items)
                setTotalItems(Number(jobResult.pagination?.total || 0))
                setServerTotalPages(Math.max(1, Number(jobResult.pagination?.total_pages || 1)))
                const returnedPage = Number(jobResult.pagination?.page || requestedPage)
                if (returnedPage !== requestedPage) setCurrentPage(returnedPage)
            } else if (Array.isArray(jobResult)) {
                setJobs(jobResult)
                setTotalItems(jobResult.length)
                setServerTotalPages(Math.max(1, Math.ceil(jobResult.length / pageSize)))
            } else if (jobResult?.msg) {
                setNoticeType("warn")
                setNotice(jobResult.msg)
            }
        } catch {
            setNoticeType("warn")
            setNotice("Ishlarni yuklashda xatolik yuz berdi.")
        } finally {
            if (requestId === jobsRequestRef.current) setLoading(false)
        }
    }

    const loadSupportingData = async () => {
        try {
            const [serviceResult, profileResult, favoriteResult, savedResult, recentResult] = await Promise.all([
                api("/services", { token }),
                api("/profile", { token }),
                api("/favorites?target_type=job", { token }),
                api("/saved-searches", { token }),
                api("/recently-viewed", { token })
            ])
            if (Array.isArray(serviceResult)) setServices(serviceResult)
            if (Array.isArray(favoriteResult)) {
                setFavoriteJobIds(
                    favoriteResult
                        .filter((item) => item.target_type === "job")
                        .map((item) => Number(item.target_id))
                        .filter((id) => Number.isFinite(id))
                )
            }
            if (Array.isArray(savedResult)) setSavedSearches(savedResult)
            if (Array.isArray(recentResult)) setRecentlyViewed(recentResult)
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
            setNotice("Profil va qo‘shimcha ma’lumotlarni yuklashda xatolik yuz berdi.")
        }
    }

    useEffect(() => {
        loadSupportingData()
    }, [])

    useEffect(() => {
        const mediaQuery = window.matchMedia("(max-width: 760px)")
        const handleChange = (event) => setIsMobile(event.matches)
        setIsMobile(mediaQuery.matches)
        mediaQuery.addEventListener("change", handleChange)
        return () => mediaQuery.removeEventListener("change", handleChange)
    }, [])

    useEffect(() => {
        const isDetailOpen = isMobile && Boolean(selectedJob?.id)
        if (!isDetailOpen) return undefined

        const handleEscape = (event) => {
            if (event.key === "Escape") {
                setSelectedJob(null)
                setJobDetails(null)
                setProposals([])
            }
        }
        document.addEventListener("keydown", handleEscape)

        return () => {
            document.removeEventListener("keydown", handleEscape)
        }
    }, [isMobile, selectedJob?.id])

    useEffect(() => {
        if (!isMobile || !selectedJob?.id || !detailPanelRef.current) return
        detailPanelRef.current.scrollTop = 0
    }, [isMobile, selectedJob?.id])

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

    const filtered = jobs

    const recommendationData = useMemo(() => {
        const normalizedSkills = profileSkills.map((skill) => skill.toLowerCase().trim()).filter(Boolean)
        const scored = filtered.map((job) => {
            const jobServices = String(job.service_name || serviceMap[String(job.service_id)] || "").split(",").map((name) => name.trim().toLowerCase()).filter(Boolean)
            const jobText = (job.title || "") + " " + (job.description || "") + " " + jobServices.join(" ")
            let score = 0
            const matchedSkills = []
            normalizedSkills.forEach((skill) => {
                if (jobServices.some((service) => service === skill)) { score += 100; matchedSkills.push(skill) }
                else if (jobServices.some((service) => service.includes(skill) || skill.includes(service))) { score += 60; matchedSkills.push(skill) }
                else if (jobText.toLowerCase().includes(skill)) { score += 25; matchedSkills.push(skill) }
            })
            return { job, score, matchedSkills }
        })
        scored.sort((a, b) => b.score - a.score || new Date(String(b.job.created_at || "").replace(" ", "T")).getTime() - new Date(String(a.job.created_at || "").replace(" ", "T")).getTime())
        return { recommended: scored.filter((item) => item.score > 0).slice(0, 6), ranked: scored }
    }, [filtered, profileSkills, serviceMap])

    const totalPages = serverTotalPages
    const pagedRanked = recommendationData.ranked

    useEffect(() => {
        const timer = setTimeout(() => {
            if (currentPage !== 1) {
                setCurrentPage(1)
                return
            }
            loadJobs(1)
        }, 250)
        return () => clearTimeout(timer)
    }, [search, selectedServices, minPrice, maxPrice, timeFilter, locationFilter, savedOnly, pageSize, currentPage])

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
        if (job?.id) {
            api("/recently-viewed/" + job.id, { method: "POST", token }).then(() => {
                setRecentlyViewed((items) => [{
                    job_id: job.id, viewed_at: new Date().toISOString(), title: job.title, price: job.price,
                    currency: job.currency, location: job.location, status: job.status, user_id: job.user_id,
                    worker_id: job.worker_id, created_at: job.created_at
                }, ...items.filter((item) => Number(item.job_id) !== Number(job.id))].slice(0, 20))
            })
        }
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


    useEffect(() => {
        if (!isMobile && !selectedJob?.id && pagedRanked.length > 0) {
            setSelectedJob(pagedRanked[0].job)
        }
    }, [pagedRanked, selectedJob?.id, isMobile])

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
    const saveCurrentSearch = async () => {
        if (!hasSearchOrFilters) { setNoticeType("warn"); setNotice("Avval qidiruv yoki kamida bitta filtr tanlang."); return }
        const name = window.prompt("Saqlangan qidiruv nomi:")
        if (!name?.trim()) return
        const selectedIds = services.filter((service) => selectedServices.includes(String(service.name).trim())).map((service) => Number(service.id)).filter((id) => Number.isFinite(id))
        const result = await api("/saved-searches", {
            method: "POST", token,
            body: { name: name.trim(), filters: { search: search.trim(), service_ids: [...new Set(selectedIds)], min_price: minPrice, max_price: maxPrice, time_filter: timeFilter, location: locationFilter.trim() } }
        })
        if (result?.ok) {
            setNoticeType("ok"); setNotice("Qidiruv saqlandi.")
            const refreshed = await api("/saved-searches", { token })
            if (Array.isArray(refreshed)) setSavedSearches(refreshed)
        } else { setNoticeType("warn"); setNotice(result?.msg || "Qidiruvni saqlab bo‘lmadi.") }
    }

    const applySavedSearch = (saved) => {
        if (!saved?.filters) return
        const filters = saved.filters
        setSearch(filters.search || "")
        const ids = Array.isArray(filters.service_ids) ? filters.service_ids.map(Number) : []
        const names = services.filter((service) => ids.includes(Number(service.id))).map((service) => String(service.name).trim())
        setSelectedServices([...new Set(names)])
        setMinPrice(filters.min_price ?? "")
        setMaxPrice(filters.max_price ?? "")
        setTimeFilter(filters.time_filter || "all")
        setLocationFilter(filters.location || "")
        setSavedOnly(false)
        setSelectedSavedSearch(String(saved.id))
        setCurrentPage(1)
    }

    const removeSavedSearch = async (id) => {
        const result = await api("/saved-searches/" + id, { method: "DELETE", token })
        if (result?.ok) {
            setSavedSearches((items) => items.filter((item) => Number(item.id) !== Number(id)))
            if (String(selectedSavedSearch) === String(id)) setSelectedSavedSearch("")
            setNoticeType("ok"); setNotice("Saqlangan qidiruv o‘chirildi.")
        } else { setNoticeType("warn"); setNotice(result?.msg || "Saqlangan qidiruvni o‘chirib bo‘lmadi.") }
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
            await loadJobs(currentPage)
            const refreshed = await api("/jobs/" + job.id, { token })
            if (refreshed?.id) setJobDetails(refreshed)
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
            await loadJobs(currentPage)
            const refreshed = await api("/jobs/" + jobId, { token })
            if (refreshed?.id) setJobDetails(refreshed)
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
        await loadJobs(currentPage)
        const refreshed = await api("/jobs/" + job.id, { token })
        if (refreshed?.id) setJobDetails(refreshed)
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


    const openProposalModal = async (job) => {
        if (!job?.id || String(job.user_id) === String(user?.id) || job.worker_id != null || String(job.status).toLowerCase() !== "active") return
        setProposalModalJob(job)
        setProposalModalExisting(null)
        setProposalPrice(String(job.price ?? ""))
        setProposalDeadline("")
        setProposalMessage("")
        const result = await api(`/jobs/${job.id}/proposals`, { token })
        const ownProposal = Array.isArray(result)
            ? result.find((item) => String(item.worker_id) === String(user?.id) && item.status === "pending")
            : null
        if (ownProposal) {
            setProposalModalExisting(ownProposal)
            setProposalPrice(String(ownProposal.price ?? job.price ?? ""))
            setProposalDeadline(ownProposal.deadline || "")
            setProposalMessage(ownProposal.message || "")
        }
    }
    const submitProposal = async (event) => {
        event.preventDefault()
        if (!proposalModalJob || proposalSubmitting) return

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

        const existingProposal = proposalModalExisting

        setProposalSubmitting(true)
        try {
            const result = existingProposal
                ? await api(`/proposals/${existingProposal.id}`, {
                    method: "PATCH",
                    token,
                    body: {
                        action: "edit",
                        price,
                        deadline: proposalDeadline.trim(),
                        message: proposalMessage.trim()
                    }
                })
                : await api(`/jobs/${proposalModalJob.id}/proposals`, {
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
                setNotice(existingProposal ? "Taklif yangilandi." : "Taklif muvaffaqiyatli yuborildi.")
                const jobId = proposalModalJob.id
                setProposalModalJob(null)
                setProposalModalExisting(null)
                const refreshed = await api(`/jobs/${jobId}/proposals`, { token })
                setProposals(Array.isArray(refreshed) ? refreshed : [])
                await loadJobs(currentPage)
            } else {
                setNoticeType("warn")
                setNotice(result?.msg || "Taklif yuborilmadi.")
            }
        } finally {
            setProposalSubmitting(false)
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
            await loadJobs(currentPage)
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
            await loadJobs(currentPage)
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
    const myProposal = proposals.find((item) => String(item.job_id) === String(activeJobDetails?.id) && String(item.worker_id) === String(user?.id) && item.status === "pending")
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
            <div className="jobs-page-shell">
            <div className="card jobs-controls-card" style={{ marginBottom: 18 }}>
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
                                                            <div className="jobs-saved-only-field">
                                            <span>Saqlangan ishlar</span>
                                            <label className="jobs-checkbox-row">
                                                <input type="checkbox" checked={savedOnly} onChange={(e) => setSavedOnly(e.target.checked)} />
                                                <span>Faqat ★ bilan saqlangan ishlarni ko‘rsatish</span>
                                            </label>
                                        </div>
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
                        <button className="btn btn-secondary" onClick={() => loadJobs(currentPage)} disabled={loading}>{loading ? "Yangilanmoqda..." : "Yangilash"}</button>
                        <button className="btn btn-primary" onClick={() => navigate("/create")}>Ish yaratish</button>
                    </div>
                </div>
                <div className="jobs-filter-note">
                    <span><strong>{totalItems}</strong> ta ish topildi</span>
                    {activeFilterCount > 0 && <span className="jobs-active-filter-label">{activeFilterCount} ta filtr faol</span>}
                    {hasSearchOrFilters && <button type="button" className="jobs-clear-inline" onClick={clearAllFilters}>Hammasini tozalash</button>}
                </div>
                {notice && <div className={"notice " + (noticeType === "ok" ? "ok" : "warn")} style={{ marginTop: 14 }}>{notice}</div>}
                <div className="jobs-saved-search-bar">
                    <div style={{ minWidth: 0, flex: 1 }}>
                        <span className="helper">SAQLANGAN QIDIRUVLAR</span>
                        <select className="input" value={selectedSavedSearch} onChange={(event) => {
                            const saved = savedSearches.find((item) => String(item.id) === event.target.value)
                            if (saved) applySavedSearch(saved)
                            else setSelectedSavedSearch("")
                        }}>
                            <option value="">Qidiruvni tanlang</option>
                            {savedSearches.map((saved) => <option key={saved.id} value={saved.id}>{saved.name}</option>)}
                        </select>
                    </div>
                    <div className="actions">
                        <button type="button" className="btn btn-secondary" onClick={saveCurrentSearch}>Qidiruvni saqlash</button>
                        {selectedSavedSearch && <button type="button" className="btn btn-secondary" onClick={() => removeSavedSearch(selectedSavedSearch)}>O‘chirish</button>}
                    </div>
                </div>
                {recentlyViewed.length > 0 && (
                    <div className="jobs-recently-viewed">
                        <div>
                            <span className="helper">Yaqinda ko‘rilganlar</span>
                            <p className="muted">Oxirgi ko‘rgan ishlaringizga tez qayting.</p>
                        </div>
                        <div className="jobs-recent-list">
                            {recentlyViewed.slice(0, 6).map((item) => (
                                <button key={item.job_id} type="button" className="jobs-recent-item" onClick={() => {
                                    const found = jobs.find((job) => Number(job.id) === Number(item.job_id))
                                    if (found) selectJob(found)
                                    else navigate("/jobs")
                                }}>
                                    <strong>{item.title || "Ish"}</strong>
                                    <span>{item.location || "Joylashuv ko‘rsatilmagan"}</span>
                                </button>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            <div className="jobs-content-layout">
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
                                    <div className="job-grid">
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
                                                {String(job.status || "").toLowerCase() === "active" && String(job.user_id) !== String(user?.id) && job.worker_id == null && (
                                                    <div className="actions" style={{ marginTop: 12 }}>
                                                        <button
                                                            type="button"
                                                            className="btn btn-primary"
                                                            onClick={(event) => {
                                                                event.stopPropagation()
                                                                openProposalModal(job)
                                                            }}
                                                        >
                                                            Taklif yuborish
                                                        </button>
                                                        {Number(job.proposal_count || 0) > 0 && <span className="muted" style={{ alignSelf: "center" }}>{job.proposal_count} ta taklif mavjud</span>}
                                                    </div>
                                                )}
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
                                <div className="job-grid jobs-results-grid">
                                    {pagedRanked.map(({ job }) => (
                                        <article
                                            className={`card job-card ${selectedJob?.id === job.id ? "selected" : ""}`}
                                            key={job.id}
                                            onClick={() => selectJob(job)}
                                            style={{ cursor: "pointer" }}
                                        >
                                            <div className="jobs-job-card-head">
                                                <h3 className="job-title" style={{ margin: 0 }}>{job.title}</h3>
                                                <button
                                                    type="button"
                                                    className="btn btn-secondary jobs-favorite-button"
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

                                            {String(job.status || "").toLowerCase() === "active" && String(job.user_id) !== String(user?.id) && job.worker_id == null && (
                                                <div className="actions" style={{ marginTop: 12 }}>
                                                    <button
                                                        type="button"
                                                        className="btn btn-primary"
                                                        onClick={(event) => {
                                                            event.stopPropagation()
                                                            openProposalModal(job)
                                                        }}
                                                    >
                                                        Taklif yuborish
                                                    </button>
                                                    <span className="muted" style={{ alignSelf: "center" }}>
                                                        {Number(job.proposal_count || 0) > 0 ? String(job.proposal_count) + " ta taklif mavjud" : "Birinchi taklifni yuboring"}
                                                    </span>
                                                </div>
                                            )}
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
                                {totalItems > 0 && (
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
                                        <div className="jobs-page-summary">{totalItems} ta ish • {currentPage} / {totalPages} sahifa</div>
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

                {isMobile && activeJobDetails && (
                    <div
                        className="jobs-detail-backdrop"
                        aria-hidden="true"
                        onClick={() => { setSelectedJob(null); setJobDetails(null); setProposals([]) }}
                    />
                )}
                <aside
                    ref={detailPanelRef}
                    className={"card jobs-detail-panel " + (activeJobDetails ? "has-active-job" : "")}
                    role={isMobile && activeJobDetails ? "dialog" : undefined}
                    aria-modal={isMobile && activeJobDetails ? "true" : undefined}
                    aria-label={isMobile && activeJobDetails ? "Ish tafsilotlari" : undefined}
                >
                    <div className="dashboard-panel-head jobs-detail-panel-head">
                        <div>
                            <span className="profile-eyebrow">ISH MA'LUMOTI</span>
                            <h2>To‘liq ma’lumot</h2>
                            <p>Tanlangan jobning barcha tafsilotlari va amallari.</p>
                        </div>
                        <button
                            type="button"
                            className="jobs-detail-close"
                            onClick={() => { setSelectedJob(null); setJobDetails(null); setProposals([]) }}
                            aria-label="Ish tafsilotlarini yopish"
                        >×</button>
                    </div>

                    {!activeJobDetails ? (
                        <div className="empty-state">Jobni tanlang.</div>
                    ) : (
                        <div className="dashboard-job-detail-body">
                            {jobDetailsLoading && (
                                <div className="jobs-detail-loading-note">Yangilangan ma’lumotlar yuklanmoqda...</div>
                            )}
                            <div>
                                <span className="helper">ISH NOMI</span>
                                <div className="jobs-detail-title-row">
                                    <h2 className="dashboard-job-detail-title">{activeJobDetails.title}</h2>
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
                                                    <div className="jobs-proposal-head">
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
                                <div className="actions jobs-detail-actions" style={{ marginTop: 10 }}>
                                    {detailIsParticipant && (
                                        <button
                                            className="btn btn-secondary"
                                            onClick={() => navigate(`/chat/${activeJobDetails.id}`, { state: { job: activeJobDetails } })}
                                        >
                                            Suhbat
                                        </button>
                                    )}

                                    {detailCanFinish && detailIsParticipant && (
                                        <button
                                            className="btn btn-success"
                                            disabled={actionJobId === activeJobDetails.id}
                                            onClick={() => detailIsWorker ? finishJobWorker(activeJobDetails.id) : finishJobSeeker(activeJobDetails)}
                                        >
                                            {actionJobId === activeJobDetails.id ? "Yakunlanmoqda..." : "Ishni yakunlash"}
                                        </button>
                                    )}

                                    {detailIsMyJob && detailStatus === "payment_pending" && (
                                        <button
                                            className="btn btn-primary"
                                            onClick={() => navigate(`/payments/job/${activeJobDetails.id}`)}
                                        >
                                            To‘lovni amalga oshirish
                                        </button>
                                    )}

                                    {detailIsMyJob && detailCanFinish && (
                                        <button
                                            className="btn btn-warn"
                                            onClick={() => cancelWorker(activeJobDetails)}
                                        >
                                            Ishchini o‘zgartirish
                                        </button>
                                    )}

                                    {detailIsParticipant && detailStatus === "finished" && (
                                        <button
                                            className="btn btn-secondary"
                                            onClick={() => navigate(`/rating/${activeJobDetails.id}`, { state: { job: activeJobDetails } })}
                                        >
                                            Baho berish
                                        </button>
                                    )}

                                    {detailCanPropose && (
                                        <button
                                            className="btn btn-primary"
                                            onClick={() => openProposalModal(activeJobDetails)}
                                        >
                                            {myProposal?.status === "pending" ? "Taklifni tahrirlash" : "Taklif yuborish"}
                                        </button>
                                    )}

                                    {detailCanReport && (
                                        <button
                                            className="btn btn-secondary"
                                            onClick={() => setReportJobId(reportJobId === activeJobDetails.id ? null : activeJobDetails.id)}
                                        >
                                            Shikoyat qilish
                                        </button>
                                    )}

                                    {detailIsWorker && detailStatus === "payment_pending" && (
                                        <span className="chip job-accepted-chip">Ish egasining to‘lovi kutilmoqda</span>
                                    )}
                                    {detailIsWorker && detailStatus === "accepted" && (
                                        <span className="chip job-accepted-chip">Siz qabul qilgansiz</span>
                                    )}
                                    {detailIsParticipant && detailStatus === "accepted" && (activeJobDetails.owner_finished || activeJobDetails.worker_finished) && (
                                        <span className="chip">Ikkinchi tomonning yakunlashini kutmoqda</span>
                                    )}
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
                                <span className="profile-eyebrow">{proposalModalExisting ? "TAKLIFNI TAHRIRLASH" : "TAKLIF YUBORISH"}</span>
                                <h2>{proposalModalJob.title}</h2>
                                <p className="muted">{proposalModalExisting ? "Taklifingizdagi narx, muddat yoki izohni yangilang." : "Narxingiz, bajarish muddatingiz va qisqa izohni kiriting."}</p>
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
                                <button className="btn btn-primary" type="submit" disabled={proposalSubmitting}>
                                    {proposalSubmitting ? "Saqlanmoqda..." : proposalModalExisting ? "Taklifni yangilash" : "Taklifni yuborish"}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
            </div>
        </AppLayout>
    )
}

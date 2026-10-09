import { useEffect, useMemo, useState } from "react"
import { Navigate } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"
import { formatTimeAgo } from "../utils/time"

const PAGE_SIZE = 10

const money = (value) => Number(value || 0).toLocaleString("uz-UZ")
const shortName = (item) => (item.first_name || item.last_name ? ((item.first_name || "") + " " + (item.last_name || "")).trim() : "—")
const statusLabel = {
    active: "Faol",
    payment_pending: "To‘lov kutilmoqda",
    accepted: "Qabul qilingan",
    pending_finish: "Tasdiqlash kutilmoqda",
    finished: "Yakunlangan",
    blocked: "Bloklangan",
    open: "Ochiq",
    reviewing: "Ko‘rib chiqilmoqda",
    resolved: "Hal qilindi",
    rejected: "Rad etildi"
}
const blockLabels = {
    full: "To‘liq blok",
    chat: "Chat blok",
    job_creation: "Ish yaratish blok",
    job_accept: "Ish qabul qilish blok",
    proposal: "Taklif yuborish blok",
    rating: "Baholash blok",
    withdrawal: "Mablag‘ yechish blok"
}

const actionLabel = {
    commission_update: "Komissiya o‘zgarishi",
    user_role_update: "Rol o‘zgarishi",
    user_update: "Foydalanuvchi tahriri",
    user_block: "Foydalanuvchi bloklandi",
    user_unblock: "Foydalanuvchi blokdan chiqarildi",
    user_delete: "Foydalanuvchi o‘chirildi",
    job_status_update: "Ish holati o‘zgarishi",
    job_delete: "Ish o‘chirildi",
    service_create: "Xizmat yaratildi",
    service_delete: "Xizmat o‘chirildi",
    rating_delete: "Baho o‘chirildi",
    report_status_update: "Shikoyat holati o‘zgardi",
    wallet_topup: "Test balansi qo‘shildi",
    user_block_created: "Block qo‘yildi",
    user_block_lifted: "Block olib tashlandi",
    appeal_created: "Yangi appeal",
    appeal_reviewed: "Appeal ko‘rib chiqildi"
}

function Pager({ page, pages, total, onChange }) {
    if (pages <= 1) return null
    return (
        <div className="admin-pager">
            <span>{total} ta natija</span>
            <div className="admin-pager-controls">
                <button className="btn btn-secondary admin-small-btn" disabled={page <= 1} onClick={() => onChange(page - 1)}>←</button>
                <strong>{page} / {pages}</strong>
                <button className="btn btn-secondary admin-small-btn" disabled={page >= pages} onClick={() => onChange(page + 1)}>→</button>
            </div>
        </div>
    )
}

export default function Admin() {
    const token = localStorage.getItem("token")
    const user = JSON.parse(localStorage.getItem("user") || "null")

    const [data, setData] = useState(null)
    const [walletSummary, setWalletSummary] = useState(null)
    const [analytics, setAnalytics] = useState(null)
    const [finance, setFinance] = useState(null)
    const [adminBlocks, setAdminBlocks] = useState([])
    const [adminAppeals, setAdminAppeals] = useState([])
    const [adminDisputes, setAdminDisputes] = useState([])
    const [audit, setAudit] = useState(null)
    const [moderatingUser, setModeratingUser] = useState(null)
    const [userBlocks, setUserBlocks] = useState([])
    const [blockForm, setBlockForm] = useState({ block_type: "chat", duration_minutes: "1440", reason: "" })
    const [reviewingAppeal, setReviewingAppeal] = useState(null)
    const [appealReviewForm, setAppealReviewForm] = useState({ status: "reviewing", admin_response: "" })
    const [reviewingDispute, setReviewingDispute] = useState(null)
    const [disputeReviewForm, setDisputeReviewForm] = useState({ status: "reviewing", admin_response: "" })
    const [auditPage, setAuditPage] = useState(1)

    const [notice, setNotice] = useState("")
    const [noticeType, setNoticeType] = useState("ok")
    const [tab, setTab] = useState("dashboard")
    const [globalSearch, setGlobalSearch] = useState("")
    const [searchResults, setSearchResults] = useState(null)
    const [appealQuery, setAppealQuery] = useState("")
    const [appealStatus, setAppealStatus] = useState("all")
    const [appealPage, setAppealPage] = useState(1)
    const [disputeQuery, setDisputeQuery] = useState("")
    const [disputeStatus, setDisputeStatus] = useState("open")
    const [blockQuery, setBlockQuery] = useState("")
    const [blockStatus, setBlockStatus] = useState("active")
    const [blockPage, setBlockPage] = useState(1)

    const [userQuery, setUserQuery] = useState("")
    const [userRole, setUserRole] = useState("all")
    const [userBlocked, setUserBlocked] = useState("all")
    const [userPage, setUserPage] = useState(1)

    const [jobQuery, setJobQuery] = useState("")
    const [jobStatus, setJobStatus] = useState("all")
    const [jobPage, setJobPage] = useState(1)

    const [reportQuery, setReportQuery] = useState("")
    const [reportStatus, setReportStatus] = useState("all")
    const [reportPage, setReportPage] = useState(1)

    const [serviceQuery, setServiceQuery] = useState("")
    const [servicePage, setServicePage] = useState(1)

    const [ratingQuery, setRatingQuery] = useState("")
    const [ratingPage, setRatingPage] = useState(1)

    const [serviceName, setServiceName] = useState("")
    const [serviceParent, setServiceParent] = useState("")

    const [editingUser, setEditingUser] = useState(null)
    const [userForm, setUserForm] = useState({
        username: "", email: "", first_name: "", last_name: "", birthday: "", bio: "", skills: "", password: ""
    })
    const [commissionPercent, setCommissionPercent] = useState("10")

    const load = async () => {
        setNotice("")
        const [result, wallet, stats, financeData, blocks, appeals, disputesData] = await Promise.all([
            api("/admin/overview", { token }),
            api("/admin/wallet/summary", { token }),
            api("/admin/analytics", { token }),
            api("/admin/finance", { token }),
            api("/admin/blocks?status=active", { token }),
            api("/admin/appeals", { token }),
            api("/admin/disputes", { token })
        ])
        if (result?.ok) {
            setData(result)
            setCommissionPercent(String(result.settings?.commission_percent ?? 10))
            if (wallet?.ok) setWalletSummary(wallet)
            if (stats?.ok) setAnalytics(stats)
            if (financeData?.ok) setFinance(financeData)
            if (blocks?.ok) setAdminBlocks(blocks.items || [])
            if (appeals?.ok) setAdminAppeals(appeals.items || [])
            if (disputesData?.ok) setAdminDisputes(Array.isArray(disputesData) ? disputesData : (disputesData.items || []))
        } else {
            setNoticeType("warn")
            setNotice(result?.msg || "Admin ma'lumotlarini yuklab bo'lmadi.")
        }
    }

    const loadAudit = async (page = auditPage, q = "") => {
        const result = await api("/admin/audit-log?page=" + page + "&limit=10&q=" + encodeURIComponent(q), { token })
        if (result?.ok) setAudit(result)
    }

    useEffect(() => {
        if (!token || user?.role !== "admin") return
        load()
        loadAudit(1)
    }, [token, user?.role])

    useEffect(() => {
        if (!token || user?.role !== "admin") return
        if (!globalSearch.trim()) {
            setSearchResults(null)
            return
        }
        const timer = setTimeout(async () => {
            const result = await api("/admin/search?q=" + encodeURIComponent(globalSearch.trim()), { token })
            if (result?.ok) setSearchResults(result)
        }, 260)
        return () => clearTimeout(timer)
    }, [globalSearch, token, user?.role])

    const action = async (path, options = {}, successMessage = "O‘zgarish saqlandi.") => {
        setNotice("")
        setNoticeType("ok")
        const result = await api(path, { token, ...options })
        if (!result?.ok) {
            setNoticeType("warn")
            setNotice(result?.msg || "Amal bajarilmadi.")
            return false
        }
        setNotice(result?.msg || successMessage)
        await load()
        await loadAudit(1)
        return true
    }

    const saveCommission = async (event) => {
        event.preventDefault()
        const value = Number(commissionPercent)
        if (!Number.isFinite(value) || value < 0 || value > 100) {
            setNoticeType("warn")
            setNotice("Komissiya 0% dan 100% gacha bo‘lishi kerak.")
            return
        }
        await action("/admin/settings/commission", {
            method: "PATCH",
            body: { commission_percent: value }
        }, "Platforma komissiyasi yangilandi.")
    }

    const changeRole = async (item, role) => {
        if (role === item.role) return
        await action("/admin/user-role", {
            method: "PATCH",
            body: { user_id: item.id, role }
        }, "Foydalanuvchi roli o‘zgartirildi.")
    }

    const openModeration = async (item) => {
        setModeratingUser(item)
        setBlockForm({ block_type: "chat", duration_minutes: "1440", reason: "" })
        const result = await api("/admin/user/" + item.id + "/blocks", { token })
        if (result?.ok) setUserBlocks(result.blocks || [])
        else setUserBlocks([])
    }

    const createUserBlock = async (event) => {
        event.preventDefault()
        if (!moderatingUser) return
        const result = await action("/admin/user/" + moderatingUser.id + "/block", {
            method: "POST",
            body: {
                block_type: blockForm.block_type,
                duration_minutes: blockForm.duration_minutes || null,
                reason: blockForm.reason.trim()
            }
        }, "Block qo‘yildi.")
        if (result) {
            setBlockForm({ block_type: "chat", duration_minutes: "1440", reason: "" })
            const refreshed = await api("/admin/user/" + moderatingUser.id + "/blocks", { token })
            if (refreshed?.ok) setUserBlocks(refreshed.blocks || [])
        }
    }

    const liftBlock = async (block) => {
        if (!window.confirm("#" + block.id + " blockni olib tashlashni tasdiqlaysizmi?")) return
        const ok = await action("/admin/block/" + block.id, { method: "PATCH", body: { action: "lift" } }, "Block olib tashlandi.")
        if (ok && moderatingUser) {
            const refreshed = await api("/admin/user/" + moderatingUser.id + "/blocks", { token })
            if (refreshed?.ok) setUserBlocks(refreshed.blocks || [])
        }
    }

    const openAppealReview = (item) => {
        setReviewingAppeal(item)
        setAppealReviewForm({ status: item.status === "open" ? "reviewing" : item.status, admin_response: item.admin_response || "" })
    }

    const submitAppealReview = async (event) => {
        event.preventDefault()
        if (!reviewingAppeal) return
        const ok = await action("/admin/appeal/" + reviewingAppeal.id, {
            method: "PATCH",
            body: appealReviewForm
        }, "Appeal yangilandi.")
        if (ok) setReviewingAppeal(null)
    }

    const openDisputeReview = (item) => {
        setReviewingDispute(item)
        setDisputeReviewForm({
            status: item.status === "open" ? "reviewing" : item.status,
            admin_response: item.admin_response || ""
        })
    }

    const submitDisputeReview = async (event) => {
        event.preventDefault()
        if (!reviewingDispute) return
        const ok = await action("/admin/disputes/" + reviewingDispute.id, {
            method: "PATCH",
            body: disputeReviewForm
        }, "Nizo holati yangilandi.")
        if (ok) setReviewingDispute(null)
    }

    const editUser = (item) => {
        setEditingUser(item)
        setUserForm({
            username: item.username || "",
            email: item.email || "",
            first_name: item.first_name || "",
            last_name: item.last_name || "",
            birthday: item.birthday || "",
            bio: item.bio || "",
            skills: item.skills || "",
            password: ""
        })
    }

    const saveUser = async (event) => {
        event.preventDefault()
        if (!editingUser) return
        const ok = await action("/admin/user/" + editingUser.id, { method: "PATCH", body: userForm }, "Foydalanuvchi ma'lumotlari yangilandi.")
        if (ok) {
            if (editingUser.id === user.id) {
                const safe = { ...userForm }
                delete safe.password
                localStorage.setItem("user", JSON.stringify({ ...user, ...safe }))
            }
            setEditingUser(null)
        }
    }

    const addTestBalance = async (item) => {
        const value = window.prompt("@" + item.username + " hisobiga qancha test UZS qo‘shilsin?")
        if (value === null) return
        const amount = Number(value)
        if (!Number.isFinite(amount) || amount <= 0) {
            setNoticeType("warn")
            setNotice("Musbat summa kiriting.")
            return
        }
        await action("/admin/wallet/" + item.id, { method: "POST", body: { amount } }, "Test balansi qo‘shildi.")
    }

    const deleteUser = async (item) => {
        if (!window.confirm("@" + item.username + " foydalanuvchisini va unga bog‘liq ma'lumotlarni o‘chirishni tasdiqlaysizmi?")) return
        await action("/admin/user/" + item.id, { method: "DELETE" }, "Foydalanuvchi o‘chirildi.")
    }

    const updateJobStatus = async (item, status) => {
        if (status === item.status) return
        await action("/admin/job/" + item.id, { method: "PATCH", body: { status } }, "Ish holati o‘zgartirildi.")
    }

    const deleteJob = async (item) => {
        if (!window.confirm("#" + item.id + " — " + item.title + " jobini o‘chirishni tasdiqlaysizmi?")) return
        await action("/admin/job/" + item.id, { method: "DELETE" }, "Ish o‘chirildi.")
    }

    const createService = async (event) => {
        event.preventDefault()
        if (!serviceName.trim()) {
            setNoticeType("warn")
            setNotice("Xizmat nomini kiriting.")
            return
        }
        const ok = await action("/admin/service", {
            method: "POST",
            body: { name: serviceName.trim(), parent_id: serviceParent || null }
        }, "Xizmat qo‘shildi.")
        if (ok) {
            setServiceName("")
            setServiceParent("")
        }
    }

    const deleteService = async (item) => {
        if (!window.confirm('"' + item.name + '" xizmatini o‘chirishni tasdiqlaysizmi?')) return
        await action("/admin/service/" + item.id, { method: "DELETE" }, "Xizmat o‘chirildi.")
    }

    const deleteRating = async (item) => {
        if (!window.confirm("#" + item.id + " ratingni o‘chirishni tasdiqlaysizmi?")) return
        await action("/admin/rating/" + item.id, { method: "DELETE" }, "Baho o‘chirildi.")
    }

    const updateReport = async (item, status) => {
        if (status === item.status) return
        await action("/admin/report/" + item.id, { method: "PATCH", body: { status } }, "Shikoyat holati yangilandi.")
    }

    const openReportAttachment = async (report) => {
        if (!report?.id || !report.attachment_url) return
        try {
            const apiBase = (import.meta.env.VITE_API_URL || "http://localhost:5000").replace(/\/$/, "")
            const response = await fetch(apiBase + "/admin/report/" + report.id + "/attachment", {
                headers: { Authorization: "Bearer " + token }
            })
            if (!response.ok) throw new Error("Biriktirilgan faylni ochib bo‘lmadi")
            const blob = await response.blob()
            const objectUrl = URL.createObjectURL(blob)
            window.open(objectUrl, "_blank", "noopener,noreferrer")
            setTimeout(() => URL.revokeObjectURL(objectUrl), 60000)
        } catch (error) {
            setNoticeType("warn")
            setNotice(error.message || "Faylni ochib bo‘lmadi.")
        }
    }

    const users = useMemo(() => {
        const q = userQuery.trim().toLowerCase()
        const items = (data?.users || []).filter((item) => {
            const text = [item.username, item.email, item.first_name, item.last_name].join(" ").toLowerCase()
            return (!q || text.includes(q)) &&
                (userRole === "all" || item.role === userRole) &&
                (userBlocked === "all" || (userBlocked === "blocked" ? Number(item.is_blocked || 0) === 1 : Number(item.is_blocked || 0) === 0))
        })
        return { all: items, page: items.slice((userPage - 1) * PAGE_SIZE, userPage * PAGE_SIZE), pages: Math.max(1, Math.ceil(items.length / PAGE_SIZE)) }
    }, [data, userQuery, userRole, userBlocked, userPage])

    const jobs = useMemo(() => {
        const q = jobQuery.trim().toLowerCase()
        const items = (data?.jobs || []).filter((item) => {
            const text = [item.title, item.creator_username, item.worker_username, item.location].join(" ").toLowerCase()
            return (!q || text.includes(q) || String(item.id).includes(q)) && (jobStatus === "all" || item.status === jobStatus)
        })
        return { all: items, page: items.slice((jobPage - 1) * PAGE_SIZE, jobPage * PAGE_SIZE), pages: Math.max(1, Math.ceil(items.length / PAGE_SIZE)) }
    }, [data, jobQuery, jobStatus, jobPage])

    const reports = useMemo(() => {
        const q = reportQuery.trim().toLowerCase()
        const items = (data?.reports || []).filter((item) => {
            const text = [item.reason, item.details, item.reporter_username, item.reported_username].join(" ").toLowerCase()
            return (!q || text.includes(q) || String(item.id).includes(q)) && (reportStatus === "all" || item.status === reportStatus)
        })
        return { all: items, page: items.slice((reportPage - 1) * PAGE_SIZE, reportPage * PAGE_SIZE), pages: Math.max(1, Math.ceil(items.length / PAGE_SIZE)) }
    }, [data, reportQuery, reportStatus, reportPage])

    const services = useMemo(() => {
        const q = serviceQuery.trim().toLowerCase()
        const items = (data?.services || []).filter((item) => !q || [item.name, item.parent_name].join(" ").toLowerCase().includes(q) || String(item.id).includes(q))
        return { all: items, page: items.slice((servicePage - 1) * PAGE_SIZE, servicePage * PAGE_SIZE), pages: Math.max(1, Math.ceil(items.length / PAGE_SIZE)) }
    }, [data, serviceQuery, servicePage])

    const filteredAppeals = useMemo(() => {
        const q = appealQuery.trim().toLowerCase()
        const items = adminAppeals.filter((item) => {
            const text = [item.username, item.appeal_text, item.block_reason, item.block_type].join(" ").toLowerCase()
            return (!q || text.includes(q) || String(item.id).includes(q) || String(item.block_id).includes(q)) &&
                (appealStatus === "all" || item.status === appealStatus)
        })
        return { all: items, page: items.slice((appealPage - 1) * PAGE_SIZE, appealPage * PAGE_SIZE), pages: Math.max(1, Math.ceil(items.length / PAGE_SIZE)) }
    }, [adminAppeals, appealQuery, appealStatus, appealPage])

    const filteredDisputes = useMemo(() => {
        const q = disputeQuery.trim().toLowerCase()
        return adminDisputes.filter((item) => {
            const text = [
                item.id, item.job_id, item.job_title, item.opened_by_username,
                item.against_username, item.category, item.description, item.evidence
            ].join(" ").toLowerCase()
            return (!q || text.includes(q)) && (disputeStatus === "all" || item.status === disputeStatus)
        })
    }, [adminDisputes, disputeQuery, disputeStatus])

    const filteredBlocks = useMemo(() => {
        const q = blockQuery.trim().toLowerCase()
        const items = adminBlocks.filter((item) => {
            const text = [item.username, item.reason, item.block_type, item.block_label].join(" ").toLowerCase()
            return (!q || text.includes(q) || String(item.id).includes(q) || String(item.user_id).includes(q)) &&
                (blockStatus === "all" || (blockStatus === "active" ? item.active : !item.active))
        })
        return { all: items, page: items.slice((blockPage - 1) * PAGE_SIZE, blockPage * PAGE_SIZE), pages: Math.max(1, Math.ceil(items.length / PAGE_SIZE)) }
    }, [adminBlocks, blockQuery, blockStatus, blockPage])

    const ratings = useMemo(() => {
        const q = ratingQuery.trim().toLowerCase()
        const items = (data?.ratings || []).filter((item) => !q || [item.from_username, item.to_username, item.comment].join(" ").toLowerCase().includes(q) || String(item.job_id).includes(q))
        return { all: items, page: items.slice((ratingPage - 1) * PAGE_SIZE, ratingPage * PAGE_SIZE), pages: Math.max(1, Math.ceil(items.length / PAGE_SIZE)) }
    }, [data, ratingQuery, ratingPage])

    useEffect(() => {
        if (userPage > users.pages) setUserPage(users.pages)
    }, [users.pages, userPage])
    useEffect(() => {
        if (jobPage > jobs.pages) setJobPage(jobs.pages)
    }, [jobs.pages, jobPage])
    useEffect(() => {
        if (reportPage > reports.pages) setReportPage(reports.pages)
    }, [reports.pages, reportPage])
    useEffect(() => {
        if (servicePage > services.pages) setServicePage(services.pages)
    }, [services.pages, servicePage])
    useEffect(() => {
        if (ratingPage > ratings.pages) setRatingPage(ratings.pages)
    }, [ratings.pages, ratingPage])
    useEffect(() => {
        if (appealPage > filteredAppeals.pages) setAppealPage(filteredAppeals.pages)
    }, [filteredAppeals.pages, appealPage])
    useEffect(() => {
        if (blockPage > filteredBlocks.pages) setBlockPage(filteredBlocks.pages)
    }, [filteredBlocks.pages, blockPage])

    const serviceTree = useMemo(() => {
        const map = {}
        for (const item of (data?.services || [])) {
            map[item.id] = { ...item, children: [] }
        }
        const roots = []
        Object.values(map).forEach((item) => {
            if (item.parent_id && map[item.parent_id]) map[item.parent_id].children.push(item)
            else roots.push(item)
        })
        const flatten = (items, depth = 0, out = []) => {
            items.sort((a, b) => a.name.localeCompare(b.name))
            items.forEach((item) => {
                out.push({ ...item, depth })
                flatten(item.children, depth + 1, out)
            })
            return out
        }
        return flatten(roots)
    }, [data])

    const navTabs = [
        ["dashboard", "Dashboard"],
        ["users", "Foydalanuvchilar"],
        ["jobs", "Ishlar"],
        ["services", "Xizmatlar"],
        ["reports", "Shikoyatlar"],
        ["disputes", "Nizolar"],
        ["blocks", "Blocks"],
        ["appeals", "Appeals"],
        ["finance", "Moliya"],
        ["ratings", "Baholar"],
        ["audit", "Audit log"],
        ["settings", "Sozlamalar"]
    ]

    const stats = data?.stats || {}
    const paymentTotal = (analytics?.payments || []).reduce((sum, item) => sum + Number(item.amount || 0), 0)
    const completedPayments = (analytics?.payments || []).find((item) => item.status === "released")

    if (!token) return <Navigate to="/login" replace />
    if (user?.role !== "admin") return <Navigate to="/" replace />

    return (
        <AppLayout title="Admin 2.0" subtitle="FinJob platformasini markazdan boshqaring.">
            {notice && <div className={"notice " + (noticeType === "ok" ? "ok" : "warn")} style={{ marginBottom: 16 }}>{notice}</div>}

            <div className="admin-search-panel card">
                <div>
                    <span className="admin-search-eyebrow">GLOBAL SEARCH</span>
                    <strong>Foydalanuvchi, ish, xizmat yoki shikoyatni toping</strong>
                </div>
                <input className="input" value={globalSearch} onChange={(e) => setGlobalSearch(e.target.value)} placeholder="Masalan: allanazar, backend, #42..." />
                {searchResults && globalSearch.trim() && (
                    <div className="admin-search-results">
                        {searchResults.users?.length > 0 && <div><span>Foydalanuvchilar</span>{searchResults.users.map((item) => <button key={item.id} onClick={() => { setTab("users"); setUserQuery(item.username); setSearchResults(null) }}>@{item.username} · {item.email}</button>)}</div>}
                        {searchResults.jobs?.length > 0 && <div><span>Ishlar</span>{searchResults.jobs.map((item) => <button key={item.id} onClick={() => { setTab("jobs"); setJobQuery(String(item.id)); setSearchResults(null) }}>#{item.id} · {item.title}</button>)}</div>}
                        {searchResults.services?.length > 0 && <div><span>Xizmatlar</span>{searchResults.services.map((item) => <button key={item.id} onClick={() => { setTab("services"); setServiceQuery(item.name); setSearchResults(null) }}>#{item.id} · {item.name}</button>)}</div>}
                        {searchResults.reports?.length > 0 && <div><span>Shikoyatlar</span>{searchResults.reports.map((item) => <button key={item.id} onClick={() => { setTab("reports"); setReportQuery(String(item.id)); setSearchResults(null) }}>#{item.id} · {item.reason}</button>)}</div>}
                        {!searchResults.users?.length && !searchResults.jobs?.length && !searchResults.services?.length && !searchResults.reports?.length && <div className="admin-search-empty">Natija topilmadi.</div>}
                    </div>
                )}
            </div>

            <div className="admin-stat-grid">
                <div className="card admin-stat"><span>Foydalanuvchilar</span><strong>{stats.users ?? 0}</strong></div>
                <div className="card admin-stat"><span>Faol ishlar</span><strong>{stats.active_jobs ?? 0}</strong></div>
                <div className="card admin-stat"><span>Yakunlangan</span><strong>{stats.finished_jobs ?? 0}</strong></div>
                <div className="card admin-stat"><span>Ochiq shikoyatlar</span><strong>{stats.pending_reports ?? 0}</strong></div>
                <div className="card admin-stat"><span>Bloklangan ishlar</span><strong>{stats.blocked_jobs ?? 0}</strong></div>
                <div className="card admin-stat"><span>Xizmatlar</span><strong>{stats.services ?? 0}</strong></div>
                <div className="card admin-stat"><span>Escrow</span><strong>{money(walletSummary?.escrow_balance)} UZS</strong></div>
                <div className="card admin-stat"><span>FinJob daromadi</span><strong>{money(walletSummary?.platform_balance)} UZS</strong></div>
                <div className="card admin-stat"><span>Administratorlar</span><strong>{stats.admins ?? 0}</strong></div>
            </div>

            <div className="card admin-panel">
                <div className="admin-toolbar">
                    <div>
                        <span className="admin-toolbar-eyebrow">CONTROL CENTER</span>
                        <strong>Platforma boshqaruvi</strong>
                    </div>
                    <button className="btn btn-secondary" onClick={load}>Yangilash</button>
                </div>

                <div className="admin-tabs">
                    {navTabs.map(([key, label]) => (
                        <button key={key} className={"admin-tab " + (tab === key ? "active" : "")} onClick={() => setTab(key)}>
                            {label}
                            {key === "reports" && stats.pending_reports > 0 && <b className="admin-tab-count">{stats.pending_reports}</b>}
                            {key === "disputes" && adminDisputes.filter((item) => ["open", "reviewing"].includes(item.status)).length > 0 && <b className="admin-tab-count">{adminDisputes.filter((item) => ["open", "reviewing"].includes(item.status)).length}</b>}
                        </button>
                    ))}
                </div>

                {!data && <div className="muted" style={{ padding: 24 }}>Yuklanmoqda...</div>}

                {data && tab === "dashboard" && (
                    <div className="admin-dashboard">
                        <div className="admin-dashboard-grid">
                            <div className="card admin-overview-card">
                                <div className="admin-section-head"><div><span>PLATFORM HEALTH</span><h2>Bugungi nazorat markazi</h2></div></div>
                                <div className="admin-health-grid">
                                    <div><small>Jami to‘lovlar</small><strong>{money(paymentTotal)} UZS</strong><span>Payment yozuvlari bo‘yicha</span></div>
                                    <div><small>Released</small><strong>{money(completedPayments?.amount)} UZS</strong><span>Yakunlangan to‘lovlar</span></div>
                                    <div><small>Escrow</small><strong>{money(walletSummary?.escrow_balance)} UZS</strong><span>Hozir ushlab turilgan</span></div>
                                    <div><small>Komissiya</small><strong>{Number(data.settings?.commission_percent || 0).toLocaleString("uz-UZ")}%</strong><span>Platforma sozlamasi</span></div>
                                </div>
                            </div>

                            <div className="card admin-overview-card">
                                <div className="admin-section-head"><div><span>TOP SERVICES</span><h2>Eng ko‘p ishlatilgan</h2></div><button className="link" onClick={() => setTab("services")}>Barchasi</button></div>
                                <div className="admin-mini-list">
                                    {(analytics?.top_services || []).slice(0, 8).map((item, index) => <div key={item.name + index}><strong>{item.name}</strong><b>{item.total}</b></div>)}
                                    {!analytics?.top_services?.length && <span className="muted">Hali statistika yo‘q.</span>}
                                </div>
                            </div>
                        </div>

                        <div className="card admin-overview-card">
                            <div className="admin-section-head"><div><span>RECENT ADMIN ACTIONS</span><h2>Oxirgi o‘zgarishlar</h2></div><button className="link" onClick={() => setTab("audit")}>Audit log</button></div>
                            <div className="admin-audit-feed">
                                {(audit?.items || []).slice(0, 8).map((item) => <div key={item.id}><span className="admin-audit-dot"></span><div><strong>{actionLabel[item.action] || item.action}</strong><p>{item.details || "—"} · {item.admin_username || "admin"}</p></div><time>{formatTimeAgo(item.created_at)}</time></div>)}
                                {!audit?.items?.length && <span className="muted">Admin harakatlari hali yozilmagan.</span>}
                            </div>
                        </div>
                    </div>
                )}

                {data && tab === "users" && (
                    <div className="admin-section">
                        <div className="admin-filters">
                            <input className="input" placeholder="Username, email, ism..." value={userQuery} onChange={(e) => { setUserPage(1); setUserQuery(e.target.value) }} />
                            <select className="select" value={userRole} onChange={(e) => { setUserPage(1); setUserRole(e.target.value) }}>
                                <option value="all">Barcha rollar</option>
                                <option value="user">Foydalanuvchi</option>
                                <option value="admin">Administrator</option>
                            </select>
                            <select className="select" value={userBlocked} onChange={(e) => { setUserPage(1); setUserBlocked(e.target.value) }}>
                                <option value="all">Barcha holatlar</option>
                                <option value="blocked">Bloklangan</option>
                                <option value="active">Faol</option>
                            </select>
                        </div>
                        <div className="admin-table-wrap">
                            <table className="admin-table">
                                <thead><tr><th>ID</th><th>Foydalanuvchi</th><th>Email</th><th>Rol</th><th>Holat</th><th>Baho</th><th>Balans</th><th>Amallar</th></tr></thead>
                                <tbody>
                                    {users.page.map((item) => (
                                        <tr key={item.id}>
                                            <td>#{item.id}</td>
                                            <td><strong>@{item.username}</strong><small>{shortName(item)}</small></td>
                                            <td>{item.email}</td>
                                            <td><select className="admin-action-select" value={item.role} disabled={item.id === user.id} onChange={(e) => changeRole(item, e.target.value)}><option value="user">user</option><option value="admin">admin</option></select></td>
                                            <td><span className={"admin-badge " + (Number(item.is_blocked) ? "danger" : "success")}>{Number(item.is_blocked) ? "Bloklangan" : "Faol"}</span></td>
                                            <td>{Number(item.average_rating || 0).toFixed(1)}</td>
                                            <td><strong>{money(item.balance)} UZS</strong></td>
                                            <td><div className="admin-row-actions">
                                                <button className="btn btn-secondary admin-small-btn" onClick={() => editUser(item)}>Tahrirlash</button>
                                                <button className="btn btn-secondary admin-small-btn" onClick={() => openModeration(item)}>Moderatsiya</button>
                                                <button className="btn btn-secondary admin-small-btn" onClick={() => addTestBalance(item)}>+ Pul</button>
                                                <button className="btn btn-danger admin-small-btn" disabled={item.id === user.id || item.role === "admin"} onClick={() => deleteUser(item)}>O‘chirish</button>
                                            </div></td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        {!users.page.length && <div className="empty-state">Foydalanuvchi topilmadi.</div>}
                        <Pager page={userPage} pages={users.pages} total={users.all.length} onChange={setUserPage} />
                    </div>
                )}

                {data && tab === "jobs" && (
                    <div className="admin-section">
                        <div className="admin-filters">
                            <input className="input" placeholder="Job nomi, username, manzil yoki ID..." value={jobQuery} onChange={(e) => { setJobPage(1); setJobQuery(e.target.value) }} />
                            <select className="select" value={jobStatus} onChange={(e) => { setJobPage(1); setJobStatus(e.target.value) }}>
                                <option value="all">Barcha holatlar</option>
                                {Object.entries(statusLabel).slice(0, 6).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                                <option value="blocked">Bloklangan</option>
                            </select>
                        </div>
                        <div className="admin-table-wrap">
                            <table className="admin-table">
                                <thead><tr><th>ID</th><th>Job</th><th>Egasi</th><th>Bajaruvchi</th><th>Narx</th><th>Holat</th><th>Manzil</th><th>Amal</th></tr></thead>
                                <tbody>
                                    {jobs.page.map((item) => (
                                        <tr key={item.id}>
                                            <td>#{item.id}</td><td><strong>{item.title}</strong><small>{formatTimeAgo(item.created_at)}</small></td>
                                            <td>@{item.creator_username || "—"}</td><td>@{item.worker_username || "—"}</td>
                                            <td><strong>{money(item.price)} {item.currency || "UZS"}</strong></td>
                                            <td><select className="admin-action-select" value={item.status || "active"} onChange={(e) => updateJobStatus(item, e.target.value)}>{["active","payment_pending","accepted","pending_finish","finished","blocked"].map((key) => <option key={key} value={key}>{statusLabel[key]}</option>)}</select></td>
                                            <td>{item.location || "—"}</td>
                                            <td><button className="btn btn-danger admin-small-btn" onClick={() => deleteJob(item)}>O‘chirish</button></td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        {!jobs.page.length && <div className="empty-state">Job topilmadi.</div>}
                        <Pager page={jobPage} pages={jobs.pages} total={jobs.all.length} onChange={setJobPage} />
                    </div>
                )}

                {data && tab === "services" && (
                    <div className="admin-section">
                        <form className="admin-create-service" onSubmit={createService}>
                            <input className="input" placeholder="Yangi xizmat yoki kategoriya nomi" value={serviceName} onChange={(e) => setServiceName(e.target.value)} />
                            <select className="select admin-parent-select" value={serviceParent} onChange={(e) => setServiceParent(e.target.value)}>
                                <option value="">Asosiy kategoriya</option>
                                {serviceTree.map((item) => <option key={item.id} value={item.id}>{"— ".repeat(item.depth)}{item.name}</option>)}
                            </select>
                            <button className="btn btn-primary" type="submit">+ Xizmat qo‘shish</button>
                        </form>
                        <div className="admin-filters"><input className="input" placeholder="Xizmat qidirish..." value={serviceQuery} onChange={(e) => { setServicePage(1); setServiceQuery(e.target.value) }} /></div>
                        <div className="admin-table-wrap">
                            <table className="admin-table">
                                <thead><tr><th>ID</th><th>Xizmat</th><th>Ota kategoriya</th><th>Yaratgan</th><th>Amal</th></tr></thead>
                                <tbody>
                                    {services.page.map((item) => (
                                        <tr key={item.id}><td>#{item.id}</td><td><strong>{item.name}</strong></td><td>{item.parent_name || "Asosiy kategoriya"}</td><td>{item.created_by || "Tizim"}</td><td><button className="btn btn-danger admin-small-btn" onClick={() => deleteService(item)}>O‘chirish</button></td></tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        {!services.page.length && <div className="empty-state">Xizmat topilmadi.</div>}
                        <Pager page={servicePage} pages={services.pages} total={services.all.length} onChange={setServicePage} />
                    </div>
                )}

                {data && tab === "reports" && (
                    <div className="admin-section">
                        <div className="admin-filters">
                            <input className="input" placeholder="Sabab, tafsilot, username yoki ID..." value={reportQuery} onChange={(e) => { setReportPage(1); setReportQuery(e.target.value) }} />
                            <select className="select" value={reportStatus} onChange={(e) => { setReportPage(1); setReportStatus(e.target.value) }}>
                                <option value="all">Barcha statuslar</option><option value="open">Ochiq</option><option value="reviewing">Ko‘rib chiqilmoqda</option><option value="resolved">Hal qilindi</option><option value="rejected">Rad etildi</option>
                            </select>
                        </div>
                        <div className="admin-table-wrap">
                            <table className="admin-table">
                                <thead><tr><th>ID</th><th>Yuboruvchi</th><th>Foydalanuvchi</th><th>Manba</th><th>Sabab</th><th>Tafsilot</th><th>Fayl</th><th>Sana</th><th>Holat</th></tr></thead>
                                <tbody>
                                    {reports.page.map((item) => (
                                        <tr key={item.id}>
                                            <td>#{item.id}</td><td>@{item.reporter_username || "—"}</td><td>@{item.reported_username || "—"}</td>
                                            <td>{item.message_id ? "Xabar #" + item.message_id : "Ish #" + (item.job_id || "—")}</td>
                                            <td><strong>{item.reason}</strong></td><td>{item.details || "—"}</td>
                                            <td>{item.attachment_url ? <button className="btn btn-secondary admin-small-btn" onClick={() => openReportAttachment(item)}>Fayl</button> : "—"}</td>
                                            <td>{formatTimeAgo(item.created_at)}</td>
                                            <td><select className="admin-action-select" value={item.status} onChange={(e) => updateReport(item, e.target.value)}>{["open","reviewing","resolved","rejected"].map((key) => <option key={key} value={key}>{statusLabel[key]}</option>)}</select></td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        {!reports.page.length && <div className="empty-state">Shikoyat topilmadi.</div>}
                        <Pager page={reportPage} pages={reports.pages} total={reports.all.length} onChange={setReportPage} />
                    </div>
                )}

                {data && tab === "blocks" && (
                    <div className="admin-section">
                        <div className="admin-filters">
                            <input className="input" placeholder="Username, block turi, sabab yoki ID..." value={blockQuery} onChange={(e) => { setBlockPage(1); setBlockQuery(e.target.value) }} />
                            <select className="select" value={blockStatus} onChange={(e) => { setBlockPage(1); setBlockStatus(e.target.value) }}><option value="active">Faol blocklar</option><option value="all">Barcha blocklar</option><option value="lifted">Olib tashlanganlar</option></select>
                        </div>
                        <div className="admin-table-wrap">
                            <table className="admin-table">
                                <thead><tr><th>ID</th><th>User</th><th>Block turi</th><th>Nega</th><th>Berilgan</th><th>Tugash</th><th>Admin</th><th>Amal</th></tr></thead>
                                <tbody>{filteredBlocks.page.map((item) => <tr key={item.id}>
                                    <td>#{item.id}</td><td><strong>@{item.username}</strong><small>User ID: #{item.user_id}</small></td>
                                    <td><span className={"admin-badge " + (item.active ? "danger" : "neutral")}>{item.block_label || blockLabels[item.block_type] || item.block_type}</span></td>
                                    <td>{item.reason}</td><td>{formatTimeAgo(item.created_at)}</td><td>{item.expires_at ? formatTimeAgo(item.expires_at) : "Muddatsiz"}</td><td>@{item.admin_username || "—"}</td>
                                    <td>{item.active ? <button className="btn btn-secondary admin-small-btn" onClick={() => liftBlock(item)}>Lift</button> : "—"}</td>
                                </tr>)}</tbody>
                            </table>
                        </div>
                        {!filteredBlocks.page.length && <div className="empty-state">Block topilmadi.</div>}
                        <Pager page={blockPage} pages={filteredBlocks.pages} total={filteredBlocks.all.length} onChange={setBlockPage} />
                    </div>
                )}

                {data && tab === "appeals" && (
                    <div className="admin-section">
                        <div className="admin-filters">
                            <input className="input" placeholder="User, appeal matni, sabab, block ID..." value={appealQuery} onChange={(e) => { setAppealPage(1); setAppealQuery(e.target.value) }} />
                            <select className="select" value={appealStatus} onChange={(e) => { setAppealPage(1); setAppealStatus(e.target.value) }}><option value="all">Barcha statuslar</option><option value="open">Ochiq</option><option value="reviewing">Ko‘rib chiqilmoqda</option><option value="approved">Tasdiqlangan</option><option value="rejected">Rad etilgan</option></select>
                        </div>
                        <div className="admin-table-wrap">
                            <table className="admin-table admin-appeal-table">
                                <thead><tr><th>Appeal</th><th>User</th><th>Block</th><th>Block sababi</th><th>Appeal matni</th><th>Vaqt</th><th>Status</th><th>Amal</th></tr></thead>
                                <tbody>{filteredAppeals.page.map((item) => <tr key={item.id}>
                                    <td><strong>#{item.id}</strong><small>Block #{item.block_id}</small></td>
                                    <td><strong>@{item.username}</strong><small>User ID: #{item.user_id}</small></td>
                                    <td><span className="admin-badge danger">{item.block_label || blockLabels[item.block_type] || item.block_type}</span><small>{item.expires_at ? "Tugaydi: " + formatTimeAgo(item.expires_at) : "Muddatsiz"}</small></td>
                                    <td>{item.block_reason}</td>
                                    <td className="admin-long-cell">{item.appeal_text}</td>
                                    <td>{formatTimeAgo(item.created_at)}</td>
                                    <td><span className={"admin-badge " + (item.status === "approved" ? "success" : item.status === "rejected" ? "danger" : "neutral")}>{statusLabel[item.status] || item.status}</span></td>
                                    <td><button className="btn btn-primary admin-small-btn" onClick={() => openAppealReview(item)}>Ko‘rib chiqish</button></td>
                                </tr>)}</tbody>
                            </table>
                        </div>
                        {!filteredAppeals.page.length && <div className="empty-state">Appeal topilmadi.</div>}
                        <Pager page={appealPage} pages={filteredAppeals.pages} total={filteredAppeals.all.length} onChange={setAppealPage} />
                    </div>
                )}

                {data && tab === "disputes" && (
                    <div className="admin-section">
                        <div className="admin-section-head">
                            <div><span>DISPUTE CENTER</span><h2>Nizolarni ko‘rib chiqish</h2><p className="muted">Tomonlar, dalillar va nizo holatini shu bo‘limda boshqaring.</p></div>
                            <span className="profile-count">{filteredDisputes.length} ta</span>
                        </div>
                        <div className="admin-filters">
                            <input className="input" placeholder="Ish nomi, foydalanuvchi, nizo ID yoki matn..." value={disputeQuery} onChange={(e) => setDisputeQuery(e.target.value)} />
                            <select className="select" value={disputeStatus} onChange={(e) => setDisputeStatus(e.target.value)}>
                                <option value="open">Ochiq</option>
                                <option value="reviewing">Ko‘rib chiqilmoqda</option>
                                <option value="resolved">Hal qilingan</option>
                                <option value="rejected">Rad etilgan</option>
                                <option value="all">Barcha holatlar</option>
                            </select>
                        </div>
                        <div className="dispute-list">
                            {filteredDisputes.map((item) => (
                                <article className="dispute-item" key={item.id}>
                                    <div>
                                        <strong>#{item.id} · {item.job_title || `Ish #${item.job_id}`}</strong>
                                        <span>{({ payment: "To‘lov", quality: "Ish sifati", deadline: "Muddat", communication: "Muloqot", other: "Boshqa" })[item.category] || item.category} · {statusLabel[item.status] || item.status}</span>
                                        <p><strong>Muammo:</strong> {item.description}</p>
                                        <span>Ochildi: @{item.opened_by_username || "—"} · Qarshi tomon: @{item.against_username || "—"} · Ish ID: #{item.job_id}</span>
                                        {item.evidence && <p><strong>Dalillar:</strong> {item.evidence}</p>}
                                        {item.admin_response && <p><strong>Admin javobi:</strong> {item.admin_response}</p>}
                                        <small>{formatTimeAgo(item.created_at)}</small>
                                    </div>
                                    <button className="btn btn-primary admin-dispute-review-btn" type="button" onClick={() => openDisputeReview(item)}>
                                        {reviewingDispute?.id === item.id ? "Yopish" : "Ko‘rib chiqish"}
                                    </button>
                                    {reviewingDispute?.id === item.id && (
                                        <form className="dispute-detail" onSubmit={submitDisputeReview}>
                                            <label className="field">
                                                <span>Nizo holati</span>
                                                <select className="select" value={disputeReviewForm.status} onChange={(e) => setDisputeReviewForm({ ...disputeReviewForm, status: e.target.value })}>
                                                    <option value="open">Ochiq</option>
                                                    <option value="reviewing">Ko‘rib chiqilmoqda</option>
                                                    <option value="resolved">Hal qilindi</option>
                                                    <option value="rejected">Rad etildi</option>
                                                </select>
                                            </label>
                                            <label className="field">
                                                <span>Administrator javobi</span>
                                                <textarea className="textarea" rows="4" maxLength="3000" required={["resolved", "rejected"].includes(disputeReviewForm.status)} value={disputeReviewForm.admin_response} onChange={(e) => setDisputeReviewForm({ ...disputeReviewForm, admin_response: e.target.value })} placeholder="Tomonlar uchun qaror va izoh..." />
                                            </label>
                                            <div className="form-row">
                                                <button className="btn btn-primary" type="submit">Qarorni saqlash</button>
                                                <button className="btn btn-secondary" type="button" onClick={() => setReviewingDispute(null)}>Bekor qilish</button>
                                            </div>
                                        </form>
                                    )}
                                </article>
                            ))}
                        </div>
                        {!filteredDisputes.length && <div className="empty-state">Bu filtrga mos nizo topilmadi.</div>}
                    </div>
                )}

                {data && tab === "finance" && (
                    <div className="admin-section">
                        <div className="admin-finance-grid">
                            <div className="card admin-finance-main"><span>PLATFORM BALANCE</span><strong>{money(finance?.wallet?.balance)} UZS</strong><small>FinJob komissiyasi va platforma mablag‘i</small></div>
                            <div className="card admin-finance-main"><span>ESCROW</span><strong>{money(finance?.wallet?.escrow_balance)} UZS</strong><small>Hozirda ishlar uchun ushlab turilgan</small></div>
                        </div>
                        <div className="admin-subsection">
                            <div className="admin-section-head"><div><span>PAYMENTS</span><h2>To‘lovlar holati</h2></div></div>
                            <div className="admin-finance-status-grid">{(analytics?.payments || []).map((item) => <div key={item.status} className="admin-finance-status"><span>{statusLabel[item.status] || item.status}</span><strong>{item.count}</strong><small>{money(item.amount)} UZS</small></div>)}</div>
                        </div>
                        <div className="admin-subsection">
                            <div className="admin-section-head"><div><span>RECENT TRANSACTIONS</span><h2>Wallet tranzaksiyalari</h2></div></div>
                            <div className="admin-table-wrap">
                                <table className="admin-table">
                                    <thead><tr><th>ID</th><th>User</th><th>Tur</th><th>Summa</th><th>Balansdan keyin</th><th>Tavsif</th><th>Sana</th></tr></thead>
                                    <tbody>{(finance?.transactions || []).slice(0, 40).map((item) => <tr key={item.id}><td>#{item.id}</td><td>@{item.username}</td><td><span className="admin-badge neutral">{item.type}</span></td><td className={Number(item.amount) >= 0 ? "admin-amount-positive" : "admin-amount-negative"}>{Number(item.amount) >= 0 ? "+" : ""}{money(item.amount)} UZS</td><td>{money(item.balance_after)} UZS</td><td>{item.description}</td><td>{formatTimeAgo(item.created_at)}</td></tr>)}</tbody>
                                </table>
                            </div>
                            {!finance?.transactions?.length && <div className="empty-state">Tranzaksiyalar yo‘q.</div>}
                        </div>
                    </div>
                )}

                {data && tab === "ratings" && (
                    <div className="admin-section">
                        <div className="admin-filters"><input className="input" placeholder="Username, izoh yoki job ID..." value={ratingQuery} onChange={(e) => { setRatingPage(1); setRatingQuery(e.target.value) }} /></div>
                        <div className="admin-table-wrap">
                            <table className="admin-table">
                                <thead><tr><th>ID</th><th>Job</th><th>Kimdan</th><th>Kimga</th><th>Baho</th><th>Izoh</th><th>Amal</th></tr></thead>
                                <tbody>{ratings.page.map((item) => <tr key={item.id}><td>#{item.id}</td><td>#{item.job_id}</td><td>@{item.from_username || "—"}</td><td>@{item.to_username || "—"}</td><td><strong>{item.score}/10</strong></td><td>{item.comment || "—"}</td><td><button className="btn btn-danger admin-small-btn" onClick={() => deleteRating(item)}>O‘chirish</button></td></tr>)}</tbody>
                            </table>
                        </div>
                        {!ratings.page.length && <div className="empty-state">Baho topilmadi.</div>}
                        <Pager page={ratingPage} pages={ratings.pages} total={ratings.all.length} onChange={setRatingPage} />
                    </div>
                )}

                {data && tab === "audit" && (
                    <div className="admin-section">
                        <div className="admin-filters"><input className="input" placeholder="Action, target, admin yoki tafsilot..." onChange={(e) => { setAuditPage(1); loadAudit(1, e.target.value) }} /></div>
                        <div className="admin-table-wrap">
                            <table className="admin-table">
                                <thead><tr><th>ID</th><th>Admin</th><th>Amal</th><th>Target</th><th>Tafsilot</th><th>Sana</th></tr></thead>
                                <tbody>{(audit?.items || []).map((item) => <tr key={item.id}><td>#{item.id}</td><td>@{item.admin_username || "—"}</td><td><strong>{actionLabel[item.action] || item.action}</strong><small>{item.action}</small></td><td>{item.target_type || "—"}{item.target_id ? " #" + item.target_id : ""}</td><td>{item.details || "—"}</td><td>{formatTimeAgo(item.created_at)}</td></tr>)}</tbody>
                            </table>
                        </div>
                        {!audit?.items?.length && <div className="empty-state">Audit yozuvlari topilmadi.</div>}
                        <Pager page={auditPage} pages={audit?.pages || 1} total={audit?.total || 0} onChange={(p) => { setAuditPage(p); loadAudit(p) }} />
                    </div>
                )}

                {data && tab === "settings" && (
                    <div className="admin-settings-grid">
                        <div className="card admin-setting-card">
                            <div className="admin-section-head"><div><span>PAYMENTS</span><h2>Platforma komissiyasi</h2><p className="muted">Ish yakunlanganda platformada ushlab qolinadigan komissiya.</p></div></div>
                            <form onSubmit={saveCommission} className="admin-setting-form">
                                <label className="field"><span>Komissiya (%)</span><input className="input" type="number" min="0" max="100" step="0.01" value={commissionPercent} onChange={(e) => setCommissionPercent(e.target.value)} /></label>
                                <div className="admin-setting-preview"><span>Hozirgi qiymat</span><strong>{Number(commissionPercent || 0).toLocaleString("uz-UZ")}%</strong></div>
                                <div className="notice" style={{ gridColumn: "1 / -1" }}>Komissiya alohida ustama emas; yakunlangan ish to‘lovidan hisoblanadi.</div>
                                <button className="btn btn-primary" type="submit">Sozlamani saqlash</button>
                            </form>
                        </div>
                        <div className="card admin-setting-card">
                            <div className="admin-section-head"><div><span>SECURITY</span><h2>Admin xavfsizligi</h2></div></div>
                            <div className="admin-setting-list"><div><span>Admin-only API</span><strong>Faol</strong></div><div><span>Audit log</span><strong>Faol</strong></div><div><span>Token versioning</span><strong>Faol</strong></div><div><span>User blocking</span><strong>Faol</strong></div><div><span>Reports moderation</span><strong>Faol</strong></div></div>
                        </div>
                    </div>
                )}
            </div>

            {moderatingUser && (
                <div className="admin-modal-backdrop" onClick={() => setModeratingUser(null)}>
                    <div className="card admin-modal admin-moderation-modal" onClick={(e) => e.stopPropagation()}>
                        <div className="admin-modal-head">
                            <div><span className="admin-search-eyebrow">MODERATION CENTER</span><h3>@{moderatingUser.username}</h3><p>User #{moderatingUser.id} · cheklovlarni boshqarish</p></div>
                            <button className="admin-modal-close" onClick={() => setModeratingUser(null)}>×</button>
                        </div>
                        <div className="admin-moderation-body">
                            <div>
                                <div className="admin-subtitle-row"><strong>Faol va tarixiy blocklar</strong><span>{userBlocks.filter((x) => x.active).length} faol</span></div>
                                <div className="admin-user-block-list">
                                    {userBlocks.map((block) => <div className="admin-user-block" key={block.id}>
                                        <div><span className={"admin-badge " + (block.active ? "danger" : "neutral")}>{blockLabels[block.block_type] || block.block_type}</span><strong>#{block.id}</strong></div>
                                        <p>{block.reason}</p>
                                        <small>{formatTimeAgo(block.created_at)} · {block.expires_at ? "Tugashi: " + formatTimeAgo(block.expires_at) : "Muddatsiz"} · @{block.created_by_username || "admin"}</small>
                                        {block.active && <button className="btn btn-secondary admin-small-btn" onClick={() => liftBlock(block)}>Blockni olib tashlash</button>}
                                    </div>)}
                                    {!userBlocks.length && <div className="empty-state">Bu userda block tarixi yo‘q.</div>}
                                </div>
                            </div>
                            <form className="admin-user-form admin-create-block-form" onSubmit={createUserBlock}>
                                <div className="admin-subtitle-row"><strong>Yangi cheklov</strong><span>Sabab majburiy</span></div>
                                <label>Block turi<select className="select" value={blockForm.block_type} onChange={(e) => setBlockForm({ ...blockForm, block_type: e.target.value })}>{Object.entries(blockLabels).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
                                <label>Muddati<select className="select" value={blockForm.duration_minutes} onChange={(e) => setBlockForm({ ...blockForm, duration_minutes: e.target.value })}><option value="60">1 soat</option><option value="360">6 soat</option><option value="1440">1 kun</option><option value="10080">7 kun</option><option value="43200">30 kun</option><option value="">Muddatsiz</option></select></label>
                                <label>Nega block qilinyapti<textarea className="input admin-textarea" maxLength="2000" value={blockForm.reason} onChange={(e) => setBlockForm({ ...blockForm, reason: e.target.value })} placeholder="Aniq va tushunarli sabab yozing..." /></label>
                                <button className="btn btn-danger" type="submit" disabled={!blockForm.reason.trim()}>Block qo‘yish</button>
                            </form>
                        </div>
                    </div>
                </div>
            )}

            {reviewingAppeal && (
                <div className="admin-modal-backdrop" onClick={() => setReviewingAppeal(null)}>
                    <div className="card admin-modal appeal-review-modal" onClick={(e) => e.stopPropagation()}>
                        <div className="admin-modal-head"><div><span className="admin-search-eyebrow">APPEAL #{reviewingAppeal.id}</span><h3>@{reviewingAppeal.username}</h3><p>{blockLabels[reviewingAppeal.block_type] || reviewingAppeal.block_type} · Block #{reviewingAppeal.block_id}</p></div><button className="admin-modal-close" onClick={() => setReviewingAppeal(null)}>×</button></div>
                        <div className="admin-appeal-detail">
                            <div><span>BLOCK SABABI</span><p>{reviewingAppeal.block_reason}</p></div>
                            <div><span>APPEAL MATNI</span><p>{reviewingAppeal.appeal_text}</p></div>
                            <div className="admin-appeal-meta"><span>Berilgan: {formatTimeAgo(reviewingAppeal.created_at)}</span><span>Block tugashi: {reviewingAppeal.expires_at ? formatTimeAgo(reviewingAppeal.expires_at) : "Muddatsiz"}</span></div>
                        </div>
                        <form className="admin-user-form" onSubmit={submitAppealReview}>
                            <label>Qaror<select className="select" value={appealReviewForm.status} disabled={reviewingAppeal.status === "approved" || reviewingAppeal.status === "rejected"} onChange={(e) => setAppealReviewForm({ ...appealReviewForm, status: e.target.value })}><option value="reviewing">Ko‘rib chiqilmoqda</option><option value="approved">Tasdiqlash — block olib tashlanadi</option><option value="rejected">Rad etish</option></select></label>
                            <label>Admin izohi<textarea className="input admin-textarea" maxLength="3000" value={appealReviewForm.admin_response} onChange={(e) => setAppealReviewForm({ ...appealReviewForm, admin_response: e.target.value })} placeholder="Qaroringiz sababini foydalanuvchiga tushuntiring..." /></label>
                            <div className="admin-modal-actions"><button type="button" className="btn btn-secondary" onClick={() => setReviewingAppeal(null)}>Yopish</button><button type="submit" className="btn btn-primary" disabled={reviewingAppeal.status === "approved" || reviewingAppeal.status === "rejected"}>Qarorni saqlash</button></div>
                        </form>
                    </div>
                </div>
            )}

            {editingUser && (
                <div className="admin-modal-backdrop" onClick={() => setEditingUser(null)}>
                    <div className="card admin-modal" onClick={(e) => e.stopPropagation()}>
                        <div className="admin-modal-head"><div><span className="admin-search-eyebrow">USER MANAGEMENT</span><h3>Foydalanuvchini tahrirlash</h3><p>@{editingUser.username}</p></div><button className="admin-modal-close" onClick={() => setEditingUser(null)}>×</button></div>
                        <form onSubmit={saveUser} className="admin-user-form">
                            <div className="admin-form-grid">
                                <label>Username<input className="input" value={userForm.username} onChange={(e) => setUserForm({ ...userForm, username: e.target.value })} /></label>
                                <label>Elektron pochta<input className="input" type="email" value={userForm.email} onChange={(e) => setUserForm({ ...userForm, email: e.target.value })} /></label>
                                <label>Ism<input className="input" value={userForm.first_name} onChange={(e) => setUserForm({ ...userForm, first_name: e.target.value })} /></label>
                                <label>Familiya<input className="input" value={userForm.last_name} onChange={(e) => setUserForm({ ...userForm, last_name: e.target.value })} /></label>
                                <label>Tug‘ilgan sana<input className="input" value={userForm.birthday} onChange={(e) => setUserForm({ ...userForm, birthday: e.target.value })} /></label>
                                <label>Yangi parol<input className="input" type="password" placeholder="Bo‘sh qolsa o‘zgarmaydi" value={userForm.password} onChange={(e) => setUserForm({ ...userForm, password: e.target.value })} /></label>
                            </div>
                            <label>O‘zingiz haqingizda<textarea className="input admin-textarea" value={userForm.bio} onChange={(e) => setUserForm({ ...userForm, bio: e.target.value })} /></label>
                            <label>Ko‘nikmalar<textarea className="input admin-textarea" value={userForm.skills} onChange={(e) => setUserForm({ ...userForm, skills: e.target.value })} /></label>
                            <div className="admin-modal-actions"><button type="button" className="btn btn-secondary" onClick={() => setEditingUser(null)}>Bekor qilish</button><button type="submit" className="btn btn-primary">Saqlash</button></div>
                        </form>
                    </div>
                </div>
            )}
        </AppLayout>
    )
}

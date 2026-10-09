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
    rejected: "Rad etildi",
    modified: "Qisman tasdiqlandi",
    held: "Escrowda ushlab turilgan",
    refunded: "Qaytarilgan",
    released: "O‘tkazilgan",
    paid: "To‘langan",
    pending: "Kutilmoqda"
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

const disputeDecisionLabels = {
    favor_opener: "Nizo ochgan tomon foydasiga",
    favor_opponent: "Qarshi tomon foydasiga",
    mutual_agreement: "Tomonlar kelishuvi bilan",
    insufficient_evidence: "Dalillar yetarli emas",
    policy_violation: "Qoidabuzarlik aniqlandi",
    no_violation: "Qoidabuzarlik aniqlanmadi"
}
const disputePaymentActionLabels = {
    none: "To‘lovga tegilmagan",
    refund_payer: "Pul buyurtmachiga qaytarildi",
    release_to_worker: "Pul ijrochiga o‘tkazildi"
}
const disputeJobActionLabels = {
    none: "Ish o‘zgarishsiz qoldi",
    block: "Ish bloklandi"
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
    user_block_created: "Cheklov qo‘yildi",
    user_block_lifted: "Cheklov olib tashlandi",
    appeal_created: "Yangi appeal",
    appeal_reviewed: "Ariza ko‘rib chiqildi",
    dispute_decision: "Nizo bo‘yicha hukm",
    report_decision: "Shikoyat bo‘yicha hukm",
    user_block_modified: "Cheklov o‘zgartirildi",
    verification_update: "Verifikatsiya o‘zgardi",
    service_update: "Xizmat tahrirlandi",
    admin_payment_action: "To‘lov bo‘yicha admin amali"
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
    const [appealReviewForm, setAppealReviewForm] = useState({
        status: "reviewing", admin_response: "", block_action: "reduce_duration",
        duration_minutes: "1440", new_block_type: "chat"
    })
    const [reviewingReport, setReviewingReport] = useState(null)
    const [reportReviewForm, setReportReviewForm] = useState({
        status: "reviewing", admin_response: "", decision: "", payment_action: "none",
        job_action: "none", notify_target: "none", sanction_target: "reported",
        sanction_type: "none", sanction_duration_minutes: "1440"
    })
    const [reportReviewError, setReportReviewError] = useState("")
    const [reportReviewSaving, setReportReviewSaving] = useState(false)
    const [editingService, setEditingService] = useState(null)
    const [serviceEditForm, setServiceEditForm] = useState({ name: "", parent_id: "" })
    const [verifyingUser, setVerifyingUser] = useState(null)
    const [verificationForm, setVerificationForm] = useState({ email_verified: false, phone_verified: false, identity_verified: false })
    const [reviewingDispute, setReviewingDispute] = useState(null)
    const [disputeReviewForm, setDisputeReviewForm] = useState({
        status: "reviewing", admin_response: "", decision: "", payment_action: "none",
        job_action: "none", sanction_target: "opponent", sanction_type: "none",
        sanction_duration_minutes: "1440"
    })
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
            setNotice(result?.msg || "Administrator ma’lumotlarini yuklab bo‘lmadi.")
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

    const action = async (path, options = {}, successMessage = "O‘zgarish saqlandi.", onError = null) => {
        setNotice("")
        setNoticeType("ok")
        const result = await api(path, { token, ...options })
        if (!result?.ok) {
            const message = result?.msg || "Amal bajarilmadi."
            setNoticeType("warn")
            setNotice(message)
            if (onError) onError(message)
            return false
        }
        await load()
        await loadAudit(1)
        setNotice(result?.msg || successMessage)
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
        if (role === "admin" && !window.confirm("@" + item.username + " ga administrator huquqi berilsinmi? U barcha admin amallarini bajara oladi.")) {
            await load()
            return
        }
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
        }, "Cheklov qo‘yildi.")
        if (result) {
            setBlockForm({ block_type: "chat", duration_minutes: "1440", reason: "" })
            const refreshed = await api("/admin/user/" + moderatingUser.id + "/blocks", { token })
            if (refreshed?.ok) setUserBlocks(refreshed.blocks || [])
        }
    }

    const liftBlock = async (block) => {
        if (!window.confirm("#" + block.id + " blockni olib tashlashni tasdiqlaysizmi?")) return
        const reason = window.prompt("Blockni olib tashlash sababi (ixtiyoriy):")
        if (reason === null) return
        const ok = await action("/admin/block/" + block.id, { method: "PATCH", body: { action: "lift", reason: reason.trim() } }, "Cheklov olib tashlandi.")
        if (ok && moderatingUser) {
            const refreshed = await api("/admin/user/" + moderatingUser.id + "/blocks", { token })
            if (refreshed?.ok) setUserBlocks(refreshed.blocks || [])
        }
    }

    const openAppealReview = (item) => {
        const durationOptions = [1, 5, 15, 30, 60, 360, 1440, 10080, 43200, 525600]
        const remainingMinutes = item.expires_at
            ? Math.max(1, Math.ceil((new Date(item.expires_at).getTime() - Date.now()) / 60000))
            : null
        const shorterOptions = remainingMinutes === null
            ? durationOptions
            : durationOptions.filter((minutes) => minutes < remainingMinutes)
        const defaultDuration = remainingMinutes === null
            ? 1440
            : (shorterOptions[shorterOptions.length - 1] || 1)
        setReviewingAppeal(item)
        setAppealReviewForm({
            status: item.status === "open" ? "reviewing" : item.status,
            admin_response: item.admin_response || "",
            block_action: "reduce_duration",
            duration_minutes: String(defaultDuration),
            new_block_type: item.block_type === "full" ? "chat" : (item.block_type || "chat")
        })
    }

    const submitAppealReview = async (event) => {
        event.preventDefault()
        if (!reviewingAppeal) return
        if (appealReviewForm.status === "modified" && !appealReviewForm.admin_response.trim()) {
            setNoticeType("warn")
            setNotice("Cheklovni yengillashtirish uchun sabab yozing.")
            return
        }
        const ok = await action("/admin/appeal/" + reviewingAppeal.id, {
            method: "PATCH",
            body: appealReviewForm
        }, "Ariza bo‘yicha qaror saqlandi.")
        if (ok) setReviewingAppeal(null)
    }

    const openReportReview = (item) => {
        setReviewingReport(item)
        setReportReviewError("")
        const legacyFinalReport = ["resolved", "rejected"].includes(item.status) &&
            (!item.decision || !String(item.admin_response || "").trim())
        setReportReviewForm({
            status: item.status === "open" || legacyFinalReport ? "reviewing" : item.status,
            admin_response: item.admin_response || "",
            decision: item.decision || "",
            payment_action: item.payment_action || "none",
            job_action: item.job_action || "none",
            notify_target: item.notify_target || "none",
            sanction_target: Number(item.sanction_user_id) === Number(item.reporter_id) ? "reporter" : "reported",
            sanction_type: item.sanction_type || "none",
            sanction_duration_minutes: item.sanction_duration_minutes == null
                ? (item.sanction_type && item.sanction_type !== "none" ? "0" : "1440")
                : String(item.sanction_duration_minutes)
        })
    }

    const submitReportReview = async (event) => {
        event.preventDefault()
        if (!reviewingReport || reportReviewSaving) return
        setReportReviewError("")
        if (["resolved", "rejected"].includes(reportReviewForm.status) && (!reportReviewForm.decision || !reportReviewForm.admin_response.trim())) {
            setReportReviewError("Yakuniy qaror uchun hukm turini tanlang va sababini yozing.")
            return
        }

        setReportReviewSaving(true)
        try {
            const ok = await action("/admin/report/" + reviewingReport.id, {
                method: "PATCH",
                body: reportReviewForm
            }, "Shikoyat bo‘yicha qaror saqlandi.", (message) => setReportReviewError(message))
            if (ok) setReviewingReport(null)
        } catch (error) {
            const message = error?.message || "Shikoyatni saqlashda kutilmagan xato yuz berdi."
            setReportReviewError(message)
            setNoticeType("warn")
            setNotice(message)
        } finally {
            setReportReviewSaving(false)
        }
    }

    const openVerification = (item) => {
        setVerifyingUser(item)
        setVerificationForm({
            email_verified: Boolean(item.email_verified),
            phone_verified: Boolean(item.phone_verified),
            identity_verified: Boolean(item.identity_verified)
        })
    }

    const saveVerification = async (event) => {
        event.preventDefault()
        if (!verifyingUser) return
        const ok = await action("/admin/user/" + verifyingUser.id + "/verification", {
            method: "PATCH", body: verificationForm
        }, "Verifikatsiya holati yangilandi.")
        if (ok) setVerifyingUser(null)
    }

    const editService = (item) => {
        setEditingService(item)
        setServiceEditForm({ name: item.name || "", parent_id: item.parent_id == null ? "" : String(item.parent_id) })
    }

    const saveServiceEdit = async (event) => {
        event.preventDefault()
        if (!editingService) return
        const ok = await action("/admin/service/" + editingService.id, {
            method: "PATCH",
            body: { name: serviceEditForm.name.trim(), parent_id: serviceEditForm.parent_id || null }
        }, "Xizmat yangilandi.")
        if (ok) setEditingService(null)
    }

    const reviseBlock = async (item) => {
        const duration = window.prompt("Yangi muddatni daqiqalarda kiriting (masalan, 1440 = 1 kun):", String(item.duration_minutes || 1440))
        if (duration === null) return
        const minutes = Number(duration)
        if (!Number.isInteger(minutes) || minutes < 1 || minutes > 525600) {
            setNoticeType("warn")
            setNotice("Muddat 1 dan 525600 daqiqagacha bo‘lishi kerak.")
            return
        }
        const reason = window.prompt("Yangilangan cheklov sababi:", item.reason || "")
        if (reason === null || !reason.trim()) return
        const ok = await action("/admin/block/" + item.id, {
            method: "PATCH",
            body: { action: "modify", duration_minutes: minutes, reason: reason.trim() }
        }, "Cheklov yangilandi.")
        if (ok) {
            const refreshed = await api("/admin/user/" + item.user_id + "/blocks", { token })
            if (refreshed?.ok && moderatingUser?.id === item.user_id) setUserBlocks(refreshed.blocks || [])
        }
    }

    const actOnPayment = async (item, paymentAction) => {
        const label = paymentAction === "refund" ? "pulni buyurtmachiga qaytarish" : "pulni ijrochiga o‘tkazish"
        if (!window.confirm(`Ish #${item.job_id} uchun ${money(item.amount)} UZS to‘lovi bo‘yicha "${label}" amalini bajarasizmi?`)) return
        const reason = window.prompt("Moliyaviy qaror sababi (majburiy):")
        if (reason === null || !reason.trim()) return
        await action("/admin/payment/" + item.job_id, {
            method: "PATCH", body: { action: paymentAction, reason: reason.trim() }
        }, "To‘lov bo‘yicha amal bajarildi.")
    }

    const exportAuditCsv = () => {
        const items = audit?.items || []
        if (!items.length) {
            setNoticeType("warn")
            setNotice("Eksport qilish uchun audit yozuvlari yo‘q.")
            return
        }
        const columns = ["id", "created_at", "admin_username", "action", "target_type", "target_id", "details"]
        const quote = (value) => '"' + String(value ?? "").replaceAll('"', '""') + '"'
        const csv = [columns.join(","), ...items.map((item) => columns.map((key) => quote(item[key])).join(","))].join("\r\n")
        const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8;" })
        const url = URL.createObjectURL(blob)
        const link = document.createElement("a")
        link.href = url
        link.download = `finjob-audit-${auditPage}.csv`
        document.body.appendChild(link)
        link.click()
        link.remove()
        URL.revokeObjectURL(url)
    }

    const openDisputeReview = (item) => {
        setReviewingDispute(item)
        setDisputeReviewForm({
            status: item.status === "open" ? "reviewing" : item.status,
            admin_response: item.admin_response || "",
            decision: item.decision || "",
            payment_action: item.payment_action || "none",
            job_action: item.job_action || "none",
            sanction_target: Number(item.sanction_user_id) === Number(item.opened_by) ? "opener" : "opponent",
            sanction_type: item.sanction_type || "none",
            sanction_duration_minutes: item.sanction_duration_minutes == null ? "0" : String(item.sanction_duration_minutes)
        })
    }

    const submitDisputeReview = async (event) => {
        event.preventDefault()
        if (!reviewingDispute) return
        if (["resolved", "rejected"].includes(disputeReviewForm.status) && !disputeReviewForm.decision) {
            setNoticeType("warn")
            setNotice("Yakuniy hukm uchun qaror turini tanlang.")
            return
        }
        const ok = await action("/admin/disputes/" + reviewingDispute.id, {
            method: "PATCH",
            body: disputeReviewForm
        }, "Nizo bo‘yicha hukm saqlandi.")
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
        const reason = window.prompt("O‘chirish sababi (ixtiyoriy):")
        if (reason === null) return
        await action("/admin/user/" + item.id, { method: "DELETE", body: { reason: reason.trim() } }, "Foydalanuvchi o‘chirildi.")
    }

    const updateJobStatus = async (item, status) => {
        if (status === item.status) return
        let reason = ""
        if (["blocked", "finished", "active"].includes(status)) {
            if (!window.confirm("#" + item.id + " — " + item.title + " ishini «" + (statusLabel[status] || status) + "» holatiga o‘tkazasizmi?")) {
                await load()
                return
            }
            reason = window.prompt("Holatni o‘zgartirish sababi (ixtiyoriy):") || ""
        }
        await action("/admin/job/" + item.id, { method: "PATCH", body: { status, reason: reason.trim() } }, "Ish holati o‘zgartirildi.")
    }

    const deleteJob = async (item) => {
        if (!window.confirm("#" + item.id + " — " + item.title + " ishini o‘chirishni tasdiqlaysizmi?")) return
        const reason = window.prompt("Ishni o‘chirish sababi (ixtiyoriy):")
        if (reason === null) return
        await action("/admin/job/" + item.id, { method: "DELETE", body: { reason: reason.trim() } }, "Ish o‘chirildi.")
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
        const reason = window.prompt("Xizmatni o‘chirish sababi (ixtiyoriy):")
        if (reason === null) return
        await action("/admin/service/" + item.id, { method: "DELETE", body: { reason: reason.trim() } }, "Xizmat o‘chirildi.")
    }

    const deleteRating = async (item) => {
        const reason = window.prompt("#" + item.id + " bahoni o‘chirish sababi:")
        if (reason === null) return
        if (!window.confirm("#" + item.id + " bahoni o‘chirishni tasdiqlaysizmi?")) return
        await action("/admin/rating/" + item.id, { method: "DELETE", body: { reason: reason.trim() } }, "Baho o‘chirildi.")
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
        ["dashboard", "Boshqaruv paneli"],
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
        <AppLayout title="Administrator paneli" subtitle="FinJob foydalanuvchilari, ishlar, to‘lovlar va murojaatlarni boshqaring.">
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
                        <span className="admin-toolbar-eyebrow">BOSHQARUV MARKAZI</span>
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
                                    <div><small>Jami to‘lovlar</small><strong>{money(paymentTotal)} UZS</strong><span>To‘lov yozuvlari bo‘yicha</span></div>
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
                                                <button className="btn btn-secondary admin-small-btn" onClick={() => openVerification(item)}>Verifikatsiya</button>
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
                            <input className="input" placeholder="Ish nomi, foydalanuvchi nomi, manzil yoki ID..." value={jobQuery} onChange={(e) => { setJobPage(1); setJobQuery(e.target.value) }} />
                            <select className="select" value={jobStatus} onChange={(e) => { setJobPage(1); setJobStatus(e.target.value) }}>
                                <option value="all">Barcha holatlar</option>
                                {Object.entries(statusLabel).slice(0, 6).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                                <option value="blocked">Bloklangan</option>
                            </select>
                        </div>
                        <div className="admin-table-wrap">
                            <table className="admin-table">
                                <thead><tr><th>ID</th><th>Ish</th><th>Buyurtmachi</th><th>Bajaruvchi</th><th>Narx</th><th>Holat</th><th>Manzil</th><th>Amal</th></tr></thead>
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
                        {!jobs.page.length && <div className="empty-state">Ish topilmadi.</div>}
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
                                        <tr key={item.id}><td>#{item.id}</td><td><strong>{item.name}</strong></td><td>{item.parent_name || "Asosiy kategoriya"}</td><td>{item.created_by || "Tizim"}</td><td><div className="admin-row-actions"><button className="btn btn-secondary admin-small-btn" onClick={() => editService(item)}>Tahrirlash</button><button className="btn btn-danger admin-small-btn" onClick={() => deleteService(item)}>O‘chirish</button></div></td></tr>
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
                                <thead><tr><th>ID</th><th>Yuboruvchi</th><th>Foydalanuvchi</th><th>Manba</th><th>Sabab</th><th>Tafsilot</th><th>Fayl</th><th>Sana</th><th>Holat / Amal</th></tr></thead>
                                <tbody>
                                    {reports.page.map((item) => (
                                        <tr key={item.id}>
                                            <td>#{item.id}</td><td>@{item.reporter_username || "—"}</td><td>@{item.reported_username || "—"}</td>
                                            <td>{item.message_id ? "Xabar #" + item.message_id : "Ish #" + (item.job_id || "—")}</td>
                                            <td><strong>{item.reason}</strong></td><td>{item.details || "—"}</td>
                                            <td>{item.attachment_url ? <button className="btn btn-secondary admin-small-btn" onClick={() => openReportAttachment(item)}>Fayl</button> : "—"}</td>
                                            <td>{formatTimeAgo(item.created_at)}</td>
                                            <td><span className={"admin-badge " + (item.status === "resolved" ? "success" : item.status === "rejected" ? "danger" : "neutral")}>{statusLabel[item.status] || item.status}</span><button className="btn btn-primary admin-small-btn" type="button" onClick={() => openReportReview(item)}>Ko‘rib chiqish</button></td>
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
                                <thead><tr><th>ID</th><th>Foydalanuvchi</th><th>Cheklov turi</th><th>Sabab</th><th>Berilgan</th><th>Tugash</th><th>Administrator</th><th>Amal</th></tr></thead>
                                <tbody>{filteredBlocks.page.map((item) => <tr key={item.id}>
                                    <td>#{item.id}</td><td><strong>@{item.username}</strong><small>Foydalanuvchi ID: #{item.user_id}</small></td>
                                    <td><span className={"admin-badge " + (item.active ? "danger" : "neutral")}>{item.block_label || blockLabels[item.block_type] || item.block_type}</span></td>
                                    <td>{item.reason}</td><td>{formatTimeAgo(item.created_at)}</td><td>{item.expires_at ? formatTimeAgo(item.expires_at) : "Muddatsiz"}</td><td>@{item.admin_username || "—"}</td>
                                    <td>{item.active ? <div className="admin-row-actions"><button className="btn btn-secondary admin-small-btn" onClick={() => reviseBlock(item)}>Muddat/sabab</button><button className="btn btn-secondary admin-small-btn" onClick={() => liftBlock(item)}>Olib tashlash</button></div> : "—"}</td>
                                </tr>)}</tbody>
                            </table>
                        </div>
                        {!filteredBlocks.page.length && <div className="empty-state">Cheklov topilmadi.</div>}
                        <Pager page={blockPage} pages={filteredBlocks.pages} total={filteredBlocks.all.length} onChange={setBlockPage} />
                    </div>
                )}

                {data && tab === "appeals" && (
                    <div className="admin-section">
                        <div className="admin-filters">
                            <input className="input" placeholder="Foydalanuvchi, ariza matni, sabab yoki cheklov ID..." value={appealQuery} onChange={(e) => { setAppealPage(1); setAppealQuery(e.target.value) }} />
                            <select className="select" value={appealStatus} onChange={(e) => { setAppealPage(1); setAppealStatus(e.target.value) }}><option value="all">Barcha statuslar</option><option value="open">Ochiq</option><option value="reviewing">Ko‘rib chiqilmoqda</option><option value="approved">Tasdiqlangan</option><option value="modified">Qisman tasdiqlangan</option><option value="rejected">Rad etilgan</option></select>
                        </div>
                        <div className="admin-table-wrap">
                            <table className="admin-table admin-appeal-table">
                                <thead><tr><th>Ariza</th><th>Foydalanuvchi</th><th>Cheklov</th><th>Cheklov sababi</th><th>Ariza matni</th><th>Vaqt</th><th>Holat</th><th>Amal</th></tr></thead>
                                <tbody>{filteredAppeals.page.map((item) => <tr key={item.id}>
                                    <td><strong>#{item.id}</strong><small>Cheklov #{item.block_id}</small></td>
                                    <td><strong>@{item.username}</strong><small>Foydalanuvchi ID: #{item.user_id}</small></td>
                                    <td><span className="admin-badge danger">{item.block_label || blockLabels[item.block_type] || item.block_type}</span><small>{item.expires_at ? "Tugaydi: " + formatTimeAgo(item.expires_at) : "Muddatsiz"}</small></td>
                                    <td>{item.block_reason}</td>
                                    <td className="admin-long-cell">{item.appeal_text}</td>
                                    <td>{formatTimeAgo(item.created_at)}</td>
                                    <td><span className={"admin-badge " + (item.status === "approved" ? "success" : item.status === "rejected" ? "danger" : "neutral")}>{statusLabel[item.status] || item.status}</span></td>
                                    <td><button className="btn btn-primary admin-small-btn" onClick={() => openAppealReview(item)}>Ko‘rib chiqish</button></td>
                                </tr>)}</tbody>
                            </table>
                        </div>
                        {!filteredAppeals.page.length && <div className="empty-state">Ariza topilmadi.</div>}
                        <Pager page={appealPage} pages={filteredAppeals.pages} total={filteredAppeals.all.length} onChange={setAppealPage} />
                    </div>
                )}

                {data && tab === "disputes" && (
                    <div className="admin-section">
                        <div className="admin-section-head">
                            <div><span>NIZOLAR MARKAZI</span><h2>Nizolarni ko‘rib chiqish</h2><p className="muted">Tomonlar, dalillar va nizo holatini shu bo‘limda boshqaring.</p></div>
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
                                        {item.admin_response && <p><strong>Administrator javobi:</strong> {item.admin_response}</p>}
                                        {item.decision && <p><strong>Hukm:</strong> {disputeDecisionLabels[item.decision] || item.decision}</p>}
                                        {item.payment_action && item.payment_action !== "none" && <p><strong>To‘lov chorasi:</strong> {disputePaymentActionLabels[item.payment_action] || item.payment_action}</p>}
                                        {item.job_action && item.job_action !== "none" && <p><strong>Ish bo‘yicha:</strong> {disputeJobActionLabels[item.job_action] || item.job_action}</p>}
                                        {item.sanction_type && item.sanction_type !== "none" && <p><strong>Qo‘llangan cheklov:</strong> {blockLabels[item.sanction_type] || item.sanction_type} · @{Number(item.sanction_user_id) === Number(item.opened_by) ? item.opened_by_username : item.against_username}</p>}
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
                                            <div className="form-row">
                                                <label className="field">
                                                    <span>Yakuniy hukm turi</span>
                                                    <select className="select" value={disputeReviewForm.decision} onChange={(e) => setDisputeReviewForm({ ...disputeReviewForm, decision: e.target.value })}>
                                                        <option value="">Hukmni tanlang...</option>
                                                        <option value="favor_opener">Nizo ochgan tomon foydasiga</option>
                                                        <option value="favor_opponent">Qarshi tomon foydasiga</option>
                                                        <option value="mutual_agreement">Tomonlar kelishuvi bilan</option>
                                                        <option value="insufficient_evidence">Dalillar yetarli emas</option>
                                                        <option value="policy_violation">Qoidabuzarlik aniqlandi</option>
                                                        <option value="no_violation">Qoidabuzarlik aniqlanmadi</option>
                                                    </select>
                                                </label>
                                                <label className="field">
                                                    <span>To‘lov bo‘yicha chora</span>
                                                    <select className="select" value={disputeReviewForm.payment_action} onChange={(e) => setDisputeReviewForm({ ...disputeReviewForm, payment_action: e.target.value })}>
                                                        <option value="none">To‘lovga tegmaslik</option>
                                                        <option value="refund_payer">Escrowdagi pulni buyurtmachiga qaytarish</option>
                                                        <option value="release_to_worker">Escrowdagi pulni ijrochiga o‘tkazish</option>
                                                    </select>
                                                </label>
                                            </div>
                                            <div className="form-row">
                                                <label className="field">
                                                    <span>Ish bo‘yicha chora</span>
                                                    <select className="select" value={disputeReviewForm.job_action} onChange={(e) => setDisputeReviewForm({ ...disputeReviewForm, job_action: e.target.value })}>
                                                        <option value="none">Ishni o‘zgarishsiz qoldirish</option>
                                                        <option value="block">Ishni bloklash</option>
                                                    </select>
                                                </label>
                                                <label className="field">
                                                    <span>Kimga cheklov qo‘yiladi?</span>
                                                    <select className="select" value={disputeReviewForm.sanction_target} onChange={(e) => setDisputeReviewForm({ ...disputeReviewForm, sanction_target: e.target.value })}>
                                                        <option value="opener">Nizo ochgan: @{reviewingDispute.opened_by_username || "foydalanuvchi"}</option>
                                                        <option value="opponent">Qarshi tomon: @{reviewingDispute.against_username || "foydalanuvchi"}</option>
                                                    </select>
                                                </label>
                                            </div>
                                            <div className="form-row">
                                                <label className="field">
                                                    <span>Foydalanuvchi chorasi</span>
                                                    <select className="select" value={disputeReviewForm.sanction_type} onChange={(e) => setDisputeReviewForm({ ...disputeReviewForm, sanction_type: e.target.value })}>
                                                        <option value="none">Cheklov qo‘llamaslik</option>
                                                        <option value="chat">Chatdan vaqtincha cheklash</option>
                                                        <option value="job_creation">Ish yaratishni cheklash</option>
                                                        <option value="job_accept">Ish qabul qilishni cheklash</option>
                                                        <option value="proposal">Taklif yuborishni cheklash</option>
                                                        <option value="rating">Baholashni cheklash</option>
                                                        <option value="withdrawal">Mablag‘ yechishni cheklash</option>
                                                        <option value="full">To‘liq akkaunt bloki</option>
                                                    </select>
                                                </label>
                                                <label className="field">
                                                    <span>Cheklov muddati</span>
                                                    <select className="select" disabled={disputeReviewForm.sanction_type === "none"} value={disputeReviewForm.sanction_duration_minutes} onChange={(e) => setDisputeReviewForm({ ...disputeReviewForm, sanction_duration_minutes: e.target.value })}>
                                                        <option value="60">1 soat</option>
                                                        <option value="1440">1 kun</option>
                                                        <option value="10080">7 kun</option>
                                                        <option value="43200">30 kun</option>
                                                        <option value="525600">365 kun</option>
                                                        <option value="0">Muddatsiz</option>
                                                    </select>
                                                </label>
                                            </div>
                                            <label className="field">
                                                <span>Administrator javobi va qaror asoslari</span>
                                                <textarea className="textarea" rows="4" maxLength="3000" required={["resolved", "rejected"].includes(disputeReviewForm.status)} value={disputeReviewForm.admin_response} onChange={(e) => setDisputeReviewForm({ ...disputeReviewForm, admin_response: e.target.value })} placeholder="Dalillar, qoida bandi va qaror sababini yozing..." />
                                            </label>
                                            <p className="muted">Pul harakati faqat escrowda ushlab turilgan to‘lovga qo‘llanadi. Yakuniy hukm bilan tanlangan ish yoki akkaunt chorasi ham bajariladi.</p>
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
                                    <thead><tr><th>ID</th><th>Foydalanuvchi</th><th>Tur</th><th>Summa</th><th>Amaldan keyingi balans</th><th>Tavsif</th><th>Sana</th></tr></thead>
                                    <tbody>{(finance?.transactions || []).slice(0, 40).map((item) => <tr key={item.id}><td>#{item.id}</td><td>@{item.username}</td><td><span className="admin-badge neutral">{item.type}</span></td><td className={Number(item.amount) >= 0 ? "admin-amount-positive" : "admin-amount-negative"}>{Number(item.amount) >= 0 ? "+" : ""}{money(item.amount)} UZS</td><td>{money(item.balance_after)} UZS</td><td>{item.description}</td><td>{formatTimeAgo(item.created_at)}</td></tr>)}</tbody>
                                </table>
                            </div>
                            {!finance?.transactions?.length && <div className="empty-state">Tranzaksiyalar yo‘q.</div>}
                        </div>
                        <div className="admin-subsection">
                            <div className="admin-section-head"><div><span>PAYMENT ACTIONS</span><h2>Eskroudagi to‘lovlar</h2><p className="muted">Faqat ushlab turilgan to‘lovlar bo‘yicha sabab bilan qaror chiqaring.</p></div></div>
                            <div className="admin-table-wrap">
                                <table className="admin-table">
                                    <thead><tr><th>ID</th><th>Ish</th><th>To‘lovchi</th><th>Ijrochi</th><th>Summa</th><th>Holat</th><th>Amallar</th></tr></thead>
                                    <tbody>{(finance?.payments || []).map((item) => <tr key={item.id}>
                                        <td>#{item.id}</td><td>#{item.job_id}<small>{statusLabel[item.job_status] || item.job_status || "—"}</small></td>
                                        <td>@{item.payer_username}</td><td>@{item.payee_username}</td><td><strong>{money(item.amount)} {item.currency || "UZS"}</strong></td>
                                        <td><span className={"admin-badge " + (item.status === "held" ? "danger" : "neutral")}>{statusLabel[item.status] || item.status}</span></td>
                                        <td>{item.status === "held" ? <div className="admin-row-actions"><button className="btn btn-secondary admin-small-btn" onClick={() => actOnPayment(item, "refund")}>Qaytarish</button><button className="btn btn-primary admin-small-btn" disabled={!["pending_finish", "finished"].includes(item.job_status)} title={!["pending_finish", "finished"].includes(item.job_status) ? "To‘lovni faqat yakunlash bosqichidagi ishda chiqarish mumkin" : ""} onClick={() => actOnPayment(item, "release")}>Ijrochiga o‘tkazish</button></div> : "—"}</td>
                                    </tr>)}</tbody>
                                </table>
                            </div>
                            {!finance?.payments?.length && <div className="empty-state">To‘lov topilmadi.</div>}
                        </div>
                    </div>
                )}

                {data && tab === "ratings" && (
                    <div className="admin-section">
                        <div className="admin-filters"><input className="input" placeholder="Username, izoh yoki job ID..." value={ratingQuery} onChange={(e) => { setRatingPage(1); setRatingQuery(e.target.value) }} /></div>
                        <div className="admin-table-wrap">
                            <table className="admin-table">
                                <thead><tr><th>ID</th><th>Ish</th><th>Kimdan</th><th>Kimga</th><th>Baho</th><th>Izoh</th><th>Amal</th></tr></thead>
                                <tbody>{ratings.page.map((item) => <tr key={item.id}><td>#{item.id}</td><td>#{item.job_id}</td><td>@{item.from_username || "—"}</td><td>@{item.to_username || "—"}</td><td><strong>{item.score}/10</strong></td><td>{item.comment || "—"}</td><td><button className="btn btn-danger admin-small-btn" onClick={() => deleteRating(item)}>O‘chirish</button></td></tr>)}</tbody>
                            </table>
                        </div>
                        {!ratings.page.length && <div className="empty-state">Baho topilmadi.</div>}
                        <Pager page={ratingPage} pages={ratings.pages} total={ratings.all.length} onChange={setRatingPage} />
                    </div>
                )}

                {data && tab === "audit" && (
                    <div className="admin-section">
                        <div className="admin-filters"><input className="input" placeholder="Action, target, admin yoki tafsilot..." onChange={(e) => { setAuditPage(1); loadAudit(1, e.target.value) }} /><button className="btn btn-secondary admin-small-btn" type="button" onClick={exportAuditCsv}>Joriy sahifani CSV</button></div>
                        <div className="admin-table-wrap">
                            <table className="admin-table">
                                <thead><tr><th>ID</th><th>Administrator</th><th>Amal</th><th>Obyekt</th><th>Tafsilot</th><th>Sana</th></tr></thead>
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
                            <div className="admin-section-head"><div><span>XAVFSIZLIK</span><h2>Admin xavfsizligi</h2></div></div>
                            <div className="admin-setting-list"><div><span>Faqat administrator uchun API</span><strong>Faol</strong></div><div><span>Audit log</span><strong>Faol</strong></div><div><span>Token versiyasini tekshirish</span><strong>Faol</strong></div><div><span>Foydalanuvchini cheklash</span><strong>Faol</strong></div><div><span>Shikoyatlarni ko‘rib chiqish</span><strong>Faol</strong></div></div>
                        </div>
                    </div>
                )}
            </div>

            {moderatingUser && (
                <div className="admin-modal-backdrop" onClick={() => setModeratingUser(null)}>
                    <div className="card admin-modal admin-moderation-modal" onClick={(e) => e.stopPropagation()}>
                        <div className="admin-modal-head">
                            <div><span className="admin-search-eyebrow">CHEKLOVLARNI BOSHQARISH</span><h3>@{moderatingUser.username}</h3><p>Foydalanuvchi ID: #{moderatingUser.id} · cheklovlarni boshqarish</p></div>
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
                                <label>Cheklov turi<select className="select" value={blockForm.block_type} onChange={(e) => setBlockForm({ ...blockForm, block_type: e.target.value })}>{Object.entries(blockLabels).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
                                <label>Muddati<select className="select" value={blockForm.duration_minutes} onChange={(e) => setBlockForm({ ...blockForm, duration_minutes: e.target.value })}><option value="60">1 soat</option><option value="360">6 soat</option><option value="1440">1 kun</option><option value="10080">7 kun</option><option value="43200">30 kun</option><option value="">Muddatsiz</option></select></label>
                                <label>Nega block qilinyapti<textarea className="input admin-textarea" maxLength="2000" value={blockForm.reason} onChange={(e) => setBlockForm({ ...blockForm, reason: e.target.value })} placeholder="Aniq va tushunarli sabab yozing..." /></label>
                                <button className="btn btn-danger" type="submit" disabled={!blockForm.reason.trim()}>Cheklov qo‘yish</button>
                            </form>
                        </div>
                    </div>
                </div>
            )}

            {reviewingReport && (
                <div className="admin-modal-backdrop" onClick={() => setReviewingReport(null)}>
                    <div className="card admin-modal report-review-modal" onClick={(e) => e.stopPropagation()}>
                        <div className="admin-modal-head"><div><span className="admin-search-eyebrow">REPORT #{reviewingReport.id}</span><h3>Shikoyat bo‘yicha qaror</h3><p>@{reviewingReport.reporter_username || "—"} → @{reviewingReport.reported_username || "—"}</p></div><button className="admin-modal-close" onClick={() => setReviewingReport(null)}>×</button></div>
                        <div className="admin-appeal-detail">
                            <div><span>SABAB</span><p>{reviewingReport.reason}</p></div>
                            <div><span>TAFSILOT</span><p>{reviewingReport.details || "Tafsilot berilmagan."}</p></div>
                            <div><span>MANBA</span><p>{reviewingReport.message_id ? "Xabar #" + reviewingReport.message_id : "Ish #" + (reviewingReport.job_id || "—")}</p></div>
                        </div>
                        {["resolved", "rejected"].includes(reviewingReport.status) && reportReviewForm.status === "reviewing" &&
                            (!reviewingReport.decision || !String(reviewingReport.admin_response || "").trim()) &&
                            <p className="muted" role="status">Bu shikoyat eski versiyada yakunlangan, lekin hukm tafsilotlari saqlanmagan. Uni qayta ko‘rib chiqish uchun holat vaqtincha “Ko‘rib chiqilmoqda”ga o‘rnatildi.</p>}
                        {reportReviewError && <div className="notice warn" role="alert" style={{ marginBottom: 12 }}>{reportReviewError}</div>}
                        <form className="admin-user-form" noValidate onSubmit={submitReportReview}>
                            <label>Holat<select className="select" value={reportReviewForm.status} onChange={(e) => setReportReviewForm({ ...reportReviewForm, status: e.target.value })}><option value="reviewing">Ko‘rib chiqilmoqda</option><option value="resolved">Hal qilindi</option><option value="rejected">Rad etildi</option><option value="open">Ochiq qoldirish</option></select></label>
                            <label>Hukm turi<select className="select" value={reportReviewForm.decision} onChange={(e) => setReportReviewForm({ ...reportReviewForm, decision: e.target.value })}><option value="">Hukmni tanlang...</option><option value="violation">Qoidabuzarlik aniqlandi</option><option value="no_violation">Qoidabuzarlik aniqlanmadi</option><option value="insufficient_evidence">Dalil yetarli emas</option><option value="duplicate">Takroriy shikoyat</option><option value="mistake">Xato shikoyat</option><option value="other">Boshqa holat</option></select></label>
                            <div className="form-row">
                                <label className="field"><span>To‘lov chorasi</span><select className="select" value={reportReviewForm.payment_action} onChange={(e) => setReportReviewForm({ ...reportReviewForm, payment_action: e.target.value })}><option value="none">To‘lovga tegmaslik</option><option value="refund_payer" disabled={!reviewingReport.job_id || Boolean(reviewingReport.message_id)}>Buyurtmachiga qaytarish</option><option value="release_to_worker" disabled={!reviewingReport.job_id || Boolean(reviewingReport.message_id)}>Ijrochiga o‘tkazish</option></select></label>
                                <label className="field"><span>Ish chorasi</span><select className="select" value={reportReviewForm.job_action} onChange={(e) => setReportReviewForm({ ...reportReviewForm, job_action: e.target.value })}><option value="none">O‘zgarishsiz qoldirish</option><option value="block" disabled={!reviewingReport.job_id}>Ishni bloklash</option></select></label>
                            </div>
                            <label>Ogohlantirish kimga yuborilsin?<select className="select" value={reportReviewForm.notify_target} onChange={(e) => setReportReviewForm({ ...reportReviewForm, notify_target: e.target.value })}><option value="none">Ogohlantirish yubormaslik</option><option value="reporter">Shikoyat yuboruvchiga</option><option value="reported" disabled={!reviewingReport.reported_username}>Shikoyat qilingan foydalanuvchiga</option><option value="both" disabled={!reviewingReport.reported_username}>Ikkalasiga</option></select></label>
                            <div className="form-row">
                                <label className="field"><span>Cheklov kimga qo‘yiladi?</span><select className="select" value={reportReviewForm.sanction_target} onChange={(e) => setReportReviewForm({ ...reportReviewForm, sanction_target: e.target.value })}><option value="reported" disabled={!reviewingReport.reported_username}>@{reviewingReport.reported_username || "foydalanuvchi"}</option><option value="reporter">@{reviewingReport.reporter_username || "yuboruvchi"}</option></select></label>
                                <label className="field"><span>Foydalanuvchi chorasi</span><select className="select" value={reportReviewForm.sanction_type} onChange={(e) => setReportReviewForm({ ...reportReviewForm, sanction_type: e.target.value })}><option value="none">Cheklov qo‘llamaslik</option><option value="chat">Chat</option><option value="job_creation">Ish yaratish</option><option value="job_accept">Ish qabul qilish</option><option value="proposal">Taklif yuborish</option><option value="rating">Baholash</option><option value="withdrawal">Pul yechish</option><option value="full">To‘liq blok</option></select></label>
                            </div>
                            <label>Cheklov muddati<select className="select" disabled={reportReviewForm.sanction_type === "none"} value={reportReviewForm.sanction_duration_minutes} onChange={(e) => setReportReviewForm({ ...reportReviewForm, sanction_duration_minutes: e.target.value })}><option value="1">1 daqiqa</option><option value="5">5 daqiqa</option><option value="15">15 daqiqa</option><option value="30">30 daqiqa</option><option value="60">1 soat</option><option value="360">6 soat</option><option value="1440">1 kun</option><option value="10080">7 kun</option><option value="43200">30 kun</option><option value="525600">365 kun</option><option value="0">Muddatsiz</option></select></label>
                            <label>Qaror asosi va izoh<textarea className="input admin-textarea" maxLength="3000" required={["resolved", "rejected"].includes(reportReviewForm.status)} value={reportReviewForm.admin_response} onChange={(e) => setReportReviewForm({ ...reportReviewForm, admin_response: e.target.value })} placeholder="Dalillar va qoida bandi asosida tushuntiring..." /></label>
                            <p className="muted">To‘lov amallari faqat escrowda ushlangan to‘lovda ishlaydi. Qaytarish yoki bloklash qarorini berishdan oldin dalillarni tekshiring.</p>
                            <div className="admin-modal-actions"><button type="button" className="btn btn-secondary" disabled={reportReviewSaving} onClick={() => setReviewingReport(null)}>Yopish</button><button type="submit" className="btn btn-primary" disabled={reportReviewSaving}>{reportReviewSaving ? "Saqlanmoqda..." : "Qarorni saqlash"}</button></div>
                        </form>
                    </div>
                </div>
            )}

            {verifyingUser && (
                <div className="admin-modal-backdrop" onClick={() => setVerifyingUser(null)}>
                    <div className="card admin-modal" onClick={(e) => e.stopPropagation()}>
                        <div className="admin-modal-head"><div><span className="admin-search-eyebrow">USER VERIFICATION</span><h3>@{verifyingUser.username}</h3><p>Verifikatsiya belgilarini tasdiqlash yoki bekor qilish</p></div><button className="admin-modal-close" onClick={() => setVerifyingUser(null)}>×</button></div>
                        <form className="admin-user-form" onSubmit={saveVerification}>
                            <label><input type="checkbox" checked={verificationForm.email_verified} onChange={(e) => setVerificationForm({ ...verificationForm, email_verified: e.target.checked })} /> Email tasdiqlangan</label>
                            <label><input type="checkbox" checked={verificationForm.phone_verified} onChange={(e) => setVerificationForm({ ...verificationForm, phone_verified: e.target.checked })} /> Telefon tasdiqlangan</label>
                            <label><input type="checkbox" checked={verificationForm.identity_verified} onChange={(e) => setVerificationForm({ ...verificationForm, identity_verified: e.target.checked })} /> Shaxs tasdiqlangan</label>
                            <p className="muted">Belgini faqat tegishli dalilni tekshirgandan keyin yoqing.</p>
                            <div className="admin-modal-actions"><button type="button" className="btn btn-secondary" onClick={() => setVerifyingUser(null)}>Bekor qilish</button><button type="submit" className="btn btn-primary">Saqlash</button></div>
                        </form>
                    </div>
                </div>
            )}

            {editingService && (
                <div className="admin-modal-backdrop" onClick={() => setEditingService(null)}>
                    <div className="card admin-modal" onClick={(e) => e.stopPropagation()}>
                        <div className="admin-modal-head"><div><span className="admin-search-eyebrow">SERVICE MANAGEMENT</span><h3>Xizmatni tahrirlash</h3><p>#{editingService.id} · {editingService.name}</p></div><button className="admin-modal-close" onClick={() => setEditingService(null)}>×</button></div>
                        <form className="admin-user-form" onSubmit={saveServiceEdit}>
                            <label>Xizmat nomi<input className="input" maxLength="120" value={serviceEditForm.name} onChange={(e) => setServiceEditForm({ ...serviceEditForm, name: e.target.value })} required /></label>
                            <label>Ota kategoriya<select className="select" value={serviceEditForm.parent_id} onChange={(e) => setServiceEditForm({ ...serviceEditForm, parent_id: e.target.value })}><option value="">Asosiy kategoriya</option>{serviceTree.filter((item) => Number(item.id) !== Number(editingService.id)).map((item) => <option key={item.id} value={item.id}>{"— ".repeat(item.depth)}{item.name}</option>)}</select></label>
                            <p className="muted">O‘z ichidagi kategoriyalardan birini ota kategoriya qilib tanlab bo‘lmaydi. Backend tekshiruvi buni to‘sadi.</p>
                            <div className="admin-modal-actions"><button type="button" className="btn btn-secondary" onClick={() => setEditingService(null)}>Bekor qilish</button><button type="submit" className="btn btn-primary">O‘zgarishni saqlash</button></div>
                        </form>
                    </div>
                </div>
            )}

            {reviewingAppeal && (
                <div className="admin-modal-backdrop" onClick={() => setReviewingAppeal(null)}>
                    <div className="card admin-modal appeal-review-modal" onClick={(e) => e.stopPropagation()}>
                        <div className="admin-modal-head"><div><span className="admin-search-eyebrow">ARIZA #{reviewingAppeal.id}</span><h3>@{reviewingAppeal.username}</h3><p>{blockLabels[reviewingAppeal.block_type] || reviewingAppeal.block_type} · Cheklov #{reviewingAppeal.block_id}</p></div><button className="admin-modal-close" onClick={() => setReviewingAppeal(null)}>×</button></div>
                        <div className="admin-appeal-detail">
                            <div><span>BLOCK SABABI</span><p>{reviewingAppeal.block_reason}</p></div>
                            <div><span>APPEAL MATNI</span><p>{reviewingAppeal.appeal_text}</p></div>
                            <div className="admin-appeal-meta"><span>Berilgan: {formatTimeAgo(reviewingAppeal.created_at)}</span><span>Cheklov tugashi: {reviewingAppeal.expires_at ? formatTimeAgo(reviewingAppeal.expires_at) : "Muddatsiz"}</span></div>
                        </div>
                        <form className="admin-user-form" onSubmit={submitAppealReview}>
                            <label>Qaror<select className="select" value={appealReviewForm.status} disabled={["approved", "rejected", "modified"].includes(reviewingAppeal.status)} onChange={(e) => setAppealReviewForm({ ...appealReviewForm, status: e.target.value })}><option value="reviewing">Ko‘rib chiqilmoqda</option><option value="approved">To‘liq tasdiqlash — cheklovni olib tashlash</option><option value="rejected">Rad etish — cheklov qoladi</option><option value="modified">Qisman tasdiqlash — cheklovni yengillashtirish</option></select></label>
                            {appealReviewForm.status === "modified" && <><label>Qanday yengillashtiriladi?<select className="select" value={appealReviewForm.block_action} onChange={(e) => setAppealReviewForm({ ...appealReviewForm, block_action: e.target.value })}><option value="reduce_duration">Faqat muddatini qisqartirish</option><option value="change_type" disabled={reviewingAppeal.block_type !== "full"}>Cheklov turini yengillashtirish (faqat to‘liq blokdan)</option></select></label>{appealReviewForm.block_action === "change_type" && <label>Yangi cheklov turi<select className="select" value={appealReviewForm.new_block_type} onChange={(e) => setAppealReviewForm({ ...appealReviewForm, new_block_type: e.target.value })}><option value="chat">Chat cheklovi</option><option value="job_creation">Ish yaratish cheklovi</option><option value="job_accept">Ish qabul qilish cheklovi</option><option value="proposal">Taklif yuborish cheklovi</option><option value="rating">Baholash cheklovi</option><option value="withdrawal">Pul yechish cheklovi</option></select></label>}<label>Yangi muddat<select className="select" value={appealReviewForm.duration_minutes} onChange={(e) => setAppealReviewForm({ ...appealReviewForm, duration_minutes: e.target.value })}><option value="1">1 daqiqa</option><option value="5">5 daqiqa</option><option value="15">15 daqiqa</option><option value="30">30 daqiqa</option><option value="60">1 soat</option><option value="360">6 soat</option><option value="1440">1 kun</option><option value="10080">7 kun</option><option value="43200">30 kun</option><option value="525600">365 kun</option></select></label></>}
                            <label>Admin izohi<textarea className="input admin-textarea" maxLength="3000" value={appealReviewForm.admin_response} onChange={(e) => setAppealReviewForm({ ...appealReviewForm, admin_response: e.target.value })} placeholder="Qaroringiz sababini foydalanuvchiga tushuntiring..." /></label>
                            <div className="admin-modal-actions"><button type="button" className="btn btn-secondary" onClick={() => setReviewingAppeal(null)}>Yopish</button><button type="submit" className="btn btn-primary" disabled={["approved", "rejected", "modified"].includes(reviewingAppeal.status)}>Qarorni saqlash</button></div>
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

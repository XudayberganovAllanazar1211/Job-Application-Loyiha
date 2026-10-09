import { useState, useEffect, useRef } from "react"
import AppLayout from "../components/AppLayout"
import VerificationBadges from "../components/VerificationBadges"
import { api } from "../api"
import { formatTimeAgo } from "../utils/time"

function buildServiceTree(services) {
    const nodes = Object.fromEntries(services.map((service) => [
        String(service.id),
        { ...service, children: [] }
    ]))
    const roots = []

    services.forEach((service) => {
        const node = nodes[String(service.id)]
        if (service.parent_id == null) roots.push(node)
        else if (nodes[String(service.parent_id)]) nodes[String(service.parent_id)].children.push(node)
    })

    return roots
}

function ServiceNode({ node, level, selected, onSelect }) {
    const [open, setOpen] = useState(false)
    const hasChildren = node.children.length > 0

    return (
        <div>
            <div className="service-tree-row" style={{ paddingLeft: 10 + level * 20 }}>
                {hasChildren ? (
                    <button type="button" className="service-tree-toggle" onClick={() => setOpen(!open)}>
                        {open ? "▾" : "▸"}
                    </button>
                ) : <span className="service-tree-spacer" />}
                <button
                    type="button"
                    className={selected.includes(String(node.id)) ? "service-tree-item selected" : "service-tree-item"}
                    disabled={hasChildren}
                    onClick={() => onSelect(node)}
                >
                    {node.name}
                </button>
            </div>
            {open && hasChildren && node.children.map((child) => (
                <ServiceNode
                    key={child.id}
                    node={child}
                    level={level + 1}
                    selected={selected}
                    onSelect={onSelect}
                />
            ))}
        </div>
    )
}

export default function Profile() {
    const [form, setForm] = useState({
        first_name: "",
        last_name: "",
        birthday: "",
        username: "",
        email: "",
        bio: "",
        created_at: "",
        created_jobs_count: 0,
        completed_jobs_count: 0,
        avg_rating: 0,
        balance: 0,
        role: "user"
    })

    const [savedForm, setSavedForm] = useState(null)
    const [skills, setSkills] = useState([])
    const [savedSkills, setSavedSkills] = useState([])
    const [newSkill, setNewSkill] = useState("")
    const [services, setServices] = useState([])
    const [serviceSearch, setServiceSearch] = useState("")
    const [showServicePicker, setShowServicePicker] = useState(false)
    const [isEditing, setIsEditing] = useState(false)
    const [notice, setNotice] = useState("")
    const [loading, setLoading] = useState(false)
    const [initialLoad, setInitialLoad] = useState(true)
    const [avatarUrl, setAvatarUrl] = useState("")
    const [avatarLoading, setAvatarLoading] = useState(false)
    const [cropImageUrl, setCropImageUrl] = useState("")
    const [cropZoom, setCropZoom] = useState(1)
    const [cropOffset, setCropOffset] = useState({ x: 0, y: 0 })
    const [cropImageSize, setCropImageSize] = useState({ width: 500, height: 500 })
    const [cropDragging, setCropDragging] = useState(false)
    const [walletTransactions, setWalletTransactions] = useState([])
    const [portfolio, setPortfolio] = useState([])
    const [portfolioForm, setPortfolioForm] = useState({ title: "", description: "", url: "" })
    const [portfolioFile, setPortfolioFile] = useState(null)
    const [portfolioLoading, setPortfolioLoading] = useState(false)
    const portfolioFileRef = useRef(null)
    const [walletLoading, setWalletLoading] = useState(true)
    const [withdrawOpen, setWithdrawOpen] = useState(false)
    const [withdrawAmount, setWithdrawAmount] = useState("")
    const [withdrawLoading, setWithdrawLoading] = useState(false)
    const cropImageRef = useRef(null)
    const cropAreaRef = useRef(null)
    const cropDragRef = useRef({ x: 0, y: 0, startX: 0, startY: 0 })

    const serviceTree = buildServiceTree(services)
    const filteredServices = services.filter((service) => service.name.toLowerCase().includes(serviceSearch.trim().toLowerCase()))
    const exactSearchServices = filteredServices.filter((service) => !services.some((item) => String(item.parent_id) === String(service.id)))

    useEffect(() => {
        const loadProfile = async () => {
            const token = localStorage.getItem("token")
            const result = await api("/profile", { token })

            if (result?.id) {
                const profile = {
                    first_name: result.first_name || "",
                    last_name: result.last_name || "",
                    birthday: result.birthday || "",
                    username: result.username || "",
                    email: result.email || "",
                    bio: result.bio || "",
                    created_at: result.created_at || "",
                    created_jobs_count: result.created_jobs_count || 0,
                    completed_jobs_count: result.completed_jobs_count || 0,
                    avg_rating: result.avg_rating || 0,
                    balance: Number(result.balance) || 0,
                    role: result.role || "user",
                    verification: result.verification || { badges: [] },
                    reputation: result.reputation || { badges: [], reviews_count: 0, success_rate: 0, completed_worker_jobs: 0 }
                }

                const profileSkills = Array.isArray(result.skills)
                    ? result.skills
                    : typeof result.skills === "string" && result.skills.trim()
                        ? result.skills.split(",").map((skill) => skill.trim()).filter(Boolean)
                        : []

                setForm(profile)
                setSavedForm(profile)
                setSkills(profileSkills)
                setSavedSkills(profileSkills)
                setAvatarUrl(result.avatar_url || "")
                setPortfolio(Array.isArray(result.portfolio) ? result.portfolio : [])
            }

            setInitialLoad(false)
        }

        loadProfile()
    }, [])

    useEffect(() => {
        const loadWallet = async () => {
            const token = localStorage.getItem("token") || ""
            const result = await api("/wallet", { token })
            if (result && typeof result === "object") {
                setForm((current) => ({ ...current, balance: Number(result.balance) || 0 }))
                setWalletTransactions(Array.isArray(result.transactions) ? result.transactions : [])
            }
            setWalletLoading(false)
        }
        loadWallet()
    }, [])
    useEffect(() => {
        const loadServices = async () => {
            const result = await api("/services", { token: localStorage.getItem("token") || "" })
            if (Array.isArray(result)) setServices(result)
        }
        loadServices()
    }, [])

    const formatWalletDate = formatTimeAgo

    const submitWithdrawal = async (event) => {
        event.preventDefault()
        const amount = Number(withdrawAmount)
        if (!Number.isFinite(amount) || amount <= 0) { setNotice("Yechib olish summasini to‘g‘ri kiriting"); return }
        if (amount > Number(form.balance || 0)) { setNotice("Balansda yetarli mablag‘ yo‘q"); return }
        setWithdrawLoading(true)
        const token = localStorage.getItem("token") || ""
        const result = await api("/wallet/withdraw", { method: "POST", body: { amount }, token })
        if (result?.msg === "ok") {
            setForm((current) => ({ ...current, balance: Number(result.balance) || 0 }))
            setWithdrawAmount("")
            setWithdrawOpen(false)
            setNotice(`Yechib olish muvaffaqiyatli bajarildi. Qo‘shimcha withdrawal komissiyasi: 0 UZS.`)
            const wallet = await api("/wallet", { token })
            if (wallet && typeof wallet === "object") setWalletTransactions(Array.isArray(wallet.transactions) ? wallet.transactions : [])
        } else {
            setNotice(result?.msg || "Yechib olishda xatolik yuz berdi")
        }
        setWithdrawLoading(false)
    }
    const startEditing = () => {
        setSavedForm({ ...form })
        setSavedSkills([...skills])
        setServiceSearch("")
        setShowServicePicker(false)
        setNotice("")
        setIsEditing(true)
    }

    const cancelEditing = () => {
        if (savedForm) setForm({ ...savedForm })
        setSkills([...savedSkills])
        setNewSkill("")
        setServiceSearch("")
        setShowServicePicker(false)
        setNotice("")
        setIsEditing(false)
    }

    const submit = async (e) => {
        e.preventDefault()
        setNotice("")
        setLoading(true)

        const token = localStorage.getItem("token")
        const result = await api("/profile", {
            method: "PUT",
            token,
            body: {
                ...form,
                skills: skills.join(", ")
            }
        })

        setLoading(false)

        if (result?.msg === "ok") {
            const updatedUser = {
                ...(JSON.parse(localStorage.getItem("user") || "null") || {}),
                ...form,
                skills: skills.join(", ")
            }
            localStorage.setItem("user", JSON.stringify(updatedUser))

            setSavedForm({ ...form })
            setSavedSkills([...skills])
            setServiceSearch("")
            setShowServicePicker(false)
            setNotice("Profil muvaffaqiyatli yangilandi")
            setIsEditing(false)
            setTimeout(() => setNotice(""), 3000)
        } else {
            setNotice(result?.msg || "Profilni yangilashda xatolik yuz berdi")
        }
    }

    const addServiceSkill = (service) => {
        if (!skills.some((item) => item.toLowerCase() === service.name.toLowerCase())) {
            setSkills([...skills, service.name])
        }
        setServiceSearch("")
        setShowServicePicker(false)
    }

    const closeCropModal = () => {
        if (cropImageUrl) URL.revokeObjectURL(cropImageUrl)
        setCropImageUrl("")
        setCropZoom(1)
        setCropOffset({ x: 0, y: 0 })
        setCropImageSize({ width: 500, height: 500 })
        setCropDragging(false)
    }

    const selectAvatar = (event) => {
        const file = event.target.files?.[0]
        event.target.value = ""
        if (!file) return

        const allowedTypes = ["image/png", "image/jpeg", "image/webp"]
        if (!allowedTypes.includes(file.type)) {
            setNotice("Faqat PNG, JPG, JPEG yoki WEBP rasm yuklash mumkin")
            return
        }

        if (file.size > 5 * 1024 * 1024) {
            setNotice("Rasm hajmi 5 MB dan oshmasligi kerak")
            return
        }

        if (cropImageUrl) URL.revokeObjectURL(cropImageUrl)
        setCropImageUrl(URL.createObjectURL(file))
        setCropZoom(1)
        setCropOffset({ x: 0, y: 0 })
        setCropImageSize({ width: 500, height: 500 })
        setCropDragging(false)
        setNotice("")
    }

    const handleCropPointerDown = (event) => {
        event.preventDefault()
        const pointX = event.clientX
        const pointY = event.clientY
        cropDragRef.current = {
            x: cropOffset.x,
            y: cropOffset.y,
            startX: pointX,
            startY: pointY
        }
        setCropDragging(true)
        event.currentTarget.setPointerCapture?.(event.pointerId)
    }

    const handleCropPointerMove = (event) => {
        if (!cropDragging) return

        const area = cropAreaRef.current
        const image = cropImageRef.current
        if (!area || !image) return

        const zoomedWidth = image.offsetWidth * cropZoom
        const zoomedHeight = image.offsetHeight * cropZoom
        const maxX = Math.max(0, (zoomedWidth - area.clientWidth) / 2)
        const maxY = Math.max(0, (zoomedHeight - area.clientHeight) / 2)

        const nextX = cropDragRef.current.x + event.clientX - cropDragRef.current.startX
        const nextY = cropDragRef.current.y + event.clientY - cropDragRef.current.startY

        setCropOffset({
            x: Math.max(-maxX, Math.min(maxX, nextX)),
            y: Math.max(-maxY, Math.min(maxY, nextY))
        })
    }

    const handleCropPointerUp = (event) => {
        setCropDragging(false)
        event.currentTarget.releasePointerCapture?.(event.pointerId)
    }

    const handleCropZoomChange = (event) => {
        const nextZoom = Number(event.target.value)
        const previousZoom = cropZoom
        if (previousZoom <= 0) {
            setCropZoom(nextZoom)
            return
        }

        const ratio = nextZoom / previousZoom
        const area = cropAreaRef.current
        const image = cropImageRef.current
        if (!area || !image) {
            setCropZoom(nextZoom)
            return
        }

        const zoomedWidth = image.offsetWidth * nextZoom
        const zoomedHeight = image.offsetHeight * nextZoom
        const maxX = Math.max(0, (zoomedWidth - area.clientWidth) / 2)
        const maxY = Math.max(0, (zoomedHeight - area.clientHeight) / 2)

        setCropZoom(nextZoom)
        setCropOffset({
            x: Math.max(-maxX, Math.min(maxX, cropOffset.x * ratio)),
            y: Math.max(-maxY, Math.min(maxY, cropOffset.y * ratio))
        })
    }

    const resetCrop = () => {
        setCropZoom(1)
        setCropOffset({ x: 0, y: 0 })
    }

    const saveCroppedAvatar = async () => {
        const area = cropAreaRef.current
        const image = cropImageRef.current
        if (!area || !image || !cropImageUrl) return

        setAvatarLoading(true)
        setNotice("")

        try {
            const areaSize = area.clientWidth
            const naturalWidth = image.naturalWidth
            const naturalHeight = image.naturalHeight
            if (!areaSize || !naturalWidth || !naturalHeight) {
                setNotice("Rasmni tayyorlashda xatolik yuz berdi")
                return
            }

            const baseScale = Math.max(areaSize / naturalWidth, areaSize / naturalHeight)
            const scale = baseScale * cropZoom
            const displayedWidth = naturalWidth * scale
            const displayedHeight = naturalHeight * scale
            const centerX = areaSize / 2 + cropOffset.x
            const centerY = areaSize / 2 + cropOffset.y
            const left = centerX - displayedWidth / 2
            const top = centerY - displayedHeight / 2

            const sourceX = Math.max(0, -left / scale)
            const sourceY = Math.max(0, -top / scale)
            const sourceSize = Math.min(
                naturalWidth - sourceX,
                naturalHeight - sourceY,
                areaSize / scale
            )

            if (sourceSize <= 0) {
                setNotice("Rasmni kesishda xatolik yuz berdi")
                return
            }

            const canvas = document.createElement("canvas")
            canvas.width = 512
            canvas.height = 512
            const context = canvas.getContext("2d")

            if (!context) {
                setNotice("Rasmni tayyorlashda xatolik yuz berdi")
                return
            }

            context.imageSmoothingEnabled = true
            context.imageSmoothingQuality = "high"
            context.drawImage(
                image,
                sourceX,
                sourceY,
                sourceSize,
                sourceSize,
                0,
                0,
                canvas.width,
                canvas.height
            )

            const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92))
            if (!blob) {
                setNotice("Rasmni tayyorlashda xatolik yuz berdi")
                return
            }

            const data = new FormData()
            data.append("image", new File([blob], "avatar.jpg", { type: "image/jpeg" }))

            const token = localStorage.getItem("token") || ""
            const response = await fetch((import.meta.env.VITE_API_URL || "http://localhost:5000") + "/profile/avatar", {
                method: "POST",
                headers: token ? { Authorization: `Bearer ${token}` } : {},
                body: data
            })

            const result = await response.json().catch(() => ({}))
            if (!response.ok) {
                setNotice(result?.msg || "Rasmni yuklashda xatolik yuz berdi")
                return
            }

            const nextAvatarUrl = result.avatar_url || ""
            setAvatarUrl(nextAvatarUrl)

            const currentUser = JSON.parse(localStorage.getItem("user") || "null")
            if (currentUser) {
                localStorage.setItem("user", JSON.stringify({
                    ...currentUser,
                    avatar_url: nextAvatarUrl
                }))
            }

            closeCropModal()
            setNotice("Profil rasmi muvaffaqiyatli yangilandi")
            setTimeout(() => setNotice(""), 3000)
        } catch {
            setNotice("Rasmni yuklashda xatolik yuz berdi")
        } finally {
            setAvatarLoading(false)
        }
    }

    const addSkill = () => {
        const skill = newSkill.trim()
        if (skill && !skills.some((item) => item.toLowerCase() === skill.toLowerCase())) {
            setSkills([...skills, skill])
            setNewSkill("")
        }
    }

    const removeSkill = (indexToRemove) => {
        setSkills(skills.filter((_, index) => index !== indexToRemove))
    }

    const getMembershipDuration = (dateString) => {
        if (!dateString) return "Yangi a'zo"

        const createdDate = new Date(dateString)
        if (Number.isNaN(createdDate.getTime())) return "Yangi a'zo"

        const diffDays = Math.max(1, Math.ceil(Math.abs(new Date() - createdDate) / (1000 * 60 * 60 * 24)))

        if (diffDays < 30) return `${diffDays} kun`
        const diffMonths = Math.floor(diffDays / 30)
        if (diffMonths < 12) return `${diffMonths} oy`
        return `${(diffDays / 365).toFixed(1)} yil`
    }

    const fullName = `${form.first_name} ${form.last_name}`.trim() || form.username || "Foydalanuvchi"
    const initials = fullName
        .split(" ")
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0].toUpperCase())
        .join("") || "U"

    return (
        <>
        <AppLayout
            title="Profil"
            subtitle="Shaxsiy ma'lumotlaringiz, ko'nikmalaringiz va FinJob faoliyatingiz"
        >
            {initialLoad ? (
                <div className="empty-state">Profil yuklanmoqda...</div>
            ) : (
                <div className="profile-page">
                    {notice && (
                        <div className={notice.includes("muvaffaqiyatli") ? "notice ok" : "notice warn"}>
                            {notice}
                        </div>
                    )}

                    <section className="profile-hero card">
                        <div className="profile-identity">
                            <label className="profile-avatar-wrap" title="Profil rasmini o'zgartirish">
                                <div className="profile-avatar">
                                    {avatarUrl ? <img src={(import.meta.env.VITE_API_URL || "http://localhost:5000") + avatarUrl} alt="Profil rasmi" /> : initials}
                                    {isEditing && (
                                        <span className="profile-avatar-edit" aria-label="Profil rasmini yuklash">
                                            {avatarLoading ? "..." : "✎"}
                                        </span>
                                    )}
                                </div>
                                {isEditing && (
                                    <input type="file" accept="image/png,image/jpeg,image/webp" onChange={selectAvatar} disabled={avatarLoading} />
                                )}
                            </label>
                            <div className="profile-identity-text">
                                <div className="profile-name-row">
                                    <h2>{fullName}</h2>
                                    <span className="profile-role">{form.role === "admin" ? "Administrator" : "Foydalanuvchi"}</span>
                                </div>
                                <p>@{form.username || "foydalanuvchi"}</p>
                                <span>{form.email || "Elektron pochta kiritilmagan"}</span>
                            </div>
                        </div>

                        <div className="profile-hero-actions">
                            {!isEditing && (
                                <button className="btn btn-primary" onClick={startEditing}>
                                    Profilni tahrirlash
                                </button>
                            )}
                        </div>
                    </section>

                    <section className="card profile-verification-card" style={{ marginBottom: 18 }}>
                        <div className="profile-section-head">
                            <div>
                                <span className="profile-eyebrow">ISHONCH</span>
                                <h3 className="section-title">Tasdiqlash va reputatsiya</h3>
                            </div>
                            <button className="btn btn-secondary" type="button" onClick={() => window.location.assign("/disputes")}>Nizolar markazi</button>
                        </div>
                        <div className="profile-verification-grid">
                            <div>
                                <div className="profile-verification-title">Tasdiqlash</div>
                                <VerificationBadges verification={form.verification} interactive />
                            </div>
                            <div>
                                <div className="profile-verification-title">Reputatsiya</div>
                                <div className="profile-reputation-metrics">
                                    <strong>{Number(form.reputation?.average_rating || form.avg_rating || 0).toFixed(1)} ★</strong>
                                    <span>{form.reputation?.reviews_count || 0} sharh</span>
                                    <span>{Number(form.reputation?.success_rate || 0).toFixed(0)}% success</span>
                                    <span>{form.reputation?.completed_worker_jobs || form.completed_jobs_count || 0} yakunlangan ish</span>
                                </div>
                            </div>
                        </div>
                        {(form.reputation?.badges || []).length > 0 && (
                            <div className="profile-badge-list" style={{ marginTop: 12 }}>
                                {form.reputation.badges.map((badge) => <span key={badge.key} className="profile-trust-badge reputation">{badge.label}</span>)}
                            </div>
                        )}
                    </section>
                    <section className="profile-stat-grid">
                        <div className="profile-stat card">
                            <span className="profile-stat-icon">01</span>
                            <div>
                                <div className="stat-label">Yaratilgan ishlar</div>
                                <div className="stat-value">{form.created_jobs_count}</div>
                            </div>
                        </div>
                        <div className="profile-stat card">
                            <span className="profile-stat-icon">02</span>
                            <div>
                                <div className="stat-label">Bajarilgan ishlar</div>
                                <div className="stat-value">{form.completed_jobs_count}</div>
                            </div>
                        </div>
                        <div className="profile-stat card">
                            <span className="profile-stat-icon">03</span>
                            <div>
                                <div className="stat-label">O'rtacha reyting</div>
                                <div className="stat-value">{Number(form.avg_rating).toFixed(1)} <small>★</small></div>
                            </div>
                        </div>
                        <div className="profile-stat card">
                            <span className="profile-stat-icon">04</span>
                            <div>
                                <div className="stat-label">FinJob'da</div>
                                <div className="stat-value profile-stat-small">{getMembershipDuration(form.created_at)}</div>
                            </div>
                        </div>
                    </section>

                    <section className="profile-wallet-card">
                        <div className="profile-wallet-top">
                            <div>
                                <span className="profile-wallet-eyebrow">HAMYON</span>
                                <h3>FinJob balansingiz</h3>
                                <p>FinJob ichidagi sinov balansingiz va unga oid operatsiyalar.</p>
                            </div>
                            <div className="profile-wallet-balance">
                                <span>Joriy balans</span>
                                <strong>{Number(form.balance).toLocaleString("uz-UZ")}</strong>
                                <small>UZS</small>
                            </div>
                        </div>
                        <div className="profile-wallet-controls">
                            <button type="button" className="profile-wallet-withdraw-btn" onClick={() => setWithdrawOpen((current) => !current)} disabled={walletLoading || Number(form.balance) <= 0}>
                                {withdrawOpen ? "Yopish" : "Test balansdan yechish"}
                            </button>
                            <span>Muhim: bu sinov balansi. Bu amal bank kartasi yoki haqiqiy hisobingizga pul o‘tkazmaydi. Sinov rejimida yechib olish uchun qo‘shimcha komissiya olinmaydi.</span>
                        </div>
                        {withdrawOpen && (
                            <form className="profile-withdraw-box" onSubmit={submitWithdrawal}>
                                <div className="profile-withdraw-field">
                                    <label>Sinov balansidan yechiladigan summa</label>
                                    <div className="profile-withdraw-row">
                                        <input className="input" type="number" min="1" max={Number(form.balance || 0)} step="0.01" placeholder="Masalan: 100000" value={withdrawAmount} onChange={(e) => setWithdrawAmount(e.target.value)} />
                                        <button type="button" className="btn btn-secondary" onClick={() => setWithdrawAmount(String(Number(form.balance || 0)))}>To‘liq balans</button>
                                    </div>
                                </div>
                                <button type="submit" className="btn btn-success" disabled={withdrawLoading || !withdrawAmount}>
                                    {withdrawLoading ? "Yechilmoqda..." : "Tasdiqlash"}
                                </button>
                            </form>
                        )}
                        <div className="profile-wallet-history">
                            <div className="profile-wallet-history-head">
                                <div>
                                    <span className="profile-wallet-eyebrow">TARIX</span>
                                    <h4>So‘nggi tranzaksiyalar</h4>
                                </div>
                                <span>{walletTransactions.length} ta</span>
                            </div>
                            {walletLoading ? (
                                <div className="profile-wallet-empty">Tranzaksiyalar yuklanmoqda...</div>
                            ) : walletTransactions.length ? (
                                <div className="profile-wallet-transactions">
                                    {walletTransactions.slice(0, 8).map((transaction, index) => {
                                        const amount = Number(transaction.amount || 0)
                                        const income = amount > 0
                                        return (
                                            <div className="profile-wallet-transaction" key={transaction.created_at + "-" + index}>
                                                <div className={income ? "profile-wallet-transaction-icon income" : "profile-wallet-transaction-icon outcome"}>{income ? "+" : "−"}</div>
                                                <div className="profile-wallet-transaction-text">
                                                    <strong>{transaction.description}</strong>
                                                    <span>{formatWalletDate(transaction.created_at)}</span>
                                                </div>
                                                <div className={income ? "profile-wallet-transaction-amount income" : "profile-wallet-transaction-amount outcome"}>
                                                    {income ? "+" : "−"}{Math.abs(amount).toLocaleString("uz-UZ")} UZS
                                                </div>
                                            </div>
                                        )
                                    })}
                                </div>
                            ) : (
                                <div className="profile-wallet-empty">Hali tranzaksiyalar mavjud emas.</div>
                            )}
                        </div>
                    </section>
                    <div className="profile-content-grid">
                        <section className="card">
                            <div className="profile-section-head">
                                <div>
                                    <span className="profile-eyebrow">HISOB</span>
                                    <h3 className="section-title">Shaxsiy ma'lumotlar</h3>
                                </div>
                                {!isEditing && <span className="profile-status">Ko'rish rejimi</span>}
                            </div>

                            <form className="form" onSubmit={submit}>
                                <div className="form-row">
                                    <div>
                                        <label className="helper profile-label">Ism</label>
                                        <input
                                            className="input"
                                            value={form.first_name}
                                            onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                                            disabled={!isEditing}
                                            required
                                        />
                                    </div>
                                    <div>
                                        <label className="helper profile-label">Familiya</label>
                                        <input
                                            className="input"
                                            value={form.last_name}
                                            onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                                            disabled={!isEditing}
                                            required
                                        />
                                    </div>
                                </div>

                                <div className="form-row">
                                    <div>
                                        <label className="helper profile-label">Tug'ilgan sana</label>
                                        <input
                                            className="input"
                                            type="date"
                                            value={form.birthday}
                                            onChange={(e) => setForm({ ...form, birthday: e.target.value })}
                                            disabled={!isEditing}
                                            required
                                        />
                                    </div>
                                    <div>
                                        <label className="helper profile-label">Foydalanuvchi nomi</label>
                                        <input
                                            className="input"
                                            value={form.username}
                                            onChange={(e) => setForm({ ...form, username: e.target.value })}
                                            disabled={!isEditing}
                                            required
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label className="helper profile-label">Elektron pochta manzili</label>
                                    <input
                                        className="input"
                                        type="email"
                                        value={form.email}
                                        disabled
                                        readOnly
                                        title="Emailni o‘zgartirish uchun xavfsiz qayta tasdiqlash jarayoni talab qilinadi"
                                        required
                                    />
                                </div>

                                <div>
                                    <label className="helper profile-label">O'zingiz haqingizda</label>
                                    <textarea
                                        className="textarea"
                                        value={form.bio}
                                        onChange={(e) => setForm({ ...form, bio: e.target.value })}
                                        disabled={!isEditing}
                                        placeholder="O‘zingiz, tajribangiz yoki xizmatlaringiz haqida qisqacha yozing..."
                                    />
                                </div>

                                {isEditing && (
                                    <div className="profile-form-actions">
                                        <button type="submit" className="btn btn-primary" disabled={loading}>
                                            {loading ? "Saqlanmoqda..." : "O‘zgarishlarni saqlash"}
                                        </button>
                                        <button type="button" className="btn btn-secondary" onClick={cancelEditing}>
                                            Bekor qilish
                                        </button>
                                    </div>
                                )}
                            </form>
                        </section>

                        <div className="profile-side">
                            <section className="card">
                                <div className="profile-section-head">
                                    <div>
                                        <span className="profile-eyebrow">KO‘NIKMALAR</span>
                                        <h3 className="section-title">Ko'nikmalar</h3>
                                    </div>
                                    <span className="profile-count">{skills.length}</span>
                                </div>

                                {skills.length > 0 ? (
                                    <div className="profile-skills">
                                        {skills.map((skill, index) => (
                                            <span key={index} className="profile-skill">
                                                {skill}
                                                {isEditing && (
                                                    <button type="button" onClick={() => removeSkill(index)} aria-label={`Olib tashlash: ${skill}`}>
                                                        ×
                                                    </button>
                                                )}
                                            </span>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="profile-empty">
                                        <strong>Hali ko'nikmalar qo'shilmagan</strong>
                                        <span>Tahrirlash rejimida o‘zingizga mos ko‘nikmalarni qo‘shing.</span>
                                    </div>
                                )}

                                {isEditing && (
                                    <div className="profile-skill-add">
                                        <button
                                            type="button"
                                            className="btn btn-secondary"
                                            onClick={() => {
                                                setShowServicePicker((current) => !current)
                                                setServiceSearch("")
                                            }}
                                        >
                                            {showServicePicker ? "Yopish" : "Qo‘shish"}
                                        </button>

                                        {showServicePicker && (
                                            <div className="profile-service-picker">
                                                <div className="service-search">
                                                    <input
                                                        autoFocus
                                                        className="input"
                                                        type="search"
                                                        placeholder="Xizmat qidiring..."
                                                        value={serviceSearch}
                                                        onChange={(e) => setServiceSearch(e.target.value)}
                                                    />
                                                </div>

                                                <div className="service-tree">
                                                    {serviceSearch.trim() ? (
                                                        exactSearchServices.length ? exactSearchServices.map((service) => (
                                                            <button
                                                                key={service.id}
                                                                type="button"
                                                                className={skills.some((item) => item.toLowerCase() === service.name.toLowerCase()) ? "service-search-result selected" : "service-search-result"}
                                                                onClick={() => addServiceSkill(service)}
                                                            >
                                                                {service.name}
                                                            </button>
                                                        )) : (
                                                            <div className="empty-state">Bunday xizmat topilmadi</div>
                                                        )
                                                    ) : (
                                                        serviceTree.map((node) => (
                                                            <ServiceNode
                                                                key={node.id}
                                                                node={node}
                                                                level={0}
                                                                selected={[]}
                                                                onSelect={addServiceSkill}
                                                            />
                                                        ))
                                                    )}
                                                </div>
                                            </div>
                                        )}

                                        <input
                                            className="input"
                                            type="text"
                                            placeholder="Boshqa ko‘nikma..."
                                            value={newSkill}
                                            onChange={(e) => setNewSkill(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === "Enter") {
                                                    e.preventDefault()
                                                    addSkill()
                                                }
                                            }}
                                        />
                                    </div>
                                )}
                            </section>

                            <section className="card profile-info-card">
                                <span className="profile-eyebrow">HISOB HOLATI</span>
                                <div className="profile-info-row">
                                    <span>Holat</span>
                                    <strong><i className="profile-online-dot" /> Faol</strong>
                                </div>
                                <div className="profile-info-row">
                                    <span>Ro‘yxatdan o‘tgan</span>
                                    <strong>{getMembershipDuration(form.created_at)} oldin</strong>
                                </div>
                                <div className="profile-info-row">
                                    <span>Hisob turi</span>
                                    <strong>{form.role === "admin" ? "Administrator" : "Standart"}</strong>
                                </div>
                            </section>
                        </div>
                    </div>

                <section className="card" style={{ marginTop: 18 }}>
                    <div className="profile-section-head">
                        <div>
                            <span className="profile-eyebrow">ISH NAMUNALARI</span>
                            <h3 className="section-title">Ish namunalari</h3>
                            <p className="muted">Bajargan loyihalaringizni qisqacha ko‘rsating.</p>
                        </div>
                        <span className="profile-count">{portfolio.length}/3</span>
                    </div>

                    {portfolio.length > 0 ? (
                        <div style={{ display: "grid", gap: 10 }}>
                            {portfolio.map((item) => (
                                <article key={item.id} className="card" style={{ margin: 0 }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                                        <div style={{ minWidth: 0 }}>
                                            <strong>{item.title}</strong>
                                            {item.description && <p style={{ margin: "6px 0 0" }}>{item.description}</p>}
                                            {item.image_url && (
                                                <img
                                                    src={(import.meta.env.VITE_API_URL || "http://localhost:5000") + item.image_url}
                                                    alt={item.title}
                                                    style={{ display: "block", width: "100%", maxWidth: 420, maxHeight: 240, objectFit: "cover", borderRadius: 14, marginTop: 10 }}
                                                />
                                            )}
                                            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 8 }}>
                                                {item.url && (
                                                    <a href={item.url} target="_blank" rel="noreferrer">
                                                        Loyihani ko‘rish →
                                                    </a>
                                                )}
                                                {item.file_url && (
                                                    <a href={(import.meta.env.VITE_API_URL || "http://localhost:5000") + item.file_url} target="_blank" rel="noreferrer">
                                                        {item.file_name || "Ish namunasini ochish"} →
                                                    </a>
                                                )}
                                            </div>
                                        </div>
                                        <button
                                            type="button"
                                            className="btn btn-secondary"
                                            onClick={async () => {
                                                const result = await api(`/portfolio/${item.id}`, { method: "DELETE", token: localStorage.getItem("token") || "" })
                                                if (result?.ok) {
                                                    setPortfolio((items) => items.filter((current) => current.id !== item.id))
                                                    setNotice("Ish namunasi o‘chirildi.")
                                                } else {
                                                    setNotice(result?.msg || "Ish namunasini o‘chirib bo‘lmadi.")
                                                }
                                            }}
                                        >
                                            O‘chirish
                                        </button>
                                    </div>
                                </article>
                            ))}
                        </div>
                    ) : (
                        <div className="profile-empty" style={{ marginBottom: 14 }}>
                            <strong>Hali ish namunalari qo‘shilmagan</strong>
                            <span>Kamida 1–2 ta yaxshi ish namunasi qo‘shish profilingizni kuchaytiradi.</span>
                        </div>
                    )}

                    {portfolio.length >= 3 && (
                        <div className="notice" style={{ marginTop: 12 }}>
                            Ish namunalari limiti to‘ldi: <strong>{portfolio.length}/3</strong>. Yangi ish namunasi qo‘shish uchun avval mavjud namunadan birini o‘chiring.
                        </div>
                    )}

                    <form
                        className="form"
                        style={{ marginTop: 16 }}
                        onSubmit={async (event) => {
                            event.preventDefault()
                            if (portfolio.length >= 3) {
                                setNotice("Ko‘pi bilan 3 ta ish namunasi qo‘shish mumkin. Yangi namuna qo‘shish uchun avval mavjud namunadan birini o‘chiring.")
                                return
                            }
                            if (!portfolioFile && !portfolioForm.title.trim()) {
                                setNotice("Ish namunasi nomini kiriting yoki fayl tanlang.")
                                return
                            }
                            if (portfolioFile && portfolioFile.size > 10 * 1024 * 1024) {
                                setNotice("Ish namunasi fayli 10 MB dan oshmasligi kerak.")
                                return
                            }

                            setPortfolioLoading(true)
                            const token = localStorage.getItem("token") || ""
                            let result

                            if (portfolioFile) {
                                const data = new FormData()
                                const title = portfolioForm.title.trim() || portfolioFile.name.replace(/\.[^/.]+$/, "")
                                data.append("title", title)
                                data.append("description", portfolioForm.description)
                                data.append("url", portfolioForm.url)
                                data.append("file", portfolioFile)
                                result = await api("/portfolio/upload", {
                                    method: "POST",
                                    token,
                                    body: data
                                })
                            } else {
                                result = await api("/portfolio", {
                                    method: "POST",
                                    token,
                                    body: portfolioForm
                                })
                            }

                            setPortfolioLoading(false)
                            if (result?.ok) {
                                const refreshed = await api("/portfolio", { token })
                                setPortfolio(Array.isArray(refreshed) ? refreshed : portfolio)
                                setPortfolioForm({ title: "", description: "", url: "" })
                                setPortfolioFile(null)
                                if (portfolioFileRef.current) portfolioFileRef.current.value = ""
                                setNotice("Ish namunasi qo‘shildi.")
                            } else {
                                setNotice(result?.msg || "Ish namunasini qo‘shib bo‘lmadi.")
                            }
                        }}
                    >
                        <div className="form-row">
                            <label>
                                <span className="helper profile-label">Loyiha nomi</span>
                                <input className="input" maxLength={120} value={portfolioForm.title} onChange={(e) => setPortfolioForm({ ...portfolioForm, title: e.target.value })} placeholder="Masalan: Internet-do‘kon loyihasi" />
                            </label>
                            <label>
                                <span className="helper profile-label">Havola</span>
                                <input className="input" type="url" value={portfolioForm.url} onChange={(e) => setPortfolioForm({ ...portfolioForm, url: e.target.value })} placeholder="https://..." />
                            </label>
                        </div>
                        <label>
                            <span className="helper profile-label">Qisqa tavsif</span>
                            <textarea className="textarea" maxLength={2000} value={portfolioForm.description} onChange={(e) => setPortfolioForm({ ...portfolioForm, description: e.target.value })} placeholder="Bu loyihada nimalarni bajardingiz va qanday natija chiqdi?" />
                        </label>
                        <label>
                            <span className="helper profile-label">Ish namunasi fayli</span>
                            <input
                                ref={portfolioFileRef}
                                className="input"
                                type="file"
                                accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,application/pdf,image/png,image/jpeg,image/webp,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                onChange={(event) => {
                                    const file = event.target.files?.[0] || null
                                    if (!file) {
                                        setPortfolioFile(null)
                                        return
                                    }
                                    if (file.size > 10 * 1024 * 1024) {
                                        event.target.value = ""
                                        setPortfolioFile(null)
                                        setNotice("Ish namunasi fayli 10 MB dan oshmasligi kerak.")
                                        return
                                    }
                                    setPortfolioFile(file)
                                    setNotice("")
                                }}
                            />
                            <span className="helper">PDF, DOC, DOCX, PNG, JPG yoki WEBP. Maksimal hajm: 10 MB.</span>
                        </label>
                        <button className="btn btn-primary" type="submit" disabled={portfolioLoading}>
                            {portfolioLoading ? "Saqlanmoqda..." : "Ish namunasini qo‘shish"}
                        </button>
                    </form>
                </section>
                </div>
            )}
        </AppLayout>
        {cropImageUrl && (
                <div className="avatar-crop-backdrop" role="dialog" aria-modal="true" aria-label="Profil rasmini kesish">
                    <div className="avatar-crop-modal">
                        <div className="avatar-crop-head">
                            <div>
                                <span className="profile-eyebrow">PROFIL RASMI</span>
                                <h3 className="section-title">Rasmni joylashtiring</h3>
                                <p>Sichqoncha bilan rasmni suring va kerakli joyni dumaloq oynaga moslang.</p>
                            </div>
                            <button type="button" className="avatar-crop-close" onClick={closeCropModal} disabled={avatarLoading}>×</button>
                        </div>

                        <div
                            ref={cropAreaRef}
                            className={cropDragging ? "avatar-crop-area dragging" : "avatar-crop-area"}
                            onPointerDown={handleCropPointerDown}
                            onPointerMove={handleCropPointerMove}
                            onPointerUp={handleCropPointerUp}
                            onPointerCancel={handleCropPointerUp}
                        >
                            <img
                                ref={cropImageRef}
                                src={cropImageUrl}
                                alt="Profil rasmi tanlovi"
                                draggable="false"
                                style={{width: `${cropImageSize.width}px`, height: `${cropImageSize.height}px`, transform: `translate(calc(-50% + ${cropOffset.x}px), calc(-50% + ${cropOffset.y}px)) scale(${cropZoom})`}}
                                onLoad={(event) => {
                                    const areaWidth = cropAreaRef.current?.clientWidth || 500
                                    const naturalWidth = event.currentTarget.naturalWidth
                                    const naturalHeight = event.currentTarget.naturalHeight
                                    const scale = Math.max(areaWidth / naturalWidth, areaWidth / naturalHeight)
                                    setCropImageSize({
                                        width: naturalWidth * scale,
                                        height: naturalHeight * scale
                                    })
                                    setCropOffset({ x: 0, y: 0 })
                                }}
                            />
                            <div className="avatar-crop-circle" />
                        </div>

                        <div className="avatar-crop-controls">
                            <div className="avatar-crop-zoom-row">
                                <span>🔍</span>
                                <input
                                    type="range"
                                    min="1"
                                    max="3"
                                    step="0.01"
                                    value={cropZoom}
                                    onChange={handleCropZoomChange}
                                    disabled={avatarLoading}
                                />
                                <strong>{Math.round(cropZoom * 100)}%</strong>
                            </div>
                            <button type="button" className="btn btn-secondary avatar-crop-reset" onClick={resetCrop} disabled={avatarLoading}>
                                Markazga qaytarish
                            </button>
                        </div>

                        <div className="avatar-crop-actions">
                            <button type="button" className="btn btn-secondary" onClick={closeCropModal} disabled={avatarLoading}>
                                Bekor qilish
                            </button>
                            <button type="button" className="btn btn-primary" onClick={saveCroppedAvatar} disabled={avatarLoading}>
                                {avatarLoading ? "Saqlanmoqda..." : "Rasmni saqlash"}
                            </button>
                        </div>
                    </div>
                </div>
        )}

        </>
    )
}

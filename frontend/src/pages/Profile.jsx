import { useState, useEffect, useRef } from "react"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

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
                    role: result.role || "user"
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

    const formatWalletDate = (dateString) => {
        if (!dateString) return "Vaqt noma'lum"
        const date = new Date(String(dateString).replace(" ", "T"))
        if (Number.isNaN(date.getTime())) return "Vaqt noma'lum"
        return date.toLocaleString("uz-UZ", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })
    }

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
            setNotice("Yechib olish muvaffaqiyatli bajarildi")
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
                        <div className="profile-stat card">
                            <span className="profile-stat-icon">05</span>
                            <div>
                                <div className="stat-label">Balans</div>
                                <div className="stat-value profile-stat-small">{Number(form.balance).toLocaleString("uz-UZ")} UZS</div>
                            </div>
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
                                        onChange={(e) => setForm({ ...form, email: e.target.value })}
                                        disabled={!isEditing}
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

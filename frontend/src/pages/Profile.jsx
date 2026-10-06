import { useState, useEffect } from "react"
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
        const loadServices = async () => {
            const result = await api("/services", { token: localStorage.getItem("token") || "" })
            if (Array.isArray(result)) setServices(result)
        }
        loadServices()
    }, [])

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

    const uploadAvatar = async (event) => {
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

        setAvatarLoading(true)
        setNotice("")

        try {
            const data = new FormData()
            data.append("image", file)
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
                                    <input type="file" accept="image/png,image/jpeg,image/webp" onChange={uploadAvatar} disabled={avatarLoading} />
                                )}
                            </label>
                            <div className="profile-identity-text">
                                <div className="profile-name-row">
                                    <h2>{fullName}</h2>
                                    <span className="profile-role">{form.role === "admin" ? "Administrator" : "Foydalanuvchi"}</span>
                                </div>
                                <p>@{form.username || "username"}</p>
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
                    </section>

                    <div className="profile-content-grid">
                        <section className="card">
                            <div className="profile-section-head">
                                <div>
                                    <span className="profile-eyebrow">ACCOUNT</span>
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
                                        <label className="helper profile-label">Username</label>
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
                                    <label className="helper profile-label">Email manzil</label>
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
                                        placeholder="O'zingiz, tajribangiz yoki xizmatlaringiz haqida qisqacha yozing..."
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
                                        <span className="profile-eyebrow">EXPERTISE</span>
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
                                                    <button type="button" onClick={() => removeSkill(index)} aria-label={`Remove ${skill}`}>
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
                                            placeholder="Boshqa ko'nikma..."
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
                                <span className="profile-eyebrow">ACCOUNT STATUS</span>
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
    )
}

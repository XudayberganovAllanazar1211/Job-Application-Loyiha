import { useState, useEffect } from "react"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

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
    const [isEditing, setIsEditing] = useState(false)
    const [notice, setNotice] = useState("")
    const [loading, setLoading] = useState(false)
    const [initialLoad, setInitialLoad] = useState(true)

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
            }

            setInitialLoad(false)
        }

        loadProfile()
    }, [])

    const startEditing = () => {
        setSavedForm({ ...form })
        setSavedSkills([...skills])
        setNotice("")
        setIsEditing(true)
    }

    const cancelEditing = () => {
        if (savedForm) setForm({ ...savedForm })
        setSkills([...savedSkills])
        setNewSkill("")
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
            setSavedForm({ ...form })
            setSavedSkills([...skills])
            setNotice("Profil muvaffaqiyatli yangilandi")
            setIsEditing(false)
            setTimeout(() => setNotice(""), 3000)
        } else {
            setNotice(result?.msg || "Profilni yangilashda xatolik yuz berdi")
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

        if (diffDays < 30) return `\${diffDays} kun`
        const diffMonths = Math.floor(diffDays / 30)
        if (diffMonths < 12) return `\${diffMonths} oy`
        return `\${(diffDays / 365).toFixed(1)} yil`
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
                            <div className="profile-avatar">{initials}</div>
                            <div className="profile-identity-text">
                                <div className="profile-name-row">
                                    <h2>{fullName}</h2>
                                    <span className="profile-role">{form.role === "admin" ? "Administrator" : "Foydalanuvchi"}</span>
                                </div>
                                <p>@{form.username || "username"}</p>
                                <span>{form.email || "Email kiritilmagan"}</span>
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
                                            {loading ? "Saqlanmoqda..." : "O'zgarishlarni saqlash"}
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
                                        <span>Tahrirlash rejimida o'zingizga mos ko'nikmalarni qo'shing.</span>
                                    </div>
                                )}

                                {isEditing && (
                                    <div className="profile-skill-add">
                                        <input
                                            className="input"
                                            type="text"
                                            placeholder="Masalan: Python, React..."
                                            value={newSkill}
                                            onChange={(e) => setNewSkill(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === "Enter") {
                                                    e.preventDefault()
                                                    addSkill()
                                                }
                                            }}
                                        />
                                        <button type="button" className="btn btn-secondary" onClick={addSkill}>
                                            Qo'shish
                                        </button>
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
                                    <span>Ro'yxatdan o'tgan</span>
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

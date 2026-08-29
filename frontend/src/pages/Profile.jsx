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
        avg_rating: 0
    })

    const [skills, setSkills] = useState([])
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
                setForm({
                    first_name: result.first_name || "",
                    last_name: result.last_name || "",
                    birthday: result.birthday || "",
                    username: result.username || "",
                    email: result.email || "",
                    bio: result.bio || "",
                    created_at: result.created_at || "",
                    created_jobs_count: result.created_jobs_count || 0,
                    completed_jobs_count: result.completed_jobs_count || 0,
                    avg_rating: result.avg_rating || 0
                })

                if (result.skills) {
                    if (Array.isArray(result.skills)) {
                        setSkills(result.skills)
                    } else if (typeof result.skills === 'string' && result.skills.trim() !== "") {
                        setSkills(result.skills.split(',').map(s => s.trim()))
                    }
                }
            }
            setInitialLoad(false)
        }
        loadProfile()
    }, [])

    const submit = async (e) => {
        if (e) e.preventDefault()
        setNotice("")
        setLoading(true)

        const token = localStorage.getItem("token")
        const result = await api("/profile", {
            method: "PUT",
            token: token,
            body: {
                ...form,
                skills: skills.join(", ")
            }
        })

        setLoading(false)

        if (result?.msg === "ok") {
            setNotice("Profil muvaffaqiyatli yangilandi ✅")
            setIsEditing(false)
            setTimeout(() => setNotice(""), 3000)
        } else {
            setNotice(result?.msg || "Xatolik yuz berdi!")
        }
    }

    const addSkill = () => {
        if (newSkill.trim() !== "" && !skills.includes(newSkill.trim())) {
            setSkills([...skills, newSkill.trim()])
            setNewSkill("")
        }
    }

    const removeSkill = (indexToRemove) => {
        setSkills(skills.filter((_, index) => index !== indexToRemove))
    }

    // Saytdan qancha vaqtdan beri foydalanayotganini hisoblash funksiyasi
    const getMembershipDuration = (dateString) => {
        if (!dateString) return "Yangi qo'shilgan";
        const createdDate = new Date(dateString);
        const currentDate = new Date();
        const diffTime = Math.abs(currentDate - createdDate);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

        if (diffDays < 30) return `${diffDays} kun oldin`;
        const diffMonths = Math.floor(diffDays / 30);
        if (diffMonths < 12) return `${diffMonths} oy oldin`;
        const diffYears = (diffDays / 365).toFixed(1);
        return `${diffYears} yil oldin`;
    }

    return (
        <AppLayout
            title="Mening Profilim 👤"
            subtitle="Shaxsiy ma'lumotlaringiz va faoliyat statistikangiz"
        >
            {initialLoad ? (
                <div className="empty-state">Yuklanmoqda...</div>
            ) : (
                <div style={{ display: "grid", gap: "20px" }}>

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div style={{ flex: 1 }}>
                            {notice && (
                                <div className={notice.includes("muvaffaqiyatli") ? "notice ok" : "notice warn"}>
                                    {notice}
                                </div>
                            )}
                        </div>
                        <div style={{ marginLeft: "16px" }}>
                            {!isEditing && (
                                <button className="btn btn-secondary" onClick={() => setIsEditing(true)}>
                                    Tahrirlash ✏️
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="grid-2">
                        {/* ASOSIY FORMA */}
                        <div className="card">
                            <h3 className="section-title" style={{ marginTop: 0 }}>Profil sozlamalari</h3>

                            <form className="form" onSubmit={submit}>
                                <div className="form-row">
                                    <div>
                                        <label className="helper" style={{ display: "block", marginBottom: 5 }}>Ism</label>
                                        <input
                                            className="input"
                                            value={form.first_name}
                                            onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                                            disabled={!isEditing}
                                            required
                                        />
                                    </div>
                                    <div>
                                        <label className="helper" style={{ display: "block", marginBottom: 5 }}>Familiya</label>
                                        <input
                                            className="input"
                                            value={form.last_name}
                                            onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                                            disabled={!isEditing}
                                            required
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label className="helper" style={{ display: "block", marginBottom: 5 }}>Tug'ilgan sana</label>
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
                                    <label className="helper" style={{ display: "block", marginBottom: 5 }}>Username</label>
                                    <input
                                        className="input"
                                        value={form.username}
                                        onChange={(e) => setForm({ ...form, username: e.target.value })}
                                        disabled={!isEditing}
                                        required
                                    />
                                </div>

                                <div>
                                    <label className="helper" style={{ display: "block", marginBottom: 5 }}>Email manzil</label>
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
                                    <label className="helper" style={{ display: "block", marginBottom: 5 }}>O'zingiz haqingizda (Bio)</label>
                                    <textarea
                                        className="textarea"
                                        value={form.bio}
                                        onChange={(e) => setForm({ ...form, bio: e.target.value })}
                                        disabled={!isEditing}
                                        placeholder="Hozircha bio yozilmagan..."
                                    ></textarea>
                                </div>

                                {isEditing && (
                                    <div style={{ marginTop: 10, display: "flex", gap: "10px" }}>
                                        <button type="submit" className="btn btn-primary" disabled={loading} style={{ flex: 1 }}>
                                            {loading ? "Saqlanmoqda..." : "O'zgarishlarni saqlash"}
                                        </button>
                                        <button
                                            type="button"
                                            className="btn btn-secondary"
                                            onClick={() => {
                                                setIsEditing(false)
                                                setNotice("")
                                            }}
                                        >
                                            Bekor qilish
                                        </button>
                                    </div>
                                )}
                            </form>
                        </div>

                        {/* KO'NIKMALAR VA DINAMIK STATISTIKA */}
                        <div className="chat-wrap">
                            <div className="card">
                                <h3 className="section-title" style={{ marginTop: 0 }}>Ko'nikmalar (Skills)</h3>

                                {skills.length === 0 ? (
                                    <div className="muted" style={{ fontSize: "14px", marginBottom: "10px" }}>
                                        Hozircha ko'nikmalar qo'shilmagan.
                                    </div>
                                ) : (
                                    <div className="chip-row">
                                        {skills.map((skill, index) => (
                                            <span key={index} className="chip">
                                                {skill}
                                                {isEditing && (
                                                    <button
                                                        type="button"
                                                        onClick={() => removeSkill(index)}
                                                        style={{
                                                            background: 'transparent',
                                                            border: 'none',
                                                            color: '#fca5a5',
                                                            cursor: 'pointer',
                                                            padding: '0 0 0 6px',
                                                            fontSize: '14px',
                                                            fontWeight: 'bold'
                                                        }}
                                                    >
                                                        ×
                                                    </button>
                                                )}
                                            </span>
                                        ))}
                                    </div>
                                )}

                                {isEditing && (
                                    <div style={{ marginTop: '16px', display: 'flex', gap: '8px' }}>
                                        <input
                                            type="text"
                                            className="input"
                                            placeholder="Yangi ko'nikma qo'shish..."
                                            value={newSkill}
                                            onChange={(e) => setNewSkill(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter') {
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
                            </div>

                            {/* YANGI STATISTIKA BLOKI */}
                            <div className="card stat-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
                                <div className="stat-card">
                                    <div className="stat-label">Saytdan foydalanish</div>
                                    <div className="stat-value" style={{ fontSize: "16px" }}>{getMembershipDuration(form.created_at)}</div>
                                </div>
                                <div className="stat-card">
                                    <div className="stat-label">Yaratgan ishlar</div>
                                    <div className="stat-value">{form.created_jobs_count}</div>
                                </div>
                                <div className="stat-card">
                                    <div className="stat-label">Bajargan ishlar</div>
                                    <div className="stat-value">{form.completed_jobs_count}</div>
                                </div>
                                <div className="stat-card">
                                    <div className="stat-label">O'rtacha reyting</div>
                                    <div className="stat-value">⭐ {form.avg_rating}</div>
                                </div>
                            </div>
                        </div>
                    </div>

                </div>
            )}
        </AppLayout>
    )
}
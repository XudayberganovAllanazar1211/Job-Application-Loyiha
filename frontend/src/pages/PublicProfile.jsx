import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

export default function PublicProfile() {
    const { username } = useParams()
    const navigate = useNavigate()
    const [profile, setProfile] = useState(null)
    const [loading, setLoading] = useState(true)
    const [notice, setNotice] = useState("")
    const [favorited, setFavorited] = useState(false)

    useEffect(() => {
        const load = async () => {
            setLoading(true)
            const result = await api(`/profiles/${encodeURIComponent(username || "")}`, {
                token: localStorage.getItem("token") || ""
            })
            if (result?.id) {
                setProfile(result)
                const favorites = await api("/favorites?target_type=user", { token: localStorage.getItem("token") || "" })
                setFavorited(Array.isArray(favorites) && favorites.some((item) => Number(item.target_id) === Number(result.id)))
            } else setNotice(result?.msg || "Profilni yuklashda xatolik yuz berdi")
            setLoading(false)
        }
        load()
    }, [username])

    const skills = Array.isArray(profile?.skills)
        ? profile.skills
        : String(profile?.skills || "").split(",").map((item) => item.trim()).filter(Boolean)

    const fullName = `${profile?.first_name || ""} ${profile?.last_name || ""}`.trim() || profile?.username || "Foydalanuvchi"
    const initials = fullName
        .split(" ")
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0].toUpperCase())
        .join("") || "U"

    const avatarSrc = profile?.avatar_url
        ? (import.meta.env.VITE_API_URL || "http://localhost:5000") + profile.avatar_url
        : ""

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

    const roleLabel = profile?.role === "admin" ? "Administrator" : "Foydalanuvchi"

    return (
        <>
            <AppLayout
                title="Profil"
                subtitle="Foydalanuvchining shaxsiy ma'lumotlari, ko'nikmalari va FinJob faoliyati"
            >
                {loading ? (
                    <div className="empty-state">Profil yuklanmoqda...</div>
                ) : notice ? (
                    <div className="empty-state">
                        <strong>{notice}</strong>
                        <button className="btn btn-secondary" onClick={() => navigate(-1)}>Orqaga</button>
                    </div>
                ) : (
                    <div className="profile-page">
                        <section className="profile-hero card">
                            <div className="profile-identity">
                                <div className="profile-avatar-wrap public-profile-avatar-wrap">
                                    <div className="profile-avatar">
                                        {avatarSrc ? <img src={avatarSrc} alt="Profil rasmi" /> : initials}
                                    </div>
                                </div>
                                <div className="profile-identity-text">
                                    <div className="profile-name-row">
                                        <h2>{fullName}</h2>
                                        <span className="profile-role">{roleLabel}</span>
                                    </div>
                                    <p>@{profile.username || "foydalanuvchi"}</p>
                                    <span>{profile.email || "Elektron pochta kiritilmagan"}</span>
                                </div>
                            </div>

                            <div className="profile-hero-actions">
                                <span className="profile-status">Ko'rish rejimi</span>
                                <button
                                    className="btn btn-secondary"
                                    type="button"
                                    onClick={async () => {
                                        const result = await api("/favorites", {
                                            method: favorited ? "DELETE" : "POST",
                                            token: localStorage.getItem("token") || "",
                                            body: { target_type: "user", target_id: profile.id }
                                        })
                                        if (result?.ok) setFavorited((value) => !value)
                                        else setNotice(result?.msg || "Saqlangan foydalanuvchini yangilab bo‘lmadi.")
                                    }}
                                >
                                    {favorited ? "★ Saqlangan" : "☆ Saqlash"}
                                </button>
                            </div>
                        </section>

                        <section className="profile-stat-grid">
                            <div className="profile-stat card">
                                <span className="profile-stat-icon">01</span>
                                <div>
                                    <div className="stat-label">Yaratilgan ishlar</div>
                                    <div className="stat-value">{profile.created_jobs_count}</div>
                                </div>
                            </div>
                            <div className="profile-stat card">
                                <span className="profile-stat-icon">02</span>
                                <div>
                                    <div className="stat-label">Bajarilgan ishlar</div>
                                    <div className="stat-value">{profile.completed_jobs_count}</div>
                                </div>
                            </div>
                            <div className="profile-stat card">
                                <span className="profile-stat-icon">03</span>
                                <div>
                                    <div className="stat-label">O'rtacha reyting</div>
                                    <div className="stat-value">{Number(profile.avg_rating || 0).toFixed(1)} <small>★</small></div>
                                </div>
                            </div>
                            <div className="profile-stat card">
                                <span className="profile-stat-icon">04</span>
                                <div>
                                    <div className="stat-label">FinJob'da</div>
                                    <div className="stat-value profile-stat-small">{getMembershipDuration(profile.created_at)}</div>
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
                                    <span className="profile-status">Ko'rish rejimi</span>
                                </div>

                                <div className="form">
                                    <div className="form-row">
                                        <div>
                                            <label className="helper profile-label">Ism</label>
                                            <input className="input" value={profile.first_name || ""} readOnly />
                                        </div>
                                        <div>
                                            <label className="helper profile-label">Familiya</label>
                                            <input className="input" value={profile.last_name || ""} readOnly />
                                        </div>
                                    </div>

                                    <div className="form-row">
                                        <div>
                                            <label className="helper profile-label">Tug'ilgan sana</label>
                                            <input className="input" type="date" value={profile.birthday || ""} readOnly />
                                        </div>
                                        <div>
                                            <label className="helper profile-label">Foydalanuvchi nomi</label>
                                            <input className="input" value={profile.username || ""} readOnly />
                                        </div>
                                    </div>

                                    <div>
                                        <label className="helper profile-label">Elektron pochta manzili</label>
                                        <input className="input" type="email" value={profile.email || ""} readOnly />
                                    </div>

                                    <div>
                                        <label className="helper profile-label">O'zingiz haqingizda</label>
                                        <textarea
                                            className="textarea"
                                            value={profile.bio || "O'zi haqida ma'lumot kiritilmagan."}
                                            readOnly
                                        />
                                    </div>
                                </div>
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
                                                <span key={index} className="profile-skill">{skill}</span>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="profile-empty">
                                            <strong>Hali ko'nikmalar qo'shilmagan</strong>
                                            <span>Bu foydalanuvchi hali ko‘nikmalarini kiritmagan.</span>
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
                                        <strong>{getMembershipDuration(profile.created_at)} oldin</strong>
                                    </div>
                                    <div className="profile-info-row">
                                        <span>Hisob turi</span>
                                        <strong>{roleLabel === "Administrator" ? "Administrator" : "Standart"}</strong>
                                    </div>
                                </section>
                            </div>
                        </div>

                    <section className="card" style={{ marginTop: 18 }}>
                        <div className="profile-section-head">
                            <div>
                                <span className="profile-eyebrow">PORTFOLIO</span>
                                <h3 className="section-title">Ish namunalari</h3>
                            </div>
                            <span className="profile-count">{Array.isArray(profile.portfolio) ? profile.portfolio.length : 0}</span>
                        </div>
                        {Array.isArray(profile.portfolio) && profile.portfolio.length > 0 ? (
                            <div style={{ display: "grid", gap: 10 }}>
                                {profile.portfolio.map((item) => (
                                    <article key={item.id} className="card" style={{ margin: 0 }}>
                                        <strong>{item.title}</strong>
                                        {item.description && <p style={{ margin: "6px 0 0" }}>{item.description}</p>}
                                        {item.url && (
                                            <a href={item.url} target="_blank" rel="noreferrer" style={{ display: "inline-block", marginTop: 8 }}>
                                                Loyihani ko‘rish →
                                            </a>
                                        )}
                                    </article>
                                ))}
                            </div>
                        ) : (
                            <div className="profile-empty">
                                <strong>Portfolio hali qo‘shilmagan</strong>
                                <span>Bu foydalanuvchi hozircha ish namunalari joylamagan.</span>
                            </div>
                        )}
                    </section>
                    </div>
                )}
            </AppLayout>
        </>
    )
}

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

    useEffect(() => {
        const load = async () => {
            setLoading(true)
            const result = await api(`/profiles/${encodeURIComponent(username || "")}`, {
                token: localStorage.getItem("token") || ""
            })
            if (result?.id) setProfile(result)
            else setNotice(result?.msg || "Profilni yuklashda xatolik yuz berdi")
            setLoading(false)
        }
        load()
    }, [username])

    const fullName = [profile?.first_name, profile?.last_name].filter(Boolean).join(" ") || profile?.username || "Foydalanuvchi"
    const skills = Array.isArray(profile?.skills)
        ? profile.skills
        : String(profile?.skills || "").split(",").map((item) => item.trim()).filter(Boolean)
    const initials = fullName.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase()
    const avatarSrc = profile?.avatar_url
        ? (import.meta.env.VITE_API_URL || "http://localhost:5000") + profile.avatar_url
        : ""

    return (
        <AppLayout title="Profil" subtitle="Foydalanuvchi haqida ma'lumot">
            {loading ? (
                <div className="card"><strong>Profil yuklanmoqda...</strong></div>
            ) : notice ? (
                <div className="card">
                    <div className="notice warn">{notice}</div>
                    <button className="btn btn-secondary" onClick={() => navigate(-1)}>Orqaga</button>
                </div>
            ) : (
                <div className="profile-public-layout">
                    <section className="profile-public-hero card">
                        <div className="profile-public-avatar">
                            {avatarSrc ? <img src={avatarSrc} alt={fullName} /> : initials}
                        </div>
                        <div className="profile-public-main">
                            <span className="profile-public-label">FOYDALANUVCHI PROFILI</span>
                            <h1>{fullName}</h1>
                            <p className="profile-public-username">@{profile.username}</p>
                            {profile.bio && <p className="profile-public-bio">{profile.bio}</p>}
                        </div>
                    </section>

                    <section className="profile-public-stats">
                        <div className="card"><strong>{profile.created_jobs_count}</strong><span>Yaratilgan ishlar</span></div>
                        <div className="card"><strong>{profile.completed_jobs_count}</strong><span>Yakunlangan ishlar</span></div>
                        <div className="card"><strong>{Number(profile.avg_rating || 0).toFixed(1)}</strong><span>O‘rtacha baho</span></div>
                    </section>

                    <section className="profile-public-content card">
                        <span className="profile-public-label">SOHALAR</span>
                        {skills.length ? (
                            <div className="profile-public-skills">
                                {skills.map((skill) => <span className="chip" key={skill}>{skill}</span>)}
                            </div>
                        ) : (
                            <p className="profile-public-muted">Hozircha sohalar kiritilmagan.</p>
                        )}
                    </section>
                </div>
            )}
        </AppLayout>
    )
}

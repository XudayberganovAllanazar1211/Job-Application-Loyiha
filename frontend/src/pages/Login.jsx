import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { api } from "../api"
import GoogleAuthButton from "../components/GoogleAuthButton"

export default function Login() {
    // Endi username maydoniga ham username, ham email yozib kirish mumkin
    const [form, setForm] = useState({ username: "", password: "" })
    const [notice, setNotice] = useState("")
    const [loading, setLoading] = useState(false)
    const navigate = useNavigate()

    const handleGoogleSuccess = async (credential) => {
        setNotice("")
        setLoading(true)

        const result = await api("/auth/google", {
            method: "POST",
            body: { credential }
        })

        if (result?.token) {
            localStorage.setItem("token", result.token)
            const profile = await api("/profile", { token: result.token })
            if (profile?.id) {
                localStorage.setItem("user", JSON.stringify(profile))
            }
            navigate("/")
            return
        }

        setLoading(false)
        setNotice(result?.msg || "Google orqali kirishda xatolik yuz berdi.")
    }

    const submit = async (e) => {
        e.preventDefault()
        setNotice("")
        setLoading(true)

        const result = await api("/login", {
            method: "POST",
            body: form
        })

        setLoading(false)

        if (result?.token) {
            localStorage.setItem("token", result.token)

            const profile = await api("/profile", { token: result.token })
            if (profile?.id) {
                localStorage.setItem("user", JSON.stringify(profile))
            }

            navigate("/")
            return
        }

        setNotice(result?.msg || "Login muvaffaqiyatsiz")
    }

    return (
        <div className="auth-page">
            <section className="auth-hero">
                <div className="auth-hero-card">
                    <div className="brand">
                        <div className="brand-badge">FJ</div>
                        <div>
                            <div className="brand-name">FinJob</div>
                            <div className="helper">Ish toping. Ishni yakunlang.</div>
                        </div>
                    </div>
                    <h1 className="hero-title">Tizimga kirish</h1>
                    <p className="hero-text">
                        Yagona universal profil orqali ish topish va xizmat ko‘rsatish uchun mo‘ljallangan zamonaviy platforma.
                    </p>
                    <div className="hero-points">
                        <div className="hero-point">⚡ Tezkor kirish va qulay boshqaruv paneli</div>
                        <div className="hero-point">🔐 Xavfsiz kirish</div>
                        <div className="hero-point">💬 Suhbat, ish, baholash va reyting jadvali</div>
                    </div>
                </div>
            </section>

            <section className="auth-hero">
                <div className="auth-card">
                    <h2 style={{ marginTop: 0 }}>Kirish</h2>
                    <p className="muted" style={{ marginTop: 0 }}>
                        Hisobingizga kirish uchun ma’lumotlaringizni kiriting.
                    </p>

                    {notice && <div className="notice warn" style={{ marginBottom: 14 }}>{notice}</div>}

                    <form className="form" onSubmit={submit}>
                        <input
                            className="input"
                            placeholder="Foydalanuvchi nomi yoki elektron pochta"
                            value={form.username}
                            onChange={(e) => setForm({ ...form, username: e.target.value })}
                            required
                        />
                        <input
                            className="input"
                            type="password"
                            placeholder="Parol"
                            value={form.password}
                            onChange={(e) => setForm({ ...form, password: e.target.value })}
                            required
                        />
                        <button className="btn btn-primary" disabled={loading}>
                            {loading ? "Kirilmoqda..." : "Kirish"}
                        </button>
                    </form>

                    <div style={{ textAlign: "center", marginTop: 16 }}>
                        <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>yoki Google orqali</div>
                        <GoogleAuthButton onSuccess={handleGoogleSuccess} disabled={loading} />
                    </div>

                    <p style={{ marginTop: 16 }}>
                        <Link className="link" to="/forgot-password">Parolni unutdingizmi?</Link>
                    </p>

                    <p style={{ marginTop: 8 }}>
                        Hisobingiz yo‘qmi? <Link className="link" to="/register">Ro‘yxatdan o‘tish</Link>
                    </p>
                    <div className="auth-legal-links">
                        <Link to="/privacy">Maxfiylik</Link>
                        <Link to="/terms">Shartlar</Link>
                        <Link to="/community-rules">Hamjamiyat qoidalari</Link>
                    </div>
                </div>
            </section>
        </div>
    )
}
import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { api } from "../api"

export default function Login() {
    // Endi username maydoniga ham username, ham email yozib kirish mumkin
    const [form, setForm] = useState({ username: "", password: "" })
    const [notice, setNotice] = useState("")
    const [loading, setLoading] = useState(false)
    const navigate = useNavigate()

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
                            <div className="helper">Find work. Get it done.</div>
                        </div>
                    </div>
                    <h1 className="hero-title">Tizimga kirish</h1>
                    <p className="hero-text">
                        Yagona universal profil tizimi bilan ishlaydigan, zamonaviy, responsiv va startup uslubidagi platforma.
                    </p>
                    <div className="hero-points">
                        <div className="hero-point">⚡ Tez kirish va professional dashboard</div>
                        <div className="hero-point">🔐 Token bilan himoyalangan kirish</div>
                        <div className="hero-point">💬 Chat, job, rating va liderlar paneli</div>
                    </div>
                </div>
            </section>

            <section className="auth-hero">
                <div className="auth-card">
                    <h2 style={{ marginTop: 0 }}>Login</h2>
                    <p className="muted" style={{ marginTop: 0 }}>
                        Hisobingizga kirish uchun ma’lumotlarni kiriting.
                    </p>

                    {notice && <div className="notice warn" style={{ marginBottom: 14 }}>{notice}</div>}

                    <form className="form" onSubmit={submit}>
                        <input
                            className="input"
                            placeholder="Username yoki Email"
                            value={form.username}
                            onChange={(e) => setForm({ ...form, username: e.target.value })}
                            required
                        />
                        <input
                            className="input"
                            type="password"
                            placeholder="Password"
                            value={form.password}
                            onChange={(e) => setForm({ ...form, password: e.target.value })}
                            required
                        />
                        <button className="btn btn-primary" disabled={loading}>
                            {loading ? "Kirilmoqda..." : "Login"}
                        </button>
                    </form>

                    <p style={{ marginTop: 16 }}>
                        Account yo‘qmi? <Link className="link" to="/register">Register</Link>
                    </p>
                </div>
            </section>
        </div>
    )
}
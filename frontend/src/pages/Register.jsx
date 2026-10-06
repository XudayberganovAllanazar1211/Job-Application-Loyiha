import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { api } from "../api"

export default function Register() {
    const [form, setForm] = useState({
        username: "",
        email: "",
        password: "",
        confirm_password: "",
        first_name: "",
        last_name: "",
        birthday: ""
    })

    const [step, setStep] = useState(1) // 1: Ma'lumotlarni kiritish, 2: Kodni tasdiqlash
    const [verificationCode, setVerificationCode] = useState("")
    const [notice, setNotice] = useState("")
    const [loading, setLoading] = useState(false)
    const [acceptedPolicies, setAcceptedPolicies] = useState(false)
    const navigate = useNavigate()

    // 1-QADAM: Emailga kod yuborishni so'rash
    const requestVerification = async (e) => {
        e.preventDefault()
        setNotice("")

        // Maydonlarni to'liqligini tekshirish
        for (const key in form) {
            if (!form[key]) {
                setNotice("Iltimos, barcha maydonlarni to'ldiring.")
                return
            }
        }

        // Parollar mosligini tekshirish
        if (form.password !== form.confirm_password) {
            setNotice("Kiritilgan parollar mos kelmadi!")
            return
        }

        if (!acceptedPolicies) {
            setNotice("Ro'yxatdan o'tishdan oldin Privacy Policy va Terms of Service'ni qabul qiling.")
            return
        }

        setLoading(true)

        const result = await api("/register/send-code", {
            method: "POST",
            body: {
                username: form.username,
                email: form.email,
                password: form.password,
                first_name: form.first_name,
                last_name: form.last_name,
                birthday: form.birthday
            }
        })

        setLoading(false)

        if (result?.msg === "ok") {
            setNotice("Tasdiqlash kodi elektron pochtangizga yuborildi 📩")
            setStep(2) // Ikkinchi bosqichga o'tish
        } else {
            setNotice(result?.msg || "Email yuborishda xatolik yuz berdi.")
        }
    }

    // 2-QADAM: Kodni tasdiqlab ro'yxatdan o'tishni yakunlash
    const confirmVerification = async (e) => {
        e.preventDefault()
        setNotice("")

        if (verificationCode.length !== 6) {
            setNotice("Iltimos, 6 xonali tasdiqlash kodini to'liq kiriting.")
            return
        }

        setLoading(true)

        const result = await api("/register/verify", {
            method: "POST",
            body: {
                email: form.email,
                code: verificationCode
            }
        })

        setLoading(false)

        if (result?.msg === "ok") {
            setNotice("Tabriklaymiz! Ro‘yxatdan o‘tish muvaffaqiyatli yakunlandi ✅")
            setTimeout(() => navigate("/login"), 1500)
        } else {
            setNotice(result?.msg || "Kod noto'g'ri yoki uning muddati tugagan!")
        }
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
                    <h1 className="hero-title">Xavfsiz va tezkor hisob ochish</h1>
                    <p className="hero-text">
                        Elektron pochta orqali verification tizimi bilan himoyalangan va startup uslubidagi mukammal platforma.
                    </p>
                    <div className="hero-points">
                        <div className="hero-point">📧 Email orqali 2FA tasdiqlash kodi</div>
                        <div className="hero-point">🧩 Multi-talent bitta umumiy profil</div>
                        <div className="hero-point">📱 Mobilga mos responsive dizayn</div>
                    </div>
                </div>
            </section>

            <section className="auth-hero">
                <div className="auth-card">
                    <h2 style={{ marginTop: 0 }}>Register</h2>
                    <p className="muted" style={{ marginTop: 0 }}>
                        {step === 1 ? "Ma'lumotlaringizni to'ldiring." : "Elektron pochtangizga yuborilgan kodni kiriting."}
                    </p>

                    {notice && (
                        <div className={notice.includes("muvaffaqiyatli") || notice.includes("yuborildi") ? "notice ok" : "notice warn"} style={{ marginBottom: 14 }}>
                            {notice}
                        </div>
                    )}

                    {step === 1 ? (
                        /* --- 1-QADAM: REGISTRATSIYA ANKETASI --- */
                        <form className="form" onSubmit={requestVerification}>
                            <div className="form-row">
                                <input
                                    className="input"
                                    placeholder="Ism (First name)"
                                    value={form.first_name}
                                    onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                                    required
                                />
                                <input
                                    className="input"
                                    placeholder="Familiya (Last name)"
                                    value={form.last_name}
                                    onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                                    required
                                />
                            </div>

                            <input
                                className="input"
                                type="date"
                                placeholder="Tug'ilgan sana (Birthday)"
                                value={form.birthday}
                                onChange={(e) => setForm({ ...form, birthday: e.target.value })}
                                required
                            />

                            <input
                                className="input"
                                placeholder="Username"
                                value={form.username}
                                onChange={(e) => setForm({ ...form, username: e.target.value })}
                                required
                            />

                            <input
                                className="input"
                                type="email"
                                placeholder="Email manzilingiz"
                                value={form.email}
                                onChange={(e) => setForm({ ...form, email: e.target.value })}
                                required
                            />

                            <div className="form-row">
                                <input
                                    className="input"
                                    type="password"
                                    placeholder="Parol"
                                    value={form.password}
                                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                                    required
                                />
                                <input
                                    className="input"
                                    type="password"
                                    placeholder="Parol tasdig'i"
                                    value={form.confirm_password}
                                    onChange={(e) => setForm({ ...form, confirm_password: e.target.value })}
                                    required
                                />
                            </div>

                            <label className="policy-check">
                                <input
                                    type="checkbox"
                                    checked={acceptedPolicies}
                                    onChange={(e) => setAcceptedPolicies(e.target.checked)}
                                />
                                <span>
                                    <Link className="link" to="/terms">Terms of Service</Link> va <Link className="link" to="/privacy">Privacy Policy</Link>ni o'qidim va qabul qilaman.
                                </span>
                            </label>

                            <button className="btn btn-primary" disabled={loading}>
                                {loading ? "Yuborilmoqda..." : "Kodni olish (Email)"}
                            </button>
                        </form>
                    ) : (
                        /* --- 2-QADAM: 6 XONALI KODNI TASDIQLASH --- */
                        <form className="form" onSubmit={confirmVerification}>
                            <div style={{ textAlign: "center", marginBottom: 10 }}>
                                <p style={{ fontSize: 13 }} className="muted">
                                    Kod yuborilgan manzil: <strong style={{ color: "#172033" }}>{form.email}</strong>
                                </p>
                            </div>
                            <input
                                className="input"
                                type="text"
                                maxLength="6"
                                placeholder="6 xonali tasdiqlash kodi"
                                style={{ textAlign: "center", fontSize: 22, letterSpacing: 6, fontWeight: 800 }}
                                value={verificationCode}
                                onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, ""))}
                                required
                            />

                            <button className="btn btn-success" disabled={loading}>
                                {loading ? "Tasdiqlanmoqda..." : "Tasdiqlash & Yakunlash"}
                            </button>
                            <button type="button" className="btn btn-secondary" onClick={() => setStep(1)}>
                                Orqaga qaytish
                            </button>
                        </form>
                    )}

                    <p style={{ marginTop: 16 }}>
                        Allaqachon akkaunting bor? <Link className="link" to="/login">Login</Link>
                    </p>
                    <div className="auth-legal-links">
                        <Link to="/privacy">Privacy</Link>
                        <Link to="/terms">Terms</Link>
                        <Link to="/community-rules">Community Rules</Link>
                    </div>
                </div>
            </section>
        </div>
    )
}
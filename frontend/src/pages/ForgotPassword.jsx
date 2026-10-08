import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { api } from "../api"

export default function ForgotPassword() {
    const [step, setStep] = useState(1)
    const [email, setEmail] = useState("")
    const [code, setCode] = useState("")
    const [password, setPassword] = useState("")
    const [confirmPassword, setConfirmPassword] = useState("")
    const [notice, setNotice] = useState("")
    const [loading, setLoading] = useState(false)
    const navigate = useNavigate()

    const requestCode = async (e) => {
        e.preventDefault()
        setNotice("")

        if (!email.trim()) {
            setNotice("Elektron pochta manzilini kiriting.")
            return
        }

        setLoading(true)
        const result = await api("/forgot-password/send-code", {
            method: "POST",
            body: { email: email.trim().toLowerCase() }
        })
        setLoading(false)

        if (result?.msg) {
            setNotice(result.msg)
            if (result.msg.includes("yuborildi")) {
                setStep(2)
            }
        } else {
            setNotice("So‘rovni yuborishda xatolik yuz berdi.")
        }
    }

    const resetPassword = async (e) => {
        e.preventDefault()
        setNotice("")

        if (!/^\d{6}$/.test(code)) {
            setNotice("6 xonali kodni to‘liq kiriting.")
            return
        }

        if (password.length < 8) {
            setNotice("Yangi parol kamida 8 belgidan iborat bo‘lishi kerak.")
            return
        }

        if (password !== confirmPassword) {
            setNotice("Yangi parollar mos kelmadi.")
            return
        }

        setLoading(true)
        const result = await api("/forgot-password/reset", {
            method: "POST",
            body: {
                email: email.trim().toLowerCase(),
                code,
                password
            }
        })
        setLoading(false)

        if (result?.msg === "ok") {
            setNotice("Parolingiz muvaffaqiyatli yangilandi. Endi yangi parol bilan kiring.")
            setTimeout(() => navigate("/login"), 1200)
            return
        }

        setNotice(result?.msg || "Parolni tiklashda xatolik yuz berdi.")
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
                    <h1 className="hero-title">Hisobingizni qayta tiklang</h1>
                    <p className="hero-text">
                        Email orqali yuborilgan bir martalik kod yordamida parolingizni xavfsiz yangilang.
                    </p>
                    <div className="hero-points">
                        <div className="hero-point">🔐 6 xonali bir martalik kod</div>
                        <div className="hero-point">⏱️ Kod 10 daqiqa amal qiladi</div>
                        <div className="hero-point">🚪 Parol o‘zgarganda eski sessiyalar yopiladi</div>
                    </div>
                </div>
            </section>

            <section className="auth-hero">
                <div className="auth-card">
                    <h2 style={{ marginTop: 0 }}>Parolni unutdingizmi?</h2>
                    <p className="muted" style={{ marginTop: 0 }}>
                        {step === 1 ? "Account emailingizni kiriting." : "Emailingizga kelgan kod va yangi parolni kiriting."}
                    </p>

                    {notice && (
                        <div className={notice.includes("muvaffaqiyatli") || notice.includes("yuborildi") ? "notice ok" : "notice warn"} style={{ marginBottom: 14 }}>
                            {notice}
                        </div>
                    )}

                    {step === 1 ? (
                        <form className="form" onSubmit={requestCode}>
                            <input
                                className="input"
                                type="email"
                                placeholder="Elektron pochta"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                required
                            />
                            <button className="btn btn-primary" disabled={loading}>
                                {loading ? "Yuborilmoqda..." : "Tiklash kodini yuborish"}
                            </button>
                        </form>
                    ) : (
                        <form className="form" onSubmit={resetPassword}>
                            <input
                                className="input"
                                type="text"
                                inputMode="numeric"
                                maxLength="6"
                                placeholder="6 xonali kod"
                                value={code}
                                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                                required
                            />
                            <input
                                className="input"
                                type="password"
                                placeholder="Yangi parol"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                required
                            />
                            <input
                                className="input"
                                type="password"
                                placeholder="Yangi parolni tasdiqlang"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                required
                            />
                            <button className="btn btn-primary" disabled={loading}>
                                {loading ? "Saqlanmoqda..." : "Yangi parolni saqlash"}
                            </button>
                            <button type="button" className="btn btn-secondary" onClick={() => setStep(1)}>
                                Boshqa emaildan foydalanish
                            </button>
                        </form>
                    )}

                    <p style={{ marginTop: 16 }}>
                        <Link className="link" to="/login">Kirish sahifasiga qaytish</Link>
                    </p>
                </div>
            </section>
        </div>
    )
}

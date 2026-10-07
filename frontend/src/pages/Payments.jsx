import { useEffect, useState } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

function statusLabel(status) {
    return {
        pending: "Kutilmoqda",
        paid: "To‘langan",
        failed: "Xatolik",
        refunded: "Qaytarilgan",
        released: "Yakunlangan",
        held: "Waiting — ish yakunlanishini kutmoqda"
    }[status] || status
}

export default function Payments() {
    const { jobId } = useParams()
    const [searchParams] = useSearchParams()
    const [payment, setPayment] = useState(null)
    const [payments, setPayments] = useState([])
    const [loading, setLoading] = useState(true)
    const [creating, setCreating] = useState(false)
    const [notice, setNotice] = useState("")
    const [error, setError] = useState("")
    const [wallet, setWallet] = useState({ balance: 0, transactions: [] })
    const token = localStorage.getItem("token") || ""
    const navigate = useNavigate()

    const loadWallet = async () => {
        const result = await api("/wallet", { token })
        if (result?.balance !== undefined) setWallet(result)
    }

    const loadHistory = async () => {
        const result = await api("/payments", { token })
        if (Array.isArray(result)) setPayments(result)
    }

    useEffect(() => {
        const load = async () => {
            setLoading(true)
            setError("")
            if (jobId) {
                const result = await api("/payments/create/" + jobId, {
                    method: "POST",
                    token
                })
                if (result?.payment_uuid) {
                    setPayment(result)
                } else if (result?.msg === "already_paid") {
                    setPayment({ status: "paid" })
                } else if (result?.msg) {
                    setError(result.msg)
                }
            }
            await loadHistory()
            await loadWallet()
            setLoading(false)
        }
        load()
    }, [jobId])

    useEffect(() => {
        const paymentUuid = searchParams.get("payment")
        if (!paymentUuid) return

        const check = async () => {
            const result = await api("/payments/" + paymentUuid, { token })
            if (result?.payment_uuid) setPayment(result)
        }
        check()
    }, [searchParams])

    const startPayment = async () => {
        if (!jobId || creating) return
        setCreating(true)
        setError("")
        setNotice("")
        const result = await api("/payments/create/" + jobId, {
            method: "POST",
            token
        })
        setCreating(false)

        if (result?.checkout_url) {
            window.location.href = result.checkout_url
            return
        }

        if (result?.msg === "already_paid") {
            setPayment({ status: "paid" })
            setNotice("Bu ish uchun to‘lov allaqachon amalga oshirilgan.")
            return
        }

        setError(result?.msg || "To‘lovni yaratib bo‘lmadi.")
    }

    const dummyPay = async () => {
        if (!jobId || creating) return
        setCreating(true)
        setError("")
        setNotice("")
        const result = await api("/payments/dummy/" + jobId, { method: "POST", token })
        setCreating(false)
        if (result?.status === "held" || result?.status === "paid") {
            setPayment(result)
            setNotice("To‘lov amalga oshdi va hozircha waiting holatida saqlanmoqda.")
            await loadHistory()
            await loadWallet()
            return
        }
        setError(result?.msg || "Test to‘lovini amalga oshirib bo‘lmadi.")
    }

    if (loading) {
        return (
            <AppLayout title="To‘lovlar" subtitle="To‘lov ma’lumotlari yuklanmoqda.">
                <div className="card"><div className="skeleton skeleton-line skeleton-title" /><div className="skeleton skeleton-line" /></div>
            </AppLayout>
        )
    }

    if (jobId) {
        return (
            <AppLayout title="Ish uchun to‘lov" subtitle="Hozircha test balansidan foydalanib to‘lovni sinab ko‘ring.">
                <div className="card" style={{ maxWidth: 760, margin: "0 auto" }}>
                    <div className="page-head">
                        <h2>To‘lovni tasdiqlash</h2>
                        <p className="muted">Karta ma’lumotlari FinJob serverida saqlanmaydi.</p>
                    </div>

                    {notice && <div className="notice ok">{notice}</div>}
                    {error && <div className="notice warn">{error}</div>}

                    {payment?.status === "released" ? (
                        <div className="empty-state">
                            <strong>To‘lov ishchiga o‘tkazildi.</strong>
                            <span>Ish ikki tomon tasdig‘i bilan yakunlangan.</span>
                            <button className="btn btn-primary" onClick={() => navigate("/jobs")}>Ishlarga qaytish</button>
                        </div>
                    ) : payment?.status === "refunded" ? (
                        <div className="empty-state">
                            <strong>To‘lov qaytarilgan.</strong>
                            <span>Admin qarori bilan mablag‘ egasining balansiga qaytarilgan.</span>
                            <button className="btn btn-primary" onClick={() => navigate("/jobs")}>Ishlarga qaytish</button>
                        </div>
                    ) : (
                        <>
                            <div className="payment-summary">
                                <div><span>Test balansingiz</span><strong>{Number(wallet.balance || 0).toLocaleString("uz-UZ")} UZS</strong></div>
                                <div><span>Holat</span><strong>{statusLabel(payment?.status || "pending")}</strong></div>
                                <div><span>Summa</span><strong>{payment?.amount ? Number(payment.amount).toLocaleString("uz-UZ") : "—"} {payment?.currency || "UZS"}</strong></div>
                                <div><span>To‘lov turi</span><strong>{payment?.provider === "dummy" ? "Test" : "Click"}</strong></div>
                            </div>

                            <div className="notice" style={{ marginBottom: 16 }}>
                                Bu vaqtinchalik dummy/test to‘lov. To‘lov darhol ishchiga berilmaydi: mablag‘ FinJob escrowida waiting holatida turadi va ish ikki tomon tomonidan yakunlangachgina ishchiga o‘tadi. Ishchi almashtirilsa ham shu to‘lov saqlanadi.
                            </div>

                            <button className="btn btn-primary" disabled={creating || !payment?.payment_uuid} onClick={dummyPay}>
                                {creating ? "To‘lanmoqda..." : "Test balansidan to‘lash"}
                            </button>
                            <button className="btn btn-secondary" style={{ marginLeft: 8 }} onClick={() => navigate("/jobs")}>
                                Keyinroq
                            </button>
                        </>
                    )}
                </div>
            </AppLayout>
        )
    }

    return (
        <AppLayout title="To‘lovlar" subtitle="FinJob orqali amalga oshirilgan to‘lovlar tarixi.">
            <div className="card">
                <div className="page-head">
                    <h2>To‘lovlar tarixi</h2>
                    <p className="muted">So‘nggi 100 ta transaction.</p>
                </div>
                {!payments.length ? (
                    <div className="empty-state">
                        <strong>Hozircha to‘lovlar yo‘q.</strong>
                        <span>Ish qabul qilingach, to‘lov shu yerda ko‘rinadi.</span>
                    </div>
                ) : (
                    <div className="job-grid">
                        {payments.map((item) => (
                            <article className="card job-card" key={item.payment_uuid}>
                                <h3 className="job-title">{item.title}</h3>
                                <div className="meta">
                                    <span className="chip">💰 {Number(item.amount).toLocaleString("uz-UZ")} {item.currency}</span>
                                    <span className="chip">{statusLabel(item.status)}</span>
                                    <span className="chip">{item.provider.toUpperCase()}</span>
                                </div>
                                <p className="muted">ID: {item.payment_uuid}</p>
                                <button className="btn btn-secondary" onClick={() => navigate("/payments/job/" + item.job_id)}>
                                    Ko‘rish
                                </button>
                            </article>
                        ))}
                    </div>
                )}
            </div>
        </AppLayout>
    )
}

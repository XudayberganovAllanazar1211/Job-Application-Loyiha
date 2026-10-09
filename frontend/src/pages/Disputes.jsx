import { useEffect, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

const categories = {
    payment: "To‘lov",
    quality: "Ish sifati",
    deadline: "Muddat",
    communication: "Muloqot",
    other: "Boshqa"
}

const statusLabels = {
    open: "Ochiq",
    reviewing: "Ko‘rib chiqilmoqda",
    resolved: "Hal qilindi",
    rejected: "Rad etildi",
    payment_pending: "To‘lov kutilmoqda",
    accepted: "Qabul qilingan",
    pending_finish: "Tasdiqlash kutilmoqda",
    finished: "Yakunlangan"
}

function ActiveDisputeList({ items, loading, userId }) {
    const [selected, setSelected] = useState(null)

    return (
        <section className="card">
            <div className="profile-section-head">
                <div>
                    <span className="profile-eyebrow">ACTIVE DISPUTES</span>
                    <h2 className="section-title">Aktiv nizolar</h2>
                </div>
                <span className="profile-count">{items.length}</span>
            </div>
            {loading ? <div className="empty-state">Nizolar yuklanmoqda...</div> : items.length === 0 ? (
                <div className="profile-empty">
                    <strong>Aktiv nizo yo‘q</strong>
                    <span>Bu yerda siz ochgan yoki sizga ochilgan, hali hal qilinmagan nizolar ko‘rinadi.</span>
                </div>
            ) : (
                <div className="dispute-list">
                    {items.map((item) => {
                        const openedByMe = Number(item.opened_by) === Number(userId)
                        return (
                            <article className="dispute-item" key={item.id}>
                                <div>
                                    <strong>{item.job_title || "Ish #" + item.job_id}</strong>
                                    <span>
                                        Nizo #{item.id} · {categories[item.category] || item.category} · {statusLabels[item.status] || item.status}
                                    </span>
                                    <span>{openedByMe ? "Siz ochgansiz" : "Sizga ochilgan"} · Ish #{item.job_id}</span>
                                    <p>{item.description}</p>
                                </div>
                                <button className="btn btn-secondary" type="button" onClick={() => setSelected(selected === item.id ? null : item.id)}>
                                    {selected === item.id ? "Yopish" : "Batafsil"}
                                </button>
                                {selected === item.id && (
                                    <div className="dispute-detail">
                                        <div><strong>Qarshi tomon:</strong> @{item.against_username || "foydalanuvchi"}</div>
                                        {item.evidence && <div><strong>Dalillar:</strong> {item.evidence}</div>}
                                        {item.admin_response && <div><strong>Admin javobi:</strong> {item.admin_response}</div>}
                                        <div><strong>Holat:</strong> {statusLabels[item.status] || item.status}</div>
                                        <div><strong>Oxirgi yangilanish:</strong> {item.updated_at || item.created_at || "—"}</div>
                                    </div>
                                )}
                            </article>
                        )
                    })}
                </div>
            )}
        </section>
    )
}

export default function Disputes() {
    const [items, setItems] = useState([])
    const [loading, setLoading] = useState(true)
    const token = localStorage.getItem("token") || ""
    const user = JSON.parse(localStorage.getItem("user") || "null")

    useEffect(() => {
        let alive = true
        const load = async () => {
            setLoading(true)
            const result = await api("/disputes", { token })
            if (alive) {
                setItems(Array.isArray(result) ? result : [])
                setLoading(false)
            }
        }
        load()
        return () => { alive = false }
    }, [token])

    return (
        <AppLayout title="Nizolar markazi" subtitle="Faqat siz ochgan yoki sizga ochilgan, hali aktiv bo‘lgan nizolar.">
            <div className="disputes-page">
                <ActiveDisputeList items={items} loading={loading} userId={user?.id} />
            </div>
        </AppLayout>
    )
}

export function CreateDispute() {
    const [searchParams] = useSearchParams()
    const navigate = useNavigate()
    const jobId = searchParams.get("job") || ""
    const token = localStorage.getItem("token") || ""
    const user = JSON.parse(localStorage.getItem("user") || "null")
    const [job, setJob] = useState(null)
    const [checkingJob, setCheckingJob] = useState(true)
    const [notice, setNotice] = useState("")
    const [submitted, setSubmitted] = useState(false)
    const [form, setForm] = useState({ category: "payment", description: "", evidence: "" })

    useEffect(() => {
        let alive = true
        const verifyJob = async () => {
            setCheckingJob(true)
            setJob(null)
            setNotice("")
            setSubmitted(false)
            if (!/^\d+$/.test(jobId)) {
                if (alive) {
                    setNotice("Nizo faqat ish sahifasidan ochilishi mumkin. Avval tegishli ishni tanlang.")
                    setCheckingJob(false)
                }
                return
            }
            const result = await api("/disputes/eligible-jobs?job_id=" + encodeURIComponent(jobId), { token })
            if (!alive) return
            const eligible = Array.isArray(result?.items) ? result.items : []
            const matchingJob = eligible.find((item) => String(item.id) === String(Number(jobId)))
            if (matchingJob) setJob(matchingJob)
            else setNotice("Bu ish nizo ochish uchun yaroqli emas yoki u bo‘yicha allaqachon aktiv nizo mavjud.")
            setCheckingJob(false)
        }
        verifyJob()
        return () => { alive = false }
    }, [jobId, token])

    const submit = async (event) => {
        event.preventDefault()
        if (!job || submitted) return
        setNotice("")
        const result = await api("/disputes", {
            method: "POST",
            token,
            body: {
                job_id: Number(job.id),
                category: form.category,
                description: form.description.trim(),
                evidence: form.evidence.trim()
            }
        })
        if (result?.ok) {
            setSubmitted(true)
            setNotice("Nizo muvaffaqiyatli yuborildi. Endi uni «Nizolar» bo‘limida kuzatishingiz mumkin.")
        } else setNotice(result?.msg || "Nizo ochilmadi.")
    }

    return (
        <AppLayout title="Nizo ochish" subtitle="Bu forma faqat tanlangan ish ichidan ochiladi. Ishni bu yerdan o‘zgartirib bo‘lmaydi.">
            <div className="disputes-page">
                {notice && <div className={"notice " + (submitted ? "ok" : "warn")}>{notice}</div>}
                {checkingJob ? (
                    <section className="card"><div className="empty-state">Tanlangan ish tekshirilmoqda...</div></section>
                ) : !job ? (
                    <section className="card">
                        <div className="profile-empty">
                            <strong>Nizo formasini ochib bo‘lmadi</strong>
                            <span>Nizoni tegishli ish sahifasidagi “Nizo ochish” tugmasi orqali boshlang.</span>
                            <button className="btn btn-secondary" type="button" onClick={() => navigate("/disputes")}>Aktiv nizolarga qaytish</button>
                        </div>
                    </section>
                ) : submitted ? (
                    <section className="card">
                        <div className="profile-empty">
                            <strong>Nizo yuborildi</strong>
                            <span>Yuborgan nizo faqat aktiv bo‘lganida «Nizolar» bo‘limida ko‘rinadi.</span>
                            <button className="btn btn-primary" type="button" onClick={() => navigate("/disputes")}>Nizolarimni ko‘rish</button>
                        </div>
                    </section>
                ) : (
                    <>
                        <section className="card dispute-job-lock">
                            <span className="profile-eyebrow">TANLANGAN ISH · O‘ZGARTIRIB BO‘LMAYDI</span>
                            <h2 className="section-title">{job.title}</h2>
                            <div className="dispute-locked-meta">
                                <span>Ish ID: #{job.id}</span>
                                <span>{Number(job.user_id) === Number(user?.id) ? "Siz — mijoz" : "Siz — ijrochi"}</span>
                                <span>Holat: {statusLabels[job.status] || job.status}</span>
                            </div>
                        </section>
                        <section className="card">
                            <div className="profile-section-head">
                                <div>
                                    <span className="profile-eyebrow">DISPUTE CENTER</span>
                                    <h2 className="section-title">Nizo tafsilotlari</h2>
                                </div>
                            </div>
                            <form className="form" onSubmit={submit}>
                                <div>
                                    <label className="helper" htmlFor="dispute-category">Sabab</label>
                                    <select id="dispute-category" className="select" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                                        {Object.entries(categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="helper" htmlFor="dispute-description">Muammo tavsifi</label>
                                    <textarea id="dispute-description" className="textarea" rows="5" maxLength="3000" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Muammoni aniq tushuntiring..." required />
                                </div>
                                <div>
                                    <label className="helper" htmlFor="dispute-evidence">Dalillar</label>
                                    <textarea id="dispute-evidence" className="textarea" rows="4" maxLength="3000" value={form.evidence} onChange={(e) => setForm({ ...form, evidence: e.target.value })} placeholder="Xabarlar, to‘lov yoki boshqa dalillar haqida ma’lumot..." />
                                </div>
                                <button className="btn btn-primary" type="submit" disabled={!job || !form.description.trim()}>Nizoni yuborish</button>
                                <button className="btn btn-secondary" type="button" onClick={() => navigate("/disputes")}>Bekor qilish</button>
                            </form>
                        </section>
                    </>
                )}
            </div>
        </AppLayout>
    )
}

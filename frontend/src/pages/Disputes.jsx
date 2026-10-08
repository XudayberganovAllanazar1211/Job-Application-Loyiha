import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
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
    rejected: "Rad etildi"
}

export default function Disputes() {
    const [items, setItems] = useState([])
    const [loading, setLoading] = useState(true)
    const [notice, setNotice] = useState("")
    const [selected, setSelected] = useState(null)
    const [form, setForm] = useState({ job_id: "", category: "payment", description: "", evidence: "" })
    const [searchParams] = useSearchParams()
    const token = localStorage.getItem("token") || ""

    useEffect(() => {
        const jobId = searchParams.get("job")
        if (jobId && /^\d+$/.test(jobId)) setForm((current) => ({ ...current, job_id: jobId }))
    }, [searchParams])

    const load = async () => {
        setLoading(true)
        const result = await api("/disputes", { token })
        setItems(Array.isArray(result) ? result : [])
        setLoading(false)
    }

    useEffect(() => { load() }, [])

    const submit = async (event) => {
        event.preventDefault()
        const result = await api("/disputes", {
            method: "POST",
            token,
            body: {
                job_id: Number(form.job_id),
                category: form.category,
                description: form.description.trim(),
                evidence: form.evidence.trim()
            }
        })
        if (result?.ok) {
            setNotice("Nizo muvaffaqiyatli ochildi.")
            setForm({ job_id: "", category: "payment", description: "", evidence: "" })
            await load()
        } else setNotice(result?.msg || "Nizo ochilmadi.")
    }

    return (
        <AppLayout title="Nizolar markazi" subtitle="Ish bo‘yicha muammolarni xavfsiz tarzda yuboring va qaror holatini kuzating.">
            <div className="disputes-page">
                {notice && <div className="notice ok">{notice}</div>}
                <section className="card">
                    <div className="profile-section-head">
                        <div>
                            <span className="profile-eyebrow">DISPUTE CENTER</span>
                            <h2 className="section-title">Yangi nizo ochish</h2>
                        </div>
                    </div>
                    <form className="form" onSubmit={submit}>
                        <div className="form-row">
                            <div>
                                <label className="helper">Ish ID</label>
                                <input className="input" type="number" min="1" value={form.job_id} onChange={(e) => setForm({ ...form, job_id: e.target.value })} placeholder="Masalan: 42" required />
                            </div>
                            <div>
                                <label className="helper">Sabab</label>
                                <select className="select" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                                    {Object.entries(categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                                </select>
                            </div>
                        </div>
                        <div>
                            <label className="helper">Muammo tavsifi</label>
                            <textarea className="textarea" rows="5" maxLength="3000" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Muammoni aniq tushuntiring..." required />
                        </div>
                        <div>
                            <label className="helper">Dalillar</label>
                            <textarea className="textarea" rows="4" maxLength="3000" value={form.evidence} onChange={(e) => setForm({ ...form, evidence: e.target.value })} placeholder="Xabarlar, to‘lov yoki boshqa dalillar haqida ma’lumot..." />
                        </div>
                        <button className="btn btn-primary" type="submit">Nizoni yuborish</button>
                    </form>
                </section>

                <section className="card">
                    <div className="profile-section-head">
                        <div>
                            <span className="profile-eyebrow">HISTORY</span>
                            <h2 className="section-title">Mening nizolarim</h2>
                        </div>
                        <span className="profile-count">{items.length}</span>
                    </div>
                    {loading ? <div className="empty-state">Nizolar yuklanmoqda...</div> : items.length === 0 ? (
                        <div className="profile-empty"><strong>Hali nizo yo‘q</strong><span>Muammo bo‘lsa, yuqoridagi forma orqali nizo ochishingiz mumkin.</span></div>
                    ) : (
                        <div className="dispute-list">
                            {items.map((item) => (
                                <article className="dispute-item" key={item.id}>
                                    <div>
                                        <strong>{item.job_title || "Ish #" + item.job_id}</strong>
                                        <span>{categories[item.category] || item.category} · {statusLabels[item.status] || item.status}</span>
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
                                        </div>
                                    )}
                                </article>
                            ))}
                        </div>
                    )}
                </section>
            </div>
        </AppLayout>
    )
}

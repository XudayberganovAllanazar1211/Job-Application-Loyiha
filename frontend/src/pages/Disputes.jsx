import { useEffect, useRef, useState } from "react"
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
    const [eligibleJobs, setEligibleJobs] = useState([])
    const [jobsLoading, setJobsLoading] = useState(true)
    const [form, setForm] = useState({ job_id: "", category: "payment", description: "", evidence: "" })
    const [searchParams] = useSearchParams()
    const token = localStorage.getItem("token") || ""
    const user = JSON.parse(localStorage.getItem("user") || "null")
    const prefillHandled = useRef(false)

    const loadEligibleJobs = async () => {
        setJobsLoading(true)
        const result = await api("/disputes/eligible-jobs", { token })
        setEligibleJobs(Array.isArray(result?.items) ? result.items : [])
        setJobsLoading(false)
    }

    useEffect(() => {
        if (prefillHandled.current || jobsLoading) return
        prefillHandled.current = true
        const jobId = searchParams.get("job")
        if (!jobId || !/^\d+$/.test(jobId)) return
        if (eligibleJobs.some((job) => String(job.id) === jobId)) {
            setForm((current) => ({ ...current, job_id: jobId }))
        } else {
            setNotice("Tanlangan ish nizo ochish uchun yaroqli emas yoki u bo‘yicha ochiq nizo mavjud.")
        }
    }, [searchParams, eligibleJobs, jobsLoading])

    const load = async () => {
        setLoading(true)
        const result = await api("/disputes", { token })
        setItems(Array.isArray(result) ? result : [])
        setLoading(false)
    }

    useEffect(() => { load(); loadEligibleJobs() }, [])

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
            await Promise.all([load(), loadEligibleJobs()])
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
                                <label className="helper" htmlFor="dispute-job">Ishni tanlang</label>
                                <select
                                    id="dispute-job"
                                    className="select"
                                    value={form.job_id}
                                    onChange={(e) => setForm({ ...form, job_id: e.target.value })}
                                    required
                                    disabled={jobsLoading || eligibleJobs.length === 0}
                                >
                                    <option value="">{jobsLoading ? "Ishlar yuklanmoqda..." : "Nizo ochiladigan ishni tanlang"}</option>
                                    {eligibleJobs.map((job) => (
                                        <option key={job.id} value={job.id}>
                                            #{job.id} · {job.title} — {Number(job.user_id) === Number(user?.id) ? "Mijoz" : "Ijrochi"} · {statusLabels[job.status] || job.status}
                                        </option>
                                    ))}
                                </select>
                                {!jobsLoading && eligibleJobs.length === 0 && (
                                    <p className="helper">Nizo ochish mumkin bo‘lgan ish topilmadi. Ish qabul qilingan yoki yakunlanayotgan/yakunlangan bo‘lishi va unda ochiq nizo bo‘lmasligi kerak.</p>
                                )}
                            </div>
                            <div>
                                <label className="helper" htmlFor="dispute-category">Sabab</label>
                                <select id="dispute-category" className="select" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
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
                        <button className="btn btn-primary" type="submit" disabled={jobsLoading || !form.job_id || eligibleJobs.length === 0}>Nizoni yuborish</button>
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

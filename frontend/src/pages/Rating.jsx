import { useEffect, useMemo, useState } from "react"
import { useLocation, useNavigate, useParams } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

export default function Rating() {
    const { jobId } = useParams()
    const location = useLocation()
    const navigate = useNavigate()
    const token = localStorage.getItem("token") || ""
    const me = JSON.parse(localStorage.getItem("user") || "null")
    const [job, setJob] = useState(location.state?.job || null)
    const [form, setForm] = useState({
        score: 5,
        comment: "",
        to_user: String(location.state?.job?.worker_id || location.state?.job?.user_id || "")
    })
    const [notice, setNotice] = useState("")
    const [loading, setLoading] = useState(false)

    useEffect(() => {
        const fetchJob = async () => {
            if (!job && jobId) {
                const jobData = await api(`/jobs/${jobId}`, { token })
                if (jobData?.id) {
                    setJob(jobData)
                    const targetId = jobData.user_id === me?.id ? jobData.worker_id : jobData.user_id
                    if (targetId) {
                        setForm((prev) => ({ ...prev, to_user: String(targetId) }))
                    }
                }
            }
        }
        fetchJob()
    }, [jobId, job, me?.id, token])

    const ready = useMemo(
        () => Number(form.score) >= 1 && Number(form.score) <= 10 && form.to_user,
        [form]
    )

    const submit = async (e) => {
        e.preventDefault()
        setLoading(true)
        setNotice("")

        const result = await api("/rating", {
            method: "POST",
            body: {
                job_id: Number(jobId),
                to_user: Number(form.to_user),
                score: Number(form.score),
                comment: form.comment
            },
            token
        })

        setLoading(false)

        if (result?.msg === "ok") {
            setNotice("Reyting yuborildi ✅")
            setTimeout(() => navigate("/jobs"), 1200)
            return
        }

        setNotice(result?.msg || "Rating xato")
    }

    return (
        <AppLayout
            title="Rating"
            subtitle="Job tugagach 1 dan 10 gacha baho bering."
        >
            <div className="grid-2">
                <section className="card">
                    <h2>Submit rating</h2>
                    <p className="muted">Bajarilgan ish sifatini baholang.</p>

                    {notice && (
                        <div className={notice.includes("✅") ? "notice ok" : "notice warn"} style={{ marginBottom: 14 }}>
                            {notice}
                        </div>
                    )}

                    <form className="form" onSubmit={submit}>
                        <div>
                            <div className="helper" style={{ marginBottom: 8 }}>Baho (Score): <strong>{form.score} / 10</strong></div>
                            <input
                                type="range"
                                min="1"
                                max="10"
                                value={form.score}
                                onChange={(e) => setForm({ ...form, score: e.target.value })}
                                style={{ width: "100%" }}
                            />
                        </div>

                        <div>
                            <label className="helper" style={{ display: "block", marginBottom: 4 }}>Baho berilayotgan foydalanuvchi ID</label>
                            <input
                                className="input"
                                placeholder="To user ID"
                                value={form.to_user}
                                onChange={(e) => setForm({ ...form, to_user: e.target.value })}
                                required
                            />
                        </div>

                        <div>
                            <label className="helper" style={{ display: "block", marginBottom: 4 }}>Izoh (Comment)</label>
                            <textarea
                                className="textarea"
                                placeholder="Xizmat haqida fikringizni yozing..."
                                value={form.comment}
                                onChange={(e) => setForm({ ...form, comment: e.target.value })}
                            />
                        </div>

                        <div className="actions">
                            <button className="btn btn-primary" disabled={!ready || loading}>
                                {loading ? "Yuborilmoqda..." : "Submit rating"}
                            </button>
                            <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
                                Back
                            </button>
                        </div>
                    </form>
                </section>

                <aside className="card">
                    <h3>Job context</h3>
                    <div className="chip-row">
                        <span className="chip">Job # {jobId}</span>
                        {job && <span className="chip">Title: {job.title}</span>}
                        {job?.status && <span className="chip">Status: {job.status}</span>}
                    </div>
                    <div className="empty-state" style={{ marginTop: 16 }}>
                        {job
                            ? `Ushbu baho ${job.title} ishi bo'yicha beriladi.`
                            : "Job ma'lumotlari avtomatik bog'lanadi."}
                    </div>
                </aside>
            </div>
        </AppLayout>
    )
}

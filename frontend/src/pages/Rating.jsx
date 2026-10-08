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
        to_user: ""
    })
    const [notice, setNotice] = useState("")
    const [loading, setLoading] = useState(false)

    useEffect(() => {
        if (!job) return

        const targetId = String(job.worker_id) === String(me?.id)
            ? job.user_id
            : job.worker_id

        if (targetId && String(targetId) !== String(me?.id)) {
            const nextTarget = String(targetId)
            setForm((prev) => prev.to_user === nextTarget ? prev : { ...prev, to_user: nextTarget })
        }
    }, [job, me?.id])

    useEffect(() => {
        const fetchJob = async () => {
            if (!job && jobId) {
                const jobData = await api(`/jobs/${jobId}`, { token })
                if (jobData?.ok === false && [403, 404].includes(Number(jobData.http_status))) {
                    navigate("/jobs", { replace: true })
                    return
                }
                if (jobData?.id) {
                    setJob(jobData)
                    const targetId = String(jobData.user_id) === String(me?.id)
                        ? jobData.worker_id
                        : jobData.user_id
                    if (targetId && String(targetId) !== String(me?.id)) {
                        setForm((prev) => ({ ...prev, to_user: String(targetId) }))
                    }
                }
            }
        }
        fetchJob()
    }, [jobId, job, me?.id, token])

    const ready = useMemo(
        () =>
            job?.status === "finished" &&
            Number(form.score) >= 1 &&
            Number(form.score) <= 10 &&
            form.to_user &&
            String(form.to_user) !== String(me?.id),
        [job, form, me?.id]
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

        setNotice(result?.msg || "Baho yuborishda xato")
    }

    return (
        <AppLayout
            title="Baho berish"
            subtitle="Ish tugagach 1 dan 10 gacha baho bering."
        >
            <div className="grid-2">
                <section className="card">
                    <h2>Bahoni yuborish</h2>
                    <p className="muted">Bajarilgan ish sifatini baholang.</p>

                    {notice && (
                        <div className={notice.includes("✅") ? "notice ok" : "notice warn"} style={{ marginBottom: 14 }}>
                            {notice}
                        </div>
                    )}

                    {job && job.status !== "finished" && (
                        <div className="notice warn" style={{ marginBottom: 14 }}>
                            Baho faqat ish tugagandan keyin beriladi.
                        </div>
                    )}

                    <form className="form" onSubmit={submit}>
                        <div>
                            <div className="helper" style={{ marginBottom: 8 }}>Baho: <strong>{form.score} / 10</strong></div>
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
                            <label className="helper" style={{ display: "block", marginBottom: 4 }}>Baho berilayotgan foydalanuvchi</label>
                            <div className="input rating-user-field">
                                {job
                                    ? (String(job.worker_id) === String(me?.id)
                                        ? ([job.creator_first, job.creator_last].filter(Boolean).join(" ") || job.creator_username || "Foydalanuvchi")
                                        : ([job.worker_first, job.worker_last].filter(Boolean).join(" ") || job.worker_username || "Foydalanuvchi"))
                                    : "Ish ma'lumotlari yuklanmoqda..."}
                            </div>
                        </div>

                        <div>
                            <label className="helper" style={{ display: "block", marginBottom: 4 }}>Izoh</label>
                            <textarea
                                className="textarea"
                                placeholder="Xizmat haqida fikringizni yozing..."
                                value={form.comment}
                                onChange={(e) => setForm({ ...form, comment: e.target.value })}
                            />
                        </div>

                        <div className="actions">
                            <button className="btn btn-primary" disabled={!ready || loading}>
                                {loading ? "Yuborilmoqda..." : "Bahoni yuborish"}
                            </button>
                            <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
                                Orqaga
                            </button>
                        </div>
                    </form>
                </section>

                <aside className="card">
                    <h3>Ish ma’lumotlari</h3>
                    <div className="chip-row">
                        <span className="chip">Ish # {jobId}</span>
                        {job && <span className="chip">Sarlavha: {job.title}</span>}
                        {job?.status && <span className="chip">Holat: {job.status}</span>}
                    </div>
                    <div className="empty-state" style={{ marginTop: 16 }}>
                        {job
                            ? `Ushbu baho ${job.title} ishi bo'yicha beriladi.`
                            : "Ish ma'lumotlari avtomatik bog‘lanadi."}
                    </div>
                </aside>
            </div>
        </AppLayout>
    )
}

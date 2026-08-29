import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

export default function CreateJob() {
    const [services, setServices] = useState([])
    const [form, setForm] = useState({
        service_id: "",
        title: "",
        description: "",
        price: "",
        location: ""
    })
    const [notice, setNotice] = useState("")
    const [loading, setLoading] = useState(false)
    const navigate = useNavigate()
    const token = localStorage.getItem("token") || ""

    useEffect(() => {
        const load = async () => {
            const result = await api("/services", { token })
            if (Array.isArray(result)) setServices(result)
        }
        load()
    }, [token])

    const canSubmit = useMemo(
        () => form.service_id && form.title && form.description && form.price && form.location,
        [form]
    )

    const submit = async (e) => {
        e.preventDefault()
        setNotice("")
        setLoading(true)

        const result = await api("/job", {
            method: "POST",
            body: {
                service_id: Number(form.service_id),
                title: form.title,
                description: form.description,
                price: Number(form.price),
                location: form.location
            },
            token
        })

        setLoading(false)

        if (result?.msg) {
            setNotice("Job yaratildi ✅")
            setTimeout(() => navigate("/jobs"), 700)
            return
        }

        setNotice("Job yaratishda xato")
    }

    return (
        <AppLayout
            title="Create Job"
            subtitle="Xizmat kategoriyasini tanlab, yangi ish joylang."
        >
            <div className="grid-2">
                <section className="card">
                    <h2>Job form</h2>
                    <p className="muted">Barcha maydonlarni to‘ldiring.</p>

                    {notice && <div className="notice ok" style={{ marginBottom: 14 }}>{notice}</div>}

                    <form className="form" onSubmit={submit}>
                        <select
                            className="select"
                            value={form.service_id}
                            onChange={(e) => setForm({ ...form, service_id: e.target.value })}
                        >
                            <option value="">Service category</option>
                            {services.map((service) => (
                                <option key={service.id} value={service.id}>
                                    {service.name}
                                </option>
                            ))}
                        </select>

                        <input
                            className="input"
                            placeholder="Title"
                            value={form.title}
                            onChange={(e) => setForm({ ...form, title: e.target.value })}
                        />

                        <textarea
                            className="textarea"
                            placeholder="Description"
                            value={form.description}
                            onChange={(e) => setForm({ ...form, description: e.target.value })}
                        />

                        <div className="form-row">
                            <input
                                className="input"
                                placeholder="Price"
                                value={form.price}
                                onChange={(e) => setForm({ ...form, price: e.target.value })}
                            />
                            <input
                                className="input"
                                placeholder="Location"
                                value={form.location}
                                onChange={(e) => setForm({ ...form, location: e.target.value })}
                            />
                        </div>

                        <button className="btn btn-primary" disabled={!canSubmit || loading}>
                            {loading ? "Yuborilmoqda..." : "Submit"}
                        </button>
                    </form>
                </section>

                <aside className="card">
                    <h3>Katalog</h3>
                    <p className="muted">Services ro‘yxati backenddagi /services dan olinadi.</p>
                    <div className="chip-row">
                        {services.length ? services.map((service) => (
                            <span className="chip" key={service.id}>{service.name}</span>
                        )) : <div className="empty-state">Hozircha service yo‘q</div>}
                    </div>
                </aside>
            </div>
        </AppLayout>
    )
}
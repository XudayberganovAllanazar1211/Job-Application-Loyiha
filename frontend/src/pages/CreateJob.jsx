import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

function buildServiceTree(services) {
    const nodes = Object.fromEntries(services.map((service) => [
        String(service.id),
        { ...service, children: [] }
    ]))
    const roots = []
    services.forEach((service) => {
        const node = nodes[String(service.id)]
        if (service.parent_id == null) roots.push(node)
        else if (nodes[String(service.parent_id)]) nodes[String(service.parent_id)].children.push(node)
    })
    return roots
}

function ServiceNode({ node, level, selected, onSelect }) {
    const [open, setOpen] = useState(level < 2)
    const hasChildren = node.children.length > 0

    return (
        <div>
            <div className="service-tree-row" style={{ paddingLeft: 10 + level * 20 }}>
                {hasChildren ? (
                    <button type="button" className="service-tree-toggle" onClick={() => setOpen(!open)}>
                        {open ? "▾" : "▸"}
                    </button>
                ) : <span className="service-tree-spacer" />}
                <button
                    type="button"
                    className={String(selected) === String(node.id) ? "service-tree-item selected" : "service-tree-item"}
                    disabled={hasChildren}
                    onClick={() => onSelect(node)}
                >
                    {node.name}
                </button>
            </div>
            {open && hasChildren && node.children.map((child) => (
                <ServiceNode key={child.id} node={child} level={level + 1} selected={selected} onSelect={onSelect} />
            ))}
        </div>
    )
}

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
    const serviceTree = useMemo(() => buildServiceTree(services), [services])

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

        if (result?.msg === "ok") {
            setNotice("Job yaratildi")
            setTimeout(() => navigate("/jobs"), 700)
            return
        }

        setNotice(result?.msg || "Job yaratishda xato")
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
                        <div className="service-picker">
                            <div className="service-picker-title">
                                {form.service_id
                                    ? services.find((service) => String(service.id) === String(form.service_id))?.name || "Xizmat"
                                    : "Xizmatni tanlang"}
                            </div>
                            <div className="service-tree">
                                {serviceTree.map((node) => (
                                    <ServiceNode
                                        key={node.id}
                                        node={node}
                                        level={0}
                                        selected={form.service_id}
                                        onSelect={(node) => setForm({ ...form, service_id: String(node.id) })}
                                    />
                                ))}
                            </div>
                        </div>

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
                                type="number"
                                min="0.01"
                                step="0.01"
                                placeholder="Price"
                                value={form.price}
                                onChange={(e) => setForm({ ...form, price: e.target.value })}
                                required
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

                <aside className="card job-tips-card">
                    <h3>Tips</h3>
                    <p className="muted">Yaxshi job e’lonini yaratish uchun foydali maslahatlar.</p>
                    <div className="tips-list">
                        <div className="tip-item">
                            <strong>🎯 Aniq sarlavha yozing</strong>
                            <span>Job title qisqa va tushunarli bo‘lsin. Masalan: “React landing page yaratish”.</span>
                        </div>
                        <div className="tip-item">
                            <strong>📝 Vazifani batafsil tushuntiring</strong>
                            <span>Nima kerakligini, qanday natija kutayotganingizni va muhim talablarni yozing.</span>
                        </div>
                        <div className="tip-item">
                            <strong>🛠️ To‘g‘ri service tanlang</strong>
                            <span>Jobingizga eng mos xizmatni tanlash kerakli mutaxassislarni topishni osonlashtiradi.</span>
                        </div>
                        <div className="tip-item">
                            <strong>💰 Realistik narx belgilang</strong>
                            <span>Ish hajmi va murakkabligiga mos narx qo‘yish ko‘proq yaxshi takliflarni jalb qiladi.</span>
                        </div>
                        <div className="tip-item">
                            <strong>📍 Location’ni ko‘rsating</strong>
                            <span>Offline ish bo‘lsa, ish bajariladigan joyni aniq yozing.</span>
                        </div>
                        <div className="tip-item">
                            <strong>⏱️ Muddatni ayting</strong>
                            <span>Kerak bo‘lsa, description ichida ish qachongacha tugashi kerakligini ko‘rsating.</span>
                        </div>
                        <div className="tip-item">
                            <strong>💬 Muhim tafsilotlarni yozing</strong>
                            <span>Kerakli skill, texnologiya, fayl yoki boshqa shartlarni oldindan belgilang.</span>
                        </div>
                    </div>
                </aside>
            </div>
        </AppLayout>
    )
}
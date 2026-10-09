import { useEffect, useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"
import { formatTimeAgo } from "../utils/time"

export default function Conversations() {
    const navigate = useNavigate()
    const location = useLocation()
    const token = localStorage.getItem("token") || ""
    const [items, setItems] = useState([])
    const [loading, setLoading] = useState(true)
    const [notice, setNotice] = useState(location.state?.notice || "")

    const load = async () => {
        setLoading(true)
        const result = await api("/conversations", { token })
        if (Array.isArray(result)) setItems(result)
        else setNotice(result?.msg || "Suhbatlarni yuklab bo‘lmadi.")
        setLoading(false)
    }

    useEffect(() => {
        load()
        const interval = setInterval(load, 5000)
        return () => clearInterval(interval)
    }, [])

    return (
        <AppLayout
            title="Suhbatlar"
            subtitle="Barcha ishlar bo‘yicha yozishmalarni bir joydan boshqaring."
        >
            {notice && <div className="notice warn" style={{ marginBottom: 16 }}>{notice}</div>}
            <section className="card">
                <div className="section-toolbar">
                    <div className="page-head">
                        <h2 style={{ margin: 0 }}>Suhbatlar</h2>
                        <p className="muted" style={{ margin: 0 }}>Oxirgi xabarlar va o‘qilmagan yozishmalar.</p>
                    </div>
                    <button className="btn btn-secondary" type="button" onClick={load} disabled={loading}>
                        {loading ? "Yangilanmoqda..." : "Yangilash"}
                    </button>
                </div>

                {loading && !items.length ? (
                    <div className="empty-state">Suhbatlar yuklanmoqda...</div>
                ) : !items.length ? (
                    <div className="empty-state">
                        <strong>Hali suhbatlar yo‘q.</strong>
                        <span>Biror ish bo‘yicha bajaruvchi yoki ish egasi bilan muloqot boshlang.</span>
                    </div>
                ) : (
                    <div style={{ display: "grid", gap: 10 }}>
                        {items.map((item) => (
                            <button
                                key={item.job_id}
                                type="button"
                                className="card"
                                style={{ margin: 0, textAlign: "left", cursor: "pointer", width: "100%" }}
                                onClick={() => navigate(`/chat/${item.job_id}`)}
                            >
                                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                                    <div style={{ minWidth: 0 }}>
                                        <strong>{item.title || `Ish #${item.job_id}`}</strong>
                                        <div className="muted" style={{ marginTop: 4 }}>
                                            @{item.other_username || "foydalanuvchi"} · {formatTimeAgo(item.sent_at)}
                                        </div>
                                    </div>
                                    {item.unread > 0 && <span className="chip">{item.unread} yangi</span>}
                                </div>
                                <p style={{ margin: "10px 0 0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                    {item.message || "Xabar yo‘q"}
                                </p>
                            </button>
                        ))}
                    </div>
                )}
            </section>
        </AppLayout>
    )
}

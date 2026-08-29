import { useEffect, useState } from "react"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

export default function Leaderboard() {
    const [activeTab, setActiveTab] = useState("creators") // 'creators' yoki 'workers'
    const [data, setData] = useState({ creators: [], workers: [] })
    const [loading, setLoading] = useState(true)
    const token = localStorage.getItem("token") || ""

    const load = async () => {
        setLoading(true)
        const result = await api("/leaderboard", { token })
        if (result.creators || result.workers) {
            setData({
                creators: result.creators || [],
                workers: result.workers || []
            })
        }
        setLoading(false)
    }

    useEffect(() => {
        load()
    }, [])

    const currentList = activeTab === "creators" ? data.creators : data.workers

    const getRankIcon = (index) => {
        if (index === 0) return "🥇"
        if (index === 1) return "🥈"
        if (index === 2) return "🥉"
        return `#${index + 1}`
    }

    return (
        <AppLayout
            title="Leaderboard 🏆"
            subtitle="Eng ko'p ish yaratgan va muvaffaqiyatli yakunlagan foydalanuvchilar (Top 10)"
        >
            {/* TABS (Tugmalar) QISMI */}
            <div className="card" style={{ marginBottom: 18 }}>
                <div className="actions" style={{ display: "flex", gap: "10px", width: "100%" }}>
                    <button
                        className={`btn ${activeTab === "creators" ? "btn-primary" : "btn-secondary"}`}
                        style={{ flex: 1 }}
                        onClick={() => setActiveTab("creators")}
                    >
                        ✍️ Eng ko'p ish yaratganlar
                    </button>
                    <button
                        className={`btn ${activeTab === "workers" ? "btn-primary" : "btn-secondary"}`}
                        style={{ flex: 1 }}
                        onClick={() => setActiveTab("workers")}
                    >
                        🛠️ Eng ko'p ish bajarganlar
                    </button>
                </div>
            </div>

            {/* RO'YXAT QISMI */}
            <div className="card">
                <h3 style={{ marginBottom: 18 }}>
                    {activeTab === "creators" ? "Ish Beruvchilar Reytingi" : "Ustalar Reytingi"}
                </h3>

                <div style={{ display: "grid", gap: "12px" }}>
                    {loading ? (
                        <div className="empty-state">Yuklanmoqda...</div>
                    ) : currentList.length > 0 ? (
                        currentList.map((user, idx) => (
                            <div key={user.id} style={{
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                padding: "16px 20px",
                                background: "rgba(255,255,255,.04)",
                                border: "1px solid rgba(148,163,184,.14)",
                                borderRadius: "16px",
                                transition: "transform 0.2s"
                            }}>
                                <div style={{ display: "flex", alignItems: "center", gap: "18px" }}>
                                    <div style={{
                                        fontSize: idx < 3 ? "28px" : "18px",
                                        width: "40px",
                                        textAlign: "center",
                                        fontWeight: "900",
                                        color: idx < 3 ? "#fff" : "#94a3b8"
                                    }}>
                                        {getRankIcon(idx)}
                                    </div>
                                    <div>
                                        <div style={{ fontWeight: 800, fontSize: "16px" }}>{user.name}</div>
                                        <div className="helper">Foydalanuvchi #{user.id}</div>
                                    </div>
                                </div>
                                <div className="chip" style={{
                                    fontSize: "14px",
                                    padding: "8px 14px",
                                    background: "rgba(59,130,246,.15)",
                                    color: "#60a5fa",
                                    border: "1px solid rgba(59,130,246,.3)"
                                }}>
                                    ⭐ {user.count} ta ish
                                </div>
                            </div>
                        ))
                    ) : (
                        <div className="empty-state">Hozircha yakunlangan ishlar yo'q.</div>
                    )}
                </div>
            </div>
        </AppLayout>
    )
}
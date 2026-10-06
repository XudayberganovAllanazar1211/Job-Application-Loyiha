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
            title="Reyting jadvali 🏆"
            subtitle="Eng ko‘p ish yaratgan va muvaffaqiyatli yakunlagan foydalanuvchilar (10 talik)"
        >
            {/* TABS (Tugmalar) QISMI */}
            <div className="card" style={{ marginBottom: 18 }}>
                <div className="actions" style={{ display: "flex", gap: "10px", width: "100%" }}>
                    <button
                        className={`btn ${activeTab === "creators" ? "btn-primary" : "btn-secondary"}`}
                        style={{ flex: 1 }}
                        onClick={() => setActiveTab("creators")}
                    >
                        ✍️ Eng ko‘p ish yaratganlar
                    </button>
                    <button
                        className={`btn ${activeTab === "workers" ? "btn-primary" : "btn-secondary"}`}
                        style={{ flex: 1 }}
                        onClick={() => setActiveTab("workers")}
                    >
                        🛠️ Eng ko‘p ish bajarganlar
                    </button>
                </div>
            </div>

            {/* RO'YXAT QISMI */}
            <div className="card">
                <h3 style={{ marginBottom: 18 }}>
                    {activeTab === "creators" ? "Ish beruvchilar reytingi" : "Bajaruvchilar reytingi"}
                </h3>

                <div className="leaderboard-list">
                    {loading ? (
                        <div className="empty-state">Yuklanmoqda...</div>
                    ) : currentList.length > 0 ? (
                        currentList.map((user, idx) => (
                            <div key={user.id} className={idx < 3 ? "leaderboard-item top" : "leaderboard-item"}>
                                <div style={{ display: "flex", alignItems: "center", gap: "18px" }}>
                                    <div className="leaderboard-rank">{getRankIcon(idx)}</div>
                                    <div>
                                        <div style={{ fontWeight: 800, fontSize: "16px" }}>{user.name}</div>
                                        <div className="helper">Foydalanuvchi #{user.id}</div>
                                    </div>
                                </div>
                                <div className="leaderboard-count">⭐ {user.count} ta ish</div>
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
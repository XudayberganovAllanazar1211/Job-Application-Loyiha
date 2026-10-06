import { useEffect, useState } from "react"
import { Navigate } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

export default function Admin() {
    const token = localStorage.getItem("token")
    const user = JSON.parse(localStorage.getItem("user") || "null")
    const [data, setData] = useState(null)
    const [notice, setNotice] = useState("")
    const [tab, setTab] = useState("users")

    useEffect(() => {
        if (!token || user?.role !== "admin") return

        const load = async () => {
            const result = await api("/admin/overview", { token })
            if (result?.ok) {
                setData(result)
            } else {
                setNotice(result?.msg || "Admin ma'lumotlarini yuklab bo'lmadi.")
            }
        }

        load()
    }, [token, user?.role])

    if (!token) return <Navigate to="/login" replace />
    if (user?.role !== "admin") return <Navigate to="/" replace />

    const stats = data?.stats || {}
    const tabs = [
        ["users", "Foydalanuvchilar"],
        ["jobs", "Joblar"],
        ["services", "Xizmatlar"],
        ["ratings", "Ratinglar"]
    ]

    return (
        <AppLayout
            title="Admin Dashboard"
            subtitle="FinJob platformasining umumiy holati va ma'lumotlarini boshqaring."
        >
            {notice && <div className="notice warn" style={{ marginBottom: 16 }}>{notice}</div>}

            <div className="admin-stat-grid">
                <div className="card admin-stat"><span>Users</span><strong>{stats.users ?? 0}</strong></div>
                <div className="card admin-stat"><span>Jami joblar</span><strong>{stats.jobs ?? 0}</strong></div>
                <div className="card admin-stat"><span>Active</span><strong>{stats.active_jobs ?? 0}</strong></div>
                <div className="card admin-stat"><span>Finished</span><strong>{stats.finished_jobs ?? 0}</strong></div>
                <div className="card admin-stat"><span>Xizmatlar</span><strong>{stats.services ?? 0}</strong></div>
                <div className="card admin-stat"><span>Ratinglar</span><strong>{stats.ratings ?? 0}</strong></div>
            </div>

            <div className="card admin-panel">
                <div className="admin-tabs">
                    {tabs.map(([key, label]) => (
                        <button
                            key={key}
                            className={tab === key ? "admin-tab active" : "admin-tab"}
                            onClick={() => setTab(key)}
                        >
                            {label}
                        </button>
                    ))}
                </div>

                {!data && !notice && <div className="muted">Yuklanmoqda...</div>}

                {data && tab === "users" && (
                    <div className="admin-table-wrap">
                        <table className="admin-table">
                            <thead><tr><th>ID</th><th>User</th><th>Email</th><th>Role</th><th>Rating</th><th>Qo'shilgan</th></tr></thead>
                            <tbody>
                                {data.users.map((item) => (
                                    <tr key={item.id}>
                                        <td>#{item.id}</td>
                                        <td><strong>{item.username}</strong><small>{item.first_name} {item.last_name}</small></td>
                                        <td>{item.email}</td>
                                        <td><span className={item.role === "admin" ? "admin-role" : "user-role"}>{item.role}</span></td>
                                        <td>{Number(item.average_rating || 0).toFixed(1)}</td>
                                        <td>{item.created_at || "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {data && tab === "jobs" && (
                    <div className="admin-table-wrap">
                        <table className="admin-table">
                            <thead><tr><th>ID</th><th>Job</th><th>Creator</th><th>Worker</th><th>Price</th><th>Status</th><th>Location</th></tr></thead>
                            <tbody>
                                {data.jobs.map((item) => (
                                    <tr key={item.id}>
                                        <td>#{item.id}</td>
                                        <td><strong>{item.title}</strong></td>
                                        <td>{item.creator_username || "—"}</td>
                                        <td>{item.worker_username || "—"}</td>
                                        <td>{Number(item.price || 0).toLocaleString()} {item.currency || "UZS"}</td>
                                        <td><span className="admin-status">{item.status || "—"}</span></td>
                                        <td>{item.location || "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {data && tab === "services" && (
                    <div className="admin-table-wrap">
                        <table className="admin-table">
                            <thead><tr><th>ID</th><th>Xizmat</th><th>Ota kategoriya</th><th>Created by</th></tr></thead>
                            <tbody>
                                {data.services.map((item) => (
                                    <tr key={item.id}>
                                        <td>#{item.id}</td>
                                        <td><strong>{item.name}</strong></td>
                                        <td>{item.parent_name || "Asosiy kategoriya"}</td>
                                        <td>{item.created_by || "System"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {data && tab === "ratings" && (
                    <div className="admin-table-wrap">
                        <table className="admin-table">
                            <thead><tr><th>ID</th><th>Job</th><th>From</th><th>To</th><th>Score</th><th>Comment</th></tr></thead>
                            <tbody>
                                {data.ratings.map((item) => (
                                    <tr key={item.id}>
                                        <td>#{item.id}</td>
                                        <td>#{item.job_id}</td>
                                        <td>{item.from_username || "—"}</td>
                                        <td>{item.to_username || "—"}</td>
                                        <td><strong>{item.score}/5</strong></td>
                                        <td>{item.comment || "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </AppLayout>
    )
}

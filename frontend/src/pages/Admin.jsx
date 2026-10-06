import { useEffect, useState } from "react"
import { Navigate } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

export default function Admin() {
    const token = localStorage.getItem("token")
    const user = JSON.parse(localStorage.getItem("user") || "null")
    const [data, setData] = useState(null)
    const [notice, setNotice] = useState("")
    const [noticeType, setNoticeType] = useState("ok")
    const [tab, setTab] = useState("users")
    const [serviceName, setServiceName] = useState("")
    const [serviceParent, setServiceParent] = useState("")
    const [editingUser, setEditingFoydalanuvchi] = useState(null)
    const [userForm, setUserForm] = useState({ username: "", email: "", first_name: "", last_name: "", birthday: "", bio: "", skills: "", password: "" })

    const load = async () => {
        const result = await api("/admin/overview", { token })
        if (result?.ok) {
            setData(result)
            setNotice("")
        } else {
            setNoticeType("warn")
            setNotice(result?.msg || "Admin ma'lumotlarini yuklab bo'lmadi.")
        }
    }

    useEffect(() => {
        if (!token || user?.role !== "admin") return
        load()
    }, [token, user?.role])

    const action = async (path, options = {}, successMessage = "O'zgarish saqlandi.") => {
        setNotice("")
        setNoticeType("ok")
        const result = await api(path, { token, ...options })

        if (!result?.ok) {
            setNoticeType("warn")
            setNotice(result?.msg || "Amal bajarilmadi.")
            return false
        }

        setNotice(result?.msg || successMessage)
        await load()
        return true
    }

    const changeRol = async (item, role) => {
        if (role === item.role) return
        await action(
            "/admin/user-role",
            { method: "PATCH", body: { user_id: item.id, role } },
            "Foydalanuvchi roli o‘zgartirildi."
        )
    }

    const editFoydalanuvchi = (item) => {
        setEditingFoydalanuvchi(item)
        setUserForm({
            username: item.username || "",
            email: item.email || "",
            first_name: item.first_name || "",
            last_name: item.last_name || "",
            birthday: item.birthday || "",
            bio: item.bio || "",
            skills: item.skills || "",
            password: ""
        })
    }

    const saveUser = async (event) => {
        event.preventDefault()
        if (!editingUser) return

        const ok = await action(
            "/admin/user/"+editingUser.id,
            { method: "PATCH", body: userForm },
            "Foydalanuvchi ma'lumotlari yangilandi."
        )

        if (ok) {
            if (editingUser.id === user.id) {
                const safeFoydalanuvchiForm = { ...userForm }
                delete safeFoydalanuvchiForm.password
                localStorage.setItem("user", JSON.stringify({ ...user, ...safeFoydalanuvchiForm }))
            }
            setEditingFoydalanuvchi(null)
        }
    }

    const deleteUser = async (item) => {
        if (!window.confirm("@"+item.username+" foydalanuvchisini va unga bog'liq ma'lumotlarni o'chirishni tasdiqlaysizmi?")) return
        await action("/admin/user/"+item.id, { method: "DELETE" }, "Foydalanuvchi o'chirildi.")
    }

    const updateJobHolat = async (item, status) => {
        if (status === item.status) return
        await action(
            "/admin/job/"+item.id,
            { method: "PATCH", body: { status } },
            "Ish holati o‘zgartirildi."
        )
    }

    const deleteJob = async (item) => {
        if (!window.confirm("#"+item.id+" — "+item.title+" jobini o'chirishni tasdiqlaysizmi?")) return
        await action("/admin/job/"+item.id, { method: "DELETE" }, "Ish o‘chirildi.")
    }

    const createService = async (event) => {
        event.preventDefault()

        if (!serviceName.trim()) {
            setNoticeType("warn")
            setNotice("Xizmat nomini kiriting.")
            return
        }

        const ok = await action(
            "/admin/service",
            {
                method: "POST",
                body: {
                    name: serviceName.trim(),
                    parent_id: serviceParent || null
                }
            },
            "Xizmat qo'shildi."
        )

        if (ok) {
            setServiceName("")
            setServiceParent("")
        }
    }

    const deleteService = async (item) => {
        if (!window.confirm("\""+item.name+"\" xizmatini o'chirishni tasdiqlaysizmi?")) return
        await action("/admin/service/"+item.id, { method: "DELETE" }, "Xizmat o‘chirildi.")
    }

    const deleteBaho = async (item) => {
        if (!window.confirm("#"+item.id+" ratingni o'chirishni tasdiqlaysizmi?")) return
        await action("/admin/rating/"+item.id, { method: "DELETE" }, "Baho o‘chirildi.")
    }

    if (!token) return <Navigate to="/login" replace />
    if (user?.role !== "admin") return <Navigate to="/" replace />

    const stats = data?.stats || {}
    const tabs = [
        ["users", "Foydalanuvchilar"],
        ["jobs", "Ishlar"],
        ["services", "Xizmatlar"],
        ["ratings", "Baholar"]
    ]

    return (
        <AppLayout title="Administrator paneli" subtitle="FinJob platformasini to‘liq boshqaring.">
            {notice && <div className={`notice ${noticeType === "ok" ? "ok" : "warn"}`} style={{ marginBottom: 16 }}>{notice}</div>}

            <div className="admin-stat-grid">
                <div className="card admin-stat"><span>Foydalanuvchilar</span><strong>{stats.users ?? 0}</strong></div>
                <div className="card admin-stat"><span>Jami ishlar</span><strong>{stats.jobs ?? 0}</strong></div>
                <div className="card admin-stat"><span>Faol</span><strong>{stats.active_jobs ?? 0}</strong></div>
                <div className="card admin-stat"><span>Yakunlangan</span><strong>{stats.finished_jobs ?? 0}</strong></div>
                <div className="card admin-stat"><span>Xizmatlar</span><strong>{stats.services ?? 0}</strong></div>
                <div className="card admin-stat"><span>Baholar</span><strong>{stats.ratings ?? 0}</strong></div>
            </div>

            <div className="card admin-panel">
                <div className="admin-toolbar-note">Bu yerda platformadagi asosiy maʼlumotlarni boshqarishingiz mumkin.</div>
                <div className="admin-tabs">
                    {tabs.map(([key, label]) => (
                        <button key={key} className={tab === key ? "admin-tab active" : "admin-tab"} onClick={() => setTab(key)}>
                            {label}
                        </button>
                    ))}
                </div>

                {!data && !notice && <div className="muted" style={{ padding: 20 }}>Yuklanmoqda...</div>}

                {data && tab === "users" && (
                    <div className="admin-table-wrap">
                        <table className="admin-table">
                            <thead><tr><th>ID</th><th>Foydalanuvchi</th><th>Elektron pochta</th><th>Rol</th><th>Baho</th><th>Qo‘shilgan sana</th><th>Amallar</th></tr></thead>
                            <tbody>
                                {data.users.map((item) => (
                                    <tr key={item.id}>
                                        <td>#{item.id}</td>
                                        <td><strong>{item.username}</strong><small>{item.first_name} {item.last_name}</small></td>
                                        <td>{item.email}</td>
                                        <td>
                                            <select className="admin-action-select" value={item.role} disabled={item.id === user.id} onChange={(event) => changeRol(item, event.target.value)}>
                                                <option value="user">foydalanuvchi</option>
                                                <option value="admin">administrator</option>
                                            </select>
                                        </td>
                                        <td>{Number(item.average_rating || 0).toFixed(1)}</td>
                                        <td>{item.created_at || "—"}</td>
                                        <td>
                                            <button className="btn btn-secondary admin-small-btn" onClick={() => editFoydalanuvchi(item)}>
                                                Tahrirlash
                                            </button>
                                            <button className="btn btn-danger admin-small-btn" disabled={item.id === user.id || item.role === "admin"} onClick={() => deleteUser(item)}>
                                                O'chirish
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {data && tab === "jobs" && (
                    <div className="admin-table-wrap">
                        <table className="admin-table">
                            <thead><tr><th>ID</th><th>Job</th><th>Ish beruvchi</th><th>Bajaruvchi</th><th>Narx</th><th>Holat</th><th>Manzil</th><th>Amallar</th></tr></thead>
                            <tbody>
                                {data.jobs.map((item) => (
                                    <tr key={item.id}>
                                        <td>#{item.id}</td>
                                        <td><strong>{item.title}</strong></td>
                                        <td>{item.creator_username || "—"}</td>
                                        <td>{item.worker_username || "—"}</td>
                                        <td>{Number(item.price || 0).toLocaleString()} {item.currency || "UZS"}</td>
                                        <td>
                                            <select className="admin-action-select" value={item.status || "active"} onChange={(event) => updateJobHolat(item, event.target.value)}>
                                                <option value="active">faol</option>
                                                <option value="accepted">qabul qilingan</option>
                                                <option value="pending_finish">tasdiqlash kutilmoqda</option>
                                                <option value="finished">yakunlangan</option>
                                            </select>
                                        </td>
                                        <td>{item.location || "—"}</td>
                                        <td><button className="btn btn-danger admin-small-btn" onClick={() => deleteJob(item)}>O'chirish</button></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {data && tab === "services" && (
                    <div>
                        <form className="admin-create-service" onSubmit={createService}>
                            <input className="input" placeholder="Yangi xizmat yoki kategoriya nomi" value={serviceName} onChange={(event) => setServiceName(event.target.value)} />
                            <select className="select admin-parent-select" value={serviceParent} onChange={(event) => setServiceParent(event.target.value)}>
                                <option value="">Asosiy kategoriya</option>
                                {(data.services || []).map((item) => (
                                    <option key={item.id} value={item.id}>
                                        {item.parent_name ? item.parent_name + " → " + item.name : item.name}
                                    </option>
                                ))}
                            </select>
                            <button className="btn btn-primary" type="submit">+ Xizmat qo'shish</button>
                        </form>

                        <div className="admin-table-wrap">
                            <table className="admin-table">
                                <thead><tr><th>ID</th><th>Xizmat</th><th>Ota kategoriya</th><th>Yaratgan</th><th>Amal</th></tr></thead>
                                <tbody>
                                    {data.services.map((item) => (
                                        <tr key={item.id}>
                                            <td>#{item.id}</td>
                                            <td><strong>{item.name}</strong></td>
                                            <td>{item.parent_name || "Asosiy kategoriya"}</td>
                                            <td>{item.created_by || "Tizim"}</td>
                                            <td><button className="btn btn-danger admin-small-btn" onClick={() => deleteService(item)}>O'chirish</button></td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {data && tab === "reports" && (
                    <div className="admin-table-wrap">
                        <table className="admin-table">
                            <thead><tr><th>ID</th><th>Yuboruvchi</th><th>Foydalanuvchi</th><th>Sabab</th><th>Tafsilot</th><th>Sana</th><th>Holat</th></tr></thead>
                            <tbody>
                                {(data.reports || []).map((item) => (
                                    <tr key={item.id}>
                                        <td>#{item.id}</td>
                                        <td>@{item.reporter_username || "—"}</td>
                                        <td>@{item.reported_username || "—"}</td>
                                        <td><strong>{item.reason}</strong></td>
                                        <td>{item.details || "—"}</td>
                                        <td>{item.created_at || "—"}</td>
                                        <td>
                                            <select className="admin-action-select" value={item.status} onChange={async (event) => {
                                                const result = await api("/admin/report/"+item.id, { method:"PATCH", body:{status:event.target.value}, token })
                                                if (result?.ok) load()
                                                else { setNoticeType("warn"); setNotice(result?.msg || "Holatni o‘zgartirib bo‘lmadi.") }
                                            }}>
                                                <option value="open">ochiq</option>
                                                <option value="reviewing">ko‘rib chiqilmoqda</option>
                                                <option value="resolved">hal qilindi</option>
                                                <option value="rejected">rad etildi</option>
                                            </select>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                        {!(data.reports || []).length && <div className="empty-state">Hozircha shikoyatlar yo‘q.</div>}
                    </div>
                )}

                {data && tab === "ratings" && (
                    <div className="admin-table-wrap">
                        <table className="admin-table">
                            <thead><tr><th>ID</th><th>Job</th><th>Kimdan</th><th>Kimga</th><th>Baho</th><th>Izoh</th><th>Amal</th></tr></thead>
                            <tbody>
                                {data.ratings.map((item) => (
                                    <tr key={item.id}>
                                        <td>#{item.id}</td>
                                        <td>#{item.job_id}</td>
                                        <td>{item.from_username || "—"}</td>
                                        <td>{item.to_username || "—"}</td>
                                        <td><strong>{item.score}/10</strong></td>
                                        <td>{item.comment || "—"}</td>
                                        <td><button className="btn btn-danger admin-small-btn" onClick={() => deleteBaho(item)}>O'chirish</button></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        {editingUser && (
                <div className="admin-modal-backdrop" onClick={() => setEditingFoydalanuvchi(null)}>
                    <div className="card admin-modal" onClick={(event) => event.stopPropagation()}>
                        <div className="admin-modal-head">
                            <div><h3>Foydalanuvchini tahrirlash</h3><p>@{editingUser.username}</p></div>
                            <button className="admin-modal-close" onClick={() => setEditingFoydalanuvchi(null)}>×</button>
                        </div>
                        <form onSubmit={saveUser} className="admin-user-form">
                            <div className="admin-form-grid">
                                <label>Foydalanuvchiname<input className="input" value={userForm.username} onChange={e => setUserForm({...userForm, username:e.target.value})} /></label>
                                <label>Elektron pochta<input className="input" type="email" value={userForm.email} onChange={e => setUserForm({...userForm, email:e.target.value})} /></label>
                                <label>Ism<input className="input" value={userForm.first_name} onChange={e => setUserForm({...userForm, first_name:e.target.value})} /></label>
                                <label>Familiya<input className="input" value={userForm.last_name} onChange={e => setUserForm({...userForm, last_name:e.target.value})} /></label>
                                <label>Tug'ilgan sana<input className="input" value={userForm.birthday} onChange={e => setUserForm({...userForm, birthday:e.target.value})} /></label>
                                <label>Yangi parol<input className="input" type="password" placeholder="Bo‘sh qoldirilsa, o‘zgarmaydi" value={userForm.password} onChange={e => setUserForm({...userForm, password:e.target.value})} /></label>
                            </div>
                            <label>O‘zingiz haqingizda<textarea className="input admin-textarea" value={userForm.bio} onChange={e => setUserForm({...userForm, bio:e.target.value})} /></label>
                            <label>Ko'nikmalar<textarea className="input admin-textarea" value={userForm.skills} onChange={e => setUserForm({...userForm, skills:e.target.value})} /></label>
                            <div className="admin-modal-actions">
                                <button type="button" className="btn btn-secondary" onClick={() => setEditingFoydalanuvchi(null)}>Bekor qilish</button>
                                <button type="submit" className="btn btn-primary">Saqlash</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

        </AppLayout>
    )
}

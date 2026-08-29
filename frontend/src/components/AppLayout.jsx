import { NavLink, useNavigate } from "react-router-dom"

export default function AppLayout({ title, subtitle, children }) {
    const navigate = useNavigate()
    const user = JSON.parse(localStorage.getItem("user") || "null")

    const logout = () => {
        localStorage.removeItem("token")
        localStorage.removeItem("user")
        navigate("/login")
    }

    const isAdmin = user?.role === "admin"

    return (
        <div className="shell">
            <aside className="sidebar">
                <div className="sidebar-top">
                    <div className="brand">
                        <div className="brand-badge">JP</div>
                        <div>
                            <div className="brand-name">Job Platform</div>
                            <div className="helper">Service marketplace</div>
                        </div>
                    </div>

                    <div className="sidebar-profile">
                        <div className="helper">Signed in as</div>
                        <div className="sidebar-profile-name">
                            {user?.first_name || "Guest"} {user?.last_name || ""}
                        </div>
                        <div
                            style={{
                                marginTop: 10,
                                background: isAdmin ? "rgba(239, 68, 68, 0.2)" : "rgba(255, 255, 255, 0.05)",
                                color: isAdmin ? "#f87171" : "#9ca3af",
                                border: isAdmin ? "1px solid rgba(239, 68, 68, 0.4)" : "1px solid rgba(255, 255, 255, 0.1)"
                            }}
                            className="chip"
                        >
                            {isAdmin ? "🛡️ Administrator" : "Universal User"}
                        </div>
                    </div>
                </div>

                <nav className="sidebar-menu">
                    <NavLink to="/" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                        <span>Dashboard</span><span>⌂</span>
                    </NavLink>
                    <NavLink to="/create" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                        <span>Create Job</span><span>＋</span>
                    </NavLink>
                    <NavLink to="/jobs" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                        <span>Jobs</span><span>▤</span>
                    </NavLink>
                    <NavLink to="/leaderboard" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                        <span>Leaderboard</span><span>🏆</span>
                    </NavLink>
                </nav>

                <div className="sidebar-footer">
                    <button className="btn btn-danger" onClick={logout} style={{ width: "100%" }}>
                        Logout
                    </button>
                </div>
            </aside>

            <main className="main">
                <div className="topbar">
                    <div className="page-head">
                        <h1 className="page-title">{title}</h1>
                        <p className="page-subtitle">{subtitle}</p>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
                        <div className="chip-row">
                            <span className="chip">API localhost:5000</span>
                        </div>
                        {/* --- PROFIL TUGMASI --- */}
                        <button
                            onClick={() => navigate("/profile")}
                            style={{
                                background: "rgba(59,130,246,.15)",
                                border: "1px solid rgba(59,130,246,.3)",
                                color: "#60a5fa",
                                width: "44px",
                                height: "44px",
                                borderRadius: "50%",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                cursor: "pointer",
                                fontSize: "20px",
                                transition: "all 0.2s"
                            }}
                            title="Profilni tahrirlash"
                            onMouseOver={(e) => e.currentTarget.style.background = "rgba(59,130,246,.25)"}
                            onMouseOut={(e) => e.currentTarget.style.background = "rgba(59,130,246,.15)"}
                        >
                            👤
                        </button>
                    </div>
                </div>

                {children}
            </main>
        </div>
    )
}

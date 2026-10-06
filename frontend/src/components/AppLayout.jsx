import { NavLink, useNavigate } from "react-router-dom"

const navItems = [
    ["/", "Boshqaruv paneli", "⌂"],
    ["/create", "Ish yaratish", "+"],
    ["/jobs", "Ishlar", "▤"],
    ["/leaderboard", "Reyting jadvali", "★"]
]

export default function AppLayout({ title, subtitle, children }) {
    const navigate = useNavigate()
    const user = JSON.parse(localStorage.getItem("user") || "null")
    const isAdmin = user?.role === "admin"
    const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.username || "Mehmon"
    const initials = fullName.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase()
    const avatarSrc = user?.avatar_url
        ? (import.meta.env.VITE_API_URL || "http://localhost:5000") + user.avatar_url
        : ""

    const logout = () => {
        localStorage.removeItem("token")
        localStorage.removeItem("user")
        navigate("/login")
    }

    return (
        <div className="shell">
            <aside className="sidebar">
                <div className="sidebar-top">
                    <button className="brand" onClick={() => navigate("/")} style={{background:"none",border:0,padding:0,cursor:"pointer",textAlign:"left"}}>
                        <div className="brand-badge">FJ</div>
                        <div>
                            <div className="brand-name">FinJob</div>
                            <div className="helper">Ish toping. Ishni yakunlang.</div>
                        </div>
                    </button>
                    <div className="sidebar-profile">
                        <div style={{display:"flex",alignItems:"center",gap:10}}>
                            <div className="sidebar-user-avatar">{avatarSrc ? <img src={avatarSrc} alt="" /> : initials}</div>
                            <div style={{minWidth:0}}>
                                <div className="sidebar-profile-name" style={{whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{fullName}</div>
                                <div className="helper">{user?.email || (isAdmin ? "Administrator" : "FinJob foydalanuvchisi")}</div>
                            </div>
                        </div>
                    </div>
                </div>
                <nav className="sidebar-menu">
                    {navItems.map(([to, label, icon]) => (
                        <NavLink key={to} to={to} end={to === "/"} className={({isActive}) => `nav-link ${isActive ? "active" : ""}`}>
                            <span className="nav-link-icon">{icon}</span><span className="nav-link-label">{label}</span>
                        </NavLink>
                    ))}
                </nav>
                {isAdmin && (
                    <NavLink to="/admin" className={({isActive}) => `nav-link admin-nav-link ${isActive ? "active" : ""}`}>
                        <span className="nav-link-icon">⚙</span><span className="nav-link-label">Administrator</span>
                    </NavLink>
                )}
                <div className="legal-footer">
                    <div className="legal-footer-title">FinJob huquqiy bo‘limi</div>
                    <div className="legal-footer-links">
                        <NavLink to="/privacy">Maxfiylik</NavLink>
                        <NavLink to="/terms">Shartlar</NavLink>
                        <NavLink to="/community-rules">Qoidalar</NavLink>
                    </div>
                </div>
                <div className="sidebar-footer">
                    <button className="btn btn-secondary" onClick={() => navigate("/profile")} style={{width:"100%",marginBottom:8}}>Profil</button>
                    <button className="btn btn-danger" onClick={logout} style={{width:"100%"}}>Chiqish</button>
                </div>
            </aside>
            <main className="main">
                <div className="topbar">
                    <div className="page-head">
                        <div className="chip" style={{width:"fit-content",color:"#2563eb",background:"#eff6ff",borderColor:"#dbeafe"}}>FINJOB / ISH MAYDONI</div>
                        <h1 className="page-title">{title}</h1>
                        <p className="page-subtitle">{subtitle}</p>
                    </div>
                    <button className="btn btn-secondary topbar-profile-btn" onClick={() => navigate("/profile")} aria-label="Profilni ochish">
                        <span className="topbar-avatar">{avatarSrc ? <img src={avatarSrc} alt="" /> : initials}</span>
                    </button>
                </div>
                {children}
            </main>
        </div>
    )
}

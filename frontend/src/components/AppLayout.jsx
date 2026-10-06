import { NavLink, useNavigate } from "react-router-dom"

const navItems = [
    ["/", "Dashboard", "⌂"],
    ["/create", "Create Job", "+"],
    ["/jobs", "Jobs", "▤"],
    ["/leaderboard", "Leaderboard", "★"]
]

export default function AppLayout({ title, subtitle, children }) {
    const navigate = useNavigate()
    const user = JSON.parse(localStorage.getItem("user") || "null")
    const isAdmin = user?.role === "admin"
    const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.username || "Guest"
    const initials = fullName.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase()

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
                            <div className="helper">Find work. Get it done.</div>
                        </div>
                    </button>
                    <div className="sidebar-profile">
                        <div style={{display:"flex",alignItems:"center",gap:10}}>
                            <div className="brand-badge" style={{width:38,height:38,borderRadius:12,fontSize:12}}>{initials}</div>
                            <div style={{minWidth:0}}>
                                <div className="sidebar-profile-name" style={{whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{fullName}</div>
                                <div className="helper">{isAdmin ? "Administrator" : "FinJob member"}</div>
                            </div>
                        </div>
                    </div>
                </div>
                <nav className="sidebar-menu">
                    {navItems.map(([to, label, icon]) => (
                        <NavLink key={to} to={to} end={to === "/"} className={({isActive}) => `nav-link ${isActive ? "active" : ""}`}>
                            <span>{label}</span><span style={{fontWeight:800}}>{icon}</span>
                        </NavLink>
                    ))}
                </nav>
                <div className="legal-footer">
                    <div className="legal-footer-title">FinJob Legal</div>
                    <div className="legal-footer-links">
                        <NavLink to="/privacy">Privacy</NavLink>
                        <NavLink to="/terms">Terms</NavLink>
                        <NavLink to="/community-rules">Rules</NavLink>
                    </div>
                </div>
                <div className="sidebar-footer">
                    <button className="btn btn-secondary" onClick={() => navigate("/profile")} style={{width:"100%",marginBottom:8}}>Profile</button>
                    <button className="btn btn-danger" onClick={logout} style={{width:"100%"}}>Log out</button>
                </div>
            </aside>
            <main className="main">
                <div className="topbar">
                    <div className="page-head">
                        <div className="chip" style={{width:"fit-content",color:"#2563eb",background:"#eff6ff",borderColor:"#dbeafe"}}>FINJOB / WORKSPACE</div>
                        <h1 className="page-title">{title}</h1>
                        <p className="page-subtitle">{subtitle}</p>
                    </div>
                    <button className="btn btn-secondary" onClick={() => navigate("/profile")} style={{minWidth:44}}>
                        {initials}
                    </button>
                </div>
                {children}
            </main>
        </div>
    )
}

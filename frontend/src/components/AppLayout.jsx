import { useEffect, useRef, useState } from "react"
import { NavLink, useLocation, useNavigate } from "react-router-dom"
import { api } from "../api"

const navItems = [
    ["/", "Boshqaruv paneli", "⌂"],
    ["/create", "Ish yaratish", "+"],
    ["/jobs", "Ishlar", "▤"],
    ["/payments", "To‘lovlar", "₿"],
    ["/leaderboard", "Reyting jadvali", "★"]
]

export default function AppLayout({ title, subtitle, children }) {
    const navigate = useNavigate()
    const location = useLocation()
    const [theme, setTheme] = useState(() => localStorage.getItem("finjob-theme") || "light")
    const [notifications, setNotifications] = useState([])
    const [unreadNotifications, setUnreadNotifications] = useState(0)
    const [unreadMessages, setUnreadMessages] = useState(0)
    const [showNotifications, setShowNotifications] = useState(false)
    const [showMobileMenu, setShowMobileMenu] = useState(false)
    const notificationRef = useRef(null)
    const token = localStorage.getItem("token") || ""
    const [user, setUser] = useState(() => JSON.parse(localStorage.getItem("user") || "null"))
    const isAdmin = user?.role === "admin"
    const mobileNavItems = [navItems[0], navItems[2], navItems[1], navItems[3]]
    const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.username || "Mehmon"
    const initials = fullName.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase()
    const avatarSrc = user?.avatar_url
        ? (user.avatar_url.startsWith("http://") || user.avatar_url.startsWith("https://")
            ? user.avatar_url
            : (import.meta.env.VITE_API_URL || "http://localhost:5000") + user.avatar_url)
        : ""

    useEffect(() => {
        document.documentElement.dataset.theme = theme
        localStorage.setItem("finjob-theme", theme)
    }, [theme])

    useEffect(() => {
        let alive = true
        const loadCurrentProfile = async () => {
            if (!token) return
            const profile = await api("/profile", { token })
            if (alive && profile?.id) {
                setUser(profile)
                localStorage.setItem("user", JSON.stringify(profile))
                localStorage.setItem("foydalanuvchi", JSON.stringify(profile))
            }
        }
        loadCurrentProfile()
        return () => {
            alive = false
        }
    }, [token])

    useEffect(() => {
        let alive = true
        const loadNotifications = async () => {
            const result = await api("/notifications", { token })
            if (alive && result?.items) {
                setNotifications(result.items)
                setUnreadNotifications(Number(result.unread || 0))
            }
        }
        if (token) {
            loadNotifications()
            const timer = setInterval(loadNotifications, 30000)
            return () => { alive = false; clearInterval(timer) }
        }
        return () => { alive = false }
    }, [token])

    const formatNotificationTime = (dateString) => {
        if (!dateString) return "Vaqt noma'lum"
        const value = new Date(String(dateString).replace(" ", "T"))
        if (Number.isNaN(value.getTime())) return "Vaqt noma'lum"
        const seconds = Math.max(0, Math.floor((Date.now() - value.getTime()) / 1000))
        if (seconds < 60) return "Hozirgina"
        const minutes = Math.floor(seconds / 60)
        if (minutes < 60) return `${minutes} daqiqa oldin`
        const hours = Math.floor(minutes / 60)
        if (hours < 24) return `${hours} soat oldin`
        const days = Math.floor(hours / 24)
        if (days < 7) return `${days} kun oldin`
        return value.toLocaleDateString("uz-UZ", { day: "2-digit", month: "short" })
    }

    useEffect(() => {
        const sendPresence = () => api("/presence", { method: "POST", token })
        if (!token) return undefined
        sendPresence()
        const timer = setInterval(sendPresence, 30000)
        return () => clearInterval(timer)
    }, [token])

    useEffect(() => {
        let alive = true
        const loadUnreadMessages = async () => {
            const result = await api("/messages/unread-count", { token })
            if (alive && result?.ok) setUnreadMessages(Number(result.unread || 0))
        }
        if (token) {
            loadUnreadMessages()
            const timer = setInterval(loadUnreadMessages, 15000)
            return () => { alive = false; clearInterval(timer) }
        }
        return () => { alive = false }
    }, [token])

    useEffect(() => {
        setShowMobileMenu(false)
    }, [location.pathname])

    useEffect(() => {
        if (!showNotifications) return
        const closeOnOutside = (event) => {
            if (notificationRef.current && !notificationRef.current.contains(event.target)) {
                setShowNotifications(false)
            }
        }
        const closeOnEscape = (event) => {
            if (event.key === "Escape") setShowNotifications(false)
        }
        document.addEventListener("mousedown", closeOnOutside)
        document.addEventListener("keydown", closeOnEscape)
        return () => {
            document.removeEventListener("mousedown", closeOnOutside)
            document.removeEventListener("keydown", closeOnEscape)
        }
    }, [showNotifications])

    const openNotifications = async () => {
        setShowNotifications((value) => !value)
        if (unreadNotifications > 0) {
            setUnreadNotifications(0)
            await api("/notifications/read", { method: "POST", token })
            setNotifications((items) => items.map((item) => ({ ...item, is_read: 1 })))
        }
    }

    const logout = async () => {
        try {
            if (token) await api("/logout", { method: "POST", token })
        } finally {
            localStorage.removeItem("token")
            localStorage.removeItem("user")
            navigate("/login")
        }
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
                <NavLink to="/conversations" className={({isActive}) => `nav-link ${isActive ? "active" : ""}`}>
                    <span className="nav-link-icon">✉</span>
                    <span className="nav-link-label">Suhbatlar</span>
                    {unreadMessages > 0 && <span className="notification-sidebar-badge">{unreadMessages > 99 ? "99+" : unreadMessages}</span>}
                </NavLink>
                <NavLink to="/appeals" className={({isActive}) => `nav-link ${isActive ? "active" : ""}`}>
                    <span className="nav-link-icon">⚑</span><span className="nav-link-label">Appeals</span>
                </NavLink>
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
            <nav className="mobile-nav" aria-label="Mobil navigatsiya">
                {mobileNavItems.map(([to, label, icon]) => (
                    <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `mobile-nav-item ${isActive ? "active" : ""}`}>
                        <span className="mobile-nav-icon">{icon}</span>
                        <span className="mobile-nav-label">{label}</span>
                    </NavLink>
                ))}
                <button
                    type="button"
                    className={`mobile-nav-item mobile-nav-menu-button ${showMobileMenu ? "active" : ""}`}
                    aria-expanded={showMobileMenu}
                    aria-controls="finjob-mobile-menu"
                    onClick={() => setShowMobileMenu((value) => !value)}
                >
                    <span className="mobile-nav-icon">☰</span>
                    <span className="mobile-nav-label">Menyu</span>
                </button>
            </nav>
            {showMobileMenu && (
                <div className="mobile-menu-backdrop" onClick={() => setShowMobileMenu(false)}>
                    <div id="finjob-mobile-menu" className="mobile-menu-sheet" role="dialog" aria-modal="true" aria-label="Qo‘shimcha menyu" onClick={(event) => event.stopPropagation()}>
                        <div className="mobile-menu-head">
                            <div>
                                <span className="profile-eyebrow">FINJOB</span>
                                <h2>Qo‘shimcha bo‘limlar</h2>
                            </div>
                            <button type="button" className="mobile-menu-close" onClick={() => setShowMobileMenu(false)} aria-label="Menyuni yopish">×</button>
                        </div>
                        <div className="mobile-menu-grid">
                            <NavLink to="/conversations" className="mobile-menu-link">✉ <span>Suhbatlar{unreadMessages > 0 ? ` (${unreadMessages})` : ""}</span></NavLink>
                            <NavLink to="/leaderboard" className="mobile-menu-link">★ <span>Reyting jadvali</span></NavLink>
                            <NavLink to="/profile" className="mobile-menu-link">◎ <span>Profil</span></NavLink>
                            <NavLink to="/appeals" className="mobile-menu-link">⚑ <span>Appeals</span></NavLink>
                            {isAdmin && <NavLink to="/admin" className="mobile-menu-link">⚙ <span>Administrator</span></NavLink>}
                            <NavLink to="/privacy" className="mobile-menu-link">⌁ <span>Maxfiylik</span></NavLink>
                            <NavLink to="/terms" className="mobile-menu-link">§ <span>Shartlar</span></NavLink>
                            <NavLink to="/community-rules" className="mobile-menu-link">✓ <span>Qoidalar</span></NavLink>
                        </div>
                        <button type="button" className="btn btn-danger mobile-menu-logout" onClick={logout}>Chiqish</button>
                    </div>
                </div>
            )}
            <main className="main">
                <div className="app-topbar">
                    <div className="page-head">
                        <div className="chip" style={{width:"fit-content",color:"#2563eb",background:"#eff6ff",borderColor:"#dbeafe"}}>FINJOB / ISH MAYDONI</div>
                        <h1 className="page-title">{title}</h1>
                        <p className="page-subtitle">{subtitle}</p>
                    </div>
                    <div className="topbar-actions">
                        <div className="notification-wrap" ref={notificationRef}>
                            <button className="notification-button" type="button" onClick={openNotifications} aria-label="Bildirishnomalar">
                                <span className="notification-icon" aria-hidden="true">🔔</span>
                                {unreadNotifications > 0 && <b>{unreadNotifications > 99 ? "99+" : unreadNotifications}</b>}
                            </button>
                            {showNotifications && (
                                <div className="notification-panel">
                                    <div className="notification-head"><div><strong>Bildirishnomalar</strong><span>{unreadNotifications > 0 ? `${unreadNotifications} ta yangi` : "Hammasi ko‘rilgan"}</span></div><button aria-label="Yopish" onClick={() => setShowNotifications(false)}>×</button></div>
                                    <div className="notification-list">
                                        {notifications.length ? notifications.slice(0, 8).map((item) => (
                                            <button key={item.id} className={item.is_read ? "notification-item" : "notification-item unread"} onClick={() => { setShowNotifications(false); if (item.link) navigate(item.link) }}>
                                                <strong>{item.title}</strong><span>{item.message}</span><small>{formatNotificationTime(item.created_at)}</small>
                                            </button>
                                        )) : <div className="notification-empty">Hozircha yangi bildirishnoma yo‘q.</div>}
                                    </div>
                                </div>
                            )}
                        </div>
                        <button className="theme-toggle" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label={theme === "dark" ? "Yorug‘ rejimga o‘tish" : "Qorong‘i rejimga o‘tish"}>
                            <span>{theme === "dark" ? "☀" : "☾"}</span>
                            <span>{theme === "dark" ? "Yorug‘" : "Qorong‘i"}</span>
                        </button>
                        <button className="btn btn-secondary topbar-profile-btn" onClick={() => navigate("/profile")} aria-label="Profilni ochish">
                        <span className="topbar-avatar">{avatarSrc ? <img src={avatarSrc} alt="" /> : initials}</span>
                        </button>
                    </div>
                </div>
                {children}
            </main>
        </div>
    )
}

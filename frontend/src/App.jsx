import { Navigate, Route, Routes } from "react-router-dom"
import Login from "./pages/Login"
import Register from "./pages/Register"
import Dashboard from "./pages/Dashboard"
import CreateJob from "./pages/CreateJob"
import Jobs from "./pages/Jobs"
import Chat from "./pages/Chat"
import Conversations from "./pages/Conversations"
import Rating from "./pages/Rating"
import Leaderboard from "./pages/Leaderboard"
import Profile from "./pages/Profile"
import PublicProfile from "./pages/PublicProfile"
import PrivacyPolicy from "./pages/PrivacyPolicy"
import Terms from "./pages/Terms"
import CommunityRules from "./pages/CommunityRules"
import Admin from "./pages/Admin"
import Appeals from "./pages/Appeals"
import Payments from "./pages/Payments"

function AdminOnly({ children }) {
    const user = JSON.parse(localStorage.getItem("user") || "null")
    return user?.role === "admin" ? children : <Navigate to="/" replace />
}

function Protected({ children }) {
    const token = localStorage.getItem("token")
    return token ? children : <Navigate to="/login" replace />
}

function PublicOnly({ children }) {
    const token = localStorage.getItem("token")
    return token ? <Navigate to="/" replace /> : children
}

export default function App() {
    return (
        <Routes>
            <Route path="/privacy" element={<PrivacyPolicy />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/community-rules" element={<CommunityRules />} />
            <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
            <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />
            <Route path="/" element={<Protected><Dashboard /></Protected>} />
            <Route path="/create" element={<Protected><CreateJob /></Protected>} />
            <Route path="/jobs" element={<Protected><Jobs /></Protected>} />
            <Route path="/chat/:jobId" element={<Protected><Chat /></Protected>} />
            <Route path="/conversations" element={<Protected><Conversations /></Protected>} />
            <Route path="/rating/:jobId" element={<Protected><Rating /></Protected>} />
            <Route path="/payments" element={<Protected><Payments /></Protected>} />
            <Route path="/payments/job/:jobId" element={<Protected><Payments /></Protected>} />

            <Route path="/leaderboard" element={<Protected><Leaderboard /></Protected>} />
            <Route path="/profile" element={<Protected><Profile /></Protected>} />
            <Route path="/appeals" element={<Protected><Appeals /></Protected>} />
            <Route path="/profile/:username" element={<Protected><PublicProfile /></Protected>} />
            <Route path="/profiles/:username" element={<Protected><PublicProfile /></Protected>} />
            <Route path="/admin" element={<Protected><AdminOnly><Admin /></AdminOnly></Protected>} />

            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    )
}
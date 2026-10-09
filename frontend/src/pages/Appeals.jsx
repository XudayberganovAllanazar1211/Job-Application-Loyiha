import { useEffect, useState } from "react"
import { Navigate } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"
import { formatTimeAgo } from "../utils/time"

const labels = {
    full: "To‘liq blok",
    chat: "Chat blok",
    job_creation: "Ish yaratish blok",
    job_accept: "Ish qabul qilish blok",
    proposal: "Taklif yuborish blok",
    rating: "Baholash blok",
    withdrawal: "Mablag‘ yechish blok"
}

const appealStatus = {
    open: "Ochiq",
    reviewing: "Ko‘rib chiqilmoqda",
    approved: "Tasdiqlandi",
    rejected: "Rad etildi"
}

const formatDate = formatTimeAgo

export default function Appeals() {
    const token = localStorage.getItem("token") || ""
    const [data, setData] = useState(null)
    const [selectedBlock, setSelectedBlock] = useState(null)
    const [text, setText] = useState("")
    const [notice, setNotice] = useState("")
    const [noticeType, setNoticeType] = useState("ok")
    const [loading, setLoading] = useState(false)

    const load = async () => {
        const result = await api("/appeals", { token })
        if (result?.ok) setData(result)
        else { setNoticeType("warn"); setNotice(result?.msg || "Arizalar ma’lumotlarini yuklab bo‘lmadi.") }
    }

    useEffect(() => {
        if (token) load()
    }, [token])

    const submit = async (event) => {
        event.preventDefault()
        if (!selectedBlock) return
        setLoading(true)
        setNotice("")
        const result = await api("/appeals", {
            method: "POST",
            token,
            body: { block_id: selectedBlock.id, appeal_text: text }
        })
        if (result?.ok) {
            setText("")
            setSelectedBlock(null)
            setNoticeType("ok")
            setNotice("Arizangiz yuborildi. Administratorlar uni ko‘rib chiqadi.")
            await load()
        } else {
            setNoticeType("warn")
            setNotice(result?.msg || "Ariza yuborilmadi.")
        }
        setLoading(false)
    }

    if (!token) return <Navigate to="/login" replace />

    return (
        <AppLayout title="Blok bo‘yicha arizalar" subtitle="Hisobingizdagi cheklovlar sababini ko‘ring va norozi bo‘lsangiz qayta ko‘rib chiqish uchun ariza yuboring.">
            {notice && <div className={"notice " + noticeType} style={{ marginBottom: 16 }} role="status">{notice}</div>}

            <div className="appeals-layout">
                <div className="card appeals-hero">
                    <span className="appeals-eyebrow">HISOB XAVFSIZLIGI</span>
                    <h2>Cheklovlar va qayta ko‘rib chiqish</h2>
                    <p>Har bir cheklov alohida ko‘rsatiladi. Administrator qo‘ygan sabab, turi va tugash vaqtini ko‘rishingiz mumkin. Norozi bo‘lsangiz, aynan shu cheklov bo‘yicha qayta ko‘rib chiqish arizasini yuboring.</p>
                </div>

                <div className="card appeals-section">
                    <div className="appeals-section-head">
                        <div><span>FAOL CHEKLOVLAR</span><h2>Faol cheklovlar</h2></div>
                        <button className="btn btn-secondary" onClick={load}>Yangilash</button>
                    </div>
                    {data?.active_blocks?.length ? (
                        <div className="appeal-block-grid">
                            {data.active_blocks.map((block) => (
                                <div className="appeal-block-card" key={block.id}>
                                    <div className="appeal-block-top">
                                        <span className="admin-badge danger">{labels[block.block_type] || block.block_type}</span>
                                        <strong>#{block.id}</strong>
                                    </div>
                                    <p><b>Nega:</b> {block.reason}</p>
                                    <p><b>Berilgan:</b> {formatDate(block.created_at)}</p>
                                    <p><b>Tugashi:</b> {block.expires_at ? formatDate(block.expires_at) : "Muddatsiz"}</p>
                                    <button className="btn btn-primary" onClick={() => setSelectedBlock(block)}>Shu cheklov bo‘yicha ariza</button>
                                </div>
                            ))}
                        </div>
                    ) : <div className="empty-state">Hozircha faol cheklov yo‘q.</div>}
                </div>

                <div className="card appeals-section">
                    <div className="appeals-section-head">
                        <div><span>MENING ARIZALARIM</span><h2>Yuborgan arizalarim</h2></div>
                    </div>
                    {data?.appeals?.length ? (
                        <div className="appeal-history">
                            {data.appeals.map((item) => (
                                <div className="appeal-history-item" key={item.id}>
                                    <div>
                                        <div className="appeal-history-title">
                                            <strong>Ariza #{item.id}</strong>
                                            <span className={"admin-badge " + (item.status === "approved" ? "success" : item.status === "rejected" ? "danger" : "neutral")}>{appealStatus[item.status] || item.status}</span>
                                        </div>
                                        <p><b>Cheklov:</b> #{item.block_id} · {labels[item.block_type] || item.block_type}</p>
                                        <p><b>Cheklov sababi:</b> {item.block_reason}</p>
                                        <p><b>Sizning fikringiz:</b> {item.appeal_text}</p>
                                        {item.admin_response && <p><b>Admin javobi:</b> {item.admin_response}</p>}
                                    </div>
                                    <div className="appeal-history-meta">{formatDate(item.created_at)}{item.reviewed_at ? " · Ko‘rilgan: " + formatDate(item.reviewed_at) : ""}</div>
                                </div>
                            ))}
                        </div>
                    ) : <div className="empty-state">Hali ariza yubormagansiz.</div>}
                </div>
            </div>

            {selectedBlock && (
                <div className="admin-modal-backdrop" onClick={() => setSelectedBlock(null)}>
                    <div className="card admin-modal appeal-modal" onClick={(event) => event.stopPropagation()}>
                        <div className="admin-modal-head">
                            <div>
                                <span className="admin-search-eyebrow">ARIZA #{selectedBlock.id}</span>
                                <h3>{labels[selectedBlock.block_type] || selectedBlock.block_type}</h3>
                                <p>Cheklov sababi: {selectedBlock.reason}</p>
                            </div>
                            <button className="admin-modal-close" onClick={() => setSelectedBlock(null)}>×</button>
                        </div>
                        <form className="admin-user-form" onSubmit={submit}>
                            <label>
                                Ariza matni
                                <textarea className="input admin-textarea appeal-textarea" minLength="10" maxLength="4000" value={text} onChange={(event) => setText(event.target.value)} placeholder="Nega bu cheklovni qayta ko‘rib chiqish kerak deb o‘ylaysiz? Vaziyatni tushuntiring..." />
                            </label>
                            <div className="appeal-character-count">{text.length}/4000</div>
                            <div className="admin-modal-actions">
                                <button type="button" className="btn btn-secondary" onClick={() => setSelectedBlock(null)}>Bekor qilish</button>
                                <button type="submit" className="btn btn-primary" disabled={loading || text.trim().length < 10}>{loading ? "Yuborilmoqda..." : "Ariza yuborish"}</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </AppLayout>
    )
}

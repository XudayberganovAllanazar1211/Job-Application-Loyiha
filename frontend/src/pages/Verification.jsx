import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

const METHODS = {
    phone: {
        title: "Telefon raqamini tasdiqlash",
        eyebrow: "TELEFON VERIFIKATSIYASI",
        description: "Telefon raqami sizga tegishli ekanini tasdiqlash hisobingizga qo‘shimcha ishonch beradi.",
        steps: [
            "Profilingizdagi telefon raqami to‘g‘ri ekanini tekshiring.",
            "Telefon raqamingizni tasdiqlash uchun administrator tekshiruvi talab qilinadi.",
            "Tasdiqlangandan keyin profilingizda tegishli belgi paydo bo‘ladi."
        ],
        key: "phone_verified"
    },
    identity: {
        title: "Shaxsni tasdiqlash",
        eyebrow: "SHAXSNI TASDIQLASH",
        description: "Bu tekshiruv akkaunt ortida haqiqiy shaxs borligini tasdiqlash uchun mo‘ljallangan.",
        steps: [
            "Shaxsni tasdiqlash uchun kerakli hujjatni tayyorlang.",
            "Hujjatni faqat FinJob’ning rasmiy va xavfsiz tasdiqlash jarayoni orqali taqdim eting.",
            "Administrator tekshiruvi yakunlangach, natija profilingizda ko‘rsatiladi."
        ],
        key: "identity_verified"
    }
}

export default function Verification() {
    const [searchParams, setSearchParams] = useSearchParams()
    const selectedType = searchParams.get("type") === "identity" ? "identity" : "phone"
    const [verification, setVerification] = useState(null)
    const [loading, setLoading] = useState(true)
    const [notice, setNotice] = useState("")

    useEffect(() => {
        let active = true
        const load = async () => {
            setLoading(true)
            const result = await api("/verification", { token: localStorage.getItem("token") || "" })
            if (!active) return
            if (result && typeof result === "object" && !result.msg) {
                setVerification(result)
                setNotice("")
            } else {
                setNotice(result?.msg || "Tasdiqlash holatini yuklab bo‘lmadi.")
            }
            setLoading(false)
        }
        load()
        return () => { active = false }
    }, [])

    const method = METHODS[selectedType]
    const verified = Boolean(verification?.[method.key])

    return (
        <AppLayout
            title="Tasdiqlash markazi"
            subtitle="Telefon raqamingiz va shaxsingizni tasdiqlash holatini shu yerdan ko‘ring."
        >
            {notice && <div className="notice warn" role="status">{notice}</div>}
            <section className="card verification-center">
                <div className="verification-center-intro">
                    <span className="verification-center-eyebrow">FINJOB · HISOB ISHONCHLILIGI</span>
                    <h2>Tasdiqlash menyusi</h2>
                    <p>Kerakli tasdiqlash turini tanlang va uning holati bilan tanishing.</p>
                </div>

                <div className="verification-method-tabs" role="tablist" aria-label="Tasdiqlash turi">
                    <button
                        type="button"
                        role="tab"
                        aria-selected={selectedType === "phone"}
                        className={selectedType === "phone" ? "verification-method-tab active" : "verification-method-tab"}
                        onClick={() => setSearchParams({ type: "phone" })}
                    >
                        <span aria-hidden="true">☎</span>
                        Telefon raqami
                        {verification?.phone_verified && <span className="verification-tab-check">✓</span>}
                    </button>
                    <button
                        type="button"
                        role="tab"
                        aria-selected={selectedType === "identity"}
                        className={selectedType === "identity" ? "verification-method-tab active" : "verification-method-tab"}
                        onClick={() => setSearchParams({ type: "identity" })}
                    >
                        <span aria-hidden="true">▣</span>
                        Shaxsni tasdiqlash
                        {verification?.identity_verified && <span className="verification-tab-check">✓</span>}
                    </button>
                </div>

                <div className="verification-method-panel" role="tabpanel">
                    <div className="verification-method-heading">
                        <div>
                            <span className="verification-center-eyebrow">{method.eyebrow}</span>
                            <h3>{method.title}</h3>
                        </div>
                        <span className={verified ? "verification-status-pill verified" : "verification-status-pill"}>
                            {loading ? "Tekshirilmoqda…" : verified ? "✓ Tasdiqlangan" : "Tasdiqlanmagan"}
                        </span>
                    </div>
                    <p className="verification-method-description">{method.description}</p>
                    <h4>Keyingi qadamlar</h4>
                    <ol className="verification-step-list">
                        {method.steps.map((step, index) => (
                            <li key={step}>
                                <span>{index + 1}</span>
                                <p>{step}</p>
                            </li>
                        ))}
                    </ol>
                    {!verified && (
                        <div className="verification-review-note">
                            <strong>Hozircha avtomatik yuborish yoqilmagan.</strong>
                            <p>FinJob’da foydalanuvchi uchun hujjat yoki telefon ma’lumotlarini xavfsiz yuborish endpointi mavjud bo‘lmagani sababli, bu sahifa hozircha holat va yo‘riqnomani ko‘rsatadi. Tasdiqlash belgisi administrator tekshiruvidan keyin yangilanadi.</p>
                        </div>
                    )}
                </div>
            </section>
        </AppLayout>
    )
}

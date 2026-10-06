import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import AppLayout from "../components/AppLayout"
import { api } from "../api"

function buildServiceTree(services) {
    const nodes = Object.fromEntries(services.map((service) => [
        String(service.id),
        { ...service, children: [] }
    ]))
    const roots = []
    services.forEach((service) => {
        const node = nodes[String(service.id)]
        if (service.parent_id == null) roots.push(node)
        else if (nodes[String(service.parent_id)]) nodes[String(service.parent_id)].children.push(node)
    })
    return roots
}

function ServiceNode({ node, level, selected, onSelect }) {
    const [open, setOpen] = useState(false)
    const hasChildren = node.children.length > 0

    return (
        <div>
            <div className="service-tree-row" style={{ paddingLeft: 10 + level * 20 }}>
                {hasChildren ? (
                    <button type="button" className="service-tree-toggle" onClick={() => setOpen(!open)}>
                        {open ? "▾" : "▸"}
                    </button>
                ) : <span className="service-tree-spacer" />}
                <button
                    type="button"
                    className={selected.includes(String(node.id)) ? "service-tree-item selected" : "service-tree-item"}
                    disabled={hasChildren}
                    onClick={() => onSelect(node)}
                >
                    {node.name}
                </button>
            </div>
            {open && hasChildren && node.children.map((child) => (
                <ServiceNode key={child.id} node={child} level={level + 1} selected={selected} onSelect={onSelect} />
            ))}
        </div>
    )
}

export default function CreateJob() {
    const [services, setServices] = useState([])
    const [serviceSearch, setServiceSearch] = useState("")
    const [showCategories, setShowCategories] = useState(false)
    const [selectedServiceIds, setSelectedServiceIds] = useState([])
    const [customServices, setCustomServices] = useState([])
    const [form, setForm] = useState({
        service_id: "",
        title: "",
        description: "",
        price: "",
        currency: "UZS",
        location: ""
    })
    const [notice, setNotice] = useState("")
    const [loading, setLoading] = useState(false)
    const [priceError, setPriceError] = useState("")
    const [locationLoading, setLocationLoading] = useState(false)
    const [locationError, setLocationError] = useState("")
    const navigate = useNavigate()
    const token = localStorage.getItem("token") || ""
    const serviceTree = useMemo(() => buildServiceTree(services), [services])

    const filteredServices = useMemo(() => {
        const query = serviceSearch.trim().toLowerCase()
        if (!query) return services

        return services.filter((service) => service.name.toLowerCase().includes(query))
    }, [services, serviceSearch])

    const filteredServiceTree = useMemo(() => buildServiceTree(filteredServices), [filteredServices])

    useEffect(() => {
        const load = async () => {
            const result = await api("/services", { token })
            if (Array.isArray(result)) setServices(result)
        }
        load()
    }, [token])

    const canSubmit = useMemo(
        () =>
            (selectedServiceIds.length > 0 || customServices.length > 0) &&
            form.title.trim() &&
            form.description.trim() &&
            form.price &&
            !priceError &&
            form.location.trim(),
        [form, selectedServiceIds, customServices, priceError]
    )

    const detectLocation = () => {
        if (!navigator.geolocation) {
            setLocationError("Brauzeringiz joylashuvni aniqlashni qo'llab-quvvatlamaydi.")
            return
        }

        setLocationError("")
        setLocationLoading(true)

        let bestPosition = null
        let finished = false
        let watchId = null

        const finish = async (position) => {
            if (finished || !position) return
            finished = true

            if (watchId !== null) navigator.geolocation.clearWatch(watchId)

            const { latitude, longitude, accuracy } = position.coords

            if (accuracy > 5000) {
                setLocationError(
                    `Kompyuter joylashuvni juda noaniq aniqladi (taxminan ${Math.round(accuracy / 100) / 10} km). Windows'da Location Service va Wi-Fi joylashuvini yoqing yoki joylashuvni qo'lda kiriting.`
                )
                setLocationLoading(false)
                return
            }

            const result = await api(
                `/reverse-geocode?lat=${encodeURIComponent(latitude)}&lon=${encodeURIComponent(longitude)}`,
                { token }
            )

            if (result?.ok && result.location) {
                setForm((current) => ({ ...current, location: result.location }))
                setLocationError(
                    accuracy > 1000
                        ? `Joylashuv topildi, lekin aniqlik taxminan ${Math.round(accuracy)} metr.`
                        : ""
                )
            } else {
                setLocationError(result?.msg || "Joylashuv manzilini aniqlab bo'lmadi.")
            }

            setLocationLoading(false)
        }

        const handlePosition = (position) => {
            if (!bestPosition || position.coords.accuracy < bestPosition.coords.accuracy) {
                bestPosition = position
            }

            if (position.coords.accuracy <= 100) {
                finish(position)
            }
        }

        watchId = navigator.geolocation.watchPosition(
            handlePosition,
            (error) => {
                if (finished) return

                if (bestPosition) {
                    finish(bestPosition)
                    return
                }

                if (error.code === 1) {
                    setLocationError("Joylashuvga ruxsat berilmadi. Chrome va Windows sozlamalaridan ruxsat bering.")
                } else if (error.code === 2) {
                    setLocationError("Joylashuv aniqlanmadi. Windows Location Service va Wi-Fi'ni tekshiring.")
                } else if (error.code === 3) {
                    setLocationError("Joylashuvni aniqlash vaqti tugadi. Windows Location Service va Wi-Fi'ni tekshiring.")
                } else {
                    setLocationError("Joylashuvni aniqlashda xatolik yuz berdi.")
                }

                setLocationLoading(false)
                if (watchId !== null) navigator.geolocation.clearWatch(watchId)
            },
            {
                enableHighAccuracy: true,
                timeout: 15000,
                maximumAge: 0
            }
        )

        setTimeout(() => {
            if (!finished) {
                if (bestPosition) {
                    finish(bestPosition)
                } else {
                    setLocationLoading(false)
                    setLocationError("Aniq joylashuv olinmadi. Windows Location Service yoqilganini tekshiring.")
                    if (watchId !== null) navigator.geolocation.clearWatch(watchId)
                }
            }
        }, 15000)
    }

    const submit = async (e) => {
        e.preventDefault()
        setNotice("")
        const price = Number(form.price)
        if (!Number.isFinite(price) || price <= 0 || price > 100000000000) {
            setPriceError("Narx 0 dan katta va 100 000 000 000 dan oshmasligi kerak.")
            return
        }

        setLoading(true)

        const result = await api("/job", {
            method: "POST",
            body: {
                service_id: selectedServiceIds.length ? Number(selectedServiceIds[0]) : null,
                service_ids: selectedServiceIds.map(Number),
                custom_service: customServices.join(", "),
                custom_services: customServices,
                title: form.title.trim(),
                description: form.description.trim(),
                price,
                currency: form.currency,
                location: form.location.trim()
            },
            token
        })

        setLoading(false)

        if (result?.msg === "ok") {
            setNotice("Job yaratildi")
            setTimeout(() => navigate("/jobs"), 700)
            return
        }

        setNotice(result?.msg || "Job yaratishda xato")
    }

    return (
        <AppLayout
            title="Create Job"
            subtitle="Xizmat kategoriyasini tanlab, yangi ish joylang."
        >
            <div className="grid-2">
                <section className="card">
                    <h2>Job form</h2>
                    <p className="muted">Barcha maydonlarni to‘ldiring.</p>

                    {notice && <div className="notice ok" style={{ marginBottom: 14 }}>{notice}</div>}

                    <form className="form" onSubmit={submit}>
                        <div className="service-picker">
                            <div className="service-picker-title">
                                <div className="selected-services">
                                    {selectedServiceIds.map((id) => (
                                        <span className="selected-service-chip" key={id}>
                                            {services.find((service) => String(service.id) === String(id))?.name || "Xizmat"}
                                            <button type="button" onClick={() => setSelectedServiceIds(selectedServiceIds.filter((serviceId) => serviceId !== id))} aria-label="Sohani olib tashlash">×</button>
                                        </span>
                                    ))}
                                    {customServices.map((service, index) => (
                                        <span className="selected-service-chip" key={service}>
                                            {service}
                                            <button type="button" onClick={() => setCustomServices(customServices.filter((_, i) => i !== index))} aria-label="Sohani olib tashlash">×</button>
                                        </span>
                                    ))}
                                    {!selectedServiceIds.length && !customServices.length && <span>Xizmatni tanlang</span>}
                                </div>
                            </div>
                            <button
                                type="button"
                                className="btn btn-primary service-select-button"
                                onClick={() => {
                                    setShowCategories((current) => !current)
                                    setServiceSearch("")
                                }}
                            >
                                {showCategories ? "Soha tanlashni yopish" : "Soha tanlang"}
                            </button>
                            {showCategories && (
                                <div className="service-search">
                                    <input
                                        autoFocus
                                        className="input"
                                        type="search"
                                        placeholder="Xizmatni qidiring..."
                                        value={serviceSearch}
                                        onChange={(e) => setServiceSearch(e.target.value)}
                                    />
                                </div>
                            )}
                            <div className="service-tree">
                                {!showCategories && !serviceSearch.trim() ? (
                                    <div className="service-category-placeholder">
                                        Soha tanlash uchun yuqoridagi tugmani bosing
                                    </div>
                                ) : serviceSearch.trim() ? (
                                    (() => {
                                        const parentIds = new Set(
                                            services
                                                .filter((service) => service.parent_id != null)
                                                .map((service) => String(service.parent_id))
                                        )
                                        const exactServices = filteredServices.filter(
                                            (service) => !parentIds.has(String(service.id))
                                        )
                                        return exactServices.length ? exactServices.map((service) => (
                                            <button
                                                key={service.id}
                                                type="button"
                                                className={selectedServiceIds.includes(String(service.id)) ? "service-search-result selected" : "service-search-result"}
                                                onClick={() => {
                                                    setSelectedServiceIds((current) =>
                                                        current.includes(String(service.id)) ? current : [...current, String(service.id)]
                                                    )
                                                    setServiceSearch("")
                                                    setShowCategories(false)
                                                }}
                                            >
                                                {service.name}
                                            </button>
                                        )) : (
                                            <div>
                                                <div className="empty-state">Bunday xizmat topilmadi</div>
                                                <button
                                                    type="button"
                                                    className="btn btn-secondary"
                                                    style={{ marginTop: 10, width: "100%" }}
                                                    onClick={() => {
                                                        const customService = serviceSearch.trim()
                                                        if (!customService) return

                                                        setCustomServices((current) =>
                                                            current.some((item) => item.toLowerCase() === customService.toLowerCase())
                                                                ? current
                                                                : [...current, customService]
                                                        )
                                                        setServiceSearch("")
                                                        setShowCategories(false)
                                                    }}
                                                >
                                                    “{serviceSearch.trim()}” sohasini qo'shish
                                                </button>
                                            </div>
                                        )
                                    })()
                                ) : (
                                    filteredServiceTree.length ? filteredServiceTree.map((node) => (
                                        <ServiceNode
                                            key={node.id}
                                            node={node}
                                            level={0}
                                            selected={selectedServiceIds}
                                            onSelect={(node) => {
                                                if (!selectedServiceIds.includes(String(node.id))) setSelectedServiceIds([...selectedServiceIds, String(node.id)])
                                                setShowCategories(false)
                                            }}
                                        />
                                    )) : (
                                        <div className="empty-state">Bunday xizmat topilmadi</div>
                                    )
                                )}
                            </div>
                        </div>

                        <input
                            className="input"
                            placeholder="Title"
                            value={form.title}
                            onChange={(e) => setForm({ ...form, title: e.target.value })}
                        />

                        <textarea
                            className="textarea"
                            placeholder="Description"
                            value={form.description}
                            onChange={(e) => setForm({ ...form, description: e.target.value })}
                        />

                        <div className="form-row">
                            <div className="price-field">
                                <div className="price-input-row">
                                    <input
                                        className="input"
                                        type="number"
                                        min="0.01"
                                        max="100000000000"
                                        step="0.01"
                                        placeholder="Price"
                                        value={form.price}
                                        onChange={(e) => {
                                            const value = e.target.value
                                            setForm({ ...form, price: value })
                                            const number = Number(value)
                                            if (!value || !Number.isFinite(number) || number <= 0 || number > 100000000000) {
                                                setPriceError("Narx 0 dan katta va 100 000 000 000 dan oshmasligi kerak.")
                                            } else {
                                                setPriceError("")
                                            }
                                        }}
                                        required
                                    />
                                    <select
                                        className="input currency-select"
                                        value={form.currency}
                                        onChange={(e) => setForm({ ...form, currency: e.target.value })}
                                    >
                                        <option value="UZS">UZS — So'm</option>
                                        <option value="USD">USD — Dollar</option>
                                        <option value="EUR">EUR — Euro</option>
                                    </select>
                                </div>
                                {priceError && <div className="field-error">{priceError}</div>}
                            </div>
                            <div className="location-field">
                                <div className="location-input-row">
                                    <input
                                        className="input"
                                        placeholder="Location"
                                        value={form.location}
                                        onChange={(e) => {
                                            setForm({ ...form, location: e.target.value })
                                            setLocationError("")
                                        }}
                                    />
                                    <button
                                        type="button"
                                        className="btn btn-secondary detect-location-button"
                                        onClick={detectLocation}
                                        disabled={locationLoading}
                                    >
                                        {locationLoading ? "Aniqlanmoqda..." : "Joylashuvimni aniqlash"}
                                    </button>
                                </div>
                                {locationError && <div className="location-error">{locationError}</div>}
                                <div className="location-attribution">
                                    Manzil ma'lumoti: © OpenStreetMap contributors
                                </div>
                            </div>
                        </div>

                        <button className="btn btn-primary" disabled={!canSubmit || loading}>
                            {loading ? "Yuborilmoqda..." : "Submit"}
                        </button>
                    </form>
                </section>

                <aside className="card job-tips-card">
                    <h3>Tips</h3>
                    <p className="muted">Yaxshi job e’lonini yaratish uchun foydali maslahatlar.</p>
                    <div className="tips-list">
                        <div className="tip-item">
                            <strong>🎯 Aniq sarlavha yozing</strong>
                            <span>Job title qisqa va tushunarli bo‘lsin. Masalan: “React landing page yaratish”.</span>
                        </div>
                        <div className="tip-item">
                            <strong>📝 Vazifani batafsil tushuntiring</strong>
                            <span>Nima kerakligini, qanday natija kutayotganingizni va muhim talablarni yozing.</span>
                        </div>
                        <div className="tip-item">
                            <strong>🛠️ To‘g‘ri service tanlang</strong>
                            <span>Jobingizga eng mos xizmatni tanlash kerakli mutaxassislarni topishni osonlashtiradi.</span>
                        </div>
                        <div className="tip-item">
                            <strong>💰 Realistik narx belgilang</strong>
                            <span>Ish hajmi va murakkabligiga mos narx qo‘yish ko‘proq yaxshi takliflarni jalb qiladi.</span>
                        </div>
                        <div className="tip-item">
                            <strong>📍 Location’ni ko‘rsating</strong>
                            <span>Offline ish bo‘lsa, ish bajariladigan joyni aniq yozing.</span>
                        </div>
                        <div className="tip-item">
                            <strong>⏱️ Muddatni ayting</strong>
                            <span>Kerak bo‘lsa, description ichida ish qachongacha tugashi kerakligini ko‘rsating.</span>
                        </div>
                        <div className="tip-item">
                            <strong>💬 Muhim tafsilotlarni yozing</strong>
                            <span>Kerakli skill, texnologiya, fayl yoki boshqa shartlarni oldindan belgilang.</span>
                        </div>
                    </div>
                </aside>
            </div>
        </AppLayout>
    )
}
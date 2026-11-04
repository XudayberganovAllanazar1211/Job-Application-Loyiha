import { useEffect, useState } from "react"
import { Link } from "react-router-dom"

export default function Landing() {
    const [theme, setTheme] = useState(() => localStorage.getItem("finjob-theme") || "light")

    useEffect(() => {
        document.documentElement.dataset.theme = theme
        localStorage.setItem("finjob-theme", theme)
    }, [theme])

    return (
        <div className="landing-page">
            <header className="landing-header">
                <Link to="/" className="landing-brand" aria-label="FinJob bosh sahifasi">
                    <span className="landing-brand-mark">FJ</span>
                    <span className="landing-brand-copy">
                        <strong>FinJob</strong>
                        <small>Ish va xizmatlar platformasi</small>
                    </span>
                </Link>

                <nav className="landing-nav" aria-label="Asosiy navigatsiya">
                    <a href="#for-everyone">Kimlar uchun?</a>
                    <a href="#how-it-works">Qanday ishlaydi?</a>
                    <a href="#community-rules">Qoidalar</a>
                </nav>

                <div className="landing-header-actions">
                    <button
                        type="button"
                        className="landing-theme-toggle"
                        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                    >
                        {theme === "dark" ? "Yorug‘ rejim" : "Qorong‘i rejim"}
                    </button>
                    <Link to="/login" className="landing-login-link">Kirish</Link>
                    <Link to="/register" className="landing-register-link">Akkaunt yaratish</Link>
                </div>
            </header>

            <main className="landing-main">
                <section className="landing-hero">
                    <div className="landing-hero-copy">
                        <span className="landing-eyebrow">ISH VA XIZMATLAR UCHUN YAGONA MAYDON</span>
                        <h1>Kerakli ish va kerakli mutaxassis — bitta platformada.</h1>
                        <p>
                            FinJob ish buyurtmachilari va xizmat ko‘rsatuvchilarni bir joyga jamlaydi.
                            Ish e’lon qiling, o‘zingizga mos imkoniyatlarni toping va kelishuvlarni
                            platforma orqali boshqaring.
                        </p>
                        <div className="landing-hero-actions">
                            <Link to="/register" className="landing-primary-action">Bepul akkaunt yaratish</Link>
                            <Link to="/jobs" className="landing-secondary-action">Ish topish imkoniyatlari</Link>
                        </div>
                        <div className="landing-guest-note">
                            <span className="landing-note-dot" />
                            Hozircha akkauntsiz tanishib chiqishingiz mumkin. Amallar uchun akkaunt kerak bo‘ladi.
                        </div>
                    </div>

                    <div className="landing-preview" aria-label="FinJob platformasi imkoniyatlari namunasi">
                        <div className="landing-preview-top">
                            <span className="landing-preview-brand"><i>FJ</i> FinJob</span>
                            <span className="landing-preview-status">Platforma ko‘rinishi</span>
                        </div>
                        <div className="landing-preview-heading">
                            <span className="landing-preview-label">ISH JARAYONI</span>
                            <strong>Buyurtmadan natijagacha</strong>
                            <small>Barcha muhim bosqichlar bir joyda</small>
                        </div>
                        <div className="landing-preview-step">
                            <span className="landing-preview-number">01</span>
                            <span><strong>Ish e’loni</strong><small>Vazifa va talablarni belgilang</small></span>
                            <b>01</b>
                        </div>
                        <div className="landing-preview-step">
                            <span className="landing-preview-number">02</span>
                            <span><strong>Taklif va muloqot</strong><small>Mutaxassislar bilan kelishing</small></span>
                            <b>02</b>
                        </div>
                        <div className="landing-preview-step">
                            <span className="landing-preview-number">03</span>
                            <span><strong>Ish yakuni</strong><small>Natijani tasdiqlang va baholang</small></span>
                            <b>03</b>
                        </div>
                        <div className="landing-preview-footer">
                            <span>FinJob</span>
                            <span>Ish, muloqot va natija</span>
                        </div>
                    </div>
                </section>

                <section className="landing-section" id="for-everyone">
                    <div className="landing-section-heading">
                        <span className="landing-eyebrow">BIR PLATFORMADA IKKI TOMON</span>
                        <h2>FinJob kimlar uchun?</h2>
                        <p>O‘zingizga mos yo‘nalishni tanlang. Har ikkala holatda ham bitta akkaunt yetarli.</p>
                    </div>
                    <div className="landing-audience-grid">
                        <article className="landing-audience-card">
                            <span className="landing-card-index">01 / BUYURTMACHI</span>
                            <h3>Xizmatingizga mutaxassis kerakmi?</h3>
                            <p>Vazifani tushuntiring, kerakli xizmat turini belgilang va ish bo‘yicha kelib tushgan takliflarni ko‘rib chiqing.</p>
                            <Link to="/create">Ish e’lon qilish <span aria-hidden="true">→</span></Link>
                        </article>
                        <article className="landing-audience-card landing-audience-card-blue">
                            <span className="landing-card-index">02 / MUTAXASSIS</span>
                            <h3>O‘z ko‘nikmalaringiz bilan ish toping.</h3>
                            <p>Mavjud ishlar bilan tanishing, mos buyurtmalarni tanlang va xizmatlaringizni taklif qiling.</p>
                            <Link to="/jobs">Ishlarni ko‘rish <span aria-hidden="true">→</span></Link>
                        </article>
                    </div>
                </section>

                <section className="landing-section landing-process" id="how-it-works">
                    <div className="landing-section-heading">
                        <span className="landing-eyebrow">SODDA ISH JARAYONI</span>
                        <h2>Qanday ishlaydi?</h2>
                    </div>
                    <div className="landing-process-grid">
                        <article><span>01</span><h3>Akkaunt yarating</h3><p>O‘zingiz haqingizdagi asosiy ma’lumotlar bilan profil oching.</p></article>
                        <article><span>02</span><h3>Ish yoki xizmatni tanlang</h3><p>Buyurtma joylashtiring yoki mavjud ishlar orasidan mosini toping.</p></article>
                        <article><span>03</span><h3>Muloqot qiling va yakunlang</h3><p>Takliflarni muhokama qiling, ish holatini kuzating va natijani baholang.</p></article>
                    </div>
                </section>

                <section className="landing-section" id="community-rules">
                    <div className="landing-section-heading">
                        <span className="landing-eyebrow">HAMMA UCHUN ANIQLIK</span>
                        <h2>Eng muhim qoidalar</h2>
                        <p>FinJobdan foydalanishda quyidagi oddiy qoidalarga amal qiling.</p>
                    </div>
                    <div className="landing-audience-grid">
                        <article className="landing-audience-card">
                            <span className="landing-card-index">01 / HALOLLIK</span>
                            <h3>Haqiqiy e’lonlar</h3>
                            <p>Ish, xizmat, narx va muddat haqida aniq hamda rost ma’lumot bering.</p>
                        </article>
                        <article className="landing-audience-card">
                            <span className="landing-card-index">02 / HURMAT</span>
                            <h3>Madaniyatli muloqot</h3>
                            <p>Haqorat, tahdid, kamsitish va ta’qibga yo‘l qo‘ymang.</p>
                        </article>
                        <article className="landing-audience-card">
                            <span className="landing-card-index">03 / XAVFSIZLIK</span>
                            <h3>Firibgarlikdan saqlaning</h3>
                            <p>Parol va tasdiqlash kodlarini hech kimga bermang. Shubhali havola va takliflardan ehtiyot bo‘ling.</p>
                        </article>
                        <article className="landing-audience-card">
                            <span className="landing-card-index">04 / ADOLAT</span>
                            <h3>Haqiqiy baho bering</h3>
                            <p>Faqat real ish tajribangizga asoslanib baholang. Soxta reyting va spam tarqatmang.</p>
                        </article>
                    </div>
                </section>

                <section className="landing-final-cta">
                    <div>
                        <span className="landing-eyebrow">BOSHLASHGA TAYYORMISIZ?</span>
                        <h2>FinJob bilan imkoniyatlarni kashf eting.</h2>
                        <p>Platforma bilan tanishish ochiq. Ishlashni boshlash uchun akkaunt yarating.</p>
                    </div>
                    <Link to="/register" className="landing-primary-action">Ro‘yxatdan o‘tish</Link>
                </section>
            </main>

            <footer className="landing-footer">
                <Link to="/" className="landing-footer-brand">FinJob</Link>
                <span>Ish va xizmatlar uchun yagona platforma.</span>
                <div>
                    <Link to="/terms">Foydalanish shartlari</Link>
                    <Link to="/privacy">Maxfiylik</Link>
                </div>
            </footer>
        </div>
    )
}

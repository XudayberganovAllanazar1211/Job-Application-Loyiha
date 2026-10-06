import { Link } from "react-router-dom"

export default function CommunityRules() {
    return (
        <div className="legal-page">
            <div className="legal-shell">
                <div className="legal-top">
                    <Link className="legal-brand" to="/">FinJob</Link>
                    <Link className="link" to="/">Bosh sahifaga qaytish</Link>
                </div>

                <article className="legal-card">
                    <span className="legal-eyebrow">FINJOB / SAFETY</span>
                    <h1>Community Rules</h1>
                    <p className="legal-updated">Kuchga kirish sanasi: 6-oktabr, 2026</p>

                    <p>FinJobdagi maqsad — ish topish va ish berish jarayonini foydali, halol va xavfsiz saqlash.</p>

                    <h2>Ruxsat etiladi</h2>
                    <p>Haqiqiy xizmatlar, qonuniy ish takliflari, professional muloqot, konstruktiv feedback va ishga aloqador materiallar joylashtirilishi mumkin.</p>

                    <h2>Taqiqlanadi</h2>
                    <p>Firibgarlik, phishing, spam, zararli dastur, akkaunt o'g'irlash, noqonuniy xizmatlar, tahdid va haqorat, shaxsiy ma'lumotlarni ruxsatsiz tarqatish hamda boshqa foydalanuvchilarni ataylab aldash taqiqlanadi.</p>

                    <h2>Shaxsiy xavfsizlik</h2>
                    <p>Parol va verification kodini boshqa foydalanuvchiga bermang. Offline uchrashuvlarda jamoat joylari va xavfsiz aloqa usullaridan foydalaning. Jobdagi location ma'lumotini joylashtirishdan oldin u qanchalik ochiq ko'rinishini hisobga oling.</p>

                    <h2>Qoidabuzarlik</h2>
                    <p>Shubhali yoki zararli faoliyatni ko'rsangiz, platforma administratori tomonidan ko'rib chiqilishi uchun dalillarni saqlab qo'ying. FinJob qoidabuzarlik aniqlansa kontentni cheklashi yoki akkauntga nisbatan choralar ko'rishi mumkin.</p>

                    <h2>Yangilanishlar</h2>
                    <p>Platforma rivojlanishi bilan qoidalar to'ldirilishi mumkin. Eng yangi versiya doim ushbu sahifada ko'rsatiladi.</p>
                </article>
            </div>
        </div>
    )
}

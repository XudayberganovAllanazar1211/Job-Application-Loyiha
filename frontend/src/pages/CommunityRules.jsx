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
                    <span className="legal-eyebrow">FINJOB / HAMJAMIYAT</span>
                    <h1>Hamjamiyat qoidalari</h1>
                    <p className="legal-updated">Amaldagi sana: 6-oktabr, 2026</p>
                    <p>FinJobning maqsadi — ish topish va xizmat ko‘rsatish jarayonini halol, professional va xavfsiz saqlash. Har bir foydalanuvchi boshqalarning huquqi va vaqtini hurmat qilishi kerak.</p>
                    <h2>1. Halol e’lonlar</h2>
                    <p>Haqiqiy xizmat va ishlarni aniq tavsiflang. Soxta ish, yashirin shartlar, aldov yoki ataylab chalg‘ituvchi narx va ma’lumotlardan foydalanmang.</p>
                    <h2>2. Hurmatli muloqot</h2>
                    <p>Haqorat, tahdid, kamsitish, bosim o‘tkazish va ta’qib taqiqlanadi. Muammoni professional tarzda tushuntiring.</p>
                    <h2>3. Spam va firibgarlik yo‘q</h2>
                    <p>Spam, fishing, akkaunt o‘g‘irlashga urinish, zararli dastur yoki kod, soxta havolalar va boshqa firibgarlik usullari taqiqlanadi.</p>
                    <h2>4. Shaxsiy ma’lumotlarni himoya qiling</h2>
                    <p>O‘zingizning yoki boshqa foydalanuvchining paroli, tasdiqlash kodi, maxfiy aloqa ma’lumotlari yoki boshqa shaxsiy ma’lumotlarini ruxsatsiz tarqatmang.</p>
                    <h2>5. Xavfsiz uchrashuvlar</h2>
                    <p>Oflayn uchrashuvlarda jamoat joylari va ishonchli aloqa usullaridan foydalaning. Uy manzili kabi nozik ma’lumotlarni e’lon tavsifiga keragidan ortiq kiritmang.</p>
                    <h2>6. Adolatli reyting</h2>
                    <p>Faqat real ish tajribangizga asoslangan baho bering. Soxta reyting, reytingni sun’iy oshirish yoki boshqa foydalanuvchini qasos sifatida past baholash mumkin emas.</p>
                    <h2>7. Qoidabuzarlik haqida xabar</h2>
                    <p>Shubhali faoliyatni ko‘rsangiz, imkon qadar dalillarni saqlang va platformadagi mavjud aloqa yoki administrator kanali orqali xabar bering.</p>
                    <h2>8. Moderatsiya</h2>
                    <p>FinJob qoidabuzarlik aniqlanganda kontentni olib tashlashi, cheklashi yoki akkauntga nisbatan choralar ko‘rishi mumkin.</p>
                    <div className="legal-note">Ushbu qoidalar platformadagi xavfsiz muhitni saqlash uchun mo‘ljallangan va FinJob rivojlanishi bilan yangilanib boradi.</div>
                </article>
            </div>
        </div>
    )
}

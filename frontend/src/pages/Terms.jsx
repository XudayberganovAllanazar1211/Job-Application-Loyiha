import { Link } from "react-router-dom"

export default function Terms() {
    return (
        <div className="legal-page">
            <div className="legal-shell">
                <div className="legal-top">
                    <Link className="legal-brand" to="/">FinJob</Link>
                    <Link className="link" to="/">Bosh sahifaga qaytish</Link>
                </div>
                <article className="legal-card">
                    <span className="legal-eyebrow">FINJOB / FOYDALANISH</span>
                    <h1>Foydalanish shartlari</h1>
                    <p className="legal-updated">Kuchga kirish sanasi: 6-oktabr, 2026</p>
                    <p>FinJob ish va xizmat e’lonlarini joylashtirish, mos mutaxassislarni topish, muloqot qilish va bajarilgan ishlarni baholash uchun xizmat qiladi. Platformadan foydalanish ushbu shartlarga rozilik bildirganingizni anglatadi.</p>
                    <h2>1. Akkaunt</h2>
                    <p>Ro‘yxatdan o‘tishda haqqoniy ma’lumot bering. Akkaunt, parol va tasdiqlash kodini himoya qilish sizning mas’uliyatingiz. Boshqa shaxs nomidan akkaunt yaratish yoki ruxsatsiz kirish taqiqlanadi.</p>
                    <h2>2. Ish e’lonlari</h2>
                    <p>E’lon egasi sarlavha, tavsif, xizmat, narx va manzilning to‘g‘riligi uchun javob beradi. Firibgarlik, noqonuniy faoliyat yoki boshqa shaxslarning huquqlarini buzuvchi e’lonlar taqiqlanadi.</p>
                    <h2>3. Ishni qabul qilish va yakunlash</h2>
                    <p>Ishni qabul qilish tomonlar o‘rtasidagi kelishuv jarayonining bir qismi. FinJob ish sifati, natijasi yoki tomonlar o‘rtasidagi alohida kelishuvni kafolatlamaydi.</p>
                    <h2>4. To‘lovlar</h2>
                    <p>E’londagi narx va valyuta ish shartlarini ko‘rsatadi. Agar platformada alohida to‘lov operatori ko‘rsatilmagan bo‘lsa, haqiqiy to‘lov tartibi tomonlarning qonuniy kelishuviga bog‘liq.</p>
                    <h2>5. Muloqot va kontent</h2>
                    <p>Profil, e’lon, chat va reyting orqali yuborgan kontentingiz uchun o‘zingiz javobgarsiz. Spam, fishing, tahdid, zararli kod, aldov va noqonuniy kontent taqiqlanadi.</p>
                    <h2>6. Reyting</h2>
                    <p>Reyting haqiqiy tajribaga asoslangan bo‘lishi kerak. Soxta, manipulyativ yoki qasos sifatidagi baholar taqiqlanadi.</p>
                    <h2>7. Joylashuv</h2>
                    <p>Avtomatik joylashuv ixtiyoriy. Aniqlangan manzilni e’lon qilishdan oldin tekshiring va shaxsiy xavfsizligingizga mos darajada ma’lumot bering.</p>
                    <h2>8. Qoidabuzarlik</h2>
                    <p>FinJob xavfsizlik yoki qoidabuzarlik sabab e’lon, kontent yoki akkauntni cheklashi mumkin. Zarur hollarda foydalanuvchiga tegishli ma’lumotlar qonunchilik va platforma ehtiyojlariga muvofiq saqlanadi.</p>
                    <h2>9. Platforma cheklovlari</h2>
                    <p>FinJob xizmatning uzluksiz, xatosiz yoki doimo mavjud bo‘lishini kafolatlamaydi. Foydalanuvchilar o‘zaro kelishuvlarda ehtiyotkorlik va xavfsizlik choralariga rioya qilishlari kerak.</p>
                    <h2>10. Shartlarning yangilanishi</h2>
                    <p>Yangi funksiyalar yoki qonunchilik o‘zgarishi sabab ushbu shartlar yangilanishi mumkin. Yangi versiyaning sanasi sahifada ko‘rsatiladi.</p>
                    <div className="legal-note">Ushbu hujjat umumiy loyiha shablonidir. Tijoriy ishga tushirishdan oldin mahalliy yurist tomonidan yakuniy tekshiruvdan o‘tkazing.</div>
                </article>
            </div>
        </div>
    )
}

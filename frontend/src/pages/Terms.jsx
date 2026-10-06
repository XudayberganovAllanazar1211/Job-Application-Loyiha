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
                    <span className="legal-eyebrow">FINJOB / HUQUQIY</span>
                    <h1>Foydalanish shartlari</h1>
                    <p className="legal-updated">Kuchga kirish sanasi: 6-oktabr, 2026</p>

                    <h2>1. Platforma haqida</h2>
                    <p>FinJob foydalanuvchilarga ish va xizmat e'lonlarini joylashtirish, mos mutaxassislarni topish, ish bo'yicha muloqot qilish va bajarilgan ishlar uchun baho qoldirish imkonini beruvchi platformadir.</p>

                    <h2>2. Hisob</h2>
                    <p>Foydalanuvchi ro'yxatdan o'tishda haqqoniy ma'lumot berishi va akkaunt ma'lumotlarini himoya qilishi kerak. Boshqa shaxs nomidan akkaunt yaratish, login yoki tasdiqlash kodidan ruxsatsiz foydalanish taqiqlanadi.</p>

                    <h2>3. Ish va xizmat e’lonlari</h2>
                    <p>E'lon joylashtirgan foydalanuvchi uning mazmuni, narxi, talablari va joylashuv ma'lumotlari uchun javobgardir. Qonunga zid, firibgarlikka qaratilgan, zararli yoki boshqa shaxslarning huquqlarini buzuvchi e'lonlar joylashtirilmasligi kerak.</p>

                    <h2>4. Qabul qilish va yakunlash</h2>
                    <p>Ishni qabul qilish foydalanuvchi bilan ish yaratuvchisi o'rtasidagi kelishuv jarayonining bir qismi hisoblanadi. FinJob platformasi bajariladigan ishning sifati, natijasi yoki foydalanuvchilar o'rtasidagi kelishuvni alohida shartnoma bilan kafolatlamaydi.</p>

                    <h2>5. To'lovlar</h2>
                    <p>FinJobning hozirgi versiyasida ko'rsatilgan narx/valyuta ma'lumotlari ish shartlarini ifodalaydi. Foydalanuvchilar o'rtasida haqiqiy to'lovni amalga oshirish tartibi ular o'rtasidagi qonuniy kelishuvga bog'liq. FinJob alohida to‘lov operatori sifatida ko'rsatilmagan.</p>

                    <h2>6. Suhbat va kontent</h2>
                    <p>Foydalanuvchi suhbat, profil, ish va baho orqali yuborgan kontent uchun javobgardir. Spam, tahdid, firibgarlik, zararli kod yoki boshqa noqonuniy kontent tarqatish taqiqlanadi.</p>

                    <h2>7. Baho berish</h2>
                    <p>Baholash haqiqiy ish tajribasini adolatli aks ettirishi kerak. Soxta, manipulyativ yoki qasos sifatidagi baholardan foydalanmaslik kerak.</p>

                    <h2>8. Joylashuv</h2>
                    <p>Avtomatik manzil funksiyasidan foydalanish ixtiyoriy. Foydalanuvchi aniqlangan manzilni ish yuborilishidan oldin tekshirishi va zarur bo'lsa o'zgartirishi kerak.</p>

                    <h2>9. Akkauntni cheklash</h2>
                    <p>FinJob xavfsizlik yoki qoidabuzarlik sabab akkaunt yoki kontentga nisbatan choralar ko'rishi mumkin. Qonunchilik va texnik imkoniyatlar doirasida foydalanuvchiga tegishli ma'lumotlar saqlanishi yoki o'chirilishi mumkin.</p>

                    <h2>10. Javobgarlik</h2>
                    <p>Platforma uzluksiz, xatosiz yoki har doim mavjud bo'lishini kafolatlamaydi. Foydalanuvchilar boshqa foydalanuvchilar bilan mustaqil ravishda ehtiyotkorlik bilan kelishuv tuzishlari va zarur xavfsizlik choralarini ko'rishlari kerak.</p>

                    <h2>11. Qoidalarni yangilash</h2>
                    <p>Ushbu shartlar platforma funksiyalari yoki qonunchilikdagi o'zgarishlar sabab yangilanishi mumkin. Yangilangan sana sahifada ko'rsatiladi.</p>

                    <div className="legal-note">
                        Ushbu Foydalanish shartlari umumiy loyiha shabloni hisoblanadi. FinJobni tijoriy ishga tushirishdan oldin mahalliy yurist tomonidan yakuniy tekshiruvdan o'tkazilishi kerak.
                    </div>
                </article>
            </div>
        </div>
    )
}

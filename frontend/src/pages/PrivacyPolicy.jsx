import { Link } from "react-router-dom"

export default function PrivacyPolicy() {
    return (
        <div className="legal-page">
            <div className="legal-shell">
                <div className="legal-top">
                    <Link className="legal-brand" to="/">FinJob</Link>
                    <Link className="link" to="/">Bosh sahifaga qaytish</Link>
                </div>
                <article className="legal-card">
                    <span className="legal-eyebrow">FINJOB / MAXFIYLIK</span>
                    <h1>Maxfiylik siyosati</h1>
                    <p className="legal-updated">Kuchga kirish sanasi: 6-oktabr, 2026</p>
                    <p>FinJob sizning shaxsiy ma’lumotlaringizni faqat platformani ishlatish, xavfsizlikni ta’minlash va siz so‘ragan xizmatlarni ko‘rsatish uchun qayta ishlaydi. Biz ma’lumotlaringizni sotmaymiz.</p>
                    <h2>1. Biz nimalarni saqlaymiz?</h2>
                    <p>Ro‘yxatdan o‘tishda ism, familiya, tug‘ilgan sana, foydalanuvchi nomi va elektron pochta manzili olinadi. Parol ochiq ko‘rinishda emas, himoyalangan hash ko‘rinishida saqlanadi.</p>
                    <p>Profilingizda ko‘nikmalar, profil rasmi va o‘zingiz kiritgan boshqa ma’lumotlar bo‘lishi mumkin. Ish e’lonlarida xizmat, sarlavha, tavsif, narx, valyuta va manzil; chat va reytinglarda esa tegishli xabar, baho va izohlar saqlanadi.</p>
                    <h2>2. Joylashuv qanday ishlaydi?</h2>
                    <p>Joylashuv faqat siz “Joylashuvimni aniqlash” tugmasini bosganingizda va brauzer ruxsat berganida olinadi. Aniqlangan koordinatalar manzil matniga aylantirilishi mumkin. Siz manzilni yuborishdan oldin tekshirishingiz va o‘zgartirishingiz mumkin.</p>
                    <p>Manzilni aniqlash uchun OpenStreetMap Nominatim kabi tashqi geokodlash xizmati ishlatilishi mumkin. Ularning alohida qoidalari mavjud.</p>
                    <h2>3. Ma’lumotlardan foydalanish</h2>
                    <p>Ma’lumotlar akkauntni boshqarish, email orqali tasdiqlash, ishlarni ko‘rsatish va moslashtirish, chat, reyting, xavfsizlik va platformani yaxshilash uchun ishlatiladi.</p>
                    <h2>4. Email va uchinchi tomonlar</h2>
                    <p>Tasdiqlash kodi elektron pochta yetkazib berish xizmati orqali yuboriladi. Texnik jihatdan zarur bo‘lgan xizmatlarga faqat ularning vazifasini bajarish uchun kerakli ma’lumotlar uzatiladi.</p>
                    <h2>5. Saqlash va xavfsizlik</h2>
                    <p>Biz ruxsatsiz kirish, yo‘qotish yoki o‘zgartirish xavfini kamaytirish uchun texnik choralar ko‘ramiz. Biroq internetdagi hech bir tizim mutlaq xavfsiz deb kafolatlanmaydi.</p>
                    <p>Email tasdiqlash kodi vaqtinchalik saqlanadi va tasdiqlash yoki amal qilish muddati tugagach o‘chiriladi.</p>
                    <h2>6. Brauzer xotirasi</h2>
                    <p>FinJob sessiya va ayrim interfeys sozlamalarini brauzer xotirasida saqlashi mumkin. Reklama kuzatuvi uchun majburiy cookie ishlatilmaydi.</p>
                    <h2>7. Sizning nazoratingiz</h2>
                    <p>Siz profilingizdagi ma’lumotlarni ko‘rish va tuzatish, qonunchilik doirasida o‘chirishni so‘rash hamda brauzer orqali geolokatsiya ruxsatini boshqarish huquqiga egasiz.</p>
                    <h2>8. Yangilanishlar</h2>
                    <p>Platforma funksiyalari yoki qonunchilik o‘zgarsa, ushbu siyosat yangilanadi. Amaldagi sana sahifaning yuqori qismida ko‘rsatiladi.</p>
                    <div className="legal-note">Ushbu matn umumiy platforma siyosati uchun tayyorlangan. FinJobni tijoriy ishga tushirishdan oldin O‘zbekiston qonunchiligi bo‘yicha yurist bilan yakuniy tekshiruv tavsiya etiladi.</div>
                </article>
            </div>
        </div>
    )
}

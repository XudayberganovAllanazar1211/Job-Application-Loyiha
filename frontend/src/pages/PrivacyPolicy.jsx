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
                    <span className="legal-eyebrow">FINJOB / LEGAL</span>
                    <h1>Privacy Policy</h1>
                    <p className="legal-updated">Kuchga kirish sanasi: 6-oktabr, 2026</p>

                    <p>Ushbu Privacy Policy FinJob platformasidan foydalanishda shaxsiy ma'lumotlaringiz qanday yig'ilishi, ishlatilishi, saqlanishi va himoyalanishini tushuntiradi. FinJob ushbu siyosatni O'zbekiston Respublikasining shaxsiy ma'lumotlar to'g'risidagi amaldagi talablarini hisobga olgan holda yuritadi.</p>

                    <h2>1. Qanday ma'lumotlar yig'iladi?</h2>
                    <p>Hisob yaratishda ism, familiya, tug'ilgan sana, username, email va parol bilan bog'liq ma'lumotlar olinadi. Parol ochiq ko'rinishda saqlanmaydi; platforma uni xavfsiz hash ko'rinishida saqlaydi.</p>
                    <p>Profil to'ldirilganda bio, skills va profil rasmi kabi qo'shimcha ma'lumotlar saqlanishi mumkin.</p>
                    <p>Job yaratishda xizmat tanlovi, sarlavha, tavsif, narx, valyuta va location saqlanadi. Chat va rating funksiyalaridan foydalanganda yuborilgan xabarlar, baholar va izohlar ham tegishli ish bilan bog'lanadi.</p>

                    <h2>2. Joylashuv ma'lumotlari</h2>
                    <p>FinJob avtomatik joylashuv funksiyasini faqat siz “Joylashuvimni aniqlash” tugmasini bosganingizda ishga tushiradi. Brauzer qurilma joylashuvini olish uchun ruxsat so'raydi.</p>
                    <p>Olingan koordinatalar manzil matniga aylantiriladi va job location maydoniga joylashtiriladi. Siz uni yuborishdan oldin o'zgartirishingiz yoki o'zingiz kiritishingiz mumkin.</p>
                    <p>Manzilni aniqlash jarayonida koordinatalar OpenStreetMap Nominatim geokodlash xizmatiga yuborilishi mumkin. Ushbu xizmatning o'z maxfiylik va foydalanish qoidalari mavjud.</p>

                    <h2>3. Ma'lumotlardan nima uchun foydalanamiz?</h2>
                    <p>Ma'lumotlar hisobni yaratish va boshqarish, email tasdiqlash, joblarni joylashtirish va topish, foydalanuvchilar o'rtasida aloqa, rating va platforma xavfsizligini ta'minlash uchun ishlatiladi.</p>

                    <h2>4. Email va uchinchi tomon xizmatlari</h2>
                    <p>Ro'yxatdan o'tish kodi siz ko'rsatgan email manziliga SMTP orqali yuboriladi. Email manzilingiz va verification xabari email yetkazib berish xizmatidan foydalanish uchun tegishli email provayderiga uzatilishi mumkin.</p>
                    <p>FinJob foydalanuvchi ma'lumotlarini sotmaydi. Ma'lumotlar faqat platforma ishlashi uchun zarur bo'lgan xizmatlar yoki qonunchilik talab qilgan holatlarda uzatiladi.</p>

                    <h2>5. Saqlash va xavfsizlik</h2>
                    <p>FinJob ruxsatsiz kirish, ma'lumotlarni yo'qotish yoki o'zgartirish xavfini kamaytirish uchun texnik choralarni qo'llaydi. Shunga qaramay, internet orqali uzatiladigan hech bir tizim mutlaq xavfsiz deb kafolatlanmaydi.</p>
                    <p>Email verification kodi vaqtincha server xotirasida saqlanadi va tasdiqlash jarayoni tugagach yoki kodning amal qilish muddati tugagach o'chiriladi.</p>

                    <h2>6. Brauzer xotirasi</h2>
                    <p>FinJob sessiya tokeni va ayrim foydalanuvchi ma'lumotlarini brauzerning localStorage xotirasida saqlashi mumkin. Bu klassik brauzer cookie'sidan farq qiladi. Shu sababli FinJob hozircha majburiy reklama tracking cookie'lariga tayanmaydi.</p>

                    <h2>7. Sizning huquqlaringiz</h2>
                    <p>Siz o'zingiz haqingizdagi ma'lumotlarni ko'rish, tuzatish va qonunchilik doirasida o'chirishni so'rash huquqiga egasiz. Shuningdek, avtomatik geolokatsiya ruxsatini brauzer sozlamalaridan boshqarishingiz mumkin.</p>

                    <h2>8. Voyaga yetmaganlar</h2>
                    <p>Platformadan foydalanishdan oldin foydalanuvchi o'z hududidagi yosh va xizmatlardan foydalanish talablariga rioya qilishi kerak. Zarur hollarda voyaga yetmagan foydalanuvchi ota-ona yoki qonuniy vakilining roziligini olishi lozim.</p>

                    <h2>9. Policy o'zgarishlari</h2>
                    <p>Platforma yoki qonunchilikdagi o'zgarishlar sabab ushbu siyosat yangilanishi mumkin. Yangilangan versiya FinJob saytida e'lon qilinadi va kuchga kirish sanasi ko'rsatiladi.</p>

                    <h2>10. Huquqiy asos</h2>
                    <p>Ushbu hujjat umumiy platforma siyosati sifatida tayyorlangan. FinJob faoliyati O'zbekiston Respublikasining amaldagi qonunchiligi, jumladan shaxsiy ma'lumotlar va elektron tijoratga oid talablar bilan uyg'unlashtirilishi kerak.</p>

                    <div className="legal-note">
                        Bu sahifadagi matn umumiy axborot uchun. Platformani real biznes sifatida ishga tushirishdan oldin yurist bilan yakuniy huquqiy tekshiruv o'tkazish tavsiya etiladi.
                    </div>
                </article>
            </div>
        </div>
    )
}

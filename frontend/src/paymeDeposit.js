// Payme wallet top-up helpers used by Profile.jsx. Pure functions (no React, no DOM) so they can be tested with
// `npm test` (node --test). The backend is the only source of truth: nothing here ever marks a payment as paid.

export const DEPOSIT_ID_RE = /^[0-9a-f]{32}$/
export const OPEN_DEPOSIT_STATUSES = ["pending", "processing"]

export const isOpenDeposit = (deposit) =>
    Boolean(deposit) && OPEN_DEPOSIT_STATUSES.includes(deposit.status) && !deposit.under_review

const formatUzs = (value) => Number(value || 0).toLocaleString("uz-UZ")

// api() returns { ...body, ok, status: <HTTP status> }, which hides the deposit's own `status`. The backend repeats it
// as `deposit_status`; restore it here. Failed responses keep `status` = HTTP code (used for 404 handling).
export function normalizeDepositResponse(result) {
    if (!result?.ok) return result
    return { ...result, httpStatus: result.status, status: result.deposit_status }
}

export function validateDepositAmount(raw, config) {
    const text = String(raw ?? "").trim()
    if (!/^\d+$/.test(text)) return { ok: false, error: "Summani butun son (UZS) ko‘rinishida kiriting" }
    const amount = Number(text)
    const min = Number(config?.min_amount) || 1000
    const max = Number(config?.max_amount) || 50000000
    if (!Number.isSafeInteger(amount) || amount < min || amount > max) {
        return { ok: false, error: `Summa ${formatUzs(min)} dan ${formatUzs(max)} UZS gacha bo‘lishi kerak` }
    }
    return { ok: true, amount }
}

// The backend already restricts checkout URLs to Payme; this is a second guard before leaving the site.
export function isSafeCheckoutUrl(value) {
    if (typeof value !== "string") return false
    try {
        const url = new URL(value)
        return url.protocol === "https:" && Boolean(url.hostname) && !url.username && !url.password
    } catch {
        return false
    }
}

// tone: info | success | warning | error  (maps to .profile-deposit-status.<tone>)
export function depositStatusMessage(tracking) {
    if (!tracking) return null
    const { status, amount, under_review: underReview, timedOut, resumed, networkError, message } = tracking
    if (status === "error") return { tone: "error", text: message || "To‘lov holatini tekshirib bo‘lmadi." }
    if (underReview && status !== "credited") {
        return { tone: "warning", text: "To‘lov qo‘shimcha tekshiruvga yuborildi. Mablag‘ hali hamyonga qo‘shilmagan; administrator ko‘rib chiqqach holat yangilanadi." }
    }
    if (networkError && OPEN_DEPOSIT_STATUSES.includes(status)) {
        return { tone: "warning", text: "Server bilan aloqa uzildi. To‘lov holatini tekshirish uchun “Holatni yangilash” tugmasini bosing." }
    }
    switch (status) {
        case "credited":
            return { tone: "success", text: `To‘lov tasdiqlandi: ${formatUzs(amount)} UZS hamyoningizga qo‘shildi.` }
        case "pending":
        case "processing":
            if (resumed) return { tone: "info", text: `Sizda tugallanmagan ${formatUzs(amount)} UZS lik Payme to‘lovi bor. Uni davom ettirishingiz mumkin; bekor qilgan bo‘lsangiz, buyurtma muddati tugagach avtomatik yopiladi.` }
            if (timedOut) return { tone: "warning", text: "Payme tasdig‘i kechikmoqda. To‘lov tasdiqlansa, hamyon avtomatik to‘ldiriladi. Holatni keyinroq yangilang." }
            return {
                tone: "info",
                text: status === "processing"
                    ? "Payme to‘lovni qayta ishlamoqda. Hamyon faqat tasdiqdan keyin to‘ldiriladi."
                    : "To‘lov Payme tomonidan tasdiqlanishi kutilmoqda. Hamyon faqat tasdiqdan keyin to‘ldiriladi.",
            }
        case "declined":
            return { tone: "error", text: "To‘lov rad etildi. Hamyoningiz to‘ldirilmadi." }
        case "expired":
            return { tone: "error", text: "To‘lov muddati tugadi. Hamyoningiz to‘ldirilmadi." }
        case "cancelled":
            return { tone: "error", text: "To‘lov bekor qilindi. Hamyoningiz to‘ldirilmadi." }
        case "failed":
            return { tone: "error", text: "To‘lovni boshlab bo‘lmadi. Hamyoningiz to‘ldirilmadi." }
        case "reversed":
            return { tone: "warning", text: "To‘lov Payme tomonidan qaytarildi. Savollar bo‘lsa, administrator bilan bog‘laning." }
        default:
            return { tone: "info", text: "To‘lov holati tekshirilmoqda..." }
    }
}

// Most recent deposit the user left unfinished (e.g. closed the Payme tab), if it can still be paid.
export function pickResumableDeposit(deposits, now = Date.now()) {
    if (!Array.isArray(deposits)) return null
    return deposits.find((deposit) => {
        if (!isOpenDeposit(deposit) || !DEPOSIT_ID_RE.test(String(deposit.deposit_id || ""))) return false
        const expires = Date.parse(deposit.expires_at || "")
        return Number.isFinite(expires) && expires > now
    }) || null
}

const defaultWait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// Polls GET /wallet/deposits/<id> until the backend reports a final state. Returns the reason it stopped:
// "final" | "under_review" | "timeout" | "network_error" | "not_found" | "cancelled".
export async function trackDeposit({
    depositId,
    fetchStatus,
    onUpdate,
    wait = defaultWait,
    isCancelled = () => false,
    maxAttempts = 40,
    intervalMs = 3000,
    slowIntervalMs = 10000,
    maxNetworkErrors = 4,
}) {
    let attempts = 0
    let networkErrors = 0
    let last = null
    while (!isCancelled()) {
        const result = await fetchStatus(depositId)
        if (isCancelled()) return "cancelled"
        attempts += 1
        if (!result?.ok) {
            if (result?.status === 404) {
                onUpdate({ status: "error", message: result?.msg || "To‘ldirish topilmadi." })
                return "not_found"
            }
            networkErrors += 1
            if (last) onUpdate({ ...last, networkError: true })
            else onUpdate({ status: "error", message: result?.msg || "To‘lov holatini tekshirib bo‘lmadi." })
            if (networkErrors >= maxNetworkErrors || attempts >= maxAttempts) return "network_error"
        } else {
            networkErrors = 0
            last = { ...result, networkError: false }
            if (result.under_review) { onUpdate(last); return "under_review" }
            if (!OPEN_DEPOSIT_STATUSES.includes(result.status)) { onUpdate(last); return "final" }
            if (attempts >= maxAttempts) { onUpdate({ ...last, timedOut: true }); return "timeout" }
            onUpdate(last)
        }
        await wait(attempts <= 20 ? intervalMs : slowIntervalMs)
    }
    return "cancelled"
}

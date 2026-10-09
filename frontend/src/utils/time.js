export function formatTimeAgo(value) {
    if (!value) return "Vaqt noma'lum"

    const date = new Date(String(value).replace(" ", "T"))
    if (Number.isNaN(date.getTime())) return "Vaqt noma'lum"

    const diffMs = Date.now() - date.getTime()
    const seconds = Math.floor(Math.abs(diffMs) / 1000)
    const future = diffMs < 0

    if (seconds < 45) return future ? "Hozir" : "Hozirgina"

    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) {
        return future ? `${minutes} daqiqadan so‘ng` : `${minutes} daqiqa oldin`
    }

    const hours = Math.floor(minutes / 60)
    if (hours < 24) {
        return future ? `${hours} soatdan so‘ng` : `${hours} soat oldin`
    }

    const days = Math.floor(hours / 24)
    if (days < 7) {
        return future ? `${days} kundan so‘ng` : `${days} kun oldin`
    }

    const weeks = Math.floor(days / 7)
    if (days < 35) {
        return future ? `${weeks} haftadan so‘ng` : `${weeks} hafta oldin`
    }

    const months = Math.floor(days / 30.4375)
    if (days < 365) {
        return future ? `${months} oydan so‘ng` : `${months} oy oldin`
    }

    const years = Math.floor(days / 365.25)
    return future ? `${years} yildan so‘ng` : `${years} yil oldin`
}

export function formatRelativeDay(value) {
    if (!value) return "Sana noma'lum"

    const date = new Date(String(value).replace(" ", "T"))
    if (Number.isNaN(date.getTime())) return "Sana noma'lum"

    const startOfToday = new Date()
    startOfToday.setHours(0, 0, 0, 0)
    const startOfDate = new Date(date)
    startOfDate.setHours(0, 0, 0, 0)
    const dayDifference = Math.round((startOfToday.getTime() - startOfDate.getTime()) / 86400000)

    if (dayDifference === 0) return "Bugun"
    if (dayDifference === 1) return "Kecha"
    if (dayDifference === -1) return "Ertaga"
    return formatTimeAgo(value)
}

export function getMessageDateKey(value) {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ""
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, "0")
    const day = String(date.getDate()).padStart(2, "0")
    return `${year}-${month}-${day}`
}

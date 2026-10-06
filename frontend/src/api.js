const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:5000"

export async function api(path, { method = "GET", body = null, token = "", signal } = {}) {
    try {
        const response = await fetch(API_BASE + path, {
            method,
            headers: {
                ...(body ? { "Content-Type": "application/json" } : {}),
                ...(token ? { Authorization: `Bearer ${token}` } : {})
            },
            body: body ? JSON.stringify(body) : null,
            signal
        })

        const text = await response.text()
        let data = {}

        try {
            data = text ? JSON.parse(text) : {}
        } catch {
            data = { msg: text || "Serverdan noto'g'ri javob keldi." }
        }

        if (response.status === 401 && token) {
            localStorage.removeItem("token")
            localStorage.removeItem("user")
        }

        if (!response.ok) {
            return {
                ...data,
                ok: false,
                status: response.status,
                msg: data?.msg || `Server xatosi (${response.status})`
            }
        }

        if (Array.isArray(data)) {
            data.ok = true
            data.status = response.status
            return data
        }

        return { ...data, ok: true, status: response.status }
    } catch (error) {
        if (error?.name === "AbortError") {
            return { ok: false, msg: "So'rov bekor qilindi." }
        }
        return { ok: false, msg: "Server bilan bog'lanib bo'lmadi. Backend ishlayotganini tekshiring." }
    }
}
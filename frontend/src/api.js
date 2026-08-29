const API_BASE = "http://localhost:5000"

export async function api(path, { method = "GET", body = null, token = "" } = {}) {
    const response = await fetch(API_BASE + path, {
        method,
        headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: body ? JSON.stringify(body) : null
    })

    const text = await response.text()

    try {
        return text ? JSON.parse(text) : {}
    } catch {
        return { msg: text }
    }
}
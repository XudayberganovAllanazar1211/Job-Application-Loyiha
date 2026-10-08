import { useEffect, useRef, useState } from "react"

const GOOGLE_SCRIPT_ID = "google-identity-services"

export default function GoogleAuthButton({ onSuccess, disabled = false }) {
    const buttonRef = useRef(null)
    const [error, setError] = useState("")
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID

    useEffect(() => {
        if (!clientId || disabled) return

        const render = () => {
            if (!window.google?.accounts?.id || !buttonRef.current) return
            buttonRef.current.innerHTML = ""
            window.google.accounts.id.initialize({
                client_id: clientId,
                callback: (response) => {
                    if (response?.credential) onSuccess(response.credential)
                },
                ux_mode: "popup"
            })
            window.google.accounts.id.renderButton(buttonRef.current, {
                type: "standard",
                theme: "outline",
                size: "large",
                shape: "rectangular",
                text: "continue_with",
                width: 360
            })
        }

        const existing = document.getElementById(GOOGLE_SCRIPT_ID)
        if (existing) {
            if (window.google?.accounts?.id) {
                render()
            } else {
                existing.addEventListener("load", render, { once: true })
            }
            return
        }

        const script = document.createElement("script")
        script.id = GOOGLE_SCRIPT_ID
        script.src = "https://accounts.google.com/gsi/client"
        script.async = true
        script.defer = true
        script.onload = render
        script.onerror = () => setError("Google login oynasini yuklab bo‘lmadi.")
        document.head.appendChild(script)
    }, [clientId, disabled, onSuccess])

    if (!clientId) {
        return (
            <div className="notice warn" style={{ marginTop: 12 }}>
                Google login uchun <strong>VITE_GOOGLE_CLIENT_ID</strong> sozlanishi kerak.
            </div>
        )
    }

    return (
        <div style={{ marginTop: 12 }}>
            <div ref={buttonRef} style={{ minHeight: 44, display: "flex", justifyContent: "center" }} />
            {error && <div className="notice warn" style={{ marginTop: 8 }}>{error}</div>}
        </div>
    )
}

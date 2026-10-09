import { useNavigate } from "react-router-dom"

const VERIFICATION_ITEMS = [
    {
        key: "email_verified",
        label: "Email manzili",
        description: "Elektron pochta manzili tasdiqlangan.",
        pendingDescription: "Email tasdiqlangani haqida ma’lumot yo‘q."
    },
    {
        key: "phone_verified",
        label: "Telefon raqami",
        description: "Telefon raqami tekshirilib tasdiqlangan.",
        pendingDescription: "Telefon raqami hali tasdiqlanmagan.",
        destination: "/verification?type=phone"
    },
    {
        key: "identity_verified",
        label: "Shaxsni tasdiqlash",
        description: "Shaxsni tasdiqlash tekshiruvi yakunlangan.",
        pendingDescription: "Shaxsni tasdiqlash hali yakunlanmagan.",
        destination: "/verification?type=identity"
    }
]

export default function VerificationBadges({ verification, interactive = false }) {
    const navigate = useNavigate()

    return (
        <div className="verification-badge-grid">
            {VERIFICATION_ITEMS.map((item) => {
                const verified = Boolean(verification?.[item.key])
                const clickable = interactive && Boolean(item.destination)
                const content = (
                    <>
                        <span className="verification-badge-icon" aria-hidden="true">
                            {verified ? "✓" : "—"}
                        </span>
                        <span className="verification-badge-copy">
                            <strong>{item.label}</strong>
                            <span>{verified ? item.description : item.pendingDescription}</span>
                        </span>
                        <span className="verification-badge-status">
                            {verified ? "Tasdiqlangan" : "Tasdiqlanmagan"}
                        </span>
                        {clickable && <span className="verification-badge-action">{verified ? "Holatni ko‘rish →" : "Tasdiqlash →"}</span>}
                    </>
                )

                return clickable ? (
                    <button
                        key={item.key}
                        type="button"
                        className={verified ? "verification-badge-card is-verified is-clickable" : "verification-badge-card is-clickable"}
                        onClick={() => navigate(item.destination)}
                        aria-label={`${item.label}: tasdiqlash menyusini ochish`}
                    >
                        {content}
                    </button>
                ) : (
                    <div
                        key={item.key}
                        className={verified ? "verification-badge-card is-verified" : "verification-badge-card"}
                    >
                        {content}
                    </div>
                )
            })}
        </div>
    )
}

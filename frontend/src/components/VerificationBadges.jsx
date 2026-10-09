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
        pendingDescription: "Telefon raqami hali tasdiqlanmagan."
    },
    {
        key: "identity_verified",
        label: "Shaxsni tasdiqlash",
        description: "Shaxsni tasdiqlash tekshiruvi yakunlangan.",
        pendingDescription: "Shaxsni tasdiqlash hali yakunlanmagan."
    }
]

export default function VerificationBadges({ verification }) {
    return (
        <div className="verification-badge-grid">
            {VERIFICATION_ITEMS.map((item) => {
                const verified = Boolean(verification?.[item.key])
                return (
                    <div
                        key={item.key}
                        className={verified ? "verification-badge-card is-verified" : "verification-badge-card"}
                    >
                        <span className="verification-badge-icon" aria-hidden="true">
                            {verified ? "✓" : "—"}
                        </span>
                        <div className="verification-badge-copy">
                            <strong>{item.label}</strong>
                            <span>{verified ? item.description : item.pendingDescription}</span>
                        </div>
                        <span className="verification-badge-status">
                            {verified ? "Tasdiqlangan" : "Tasdiqlanmagan"}
                        </span>
                    </div>
                )
            })}
        </div>
    )
}

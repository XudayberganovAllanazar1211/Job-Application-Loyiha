// Run with: npm test   (Node's built-in test runner; no extra dependencies)
import test from "node:test"
import assert from "node:assert/strict"
import {
    depositStatusMessage,
    isOpenDeposit,
    isSafeCheckoutUrl,
    normalizeDepositResponse,
    pickResumableDeposit,
    trackDeposit,
    validateDepositAmount,
} from "./paymeDeposit.js"

const config = { min_amount: 1000, max_amount: 50000000 }
const ID = "a".repeat(32)

test("amount validation: whole UZS within the configured limits only", () => {
    assert.deepEqual(validateDepositAmount("100000", config), { ok: true, amount: 100000 })
    assert.deepEqual(validateDepositAmount(" 1000 ", config), { ok: true, amount: 1000 })
    for (const bad of ["", "abc", "12.5", "1e6", "-1000", "999", "50000001", null, undefined, "99999999999999999999"]) {
        assert.equal(validateDepositAmount(bad, config).ok, false, String(bad))
    }
    assert.match(validateDepositAmount("10", config).error, /1.?000/)
})

test("checkout redirect only to https URLs without credentials", () => {
    assert.equal(isSafeCheckoutUrl("https://checkout.payme.uz/abc?x=1"), true)
    for (const bad of ["http://checkout.payme.uz/abc", "javascript:alert(1)", "https://user:pw@payme.uz/", "//payme.uz", "", null, 42]) {
        assert.equal(isSafeCheckoutUrl(bad), false, String(bad))
    }
})

test("success is only shown for backend-confirmed credited status", () => {
    assert.equal(depositStatusMessage({ status: "credited", amount: 250000 }).tone, "success")
    for (const status of ["pending", "processing"]) {
        const msg = depositStatusMessage({ status, amount: 250000 })
        assert.equal(msg.tone, "info")
        assert.doesNotMatch(msg.text, /tasdiqlandi/)
    }
    for (const status of ["declined", "expired", "cancelled", "failed"]) {
        assert.equal(depositStatusMessage({ status }).tone, "error", status)
    }
    assert.equal(depositStatusMessage({ status: "reversed" }).tone, "warning")
    assert.equal(depositStatusMessage({ status: "pending", under_review: true }).tone, "warning")
    assert.equal(depositStatusMessage({ status: "pending", timedOut: true }).tone, "warning")
    assert.equal(depositStatusMessage({ status: "processing", networkError: true }).tone, "warning")
    assert.match(depositStatusMessage({ status: "pending", resumed: true, amount: 5000 }).text, /tugallanmagan/)
    // a resumed deposit is checked once (maxAttempts 1 => timedOut): it must still read as "unfinished", not "delayed"
    assert.match(depositStatusMessage({ status: "pending", resumed: true, timedOut: true }).text, /tugallanmagan/)
    assert.equal(depositStatusMessage({ status: "error", message: "x" }).text, "x")
    assert.equal(depositStatusMessage(null), null)
})

test("resumable deposit: newest open, unexpired, not under review", () => {
    const now = Date.parse("2026-11-25T12:00:00Z")
    const later = "2026-11-25T13:00:00+00:00"
    const earlier = "2026-11-25T11:00:00+00:00"
    const list = [
        { deposit_id: "b".repeat(32), status: "credited", expires_at: later },
        { deposit_id: "c".repeat(32), status: "pending", expires_at: earlier },
        { deposit_id: "d".repeat(32), status: "pending", expires_at: later, under_review: true },
        { deposit_id: "e".repeat(32), status: "processing", expires_at: later },
        { deposit_id: "f".repeat(32), status: "pending", expires_at: later },
    ]
    assert.equal(pickResumableDeposit(list, now).deposit_id, "e".repeat(32))
    assert.equal(pickResumableDeposit([], now), null)
    assert.equal(pickResumableDeposit(null, now), null)
    assert.equal(isOpenDeposit({ status: "pending", under_review: true }), false)
})

test("api() response: deposit status is restored from deposit_status (api() overwrites status with HTTP code)", () => {
    // exactly what src/api.js returns for GET /wallet/deposits/<id>
    const apiShaped = { deposit_id: ID, status: 200, deposit_status: "credited", amount: 1000, ok: true }
    const normalized = normalizeDepositResponse(apiShaped)
    assert.equal(normalized.status, "credited")
    assert.equal(normalized.httpStatus, 200)
    assert.equal(depositStatusMessage(normalized).tone, "success")
    assert.notEqual(depositStatusMessage(apiShaped).tone, "success") // the raw api() shape must never read as success
    const notFound = { ok: false, status: 404, msg: "nf" }
    assert.equal(normalizeDepositResponse(notFound), notFound)
})

const noWait = async () => {}

test("polling: pending -> processing -> credited stops at the confirmed status", async () => {
    const answers = [
        { ok: true, status: "pending", amount: 1000 },
        { ok: true, status: "processing", amount: 1000 },
        { ok: true, status: "credited", amount: 1000 },
    ]
    const updates = []
    const reason = await trackDeposit({ depositId: ID, fetchStatus: async () => answers.shift(), onUpdate: (u) => updates.push(u.status), wait: noWait })
    assert.equal(reason, "final")
    assert.deepEqual(updates, ["pending", "processing", "credited"])
})

test("polling: declined is final and never reported as success", async () => {
    const updates = []
    const reason = await trackDeposit({ depositId: ID, fetchStatus: async () => ({ ok: true, status: "declined" }), onUpdate: (u) => updates.push(u), wait: noWait })
    assert.equal(reason, "final")
    assert.equal(depositStatusMessage(updates.at(-1)).tone, "error")
})

test("polling: callback delay ends in a timeout state, not a guess", async () => {
    const updates = []
    const waits = []
    const reason = await trackDeposit({
        depositId: ID, maxAttempts: 25, fetchStatus: async () => ({ ok: true, status: "pending" }),
        onUpdate: (u) => updates.push(u), wait: async (ms) => { waits.push(ms) },
    })
    assert.equal(reason, "timeout")
    assert.equal(updates.at(-1).timedOut, true)
    assert.equal(updates.at(-1).status, "pending")
    assert.equal(waits[0], 3000)
    assert.equal(waits.at(-1), 10000) // backs off after 20 attempts
})

test("polling: temporary network failures are retried, then reported", async () => {
    const answers = [{ ok: true, status: "pending" }, { ok: false, msg: "net" }, { ok: true, status: "credited", amount: 5 }]
    const updates = []
    assert.equal(await trackDeposit({ depositId: ID, fetchStatus: async () => answers.shift(), onUpdate: (u) => updates.push(u), wait: noWait }), "final")
    assert.equal(updates[1].networkError, true)
    assert.equal(updates.at(-1).status, "credited")

    const failing = []
    const reason = await trackDeposit({ depositId: ID, fetchStatus: async () => ({ ok: false, msg: "down" }), onUpdate: (u) => failing.push(u), wait: noWait, maxNetworkErrors: 3 })
    assert.equal(reason, "network_error")
    assert.equal(failing.length, 3)
    assert.equal(failing[0].status, "error")
})

test("polling: unknown deposit and under-review deposit stop immediately", async () => {
    assert.equal(await trackDeposit({ depositId: ID, fetchStatus: async () => ({ ok: false, status: 404, msg: "nf" }), onUpdate: () => {}, wait: noWait }), "not_found")
    assert.equal(await trackDeposit({ depositId: ID, fetchStatus: async () => ({ ok: true, status: "pending", under_review: true }), onUpdate: () => {}, wait: noWait }), "under_review")
})

test("polling: cancellation stops without further updates", async () => {
    let cancelled = false
    const updates = []
    const reason = await trackDeposit({
        depositId: ID, fetchStatus: async () => { cancelled = true; return { ok: true, status: "pending" } },
        onUpdate: (u) => updates.push(u), wait: noWait, isCancelled: () => cancelled,
    })
    assert.equal(reason, "cancelled")
    assert.equal(updates.length, 0)
})

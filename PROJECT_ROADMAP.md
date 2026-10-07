# FinJob Development Roadmap

This roadmap is the working priority for the FinJob project.

**Regression rule:** After every phase, run the full Phase 0 stabilization/testing pass before starting the next phase. This applies to Phase 1 through Phase 10.

## Phase 0 — Stabilization
- Run and expand backend automated tests.
- Verify frontend lint and production build.
- Verify registration, login/logout, job creation/acceptance, payment, finish, rating, notifications, withdrawal, reports/refunds, and admin flows.
- Fix schema/migration inconsistencies and endpoint/test mismatches.
- Keep CI enabled on the development branch.
- Do not modify `main` unless explicitly requested.

## Phase 1 — Marketplace
Status: implemented and regression-tested.
- Proposal/offer system.
- Worker price/deadline proposals.
- Client proposal comparison and selection.
- Accept/reject proposal lifecycle.

## Phase 2 — Search & Discovery
Status: implemented and regression-tested.
- Strong job/service search.
- Category/subcategory filters.
- Price, rating, location, status filters.
- Sorting, favorites, saved searches, recently viewed.
- Recommendations.

## Phase 3 — Professional Profiles
Status: implemented and regression-tested.
- Portfolio.
- Work history.
- Completed-job statistics.
- Success rate and response metrics.
- Verification and badges.
- Better public freelancer profiles.

## Phase 4 — Communication 2.0
Status: implemented and regression-tested.
- Better conversation list and unread counts.
- Online/offline and typing status.
- Attachments.
- Message management/reporting.
- Later: WebSocket real-time chat.

## Phase 5 — Payments 2.0
- Production payment integration.
- Strong webhook/idempotency handling.
- Withdrawal workflow and admin approval.
- Receipts/invoices.
- Finance analytics.
- Harden escrow/release/refund edge cases.

## Phase 6 — Trust & Safety
- User verification.
- Blocking.
- Anti-spam and anti-fraud.
- Dispute center.
- Moderation tooling.

## Phase 7 — Recommendation
- Personalized jobs for workers.
- Personalized workers/services for clients.
- Ranking/recommendation algorithms.

## Phase 8 — Admin 2.0
- Rich analytics dashboard.
- Revenue/commission trends.
- User/job/service growth metrics.
- Operational monitoring.

## Phase 9 — Growth
- Featured services.
- Promoted jobs.
- Levels, badges, achievements.
- Referral system.
- Promo codes and discounts.
- Announcements and marketing/SEO.

## Phase 10 — Production
- PostgreSQL.
- Redis/background jobs.
- Logging/monitoring/error tracking.
- Automated backups.
- CI/CD.
- HTTPS, domain, CDN/object storage.
- Staging and production deployment.

import os
import unittest
from io import BytesIO
from main import app, DB, pending_verifications
import main

class JobPlatformTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db_name = "test_app.db"
        cls.original_db = main.db
        cls.original_db_name = cls.original_db.db_name
        if os.path.exists(cls.test_db_name):
            os.remove(cls.test_db_name)
        DB(cls.test_db_name)
        cls.original_db.db_name = cls.test_db_name
        main.db = cls.original_db
        cls.original_send_email_code = main.send_email_code
        main.send_email_code = lambda to_email, code: True
        app.config["TESTING"] = True
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.original_db.db_name = cls.original_db_name
        main.send_email_code = cls.original_send_email_code
        if os.path.exists(cls.test_db_name):
            try:
                os.remove(cls.test_db_name)
            except Exception:
                pass

    def setUp(self):
        # Testlar bir-birining rate-limit holatiga ta’sir qilmasin.
        with main._rate_lock:
            main._rate_buckets.clear()

    def test_01_registration_flow(self):
        # 1. Send code
        payload = {
            "username": "tester_creator",
            "password": "Password123!",
            "first_name": "John",
            "last_name": "Doe",
            "birthday": "2000-01-01",
            "email": "tester_creator@example.com"
        }
        res = self.client.post("/register/send-code", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("msg"), "ok")

        # Check code stored in pending_verifications
        email_key = "tester_creator@example.com"
        self.assertIn(email_key, pending_verifications)
        code = pending_verifications[email_key]["code"]

        # 2. Verify with wrong code
        res_wrong = self.client.post("/register/verify", json={"email": email_key, "code": "000000"})
        self.assertEqual(res_wrong.status_code, 400)

        # 3. Verify with correct code
        res_verify = self.client.post("/register/verify", json={"email": email_key, "code": code})
        self.assertEqual(res_verify.status_code, 200)
        self.assertEqual(res_verify.get_json().get("role"), "user")

    def test_02_login_and_profile(self):
        # Login with username
        res = self.client.post("/login", json={"username": "tester_creator", "password": "Password123!"})
        self.assertEqual(res.status_code, 200)
        token = res.get_json().get("token")
        self.assertTrue(bool(token))

        # Login with email
        res_email = self.client.post("/login", json={"username": "tester_creator@example.com", "password": "Password123!"})
        self.assertEqual(res_email.status_code, 200)

        # Get Profile
        res_prof = self.client.get("/profile", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_prof.status_code, 200)
        prof_data = res_prof.get_json()
        self.assertEqual(prof_data["username"], "tester_creator")
        self.assertEqual(prof_data["email"], "tester_creator@example.com")
        self.assertEqual(prof_data["role"], "user")

        main.db.q("UPDATE users SET role='admin' WHERE username=?", ("tester_creator",)).close()
        self.assertIn("skills", prof_data)
        self.assertIn("bio", prof_data)

        # Update Profile
        res_put = self.client.put(
            "/profile",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "first_name": "John Updated",
                "last_name": "Doe Updated",
                "birthday": "2000-01-01",
                "username": "tester_creator",
                "email": "tester_creator@example.com",
                "bio": "Senior Python Developer",
                "skills": "Python, React, SQLite"
            }
        )
        self.assertEqual(res_put.status_code, 200)

    def test_03_services_and_job_creation(self):
        # Login creator
        res = self.client.post("/login", json={"username": "tester_creator", "password": "Password123!"})
        token_creator = res.get_json().get("token")

        # Get Services
        res_serv = self.client.get("/services")
        self.assertEqual(res_serv.status_code, 200)
        services = res_serv.get_json()
        self.assertTrue(len(services) > 0)
        parent_ids = {service["parent_id"] for service in services if service["parent_id"] is not None}
        leaf_services = [service for service in services if service["id"] not in parent_ids]
        self.assertGreaterEqual(len(leaf_services), 2)

        service_ids = [leaf_services[0]["id"], leaf_services[1]["id"]]

        # Create Job with multiple services
        job_payload = {
            "service_id": service_ids[0],
            "service_ids": service_ids,
            "title": "Fix Water Pipe",
            "description": "Bathroom pipe is leaking urgently",
            "price": 150000,
            "location": "Tashkent, Chilonzor"
        }
        res_job = self.client.post("/job", headers={"Authorization": f"Bearer {token_creator}"}, json=job_payload)
        self.assertEqual(res_job.status_code, 200)

        # Get jobs
        res_jobs = self.client.get("/jobs", headers={"Authorization": f"Bearer {token_creator}"})
        self.assertEqual(res_jobs.status_code, 200)
        jobs = res_jobs.get_json()
        created = [j for j in jobs if j["title"] == "Fix Water Pipe"][0]
        self.assertEqual(created["currency"], "UZS")
        self.assertEqual(created["status"], "active")
        self.assertEqual(created["worker_id"], None)
        self.assertIn(leaf_services[0]["name"], created["service_name"])
        self.assertIn(leaf_services[1]["name"], created["service_name"])

        # Create a custom-only service containing a comma.
        custom_job = self.client.post(
            "/job",
            headers={"Authorization": f"Bearer {token_creator}"},
            json={
                "service_ids": [],
                "custom_services": ["Custom Design, Advanced"],
                "title": "Custom Service Job",
                "description": "Checks structured custom service handling",
                "price": 250000,
                "location": "Remote"
            }
        )
        self.assertEqual(custom_job.status_code, 200)

        custom_jobs = self.client.get(
            "/jobs",
            headers={"Authorization": f"Bearer {token_creator}"}
        ).get_json()
        custom_created = [j for j in custom_jobs if j["title"] == "Custom Service Job"][0]
        self.assertEqual(custom_created["service_name"], "Custom Design, Advanced")

    def test_055_proposal_flow(self):
        owner_login = self.client.post(
            "/login",
            json={"username": "tester_creator", "password": "Password123!"}
        )
        worker_login = self.client.post(
            "/login",
            json={"username": "tester_worker", "password": "Password123!"}
        )
        self.assertEqual(owner_login.status_code, 200)
        self.assertEqual(worker_login.status_code, 200)
        owner_token = owner_login.get_json()["token"]
        worker_token = worker_login.get_json()["token"]

        created = self.client.post(
            "/job",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "service_id": 1,
                "title": "Proposal Flow Check",
                "description": "Verify worker proposals before assignment.",
                "price": 900000,
                "location": "Remote"
            }
        )
        self.assertEqual(created.status_code, 200)
        jobs = self.client.get("/jobs", headers={"Authorization": f"Bearer {owner_token}"}).get_json()
        job = [item for item in jobs if item["title"] == "Proposal Flow Check"][0]
        job_id = job["id"]
        self.assertEqual(job["status"], "active")
        self.assertEqual(job["proposal_count"], 0)

        proposal = self.client.post(
            f"/jobs/{job_id}/proposals",
            headers={"Authorization": f"Bearer {worker_token}"},
            json={
                "price": 750000,
                "deadline": "2026-10-20",
                "message": "I can complete this within the requested period."
            }
        )
        self.assertEqual(proposal.status_code, 201)

        proposal_id = proposal.get_json()["proposal_id"]
        edited = self.client.patch(
            f"/proposals/{proposal_id}",
            headers={"Authorization": f"Bearer {worker_token}"},
            json={
                "action": "edit",
                "price": 700000,
                "deadline": "2026-10-22",
                "message": "Updated offer with an earlier delivery date."
            }
        )
        self.assertEqual(edited.status_code, 200)

        owner_proposals = self.client.get(
            f"/jobs/{job_id}/proposals",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        self.assertEqual(owner_proposals.status_code, 200)
        proposal_items = owner_proposals.get_json()
        self.assertEqual(len(proposal_items), 1)
        self.assertEqual(proposal_items[0]["price"], 700000.0)
        self.assertEqual(proposal_items[0]["deadline"], "2026-10-22")
        self.assertEqual(proposal_items[0]["message"], "Updated offer with an earlier delivery date.")
        proposal_id = proposal_items[0]["id"]

        accepted = self.client.patch(
            f"/proposals/{proposal_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"action": "accept"}
        )
        self.assertEqual(accepted.status_code, 200)

        detail = self.client.get(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        self.assertEqual(detail.status_code, 200)
        detail_data = detail.get_json()
        self.assertEqual(detail_data["worker_id"], self.client.get(
            "/profile", headers={"Authorization": f"Bearer {worker_token}"}
        ).get_json()["id"])
        self.assertEqual(detail_data["price"], 700000.0)
        self.assertEqual(detail_data["status"], "payment_pending")

    def test_04_full_lifecycle_and_rating(self):
        # Register worker (Second user -> regular 'user' role)
        res_reg = self.client.post("/register/send-code", json={
            "username": "tester_worker",
            "password": "Password123!",
            "first_name": "Alex",
            "last_name": "Worker",
            "birthday": "1995-05-05",
            "email": "tester_worker@example.com"
        })
        self.assertEqual(res_reg.status_code, 200)
        code = pending_verifications["tester_worker@example.com"]["code"]
        res_verify_w = self.client.post("/register/verify", json={"email": "tester_worker@example.com", "code": code})
        self.assertEqual(res_verify_w.get_json().get("role"), "user")

        # Login both
        res_c = self.client.post("/login", json={"username": "tester_creator", "password": "Password123!"})
        token_creator = res_c.get_json()["token"]

        res_w = self.client.post("/login", json={"username": "tester_worker", "password": "Password123!"})
        token_worker = res_w.get_json()["token"]

        # Creator profile to get creator ID
        prof_c = self.client.get("/profile", headers={"Authorization": f"Bearer {token_creator}"}).get_json()
        creator_id = prof_c["id"]

        prof_w = self.client.get("/profile", headers={"Authorization": f"Bearer {token_worker}"}).get_json()
        worker_id = prof_w["id"]

        # Create Job
        self.client.post("/job", headers={"Authorization": f"Bearer {token_creator}"}, json={
            "service_id": 1,
            "title": "Build Web App",
            "description": "Build fullstack web app",
            "price": 5000000,
            "location": "Remote"
        })
        jobs = self.client.get("/jobs", headers={"Authorization": f"Bearer {token_creator}"}).get_json()
        created_job = [j for j in jobs if j["title"] == "Build Web App"][0]
        job_id = created_job["id"]

        # Test self-accept prevention
        res_self_accept = self.client.post("/accept_job", headers={"Authorization": f"Bearer {token_creator}"}, json={"job_id": job_id})
        self.assertEqual(res_self_accept.status_code, 400)

        # Worker accepts job
        res_accept = self.client.post("/accept_job", headers={"Authorization": f"Bearer {token_worker}"}, json={"job_id": job_id})
        self.assertEqual(res_accept.status_code, 200)

        # Double accept should fail
        res_double = self.client.post("/accept_job", headers={"Authorization": f"Bearer {token_worker}"}, json={"job_id": job_id})
        self.assertEqual(res_double.status_code, 409)

        # Send Message
        res_msg = self.client.post("/message", headers={"Authorization": f"Bearer {token_creator}"}, json={
            "job_id": job_id,
            "message": "Hello, welcome aboard!"
        })
        self.assertEqual(res_msg.status_code, 200)

        # Worker reads message
        res_get_msg = self.client.get(f"/messages/{job_id}", headers={"Authorization": f"Bearer {token_worker}"})
        self.assertEqual(res_get_msg.status_code, 200)
        msgs = res_get_msg.get_json()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["message"], "Hello, welcome aboard!")

        # Single job detail endpoint
        res_detail = self.client.get(f"/jobs/{job_id}", headers={"Authorization": f"Bearer {token_worker}"})
        self.assertEqual(res_detail.status_code, 200)
        detail = res_detail.get_json()
        self.assertEqual(detail["id"], job_id)
        self.assertEqual(detail["worker_id"], worker_id)

        main.db.q("UPDATE users SET balance=10000000 WHERE id=?", (creator_id,)).close()
        res_pay = self.client.post(f"/payments/dummy/{job_id}", headers={"Authorization": f"Bearer {token_creator}"})
        self.assertEqual(res_pay.status_code, 200)
        self.assertEqual(res_pay.get_json()["status"], "held")

        # Creator requests finish
        res_fin = self.client.post("/finish_job", headers={"Authorization": f"Bearer {token_creator}"}, json={"job_id": job_id})
        self.assertEqual(res_fin.status_code, 200)
        self.assertFalse(res_fin.get_json()["finished"])

        # Worker confirms finish
        res_conf = self.client.post("/finish_job", headers={"Authorization": f"Bearer {token_worker}"}, json={
            "job_id": job_id
        })
        self.assertEqual(res_conf.status_code, 200)
        self.assertTrue(res_conf.get_json()["finished"])

        # Finished jobs remain visible to participants
        creator_jobs = self.client.get(
            "/jobs",
            headers={"Authorization": f"Bearer {token_creator}"}
        ).get_json()
        worker_jobs = self.client.get(
            "/jobs",
            headers={"Authorization": f"Bearer {token_worker}"}
        ).get_json()

        self.assertTrue(any(j["id"] == job_id and j["status"] == "finished" for j in creator_jobs))
        self.assertTrue(any(j["id"] == job_id and j["status"] == "finished" for j in worker_jobs))

        # Creator rates worker
        res_rate = self.client.post("/rating", headers={"Authorization": f"Bearer {token_creator}"}, json={
            "job_id": job_id,
            "to_user": worker_id,
            "score": 10,
            "comment": "Outstanding work! Very fast and clean."
        })
        self.assertEqual(res_rate.status_code, 200)
        self.assertEqual(res_rate.get_json()["msg"], "ok")

        # Check worker updated rating & completed jobs count in profile
        updated_w = self.client.get("/profile", headers={"Authorization": f"Bearer {token_worker}"}).get_json()
        self.assertEqual(updated_w["avg_rating"], 10.0)
        self.assertGreaterEqual(updated_w["completed_jobs_count"], 1)

        # Check leaderboard
        res_lead = self.client.get("/leaderboard", headers={"Authorization": f"Bearer {token_creator}"})
        self.assertEqual(res_lead.status_code, 200)
        lead_data = res_lead.get_json()
        self.assertIn("creators", lead_data)
        self.assertIn("workers", lead_data)
        self.assertTrue(any(w["id"] == worker_id for w in lead_data["workers"]))

    def test_05_rbac_admin_authorization(self):
        # Login non-admin worker
        res_w = self.client.post("/login", json={"username": "tester_worker", "password": "Password123!"})
        token_worker = res_w.get_json()["token"]

        # Non-admin attempts to add service -> 403 Forbidden
        res_fail = self.client.post(
            "/admin/service",
            headers={"Authorization": f"Bearer {token_worker}"},
            json={"name": "Forbidden Category"}
        )
        self.assertEqual(res_fail.status_code, 403)

        # Login admin creator
        res_c = self.client.post("/login", json={"username": "tester_creator", "password": "Password123!"})
        token_admin = res_c.get_json()["token"]

        # Admin adds service -> 200 OK
        res_ok = self.client.post(
            "/admin/service",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={"name": "Konditsioner Ta'mirlash"}
        )
        self.assertEqual(res_ok.status_code, 201)
        self.assertEqual(res_ok.get_json()["msg"], "Xizmat qo‘shildi.")

    def test_06_admin_commission_setting(self):
        res_admin = self.client.post(
            "/login",
            json={"username": "tester_creator", "password": "Password123!"}
        )
        self.assertEqual(res_admin.status_code, 200)
        token_admin = res_admin.get_json()["token"]

        overview = self.client.get(
            "/admin/overview",
            headers={"Authorization": f"Bearer {token_admin}"}
        )
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(float(overview.get_json()["settings"]["commission_percent"]), 2.0)

        updated = self.client.patch(
            "/admin/settings/commission",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={"commission_percent": 12.5}
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["commission_percent"], 12.5)

        config = self.client.get(
            "/payments/config",
            headers={"Authorization": f"Bearer {token_admin}"}
        )
        self.assertEqual(config.status_code, 200)
        self.assertEqual(config.get_json()["commission_percent"], 12.5)

        # Verify the changed percentage is actually used during payout.
        res_job = self.client.post(
            "/job",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={
                "service_id": 1,
                "title": "Commission Integration Check",
                "description": "Verify dynamic payout commission.",
                "price": 1000000,
                "location": "Remote"
            }
        )
        self.assertEqual(res_job.status_code, 200)
        jobs = self.client.get(
            "/jobs",
            headers={"Authorization": f"Bearer {token_admin}"}
        ).get_json()
        job_id = [item["id"] for item in jobs if item["title"] == "Commission Integration Check"][0]

        res_worker = self.client.post(
            "/login",
            json={"username": "tester_worker", "password": "Password123!"}
        )
        self.assertEqual(res_worker.status_code, 200)
        token_worker = res_worker.get_json()["token"]

        res_accept = self.client.post(
            "/accept_job",
            headers={"Authorization": f"Bearer {token_worker}"},
            json={"job_id": job_id}
        )
        self.assertEqual(res_accept.status_code, 200)

        balance_before = self.client.get(
            "/wallet",
            headers={"Authorization": f"Bearer {token_worker}"}
        ).get_json()["balance"]

        payment = self.client.post(
            f"/payments/dummy/{job_id}",
            headers={"Authorization": f"Bearer {token_admin}"}
        )
        self.assertEqual(payment.status_code, 200)
        self.assertEqual(payment.get_json()["status"], "held")

        self.assertEqual(
            self.client.post(
                "/finish_job",
                headers={"Authorization": f"Bearer {token_admin}"},
                json={"job_id": job_id}
            ).status_code,
            200
        )
        finished = self.client.post(
            "/finish_job",
            headers={"Authorization": f"Bearer {token_worker}"},
            json={"job_id": job_id}
        )
        self.assertEqual(finished.status_code, 200)
        self.assertTrue(finished.get_json()["finished"])

        balance_after = self.client.get(
            "/wallet",
            headers={"Authorization": f"Bearer {token_worker}"}
        ).get_json()["balance"]
        self.assertAlmostEqual(balance_after - balance_before, 875000.0, places=2)

        invalid = self.client.patch(
            "/admin/settings/commission",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={"commission_percent": 100.01}
        )
        self.assertEqual(invalid.status_code, 400)

        self.client.patch(
            "/admin/settings/commission",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={"commission_percent": 2}
        )

    def test_07_notifications_read_flow(self):
        res = self.client.post(
            "/login",
            json={"username": "tester_creator", "password": "Password123!"}
        )
        self.assertEqual(res.status_code, 200)
        token_admin = res.get_json()["token"]

        notifications = self.client.get(
            "/notifications",
            headers={"Authorization": f"Bearer {token_admin}"}
        )
        self.assertEqual(notifications.status_code, 200)
        data = notifications.get_json()
        self.assertTrue("items" in data)
        self.assertTrue("unread" in data)

        read = self.client.post(
            "/notifications/read",
            headers={"Authorization": f"Bearer {token_admin}"}
        )
        self.assertEqual(read.status_code, 200)

        after = self.client.get(
            "/notifications",
            headers={"Authorization": f"Bearer {token_admin}"}
        )
        self.assertEqual(after.status_code, 200)
        self.assertEqual(after.get_json()["unread"], 0)

    def test_08_withdrawal_has_no_extra_commission(self):
        res = self.client.post(
            "/login",
            json={"username": "tester_worker", "password": "Password123!"}
        )
        self.assertEqual(res.status_code, 200)
        token_worker = res.get_json()["token"]

        before = self.client.get(
            "/wallet",
            headers={"Authorization": f"Bearer {token_worker}"}
        ).get_json()["balance"]
        amount = 10000.0

        withdrawal = self.client.post(
            "/wallet/withdraw",
            headers={"Authorization": f"Bearer {token_worker}"},
            json={"amount": amount}
        )
        self.assertEqual(withdrawal.status_code, 200)
        result = withdrawal.get_json()
        self.assertEqual(result["amount"], amount)
        self.assertEqual(result["withdrawal_fee"], 0.0)
        self.assertAlmostEqual(result["balance"], before - amount, places=2)

    def test_09_report_resolution_and_refund(self):
        res_admin = self.client.post(
            "/login",
            json={"username": "tester_creator", "password": "Password123!"}
        )
        self.assertEqual(res_admin.status_code, 200)
        token_admin = res_admin.get_json()["token"]

        res_worker = self.client.post(
            "/login",
            json={"username": "tester_worker", "password": "Password123!"}
        )
        self.assertEqual(res_worker.status_code, 200)
        token_worker = res_worker.get_json()["token"]

        created = self.client.post(
            "/job",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={
                "service_id": 1,
                "title": "Report Refund Check",
                "description": "Verify admin report refund flow.",
                "price": 300000,
                "location": "Remote"
            }
        )
        self.assertEqual(created.status_code, 200)

        jobs = self.client.get(
            "/jobs",
            headers={"Authorization": f"Bearer {token_admin}"}
        ).get_json()
        job = [item for item in jobs if item["title"] == "Report Refund Check"][0]
        job_id = job["id"]

        accepted = self.client.post(
            "/accept_job",
            headers={"Authorization": f"Bearer {token_worker}"},
            json={"job_id": job_id}
        )
        self.assertEqual(accepted.status_code, 200)

        main.db.q("UPDATE users SET balance=500000 WHERE username=?", ("tester_creator",)).close()
        paid = self.client.post(
            f"/payments/dummy/{job_id}",
            headers={"Authorization": f"Bearer {token_admin}"}
        )
        self.assertEqual(paid.status_code, 200)

        report = self.client.post(
            "/report",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={
                "job_id": job_id,
                "reported_user_id": self.client.get(
                    "/profile", headers={"Authorization": f"Bearer {token_worker}"}
                ).get_json()["id"],
                "reason": "Test report",
                "details": "Testing moderation refund."
            }
        )
        self.assertEqual(report.status_code, 201)

        reports = self.client.get(
            "/admin/overview",
            headers={"Authorization": f"Bearer {token_admin}"}
        ).get_json()["reports"]
        report_id = [item["id"] for item in reports if item["reason"] == "Test report"][0]

        resolved = self.client.patch(
            f"/admin/report/{report_id}",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={"status": "resolved"}
        )
        self.assertEqual(resolved.status_code, 200)

        job_after = self.client.get(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token_admin}"}
        )
        self.assertEqual(job_after.status_code, 404)

        balance_after = self.client.get(
            "/wallet",
            headers={"Authorization": f"Bearer {token_admin}"}
        ).get_json()["balance"]
        self.assertAlmostEqual(balance_after, 500000.0, places=2)

    def test_09b_chat_attachment_report_and_admin_access(self):
        owner_login = self.client.post(
            "/login",
            json={"username": "tester_creator", "password": "Password123!"}
        )
        worker_login = self.client.post(
            "/login",
            json={"username": "tester_worker", "password": "Password123!"}
        )
        self.assertEqual(owner_login.status_code, 200)
        self.assertEqual(worker_login.status_code, 200)
        owner_token = owner_login.get_json()["token"]
        worker_token = worker_login.get_json()["token"]

        created = self.client.post(
            "/job",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "service_id": 1,
                "title": "Chat Attachment Report Check",
                "description": "Verify reported attachments are visible to admins.",
                "price": 100000,
                "location": "Remote"
            }
        )
        self.assertEqual(created.status_code, 200)
        job_id = [item for item in self.client.get(
            "/jobs", headers={"Authorization": f"Bearer {owner_token}"}
        ).get_json() if item["title"] == "Chat Attachment Report Check"][0]["id"]

        accepted = self.client.post(
            "/accept_job",
            headers={"Authorization": f"Bearer {worker_token}"},
            json={"job_id": job_id}
        )
        self.assertEqual(accepted.status_code, 200)

        image_data = b"\x89PNG\r\n\x1a\n" + b"FinJob report attachment test"
        sent = self.client.post(
            "/message",
            headers={"Authorization": f"Bearer {worker_token}"},
            data={
                "job_id": str(job_id),
                "receiver_id": str(main.db.q("SELECT user_id FROM jobs WHERE id=?", (job_id,)).fetchone()[0]),
                "message": "",
                "file": (BytesIO(image_data), "reported.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(sent.status_code, 200)

        message = main.db.q(
            "SELECT id, attachment_url, attachment_name, attachment_type FROM messages WHERE job_id=? ORDER BY id DESC LIMIT 1",
            (job_id,)
        ).fetchone()
        self.assertIsNotNone(message)
        self.assertTrue(message[1])
        self.assertEqual(message[2], "reported.png")
        self.assertEqual(message[3], "image")

        main.db.q(
            "UPDATE jobs SET status='finished', finished_at=? WHERE id=?",
            ("2026-10-07 12:00:00", job_id)
        ).close()

        reported_user_id = self.client.get(
            "/profile", headers={"Authorization": f"Bearer {worker_token}"}
        ).get_json()["id"]
        report = self.client.post(
            "/report",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "job_id": job_id,
                "message_id": message[0],
                "reported_user_id": reported_user_id,
                "reason": "Nomaqbul kontent",
                "details": "Rasm biriktirilgan xabar testi."
            }
        )
        self.assertEqual(report.status_code, 201)

        reports = self.client.get(
            "/admin/overview",
            headers={"Authorization": f"Bearer {owner_token}"}
        ).get_json()["reports"]
        item = [item for item in reports if item["reason"] == "Nomaqbul kontent" and item["message_id"] == message[0]][0]
        self.assertEqual(item["job_id"], job_id)
        self.assertEqual(item["attachment_url"], message[1])
        self.assertEqual(item["attachment_name"], "reported.png")
        self.assertEqual(item["attachment_type"], "image")

        attachment = self.client.get(
            f"/admin/report/{item['id']}/attachment",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        self.assertEqual(attachment.status_code, 200)
        self.assertEqual(attachment.data, image_data)
        attachment.close()  # release the file handle (Windows cannot delete an open file)

        worker_attachment = self.client.get(
            f"/admin/report/{item['id']}/attachment",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(worker_attachment.status_code, 403)
        worker_attachment.close()

        main.db.q("DELETE FROM messages WHERE id=?", (message[0],)).close()
        filepath = os.path.join(main.CHAT_UPLOAD_DIR, message[1].split("/uploads/chat/")[-1])
        if os.path.exists(filepath):
            os.remove(filepath)

    def test_10b_favorites_flow(self):
        login = self.client.post(
            "/login",
            json={"username": "tester_worker", "password": "Password123!"}
        )
        self.assertEqual(login.status_code, 200)
        token = login.get_json()["token"]

        jobs = self.client.get("/jobs", headers={"Authorization": f"Bearer {token}"}).get_json()
        active_jobs = [item for item in jobs if item["status"] == "active" and item["user_id"] != main.db.q("SELECT id FROM users WHERE username=?", ("tester_worker",)).fetchone()[0]]
        self.assertTrue(active_jobs)
        job_id = active_jobs[0]["id"]

        saved = self.client.post(
            "/favorites",
            headers={"Authorization": f"Bearer {token}"},
            json={"target_type": "job", "target_id": job_id}
        )
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.get_json()["favorited"])

        favorites = self.client.get(
            "/favorites?target_type=job",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(favorites.status_code, 200)
        self.assertTrue(any(int(item["target_id"]) == job_id for item in favorites.get_json()))

        removed = self.client.delete(
            "/favorites",
            headers={"Authorization": f"Bearer {token}"},
            json={"target_type": "job", "target_id": job_id}
        )
        self.assertEqual(removed.status_code, 200)
        self.assertFalse(removed.get_json()["favorited"])

        owner_id = main.db.q("SELECT user_id FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
        saved_user = self.client.post(
            "/favorites",
            headers={"Authorization": f"Bearer {token}"},
            json={"target_type": "user", "target_id": owner_id}
        )
        self.assertEqual(saved_user.status_code, 200)
        self.assertTrue(saved_user.get_json()["favorited"])

        saved_service = self.client.post(
            "/favorites",
            headers={"Authorization": f"Bearer {token}"},
            json={"target_type": "service", "target_id": 1}
        )
        self.assertEqual(saved_service.status_code, 200)
        self.assertTrue(saved_service.get_json()["favorited"])

    def test_10c_portfolio_and_public_profile_flow(self):
        login = self.client.post(
            "/login",
            json={"username": "tester_worker", "password": "Password123!"}
        )
        self.assertEqual(login.status_code, 200)
        token = login.get_json()["token"]

        created = self.client.post(
            "/portfolio",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": "FinJob Demo Project",
                "description": "A marketplace prototype built with Flask and React.",
                "url": "https://example.com/finjob-demo"
            }
        )
        self.assertEqual(created.status_code, 201)
        item_id = created.get_json()["id"]

        portfolio = self.client.get(
            "/portfolio",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(portfolio.status_code, 200)
        self.assertTrue(any(item["id"] == item_id for item in portfolio.get_json()))

        public = self.client.get(
            "/profiles/tester_worker",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(public.status_code, 200)
        public_data = public.get_json()
        self.assertIn("portfolio", public_data)
        self.assertTrue(any(item["id"] == item_id for item in public_data["portfolio"]))
        self.assertIn("success_rate", public_data)
        self.assertIn("reviews_count", public_data)

        deleted = self.client.delete(
            f"/portfolio/{item_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(deleted.status_code, 200)

    def test_10e_portfolio_file_upload_flow(self):
        worker = main.db.q(
            "SELECT id, role, COALESCE(token_version,0) FROM users WHERE username=?",
            ("tester_worker",)
        ).fetchone()
        self.assertIsNotNone(worker)
        token = main.token(worker[0], worker[1] or "user", worker[2])

        pdf_data = b"%PDF-1.4\n% FinJob portfolio test\n"
        uploaded = self.client.post(
            "/portfolio/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "title": "Uploaded Portfolio",
                "description": "Portfolio file upload test.",
                "url": "https://example.com/uploaded",
                "file": (BytesIO(pdf_data), "portfolio.pdf"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(uploaded.status_code, 201)
        uploaded_data = uploaded.get_json()
        self.assertTrue(uploaded_data.get("file_url"))
        self.assertEqual(uploaded_data.get("file_name"), "portfolio.pdf")

        item = main.db.q(
            "SELECT file_url,file_name,image_url FROM portfolio_items WHERE id=?",
            (uploaded_data["id"],)
        ).fetchone()
        self.assertIsNotNone(item)
        self.assertTrue(item[0])
        self.assertEqual(item[1], "portfolio.pdf")
        self.assertEqual(item[2], "")

        file_response = self.client.get(item[0])
        self.assertEqual(file_response.status_code, 200)
        self.assertEqual(file_response.data[:5], b"%PDF-")

        docx_data = b"PK\x03\x04" + b"FinJob Word test"
        uploaded_docx = self.client.post(
            "/portfolio/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "title": "Word Portfolio",
                "file": (BytesIO(docx_data), "portfolio.docx"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(uploaded_docx.status_code, 201)
        docx_json = uploaded_docx.get_json()
        self.assertEqual(docx_json.get("file_name"), "portfolio.docx")
        docx_response = self.client.get(docx_json["file_url"])
        self.assertEqual(docx_response.status_code, 200)
        self.assertTrue(docx_response.data.startswith(b"PK\x03\x04"))

        doc_data = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"FinJob legacy Word test"
        uploaded_doc = self.client.post(
            "/portfolio/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "title": "Legacy Word Portfolio",
                "file": (BytesIO(doc_data), "portfolio.doc"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(uploaded_doc.status_code, 201)
        self.assertEqual(uploaded_doc.get_json().get("file_name"), "portfolio.doc")

        bad = self.client.post(
            "/portfolio/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "title": "Bad Portfolio",
                "file": (BytesIO(b"not a pdf"), "bad.pdf"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(bad.status_code, 400)

    def test_10d_chat_v2_flow(self):
        owner_login = self.client.post(
            "/login",
            json={"username": "tester_creator", "password": "Password123!"}
        )
        worker_login = self.client.post(
            "/login",
            json={"username": "tester_worker", "password": "Password123!"}
        )
        self.assertEqual(owner_login.status_code, 200)
        self.assertEqual(worker_login.status_code, 200)
        owner_token = owner_login.get_json()["token"]
        worker_token = worker_login.get_json()["token"]

        job_id = main.db.q(
            "SELECT id FROM jobs WHERE title='Build Web App' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]

        sent = self.client.post(
            "/message",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"job_id": job_id, "message": "Chat v2 unread test"}
        )
        self.assertEqual(sent.status_code, 200)

        unread = self.client.get(
            "/messages/unread-count",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(unread.status_code, 200)
        self.assertGreaterEqual(unread.get_json()["unread"], 1)

        conversations = self.client.get(
            "/conversations",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(conversations.status_code, 200)
        self.assertTrue(any(item["job_id"] == job_id for item in conversations.get_json()))

        messages = self.client.get(
            f"/messages/{job_id}",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(messages.status_code, 200)
        self.assertTrue(any(item["message"] == "Chat v2 unread test" for item in messages.get_json()))

        unread_after = self.client.get(
            "/messages/unread-count",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(unread_after.status_code, 200)
        self.assertEqual(unread_after.get_json()["unread"], 0)

        presence = self.client.post(
            "/presence",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(presence.status_code, 200)

        worker_id = self.client.get(
            "/profile",
            headers={"Authorization": f"Bearer {worker_token}"}
        ).get_json()["id"]
        seen = self.client.get(
            f"/presence/{worker_id}?job_id={job_id}",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        self.assertEqual(seen.status_code, 200)
        self.assertTrue(seen.get_json()["online"])

        typing_on = self.client.post(
            f"/typing/{job_id}",
            headers={"Authorization": f"Bearer {worker_token}"},
            json={"typing": True}
        )
        self.assertEqual(typing_on.status_code, 200)

        typing_seen = self.client.get(
            f"/typing/{job_id}",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        self.assertEqual(typing_seen.status_code, 200)
        self.assertTrue(typing_seen.get_json()["typing"])

        typing_off = self.client.post(
            f"/typing/{job_id}",
            headers={"Authorization": f"Bearer {worker_token}"},
            json={"typing": False}
        )
        self.assertEqual(typing_off.status_code, 200)


    def test_11_moderation_blocks_appeals_flow(self):
        admin_login = self.client.post(
            "/login",
            json={"username": "tester_creator", "password": "Password123!"}
        )
        worker_login = self.client.post(
            "/login",
            json={"username": "tester_worker", "password": "Password123!"}
        )
        self.assertEqual(admin_login.status_code, 200)
        self.assertEqual(worker_login.status_code, 200)
        admin_token = admin_login.get_json()["token"]
        worker_token = worker_login.get_json()["token"]

        worker = main.db.q("SELECT id FROM users WHERE username=?", ("tester_worker",)).fetchone()
        self.assertIsNotNone(worker)
        worker_id = worker[0]
        job_id = main.db.q(
            "SELECT id FROM jobs WHERE title='Build Web App' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]

        blocked = self.client.post(
            f"/admin/user/{worker_id}/block",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "block_type": "chat",
                "duration_minutes": 60,
                "reason": "Chat qoidalarini takroran buzish."
            }
        )
        self.assertEqual(blocked.status_code, 201)
        block_id = blocked.get_json()["block_id"]

        messages_blocked = self.client.get(
            f"/messages/{job_id}",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(messages_blocked.status_code, 403)
        self.assertTrue(messages_blocked.get_json().get("blocked"))
        self.assertEqual(messages_blocked.get_json().get("block_type"), "chat")

        notifications = self.client.get(
            "/notifications",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(notifications.status_code, 200)
        self.assertTrue(any("Chat blok" in item["message"] and "Chat qoidalarini" in item["message"] for item in notifications.get_json()["items"]))

        appeals = self.client.get(
            "/appeals",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(appeals.status_code, 200)
        self.assertTrue(any(item["id"] == block_id for item in appeals.get_json()["active_blocks"]))

        created_appeal = self.client.post(
            "/appeals",
            headers={"Authorization": f"Bearer {worker_token}"},
            json={
                "block_id": block_id,
                "appeal_text": "Men vaziyatni tushundim va bu cheklov juda qattiq qo‘yilgan deb hisoblayman."
            }
        )
        self.assertEqual(created_appeal.status_code, 201)
        appeal_id = created_appeal.get_json()["appeal_id"]

        admin_appeals = self.client.get(
            "/admin/appeals?q=tester_worker",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(admin_appeals.status_code, 200)
        appeal_row = next(item for item in admin_appeals.get_json()["items"] if item["id"] == appeal_id)
        self.assertEqual(appeal_row["block_id"], block_id)
        self.assertEqual(appeal_row["block_type"], "chat")
        self.assertEqual(appeal_row["username"], "tester_worker")
        self.assertIn("Chat qoidalarini", appeal_row["block_reason"])
        self.assertIn("Men vaziyatni", appeal_row["appeal_text"])

        reviewed = self.client.patch(
            f"/admin/appeal/{appeal_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "approved", "admin_response": "Appeal qabul qilindi; chat cheklovi olib tashlandi."}
        )
        self.assertEqual(reviewed.status_code, 200)

        unblocked_messages = self.client.get(
            f"/messages/{job_id}",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(unblocked_messages.status_code, 200)

        job_block = self.client.post(
            f"/admin/user/{worker_id}/block",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "block_type": "job_creation",
                "duration_minutes": 60,
                "reason": "Ish e’lonlarida qoidabuzarlik."
            }
        )
        self.assertEqual(job_block.status_code, 201)
        blocked_job = self.client.post(
            "/job",
            headers={"Authorization": f"Bearer {worker_token}"},
            json={
                "service_id": 1,
                "title": "Should Be Blocked",
                "description": "Moderation restriction test",
                "price": 100000,
                "location": "Remote"
            }
        )
        self.assertEqual(blocked_job.status_code, 403)

        worker_blocks = self.client.get(
            f"/admin/user/{worker_id}/blocks",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(worker_blocks.status_code, 200)
        self.assertTrue(any(item["active"] and item["block_type"] == "job_creation" for item in worker_blocks.get_json()["blocks"]))

        lift_target = next(item for item in worker_blocks.get_json()["blocks"] if item["active"] and item["block_type"] == "job_creation")
        lifted = self.client.patch(
            f"/admin/block/{lift_target['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"action": "lift"}
        )
        self.assertEqual(lifted.status_code, 200)

        full_block = self.client.post(
            f"/admin/user/{worker_id}/block",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"block_type": "full", "reason": "To‘liq moderation test blocki."}
        )
        self.assertEqual(full_block.status_code, 201)
        full_block_id = full_block.get_json()["block_id"]

        full_denied = self.client.get(
            "/jobs",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(full_denied.status_code, 403)
        self.assertEqual(full_denied.get_json().get("block_type"), "full")

        appeal_access = self.client.get(
            "/appeals",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(appeal_access.status_code, 200)
        self.assertTrue(any(item["id"] == full_block_id for item in appeal_access.get_json()["active_blocks"]))

        full_lift = self.client.patch(
            f"/admin/block/{full_block_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"action": "lift"}
        )
        self.assertEqual(full_lift.status_code, 200)

    def test_10_logout_invalidates_token(self):
        res = self.client.post(
            "/login",
            json={"username": "tester_worker", "password": "Password123!"}
        )
        self.assertEqual(res.status_code, 200)
        token_worker = res.get_json()["token"]

        logout = self.client.post(
            "/logout",
            headers={"Authorization": f"Bearer {token_worker}"}
        )
        self.assertEqual(logout.status_code, 200)

        profile = self.client.get(
            "/profile",
            headers={"Authorization": f"Bearer {token_worker}"}
        )
        self.assertEqual(profile.status_code, 401)


    def test_12_deep_regression(self):
        def register_user(username, email):
            sent = self.client.post(
                "/register/send-code",
                json={
                    "username": username,
                    "password": "Password123!",
                    "first_name": "Deep",
                    "last_name": "Tester",
                    "birthday": "1994-04-04",
                    "email": email,
                },
            )
            self.assertEqual(sent.status_code, 200)
            code = pending_verifications[email]["code"]
            verified = self.client.post("/register/verify", json={"email": email, "code": code})
            self.assertEqual(verified.status_code, 200)
            login = self.client.post("/login", json={"username": username, "password": "Password123!"})
            self.assertEqual(login.status_code, 200)
            return login.get_json()["token"]

        admin_token = self.client.post("/login", json={"username": "tester_creator", "password": "Password123!"}).get_json()["token"]
        bidder_token = register_user("tester_bidder2", "tester_bidder2@example.com")
        outsider_token = register_user("tester_outsider", "tester_outsider@example.com")
        cleanup_token = register_user("tester_cleanup", "tester_cleanup@example.com")

        owner_job = self.client.post("/job", headers={"Authorization": f"Bearer {admin_token}"}, json={
            "service_id": 1,
            "title": "Deep Bidding Direct Accept",
            "description": "Deep regression job",
            "price": 1000000,
            "location": "Remote",
        })
        self.assertEqual(owner_job.status_code, 200)
        jobs = self.client.get("/jobs", headers={"Authorization": f"Bearer {admin_token}"}).get_json()
        deep_job_id = [j for j in jobs if j["title"] == "Deep Bidding Direct Accept"][0]["id"]

        proposal = self.client.post(
            f"/jobs/{deep_job_id}/proposals",
            headers={"Authorization": f"Bearer {bidder_token}"},
            json={"price": 850000, "deadline": "2026-10-30", "message": "Deep regression proposal"},
        )
        self.assertEqual(proposal.status_code, 201)

        bidder_id = self.client.get("/profile", headers={"Authorization": f"Bearer {bidder_token}"}).get_json()["id"]
        proposal_block = self.client.post(
            f"/admin/user/{bidder_id}/block",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"block_type": "proposal", "reason": "Deep test proposal restriction", "duration_minutes": 60},
        )
        self.assertEqual(proposal_block.status_code, 201)

        read_while_blocked = self.client.get(f"/jobs/{deep_job_id}/proposals", headers={"Authorization": f"Bearer {bidder_token}"})
        self.assertEqual(read_while_blocked.status_code, 200)
        self.assertEqual(len(read_while_blocked.get_json()), 1)

        blocked_post = self.client.post(
            f"/jobs/{deep_job_id}/proposals",
            headers={"Authorization": f"Bearer {bidder_token}"},
            json={"price": 840000, "deadline": "2026-10-30", "message": "Should be blocked"},
        )
        self.assertEqual(blocked_post.status_code, 403)
        self.assertEqual(blocked_post.get_json()["block_type"], "proposal")

        lifted = self.client.patch(
            f"/admin/block/{proposal_block.get_json()['block_id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"action": "lift"},
        )
        self.assertEqual(lifted.status_code, 200)

        direct_accept = self.client.post("/accept_job", headers={"Authorization": f"Bearer {outsider_token}"}, json={"job_id": deep_job_id})
        self.assertEqual(direct_accept.status_code, 200)

        owner_proposals = self.client.get(f"/jobs/{deep_job_id}/proposals", headers={"Authorization": f"Bearer {admin_token}"}).get_json()
        self.assertEqual(owner_proposals[0]["status"], "rejected")

        bidder_notifications = self.client.get("/notifications", headers={"Authorization": f"Bearer {bidder_token}"}).get_json()
        self.assertTrue(any(item["type"] == "proposal_rejected" and "Deep Bidding Direct Accept" in item["message"] for item in bidder_notifications["items"]))

        full_block = self.client.post(
            f"/admin/user/{bidder_id}/block",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"block_type": "full", "reason": "Deep full-block statistics test", "duration_minutes": 60},
        )
        self.assertEqual(full_block.status_code, 201)

        overview = self.client.get("/admin/overview", headers={"Authorization": f"Bearer {admin_token}"}).get_json()
        blocked_user = [item for item in overview["users"] if item["id"] == bidder_id][0]
        self.assertEqual(blocked_user["is_blocked"], 1)
        search = self.client.get("/admin/search?q=tester_bidder2", headers={"Authorization": f"Bearer {admin_token}"}).get_json()
        self.assertEqual([item for item in search["users"] if item["id"] == bidder_id][0]["is_blocked"], 1)

        full_lift = self.client.patch(
            f"/admin/block/{full_block.get_json()['block_id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"action": "lift"},
        )
        self.assertEqual(full_lift.status_code, 200)
        overview_after = self.client.get("/admin/overview", headers={"Authorization": f"Bearer {admin_token}"}).get_json()
        self.assertEqual([item for item in overview_after["users"] if item["id"] == bidder_id][0]["is_blocked"], 0)

        chat_job = self.client.post("/job", headers={"Authorization": f"Bearer {admin_token}"}, json={
            "service_id": 1, "title": "Deep Attachment Access", "description": "Chat attachment security", "price": 500000, "location": "Remote"
        })
        self.assertEqual(chat_job.status_code, 200)
        jobs = self.client.get("/jobs", headers={"Authorization": f"Bearer {admin_token}"}).get_json()
        chat_job_id = [j for j in jobs if j["title"] == "Deep Attachment Access"][0]["id"]
        self.assertEqual(self.client.post("/accept_job", headers={"Authorization": f"Bearer {bidder_token}"}, json={"job_id": chat_job_id}).status_code, 200)

        owner_id = self.client.get("/profile", headers={"Authorization": f"Bearer {admin_token}"}).get_json()["id"]
        upload = self.client.post(
            "/message",
            headers={"Authorization": f"Bearer " + bidder_token},
            data={
                "job_id": str(chat_job_id),
                "receiver_id": str(owner_id),
                "message": "attachment",
                "file": (BytesIO(b"\x89PNG\r\n\x1a\n"), "test.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(upload.status_code, 200)
        messages = self.client.get(f"/messages/{chat_job_id}", headers={"Authorization": f"Bearer {bidder_token}"}).get_json()
        attachment_url = messages[-1]["attachment_url"]
        self.assertTrue(attachment_url)
        self.assertEqual(self.client.get(attachment_url).status_code, 401)
        self.assertEqual(self.client.get(attachment_url, headers={"Authorization": f"Bearer {outsider_token}"}).status_code, 404)
        self.assertEqual(self.client.get(attachment_url, headers={"Authorization": f"Bearer {bidder_token}"}).status_code, 200)

        cleanup_id = self.client.get("/profile", headers={"Authorization": f"Bearer {cleanup_token}"}).get_json()["id"]
        cleanup_block = self.client.post(
            f"/admin/user/{cleanup_id}/block", headers={"Authorization": f"Bearer {admin_token}",},
            json={"block_type": "chat", "reason": "Cleanup block", "duration_minutes": 60},
        )
        self.assertEqual(cleanup_block.status_code, 201)
        self.assertEqual(self.client.post("/favorites", headers={"Authorization": f"Bearer {cleanup_token}"}, json={"target_type": "job", "target_id": deep_job_id}).status_code, 200)
        self.assertEqual(self.client.post("/portfolio", headers={"Authorization": f"Bearer {cleanup_token}"}, json={"title": "Cleanup portfolio", "description": "cleanup"}).status_code, 201)

        cleanup_job = self.client.post("/job", headers={"Authorization": f"Bearer {admin_token}"}, json={
            "service_id": 1, "title": "Cleanup Proposal Job", "description": "Cleanup proposal row", "price": 400000, "location": "Remote"
        })
        self.assertEqual(cleanup_job.status_code, 200)
        jobs = self.client.get("/jobs", headers={"Authorization": f"Bearer {admin_token}"}).get_json()
        cleanup_job_id = [j for j in jobs if j["title"] == "Cleanup Proposal Job"][0]["id"]
        self.assertEqual(self.client.post(
            f"/jobs/{cleanup_job_id}/proposals",
            headers={"Authorization": f"Bearer {cleanup_token}"},
            json={"price": 350000, "deadline": "2026-11-01", "message": "Cleanup proposal"},
        ).status_code, 201)

        deleted = self.client.delete(f"/admin/user/{cleanup_id}", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(deleted.status_code, 200)
        self.assertIsNone(main.db.q("SELECT id FROM users WHERE id=?", (cleanup_id,)).fetchone())
        self.assertIsNone(main.db.q("SELECT id FROM job_proposals WHERE worker_id=?", (cleanup_id,)).fetchone())
        self.assertIsNone(main.db.q("SELECT id FROM favorites WHERE user_id=?", (cleanup_id,)).fetchone())
        self.assertIsNone(main.db.q("SELECT id FROM portfolio_items WHERE user_id=?", (cleanup_id,)).fetchone())
        self.assertIsNone(main.db.q("SELECT id FROM notifications WHERE user_id=?", (cleanup_id,)).fetchone())
        self.assertIsNone(main.db.q("SELECT id FROM user_blocks WHERE user_id=?", (cleanup_id,)).fetchone())

        self.assertEqual(self.client.delete(f"/admin/job/{deep_job_id}", headers={"Authorization": f"Bearer {admin_token}"}).status_code, 200)
        self.assertEqual(self.client.delete(f"/admin/job/{chat_job_id}", headers={"Authorization": f"Bearer {admin_token}"}).status_code, 200)
        self.assertEqual(self.client.delete(f"/admin/job/{cleanup_job_id}", headers={"Authorization": f"Bearer {admin_token}"}).status_code, 200)


    def test_13_security_and_privacy_regressions(self):
        admin_token = self.client.post(
            "/login",
            json={"username": "tester_creator", "password": "Password123!"}
        ).get_json()["token"]
        worker_token = self.client.post(
            "/login",
            json={"username": "tester_worker", "password": "Password123!"}
        ).get_json()["token"]
        outsider_token = self.client.post(
            "/login",
            json={"username": "tester_outsider", "password": "Password123!"}
        ).get_json()["token"]

        worker_profile = self.client.get(
            "/profile", headers={"Authorization": f"Bearer {worker_token}"}
        ).get_json()
        worker_id = worker_profile["id"]

        public_profile = self.client.get(
            f"/profiles/{worker_profile['username']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(public_profile.status_code, 200)
        self.assertEqual(public_profile.get_json().get("email"), worker_profile["email"])

        outsider_public_profile = self.client.get(
            f"/profiles/{worker_profile['username']}",
            headers={"Authorization": f"Bearer {outsider_token}"}
        )
        self.assertEqual(outsider_public_profile.status_code, 200)
        self.assertEqual(outsider_public_profile.get_json().get("email"), "")

        no_shared_presence = self.client.get(
            f"/presence/{worker_id}",
            headers={"Authorization": f"Bearer {outsider_token}"}
        )
        self.assertEqual(no_shared_presence.status_code, 403)

        active_job = self.client.post(
            "/job",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "service_id": 1,
                "title": "Security Presence Job",
                "description": "Security regression job",
                "price": 250000,
                "location": "Remote",
            }
        )
        self.assertEqual(active_job.status_code, 200)
        jobs = self.client.get("/jobs", headers={"Authorization": f"Bearer {admin_token}"}).get_json()
        security_job_id = [item["id"] for item in jobs if item["title"] == "Security Presence Job"][0]

        accepted = self.client.post(
            "/accept_job",
            headers={"Authorization": f"Bearer {worker_token}"},
            json={"job_id": security_job_id},
        )
        self.assertEqual(accepted.status_code, 200)

        shared_presence = self.client.get(
            f"/presence/{worker_id}?job_id={security_job_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(shared_presence.status_code, 200)

        chat_forbidden = self.client.get(
            f"/messages/{security_job_id}",
            headers={"Authorization": f"Bearer {outsider_token}"}
        )
        self.assertEqual(chat_forbidden.status_code, 403)

        payment_forbidden = self.client.get(
            f"/payments/job/{security_job_id}",
            headers={"Authorization": f"Bearer {outsider_token}"}
        )
        self.assertEqual(payment_forbidden.status_code, 404)

        malformed_profile = self.client.put(
            "/profile",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"username": {"bad": "type"}, "email": "tester_creator@example.com"},
        )
        self.assertEqual(malformed_profile.status_code, 400)

        malformed_rating = self.client.post(
            "/rating",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"job_id": security_job_id, "to_user": worker_id, "score": 10, "comment": {"bad": "type"}},
        )
        self.assertIn(malformed_rating.status_code, (400, 409))



    def test_14_payment_receipt_and_finance_summary(self):
        owner_token = self.client.post(
            "/login",
            json={"username": "tester_creator", "password": "Password123!"}
        ).get_json()["token"]
        worker_token = self.client.post(
            "/login",
            json={"username": "tester_worker", "password": "Password123!"}
        ).get_json()["token"]
        outsider_token = self.client.post(
            "/login",
            json={"username": "tester_outsider", "password": "Password123!"}
        ).get_json()["token"]

        owner_id = self.client.get(
            "/profile", headers={"Authorization": f"Bearer {owner_token}"}
        ).get_json()["id"]
        worker_id = self.client.get(
            "/profile", headers={"Authorization": f"Bearer {worker_token}"}
        ).get_json()["id"]

        now = "2026-10-08T00:00:00+00:00"
        conn = main.db.get_connection()
        try:
            job_id = conn.execute(
                """INSERT INTO jobs(
                    user_id,service_id,title,description,price,currency,location,
                    worker_id,status,created_at,finished_at,custom_service,agreed_price
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    owner_id,1,"Payment Receipt Regression",
                    "Payment receipt API regression test",500000,"UZS","Remote",
                    worker_id,"accepted",now,None,"",500000
                ),
            ).lastrowid
            payment_uuid = "test-receipt-payment-uuid"
            conn.execute(
                """INSERT INTO payments(
                    payment_uuid,job_id,payer_id,payee_id,amount,currency,provider,status,
                    provider_transaction_id,created_at,paid_at,released_at,refunded_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    payment_uuid,job_id,owner_id,worker_id,500000,"UZS","dummy","released",
                    "test-provider-tx",now,now,now,None
                ),
            )
            conn.commit()
        finally:
            conn.close()

        receipt = self.client.get(
            f"/payments/{payment_uuid}/receipt",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        self.assertEqual(receipt.status_code, 200)
        receipt_data = receipt.get_json()
        self.assertEqual(receipt_data["payment_uuid"], payment_uuid)
        self.assertEqual(receipt_data["amount"], 500000)
        self.assertEqual(receipt_data["currency"], "UZS")
        self.assertEqual(receipt_data["status"], "released")
        self.assertEqual(receipt_data["provider_transaction_id"], "test-provider-tx")
        self.assertIn("commission_amount", receipt_data)
        self.assertIn("worker_amount", receipt_data)

        forbidden = self.client.get(
            f"/payments/{payment_uuid}/receipt",
            headers={"Authorization": f"Bearer {outsider_token}"}
        )
        self.assertEqual(forbidden.status_code, 403)

        summary = self.client.get(
            "/admin/finance/summary",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        self.assertEqual(summary.status_code, 200)
        summary_data = summary.get_json()
        self.assertIn("payments", summary_data)
        self.assertIn("platform", summary_data)
        self.assertIn("withdrawals", summary_data)
        self.assertGreaterEqual(summary_data["payments"]["count"], 1)

        main.db.q("DELETE FROM payments WHERE payment_uuid=?", (payment_uuid,)).close()
        main.db.q("DELETE FROM jobs WHERE id=?", (job_id,)).close()


# ---------------------------------------------------------------------------
# Payme wallet top-up tests. Payme is always mocked: no network, no real credentials.
# ---------------------------------------------------------------------------
import json as _json
import threading
from unittest import mock

import payme

PAYME_TEST_ENV = {
    "FINJOB_ENV": "development",
    "PAYME_ENABLED": "1",
    "PAYME_TEST_MODE": "1",
    "PAYME_MERCHANT_ID": "4056281",
    "PAYME_MERCHANT_KEY": "unit-test-secret-key",
    "PAYME_CHECKOUT_BASE_URL": "https://pay.payme.uz",
    "PAYME_CALLBACK_URL": "https://api.example.test/payments/payme/callback",
    "PAYME_RESPONSE_URL": "https://api.example.test/wallet/deposits/return",
    "PAYME_FRONTEND_RETURN_URL": "https://app.example.test/profile",
}
PAYME_KEY = PAYME_TEST_ENV["PAYME_MERCHANT_KEY"]
_REAL_HTTP_POST_JSON = payme._http_post_json  # captured before setUp() mocks it


def _docs_reference_signature(secret_key, params):
    """Independent copy of the Python snippet on docs.payme.uz/api/building-signature (not FinJob's code)."""
    import hashlib
    data = [secret_key]
    data.extend([str(params[key]) for key in sorted(iter(params.keys()))
                 if params[key] != '' and not params[key] is None and key != 'signature'])
    return hashlib.sha1('|'.join(data).encode('utf-8')).hexdigest()


def _docs_shaped_callback(order_id, amount_minor, payment_id, merchant_id=4056281, status="approved", is_test=True):
    """Field set and JSON types of the callback example on docs.payme.uz/api/callbacks (numbers stay numbers,
    empty fields stay "", additional_info is a JSON *string*)."""
    approved = status == "approved"
    return {
        "rrn": "111111111111", "masked_card": "444455XXXXXX1111", "sender_cell_phone": "", "sender_account": "",
        "currency": "UZS", "fee": "", "reversal_amount": "0", "settlement_amount": "0",
        "actual_amount": str(amount_minor) if approved else "", "response_description": "",
        "sender_email": "", "order_status": status, "response_status": "success",
        "order_time": "25.11.2026 20:23:59", "actual_currency": "UZS" if approved else "", "order_id": order_id,
        "tran_type": "purchase", "eci": "5", "settlement_date": "", "payment_system": "card",
        "approval_code": "123456", "merchant_id": merchant_id, "settlement_currency": "", "payment_id": payment_id,
        "card_bin": 444455, "response_code": "", "card_type": "VISA", "amount": str(amount_minor),
        "product_id": "", "merchant_data": "FinJob hamyoni — to‘ldirish", "rectoken": "", "rectoken_lifetime": "",
        "verification_status": "", "parent_order_id": "", "fee_oplata": "0",
        "additional_info": _json.dumps({"capture_status": None, "is_test": is_test, "version_3ds": 1,
                                        "bank_name": "Тест банк", "payment_method": "card"}),
    }


class PaymeWalletTopUpTests(unittest.TestCase):
    _seq = 0

    _payment_counter = 700000000

    @classmethod
    def _next_payment_id(cls):
        cls._payment_counter += 1
        return cls._payment_counter

    @classmethod
    def setUpClass(cls):
        cls.test_db_name = "test_payme.db"
        cls.original_db = main.db
        cls.original_db_name = cls.original_db.db_name
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(cls.test_db_name + suffix):
                os.remove(cls.test_db_name + suffix)
        DB(cls.test_db_name)
        cls.original_db.db_name = cls.test_db_name
        cls.original_send_email_code = main.send_email_code
        main.send_email_code = lambda to_email, code: True
        app.config["TESTING"] = True
        cls.client = app.test_client()
        cls.make_user("payme_first_admin")
        main.db.q("UPDATE users SET role='admin' WHERE username='payme_first_admin'").close()

    @classmethod
    def tearDownClass(cls):
        cls.original_db.db_name = cls.original_db_name
        main.send_email_code = cls.original_send_email_code
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(cls.test_db_name + suffix)
            except OSError:
                pass

    @classmethod
    def make_user(cls, name):
        email = f"{name}@example.com"
        res = cls.client.post("/register/send-code", json={
            "username": name, "password": "Password123!", "first_name": "T", "last_name": "U",
            "birthday": "1999-01-01", "email": email,
        })
        assert res.status_code == 200, res.get_json()
        code = pending_verifications[email]["code"]
        assert cls.client.post("/register/verify", json={"email": email, "code": code}).status_code == 200
        token = cls.client.post("/login", json={"username": name, "password": "Password123!"}).get_json()["token"]
        uid = cls.client.get("/profile", headers={"Authorization": f"Bearer {token}"}).get_json()["id"]
        return token, uid

    def setUp(self):
        with main._rate_lock:
            main._rate_buckets.clear()
        env = mock.patch.dict(os.environ, PAYME_TEST_ENV)
        env.start()
        self.addCleanup(env.stop)
        self.sent = []
        self.status_answer = None

        def fake_post(url, body, timeout=15):
            self.sent.append((url, body))
            if url.endswith("/api/checkout/url"):
                order_id = body["request"]["order_id"]
                return {"response": {
                    "response_status": "success", "payment_id": str(PaymeWalletTopUpTests._next_payment_id()),
                    "checkout_url": f"https://pay.payme.uz/merchants/abc/default/index.html?token={order_id}",
                }}
            if self.status_answer:
                return self.status_answer(body["request"]["order_id"])
            return {"response": {"response_status": "failure", "error_code": 1002}}

        patcher = mock.patch.object(payme, "_http_post_json", side_effect=fake_post)
        patcher.start()
        self.addCleanup(patcher.stop)
        PaymeWalletTopUpTests._seq += 1
        self.token, self.uid = self.make_user(f"payme_user_{PaymeWalletTopUpTests._seq}")

    # ---- helpers
    def auth(self, token=None):
        return {"Authorization": f"Bearer {token or self.token}"}

    def create_deposit(self, amount=250000, token=None, **extra):
        return self.client.post("/wallet/deposits", headers=self.auth(token), json={"amount": amount, **extra})

    def callback_payload(self, deposit_id, amount_uzs=250000, status="approved", sign=True, **override):
        body = {
            "rrn": "111111111111", "masked_card": "444455XXXXXX1111", "currency": "UZS", "fee": "",
            "actual_amount": str(amount_uzs * 100) if status == "approved" else "",
            "actual_currency": "UZS" if status == "approved" else "",
            "order_status": status, "response_status": "success", "order_id": deposit_id,
            "merchant_id": 4056281, "payment_id": 805243692, "amount": str(amount_uzs * 100),
            "tran_type": "purchase", "response_description": "", "response_code": "",
        }
        body.update(override)
        if sign:
            body["signature"] = payme.payme_signature(PAYME_KEY, body)
        return body

    def send_callback(self, body):
        return self.client.post("/payments/payme/callback", json=body)

    def balance(self, uid=None):
        return float(main.db.q("SELECT COALESCE(balance,0) FROM users WHERE id=?", (uid or self.uid,)).fetchone()[0])

    def deposit_txs(self, uid=None):
        return main.db.q(
            "SELECT amount,balance_after FROM wallet_transactions WHERE user_id=? AND type='deposit'", (uid or self.uid,)
        ).fetchall()

    def deposit_status(self, deposit_id):
        return main.db.q("SELECT status FROM wallet_deposits WHERE deposit_uuid=?", (deposit_id,)).fetchone()[0]

    def pay(self, amount=250000, **override):
        """Create a deposit and build the signed 'approved' callback Payme would send for it."""
        dep = self.create_deposit(amount).get_json()
        override.setdefault("payment_id", self._next_payment_id())
        return dep["deposit_id"], self.callback_payload(dep["deposit_id"], amount, **override)

    # ---- creation and validation
    def test_create_deposit_builds_signed_payme_order_without_crediting(self):
        res = self.create_deposit(250000)
        self.assertEqual(res.status_code, 201, res.get_json())
        data = res.get_json()
        self.assertEqual(data["status"], "pending")
        self.assertTrue(data["checkout_url"].startswith("https://pay.payme.uz/"))
        url, body = self.sent[0]
        self.assertTrue(url.endswith("/api/checkout/url"))
        req = body["request"]
        self.assertEqual(req["order_id"], data["deposit_id"])
        self.assertEqual(req["amount"], 25000000)  # 250 000 UZS = 25 000 000 tiyin
        self.assertEqual(req["currency"], "UZS")
        self.assertEqual(req["merchant_id"], 4056281)
        self.assertTrue(payme.verify_signature(PAYME_KEY, req))
        self.assertEqual(self.balance(), 0)
        row = main.db.q("SELECT user_id,amount_uzs,amount_minor,provider,status FROM wallet_deposits WHERE deposit_uuid=?",
                        (data["deposit_id"],)).fetchone()
        self.assertEqual(tuple(row), (self.uid, 250000, 25000000, "payme", "pending"))

    def test_uzs_tiyin_conversion_is_explicit_and_single_step(self):
        self.assertEqual(payme.TIYIN_PER_UZS, 100)
        self.assertEqual(payme.uzs_to_tiyin(1000), 100000)  # docs: 100020 = 1000 UZS 20 tiyin
        self.assertEqual(payme.uzs_to_tiyin(100000), 10000000)
        dep = self.create_deposit(100000).get_json()
        self.assertEqual(dep["amount"], 100000)  # API/UI stay in UZS
        self.assertEqual(self.sent[0][1]["request"]["amount"], 10000000)  # Payme gets tiyin
        row = main.db.q("SELECT amount_uzs,amount_minor FROM wallet_deposits WHERE deposit_uuid=?", (dep["deposit_id"],)).fetchone()
        self.assertEqual(tuple(row), (100000, 10000000))
        # Payme echoing UZS instead of tiyin (no x100) is a mismatch, never a credit
        wrong_unit = self.callback_payload(dep["deposit_id"], 100000, amount="100000", actual_amount="100000", payment_id=11)
        self.assertEqual(self.send_callback(wrong_unit).get_json()["status"], "amount_mismatch")
        # double conversion (x10 000) is also rejected
        double = self.callback_payload(dep["deposit_id"], 100000, amount="1000000000", actual_amount="1000000000", payment_id=11)
        self.assertEqual(self.send_callback(double).get_json()["status"], "amount_mismatch")
        # actual_amount must equal the stored tiyin amount too
        bad_actual = self.callback_payload(dep["deposit_id"], 100000, actual_amount="9999999", payment_id=11)
        self.assertEqual(self.send_callback(bad_actual).get_json()["status"], "actual_amount_mismatch")
        self.assertEqual(self.balance(), 0)
        ok = self.callback_payload(dep["deposit_id"], 100000, amount="10000000", actual_amount="10000000", payment_id=11)
        self.assertEqual(self.send_callback(ok).status_code, 200)
        self.assertEqual(self.balance(), 100000)  # exactly 100 000 UZS, not 10 000 000
        self.assertEqual(float(self.deposit_txs()[0][0]), 100000.0)

    def test_amount_limit_must_fit_payme_integer_12(self):
        with mock.patch.dict(os.environ, {"PAYME_MAX_AMOUNT_UZS": "20000000000"}):
            self.assertFalse(payme.load_config()["enabled"])

    # ---- final callback-contract checks (HTTP codes, audit trail, retries)
    def events(self, dep):
        return main.db.q("SELECT source,order_status,outcome,http_status,flagged FROM wallet_deposit_events "
                         "WHERE deposit_uuid=? ORDER BY id", (dep,)).fetchall()

    def test_final_every_handled_callback_is_200_and_audited(self):
        dep, body = self.pay(100000)
        first = self.send_callback(body)
        dup = self.send_callback(body)
        self.assertEqual((first.status_code, dup.status_code), (200, 200))
        self.assertEqual(len(self.deposit_txs()), 1)  # duplicate callback -> no second wallet transaction
        rows = [tuple(r) for r in self.events(dep)]
        self.assertEqual([(r[2], r[3], r[4]) for r in rows], [("credited", 200, 0), ("already_credited", 200, 0)])

    def test_final_flagged_callbacks_are_persisted_and_answer_200(self):
        dep, body = self.pay(100000)
        self.send_callback(self.callback_payload(dep, 100000, status="declined", payment_id=body["payment_id"]))
        late = self.send_callback(body)  # late approved after declined
        self.assertEqual((late.status_code, late.get_json()["flagged"]), (200, True))
        row = main.db.q("SELECT review_required,review_note FROM wallet_deposits WHERE deposit_uuid=?", (dep,)).fetchone()
        self.assertEqual(row[0], 1)
        self.assertIn("invalid_transition", row[1])
        flagged = [tuple(r) for r in self.events(dep) if r[4] == 1]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0][2], "invalid_transition")
        self.assertEqual(self.balance(), 0)
        # the audit row holds no card data / secrets
        cols = [c[1] for c in main.db.q("PRAGMA table_info(wallet_deposit_events)").fetchall()]
        self.assertFalse({"masked_card", "signature", "payload", "card"} & set(cols))

    def test_final_config_problems_and_db_errors_stay_retryable(self):
        dep, body = self.pay(100000)
        wrong_merchant = self.callback_payload(dep, 100000, merchant_id=999, payment_id=body["payment_id"])
        self.assertEqual(self.send_callback(wrong_merchant).status_code, 400)  # operator-fixable: keep retries
        with mock.patch.dict(os.environ, {"PAYME_ENABLED": "0"}):
            self.assertEqual(self.send_callback(body).status_code, 503)
        self.assertEqual(self.balance(), 0)
        self.assertEqual(self.deposit_status(dep), "pending")

    def test_final_partial_reversal_after_credit_is_flagged_without_debit(self):
        dep, body = self.pay(100000)
        self.assertEqual(self.send_callback(body).status_code, 200)
        partial = self.callback_payload(dep, 100000, payment_id=body["payment_id"], reversal_amount="500000")
        for _ in range(2):  # idempotent
            res = self.send_callback(partial)
            self.assertEqual((res.status_code, res.get_json()["status"]), (200, "reversal_flagged"))
        self.assertEqual(self.balance(), 100000)
        self.assertEqual(len(self.deposit_txs()), 1)
        self.assertEqual(self.deposit_status(dep), "credited")
        self.assertEqual(main.db.q("SELECT review_required FROM wallet_deposits WHERE deposit_uuid=?", (dep,)).fetchone()[0], 1)

    def test_final_stale_processing_after_credit_is_harmless(self):
        dep, body = self.pay(100000)
        self.send_callback(body)
        stale = self.callback_payload(dep, 100000, status="processing", payment_id=body["payment_id"])
        res = self.send_callback(stale)
        self.assertEqual((res.status_code, res.get_json()["status"]), (200, "stale_ignored"))
        self.assertEqual(self.deposit_status(dep), "credited")
        self.assertEqual(main.db.q("SELECT review_required FROM wallet_deposits WHERE deposit_uuid=?", (dep,)).fetchone()[0], 0)

    def test_final_callback_never_redirects(self):
        dep, body = self.pay(100000)
        res = self.send_callback(body)
        self.assertNotIn(res.status_code, (301, 302, 303, 307, 308))
        self.assertNotIn("Location", res.headers)

    def test_signature_follows_documented_algorithm(self):
        # docs.payme.uz/api/building-signature documents this exact string for this request.
        params = {"server_callback_url": "http://myshop/callback/", "order_id": "TestOrder2", "currency": "UZS",
                  "merchant_id": 4056281, "order_desc": "Test payment", "amount": 1000}
        self.assertEqual(payme.payme_signature_string("test", params),
                         "test|1000|UZS|4056281|Test payment|TestOrder2|http://myshop/callback/")
        # NOTE: the digest printed in the docs (91ea7da4...) does not equal sha1 of that string; we follow the
        # documented algorithm and the documented string layout and must confirm against the test merchant.
        self.assertEqual(payme.payme_signature("test", params), "e93ea1bf30004ce83308ccd390d12bc39bb10c37")
        # empty / null values are skipped, signature fields are excluded
        self.assertEqual(payme.payme_signature_string("k", {"b": "", "a": 1, "c": None, "signature": "x"}), "k|1")

    def test_signature_string_layout_matches_documented_callback_sample(self):
        # Callback sample from docs.payme.uz/api/callbacks (key masked as ********** in the docs).
        sample = {
            "rrn": "111111111111", "masked_card": "444455XXXXXX1111", "sender_cell_phone": "", "sender_account": "",
            "currency": "UZS", "fee": "", "reversal_amount": "0", "settlement_amount": "0", "actual_amount": "200",
            "response_description": "", "sender_email": "test@test.com", "order_status": "approved",
            "response_status": "success", "order_time": "13.07.2024 01:23:59", "actual_currency": "UZS",
            "order_id": "test33694502191", "tran_type": "purchase", "eci": "5", "settlement_date": "",
            "payment_system": "card", "approval_code": "123456", "merchant_id": 4056281, "settlement_currency": "",
            "payment_id": 805243692, "card_bin": 444455, "response_code": "", "card_type": "VISA", "amount": "200",
            "signature": "b7884b5c4906956fbac4d20390388d913a78c0b0", "product_id": "", "merchant_data": "Test merchant data",
            "rectoken": "", "rectoken_lifetime": "", "verification_status": "", "parent_order_id": "", "fee_oplata": "0",
            "additional_info": "{\"capture_status\": null, \"is_test\": true}",
        }
        docs_string = ("KEY|200|UZS|{\"capture_status\": null, \"is_test\": true}|200|123456|444455|VISA|UZS|5|0|"
                       "444455XXXXXX1111|Test merchant data|4056281|test33694502191|approved|13.07.2024 01:23:59|"
                       "805243692|card|success|0|111111111111|test@test.com|0|purchase")
        self.assertEqual(payme.payme_signature_string("KEY", sample), docs_string)

    def test_unauthenticated_deposit_rejected(self):
        res = self.client.post("/wallet/deposits", json={"amount": 100000})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(self.sent, [])

    def test_invalid_amounts_rejected(self):
        for bad in (0, -1000, 1.5, "abc", "12.5", 999, 50_000_001, True, None, [], {}, "1e9"):
            with main._rate_lock:
                main._rate_buckets.clear()
            res = self.create_deposit(bad)
            self.assertEqual(res.status_code, 400, f"{bad!r} -> {res.status_code}")
        self.assertEqual(self.client.post("/wallet/deposits", headers=self.auth(), json={}).status_code, 400)
        self.assertEqual(self.sent, [])
        self.assertEqual(main.db.q("SELECT COUNT(*) FROM wallet_deposits WHERE user_id=?", (self.uid,)).fetchone()[0], 0)

    def test_cannot_deposit_into_or_read_another_users_wallet(self):
        other_token, other_uid = self.make_user(f"payme_other_{PaymeWalletTopUpTests._seq}")
        res = self.create_deposit(100000, user_id=other_uid)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(main.db.q("SELECT COUNT(*) FROM wallet_deposits WHERE user_id=?", (other_uid,)).fetchone()[0], 0)
        mine, body = self.pay(100000)
        self.assertEqual(self.client.get(f"/wallet/deposits/{mine}", headers=self.auth(other_token)).status_code, 404)
        self.assertEqual(self.client.get(f"/wallet/deposits/{mine}", headers=self.auth()).status_code, 200)
        self.assertEqual(len(self.client.get("/wallet/deposits", headers=self.auth(other_token)).get_json()), 0)
        self.send_callback(body)
        self.assertEqual(self.balance(other_uid), 0)
        self.assertEqual(self.balance(), 100000)

    def test_integration_fails_safe_without_explicit_configuration(self):
        for removal in ("PAYME_ENABLED", "PAYME_MERCHANT_KEY", "PAYME_TEST_MODE", "PAYME_CALLBACK_URL"):
            with mock.patch.dict(os.environ, PAYME_TEST_ENV):
                os.environ.pop(removal, None)
                self.assertEqual(self.create_deposit().status_code, 503, removal)
        self.assertEqual(self.sent, [])

    def test_test_mode_and_test_merchant_refused_in_production(self):
        with mock.patch.dict(os.environ, {"FINJOB_ENV": "production"}):
            self.assertFalse(payme.load_config()["enabled"])
            self.assertEqual(self.create_deposit().status_code, 503)
        with mock.patch.dict(os.environ, {"FINJOB_ENV": "production", "PAYME_TEST_MODE": "0"}):
            self.assertFalse(payme.load_config()["enabled"])  # public test merchant id in live mode
        live_ok = {"FINJOB_ENV": "production", "PAYME_TEST_MODE": "0", "PAYME_MERCHANT_ID": "123456"}
        with mock.patch.dict(os.environ, live_ok):
            self.assertTrue(payme.load_config()["enabled"])

    def test_test_deposit_cannot_be_completed_in_live_mode(self):
        dep = self.create_deposit(100000).get_json()["deposit_id"]
        with mock.patch.dict(os.environ, {"PAYME_TEST_MODE": "0", "PAYME_MERCHANT_ID": "123456"}):
            res = self.send_callback(self.callback_payload(dep, 100000, merchant_id=123456))
            self.assertEqual(res.status_code, 400)
        self.assertEqual(self.balance(), 0)

    # ---- callback authentication / validation
    def test_callback_authentication_failures(self):
        dep = self.create_deposit(100000).get_json()["deposit_id"]
        self.assertEqual(self.send_callback(self.callback_payload(dep, 100000, sign=False)).status_code, 403)
        wrong_sig = self.callback_payload(dep, 100000)
        wrong_sig["signature"] = "0" * 40
        self.assertEqual(self.send_callback(wrong_sig).status_code, 403)
        tampered = self.callback_payload(dep, 100000)
        tampered["amount"] = "1"  # tampered after signing
        self.assertEqual(self.send_callback(tampered).status_code, 403)
        wrong_key = self.callback_payload(dep, 100000, sign=False)
        wrong_key["signature"] = payme.payme_signature("some-other-key", wrong_key)
        self.assertEqual(self.send_callback(wrong_key).status_code, 403)
        self.assertEqual(self.client.post("/payments/payme/callback", data="not json",
                                          content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post("/payments/payme/callback", json=[1, 2]).status_code, 400)
        self.assertEqual(self.balance(), 0)
        self.assertEqual(self.deposit_status(dep), "pending")

    def test_callback_rejected_when_integration_disabled(self):
        dep, body = self.pay(100000)
        with mock.patch.dict(os.environ, {"PAYME_ENABLED": "0"}):
            self.assertEqual(self.send_callback(body).status_code, 503)
        self.assertEqual(self.balance(), 0)

    def test_callback_rejects_incorrect_amount_merchant_currency_and_payment_id(self):
        dep = self.create_deposit(100000).get_json()["deposit_id"]
        cases = [
            self.callback_payload(dep, 100000, amount="9999999"),
            self.callback_payload(dep, 100000, amount="10000000", actual_amount="1"),
            self.callback_payload(dep, 100000, actual_currency="USD"),  # (wrong merchant_id stays 400/retryable: see final tests)
            self.callback_payload(dep, 100000, currency="USD"),
            self.callback_payload(dep, 100000, payment_id="not-a-number"),
            self.callback_payload(dep, 100000, order_status="mystery"),
        ]
        for body in cases:
            res = self.send_callback(body)
            self.assertEqual(res.status_code, 200, body)  # signed + handled: 200 stops Payme retries
            self.assertTrue(res.get_json()["flagged"], body)
        self.assertEqual(self.balance(), 0)
        self.assertEqual(self.deposit_status(dep), "pending")

    def test_callback_rejects_unknown_merchant_transaction_id(self):
        for order_id in ("a" * 32, "unknown-order", "", "1' OR '1'='1"):
            res = self.send_callback(self.callback_payload(order_id, 100000))
            self.assertEqual(res.status_code, 200, order_id)
            self.assertTrue(res.get_json()["flagged"])
            self.assertEqual(res.get_json()["status"], "unknown_order")
        self.assertEqual(self.balance(), 0)

    def test_callback_rejects_mismatching_provider_payment_id(self):
        dep, body = self.pay(100000)
        processing = self.callback_payload(dep, 100000, status="processing", payment_id=body["payment_id"])
        self.assertEqual(self.send_callback(processing).status_code, 200)  # first signed event fixes the id
        res = self.send_callback(self.callback_payload(dep, 100000, payment_id=1))
        self.assertEqual((res.status_code, res.get_json()["status"]), (200, "payment_id_mismatch"))
        self.assertEqual(self.balance(), 0)

    def test_audit_non_ascii_signature_is_rejected_not_500(self):
        dep, body = self.pay(100000)
        res = self.send_callback(dict(body, signature="\u00e9\u4e2d" * 10))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.balance(), 0)

    def test_audit_response_status_must_be_success(self):
        dep, body = self.pay(100000)
        for bad in ("failure", "", "weird"):
            res = self.send_callback(self.callback_payload(dep, 100000, payment_id=body["payment_id"], response_status=bad))
            self.assertEqual((res.status_code, res.get_json()["flagged"]), (200, True), bad)
        self.assertEqual(self.balance(), 0)
        self.assertEqual(self.deposit_status(dep), "pending")

    def test_audit_approved_with_reversal_amount_is_not_credited(self):
        dep, body = self.pay(100000, reversal_amount="500")
        res = self.send_callback(body)
        self.assertEqual((res.status_code, res.get_json()["status"]), (200, "reversal_present"))
        self.assertEqual(self.balance(), 0)
        self.assertEqual(main.db.q("SELECT review_required FROM wallet_deposits WHERE deposit_uuid=?", (dep,)).fetchone()[0], 1)
        # "0" reversal (as in the documented sample) is normal
        dep2, body2 = self.pay(100000, reversal_amount="0")
        self.assertEqual(self.send_callback(body2).status_code, 200)
        self.assertEqual(self.balance(), 100000)

    def test_audit_order_request_has_no_version_and_payment_id_not_stored_at_creation(self):
        dep, _ = self.pay(100000)
        req = self.sent[0][1]["request"]
        self.assertNotIn("version", req)
        self.assertEqual(req["delayed"], "N")
        self.assertIsNone(main.db.q("SELECT provider_payment_id FROM wallet_deposits WHERE deposit_uuid=?", (dep,)).fetchone()[0])

    # ---- success path, idempotency
    def test_successful_callback_credits_wallet_exactly_once_with_history(self):
        dep, body = self.pay(250000)
        res = self.send_callback(body)
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertEqual(res.get_json()["status"], "credited")
        self.assertEqual(self.balance(), 250000)
        txs = self.deposit_txs()
        self.assertEqual(len(txs), 1)
        self.assertEqual(float(txs[0][0]), 250000.0)
        self.assertEqual(float(txs[0][1]), 250000.0)
        self.assertEqual(self.deposit_status(dep), "credited")
        wallet = self.client.get("/wallet", headers=self.auth()).get_json()
        self.assertEqual(wallet["balance"], 250000)
        self.assertEqual([t["type"] for t in wallet["transactions"]], ["deposit"])
        status = self.client.get(f"/wallet/deposits/{dep}", headers=self.auth()).get_json()
        self.assertEqual(status["status"], "credited")
        self.assertIsNotNone(status["credited_at"])

    def test_duplicate_callbacks_are_idempotent(self):
        dep, body = self.pay(100000)
        results = [self.send_callback(body) for _ in range(4)]
        self.assertTrue(all(r.status_code == 200 for r in results))
        self.assertEqual([r.get_json()["status"] for r in results], ["credited"] + ["already_credited"] * 3)
        self.assertEqual(self.balance(), 100000)
        self.assertEqual(len(self.deposit_txs()), 1)

    def test_concurrent_callbacks_credit_once(self):
        dep, body = self.pay(300000)
        codes = []

        def hit():
            with app.test_client() as c:
                codes.append(c.post("/payments/payme/callback", json=body).status_code)

        threads = [threading.Thread(target=hit) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertTrue(all(code in (200, 500) for code in codes), codes)
        self.assertIn(200, codes)
        self.assertEqual(self.balance(), 300000)
        self.assertEqual(len(self.deposit_txs()), 1)

    def test_processing_then_approved_flow(self):
        dep, body = self.pay(120000)
        processing = self.callback_payload(dep, 120000, status="processing", payment_id=body["payment_id"])
        self.assertEqual(self.send_callback(processing).status_code, 200)
        self.assertEqual(self.deposit_status(dep), "processing")
        self.assertEqual(self.balance(), 0)
        self.assertEqual(self.send_callback(body).status_code, 200)
        self.assertEqual(self.balance(), 120000)

    def test_two_deposits_are_independent(self):
        dep1, body1 = self.pay(100000)
        dep2, body2 = self.pay(150000)
        self.send_callback(body1)
        self.send_callback(body2)
        self.send_callback(body1)
        self.assertEqual(self.balance(), 250000)
        self.assertEqual(len(self.deposit_txs()), 2)

    # ---- invalid transitions, cancel, expiry
    def test_declined_deposits_never_credit(self):
        dep, body = self.pay(100000)
        declined = self.callback_payload(dep, 100000, status="declined", payment_id=body["payment_id"],
                                         response_description="General decline", response_code=1000)
        self.assertEqual(self.send_callback(declined).status_code, 200)
        self.assertEqual(self.send_callback(declined).status_code, 200)  # idempotent
        self.assertEqual(self.deposit_status(dep), "declined")
        self.assertEqual(self.balance(), 0)
        self.assertEqual(self.deposit_txs(), [])
        row = main.db.q("SELECT cancelled_at,cancel_reason FROM wallet_deposits WHERE deposit_uuid=?", (dep,)).fetchone()
        self.assertTrue(row[0] and row[1])

    def test_invalid_state_transitions_are_rejected_and_flagged(self):
        dep, body = self.pay(100000)  # declined -> approved
        self.send_callback(self.callback_payload(dep, 100000, status="declined", payment_id=body["payment_id"]))
        res = self.send_callback(body)
        self.assertEqual((res.status_code, res.get_json()["status"]), (200, "invalid_transition"))
        self.assertEqual(self.balance(), 0)
        self.assertEqual(main.db.q("SELECT review_required FROM wallet_deposits WHERE deposit_uuid=?", (dep,)).fetchone()[0], 1)
        dep2, body2 = self.pay(50000)  # credited -> declined/expired must not alter the credit
        self.assertEqual(self.send_callback(body2).status_code, 200)
        for late in ("declined", "expired"):
            res = self.send_callback(self.callback_payload(dep2, 50000, status=late, payment_id=body2["payment_id"]))
            self.assertEqual((res.status_code, res.get_json()["status"]), (200, "invalid_transition"))
        self.assertEqual(self.deposit_status(dep2), "credited")
        self.assertEqual(self.balance(), 50000)

    def test_expired_order_cannot_be_completed_afterwards(self):
        dep, body = self.pay(100000)
        expired = self.callback_payload(dep, 100000, status="expired", payment_id=body["payment_id"])
        self.assertEqual(self.send_callback(expired).status_code, 200)
        self.assertEqual(self.deposit_status(dep), "expired")
        res = self.send_callback(body)  # late approved after expired: not credited, flagged, 200 (no endless retries)
        self.assertEqual((res.status_code, res.get_json()["status"]), (200, "invalid_transition"))
        self.assertEqual(self.balance(), 0)
        self.assertEqual(self.deposit_txs(), [])
        self.assertEqual(main.db.q("SELECT review_required FROM wallet_deposits WHERE deposit_uuid=?", (dep,)).fetchone()[0], 1)

    def test_reversal_after_credit_is_flagged_not_auto_debited(self):
        dep, body = self.pay(100000)
        self.send_callback(body)
        rev = self.callback_payload(dep, 100000, status="reversed", payment_id=body["payment_id"])
        self.assertEqual(self.send_callback(rev).status_code, 200)
        self.assertEqual(self.deposit_status(dep), "reversed")
        self.assertEqual(self.balance(), 100000)
        self.assertEqual(main.db.q("SELECT review_required FROM wallet_deposits WHERE deposit_uuid=?", (dep,)).fetchone()[0], 1)
        self.assertEqual(len(self.deposit_txs()), 1)

    # ---- atomicity
    def test_credit_is_atomic_and_rolls_back_on_failure(self):
        dep, body = self.pay(100000)
        conn = main.db.get_connection()
        conn.execute("""CREATE TRIGGER fail_deposit_tx BEFORE INSERT ON wallet_transactions
                        WHEN NEW.type='deposit' BEGIN SELECT RAISE(ABORT,'boom'); END""")
        conn.commit()
        try:
            with self.assertLogs(app.logger, level="ERROR"):
                res = self.send_callback(body)
            self.assertEqual(res.status_code, 500)
            self.assertEqual(self.balance(), 0)
            self.assertEqual(self.deposit_status(dep), "pending")
        finally:
            conn.execute("DROP TRIGGER fail_deposit_tx")
            conn.commit()
            conn.close()
        self.assertEqual(self.send_callback(body).status_code, 200)  # Payme's retry succeeds
        self.assertEqual(self.balance(), 100000)
        self.assertEqual(len(self.deposit_txs()), 1)

    # ---- browser return / status reconciliation
    def test_browser_return_never_credits(self):
        dep = self.create_deposit(100000).get_json()["deposit_id"]
        res = self.client.post(f"/wallet/deposits/return?deposit={dep}", data={"order_status": "approved", "amount": "10000000"})
        self.assertEqual(res.status_code, 303)
        self.assertEqual(res.headers["Location"], f"https://app.example.test/profile?payme_deposit={dep}")
        res = self.client.get("/wallet/deposits/return?deposit=https://evil.example")
        self.assertEqual(res.headers["Location"], "https://app.example.test/profile")
        self.assertEqual(self.balance(), 0)
        self.assertEqual(self.deposit_status(dep), "pending")

    def test_status_endpoint_reconciles_with_signed_payme_status_response(self):
        dep, body = self.pay(100000)

        def answer(order_id):
            resp = {k: v for k, v in body.items() if k != "signature"}
            resp["signature"] = payme.payme_signature(PAYME_KEY, resp)
            return {"response": resp}

        self.status_answer = answer
        status = self.client.get(f"/wallet/deposits/{dep}", headers=self.auth()).get_json()
        self.assertEqual(status["status"], "credited")
        self.assertEqual(self.balance(), 100000)
        self.client.get(f"/wallet/deposits/{dep}", headers=self.auth())
        self.assertEqual(len(self.deposit_txs()), 1)

    def test_status_endpoint_ignores_unsigned_payme_status_response(self):
        dep, body = self.pay(100000)
        forged = {k: v for k, v in body.items() if k != "signature"}
        forged["signature"] = "f" * 40
        self.status_answer = lambda order_id: {"response": forged}
        status = self.client.get(f"/wallet/deposits/{dep}", headers=self.auth()).get_json()
        self.assertEqual(status["status"], "pending")
        self.assertEqual(self.balance(), 0)

    def test_payme_failure_marks_deposit_failed_and_credits_nothing(self):
        with mock.patch.object(payme, "_http_post_json", side_effect=OSError("network down")):
            res = self.create_deposit(100000)
        self.assertEqual(res.status_code, 502)
        row = main.db.q("SELECT status FROM wallet_deposits WHERE user_id=?", (self.uid,)).fetchone()
        self.assertEqual(row[0], "failed")
        self.assertEqual(self.balance(), 0)

    def test_checkout_url_on_unexpected_host_is_refused(self):
        evil = {"response": {"response_status": "success", "checkout_url": "https://evil.example/pay", "payment_id": "1"}}
        with mock.patch.object(payme, "_http_post_json", return_value=evil):
            self.assertEqual(self.create_deposit(100000).status_code, 502)

    def test_open_deposit_limit(self):
        for _ in range(5):
            self.assertEqual(self.create_deposit(100000).status_code, 201)
        self.assertEqual(self.create_deposit(100000).status_code, 429)

    def test_unique_provider_payment_id_constraint(self):
        dep1, body1 = self.pay(100000)
        self.assertEqual(self.send_callback(body1).status_code, 200)  # signed callback stores the id
        dep2 = self.create_deposit(100000).get_json()["deposit_id"]
        with self.assertRaises(Exception):
            main.db.q("UPDATE wallet_deposits SET provider_payment_id=? WHERE deposit_uuid=?",
                      (str(body1["payment_id"]), dep2)).close()

    def test_deposit_config_exposes_no_secrets(self):
        data = self.client.get("/wallet/deposit-config", headers=self.auth()).get_json()
        self.assertTrue(data["enabled"])
        self.assertNotIn(PAYME_KEY, _json.dumps(data))
        self.assertNotIn("merchant_key", data)

    def test_invalid_signature_log_contains_no_secrets(self):
        dep, body = self.pay(100000)
        with self.assertLogs(app.logger, level="WARNING") as captured:
            self.send_callback(dict(body, signature="0" * 40))
        joined = "\n".join(captured.output)
        self.assertNotIn(PAYME_KEY, joined)
        self.assertNotIn("0" * 40, joined)

    # ---- existing wallet / escrow / refund behaviour on top of a Payme deposit
    def test_deposit_then_job_payment_release_refund_and_history(self):
        creator_token, creator_id = self.token, self.uid
        worker_token, worker_id = self.make_user(f"payme_worker_{PaymeWalletTopUpTests._seq}")
        dep, body = self.pay(1000000)
        self.assertEqual(self.send_callback(body).status_code, 200)

        def make_job(title, price):
            self.client.post("/job", headers=self.auth(creator_token), json={
                "service_id": 1, "title": title, "description": "Payme E2E job", "price": price, "location": "Remote"})
            jobs = self.client.get("/jobs", headers=self.auth(creator_token)).get_json()
            job_id = [j["id"] for j in jobs if j["title"] == title][0]
            self.assertEqual(self.client.post("/accept_job", headers=self.auth(worker_token), json={"job_id": job_id}).status_code, 200)
            return job_id

        # job paid from wallet balance (escrow hold), then released to the worker at the configured commission
        job_id = make_job("Payme E2E release", 500000)
        pay = self.client.post(f"/payments/dummy/{job_id}", headers=self.auth(creator_token))
        self.assertEqual(pay.status_code, 200, pay.get_json())
        self.assertEqual(self.balance(creator_id), 500000)
        self.client.post("/finish_job", headers=self.auth(creator_token), json={"job_id": job_id})
        fin = self.client.post("/finish_job", headers=self.auth(worker_token), json={"job_id": job_id})
        self.assertTrue(fin.get_json()["finished"])
        commission = float(main.db.q("SELECT value FROM platform_settings WHERE key='commission_percent'").fetchone()[0])
        self.assertEqual(commission, 2.0)  # fresh-install default
        self.assertAlmostEqual(self.balance(worker_id), 500000 * (1 - commission / 100), places=2)

        # refund path returns held funds to the payer
        job2 = make_job("Payme E2E refund", 200000)
        self.assertEqual(self.client.post(f"/payments/dummy/{job2}", headers=self.auth(creator_token)).status_code, 200)
        self.assertEqual(self.balance(creator_id), 300000)
        admin_token = self.client.post("/login", json={"username": "payme_first_admin", "password": "Password123!"}).get_json()["token"]
        refund = self.client.post(f"/payments/refund/{job2}", headers=self.auth(admin_token))
        self.assertEqual(refund.status_code, 200, refund.get_json())
        self.assertEqual(self.balance(creator_id), 500000)

        # history: deposit + hold + refund for the creator, nothing lost
        types = [t["type"] for t in self.client.get("/wallet", headers=self.auth(creator_token)).get_json()["transactions"]]
        for expected in ("deposit", "payment_hold", "payment_refund"):
            self.assertIn(expected, types)
        self.assertEqual(types.count("deposit"), 1)

    def test_non_admin_cannot_top_up_wallets_directly(self):
        self.assertEqual(self.client.post("/admin/wallet/1", headers=self.auth(), json={"amount": 1000}).status_code, 403)
        self.assertEqual(self.balance(), 0)

    # =====================================================================================================
    # Integration audit (2026-11): configuration
    # =====================================================================================================
    LIVE_ENV = {"PAYME_TEST_MODE": "0", "PAYME_MERCHANT_ID": "123456"}

    def admin_token(self):
        return self.client.post("/login", json={"username": "payme_first_admin", "password": "Password123!"}).get_json()["token"]

    def test_cfg_non_integer_or_invalid_limits_disable_integration(self):
        for name in ("PAYME_MIN_AMOUNT_UZS", "PAYME_MAX_AMOUNT_UZS", "PAYME_ORDER_LIFETIME_SECONDS", "PAYME_MAX_OPEN_DEPOSITS"):
            with mock.patch.dict(os.environ, {name: "10k"}):
                cfg = payme.load_config()
                self.assertFalse(cfg["enabled"], name)
                self.assertTrue(any(name in p for p in cfg["problems"]), cfg["problems"])
        for env in ({"PAYME_MAX_OPEN_DEPOSITS": "0"}, {"PAYME_MIN_AMOUNT_UZS": "0"},
                    {"PAYME_MIN_AMOUNT_UZS": "5000", "PAYME_MAX_AMOUNT_UZS": "4000"}):
            with mock.patch.dict(os.environ, env):
                self.assertFalse(payme.load_config()["enabled"], env)

    def test_cfg_invalid_ids_and_urls_disable_integration(self):
        for env in ({"PAYME_MERCHANT_ID": "abc"}, {"PAYME_MERCHANT_ID": ""}, {"PAYME_MERCHANT_KEY": ""},
                    {"PAYME_CALLBACK_URL": "not-a-url"}, {"PAYME_RESPONSE_URL": "javascript:alert(1)"},
                    {"PAYME_FRONTEND_RETURN_URL": "//evil.example/profile"},
                    {"PAYME_FRONTEND_RETURN_URL": "https://user:pw@app.example.test/profile"},
                    {"PAYME_CHECKOUT_BASE_URL": "http://pay.payme.uz"}, {"PAYME_ENABLED": "0"}):
            with mock.patch.dict(os.environ, env):
                self.assertFalse(payme.load_config()["enabled"], env)
                self.assertEqual(self.create_deposit(100000).status_code, 503, env)
            with main._rate_lock:
                main._rate_buckets.clear()
        self.assertEqual(self.sent, [])

    def test_cfg_test_mode_accepts_dev_urls_but_live_mode_is_strict(self):
        dev = {"PAYME_CALLBACK_URL": "http://localhost:5000/payments/payme/callback",
               "PAYME_RESPONSE_URL": "http://localhost:5000/wallet/deposits/return",
               "PAYME_FRONTEND_RETURN_URL": "http://localhost:5173/profile"}
        with mock.patch.dict(os.environ, dev):
            self.assertTrue(payme.load_config()["enabled"])  # local sandbox testing
        with mock.patch.dict(os.environ, self.LIVE_ENV):
            self.assertTrue(payme.load_config()["enabled"])
        for extra in ({"PAYME_MERCHANT_KEY": "test"}, {"PAYME_MERCHANT_KEY": "testcredit"},
                      {"PAYME_MERCHANT_ID": payme.PAYME_TEST_MERCHANT_ID},
                      {"PAYME_CHECKOUT_BASE_URL": "https://payments.example.test"},
                      dict(dev)):
            with mock.patch.dict(os.environ, {**self.LIVE_ENV, **extra}):
                self.assertFalse(payme.load_config()["enabled"], extra)
        with mock.patch.dict(os.environ, {"FINJOB_ENV": "production", **self.LIVE_ENV, **dev}):
            self.assertFalse(payme.load_config()["enabled"])  # production needs https everywhere
        with mock.patch.dict(os.environ, {"FINJOB_ENV": "production", **self.LIVE_ENV}):
            self.assertTrue(payme.load_config()["enabled"])

    def test_cfg_diagnostics_never_expose_the_key(self):
        secret = "super-secret-merchant-key-123"
        with mock.patch.dict(os.environ, {**self.LIVE_ENV, "PAYME_MERCHANT_KEY": secret, "PAYME_MAX_OPEN_DEPOSITS": "x"}):
            cfg = payme.load_config()
            self.assertFalse(cfg["enabled"])
            text = _json.dumps(payme.config_summary(cfg))
            self.assertNotIn(secret, text)
            self.assertEqual(payme.config_summary(cfg)["merchant_id"], "**3456")
            admin = self.client.get("/admin/payme/diagnostics", headers=self.auth(self.admin_token()))
            self.assertEqual(admin.status_code, 200)
            self.assertNotIn(secret, admin.get_data(as_text=True))
            self.assertFalse(admin.get_json()["config"]["enabled"])
            self.assertTrue(admin.get_json()["config"]["problems"])
            self.assertNotIn(secret, self.client.get("/wallet/deposit-config", headers=self.auth()).get_data(as_text=True))
        self.assertEqual(self.client.get("/admin/payme/diagnostics", headers=self.auth()).status_code, 403)
        self.assertEqual(self.client.get("/admin/wallet-deposits", headers=self.auth()).status_code, 403)
        self.assertEqual(self.client.get("/admin/payme/diagnostics").status_code, 401)

    # =====================================================================================================
    # checkout creation
    # =====================================================================================================
    def test_checkout_payme_error_answer_fails_safely_and_logs_code_without_secrets(self):
        fail = {"response": {"error_code": 1014, "error_message": "Invalid signature", "request_id": "x",
                             "response_status": "failure"}}
        with mock.patch.object(payme, "_http_post_json", return_value=fail), \
                self.assertLogs(app.logger, level="ERROR") as logs:
            res = self.create_deposit(100000)
        self.assertEqual((res.status_code, res.get_json()["code"]), (502, "checkout_failed"))
        self.assertNotIn("checkout_url", res.get_json())
        joined = "\n".join(logs.output)
        self.assertIn("payme_error_1014", joined)
        self.assertNotIn(PAYME_KEY, joined)
        self.assertEqual(main.db.q("SELECT status FROM wallet_deposits WHERE user_id=?", (self.uid,)).fetchone()[0], "failed")
        self.assertEqual(self.balance(), 0)

    def test_checkout_network_timeout_and_malformed_answers_fail_safely(self):
        import socket
        import urllib.error
        effects = [socket.timeout("timed out"), TimeoutError(), urllib.error.URLError("dns"), ConnectionResetError(),
                   ValueError("not json"), payme.PaymeAPIError("http_502")]
        answers = [None, [], {"response": "x"}, {"response": {"response_status": "success"}},
                   {"response": {"response_status": "success", "checkout_url": "http://pay.payme.uz/x"}},
                   {"response": {"response_status": "success", "checkout_url": "https://pay.payme.uz.evil.example/x"}},
                   {"response": {"response_status": "success", "checkout_url": "https://pay.payme.uz@evil.example/x"}},
                   {"response": {"response_status": "success", "checkout_url": "javascript:alert(1)"}},
                   {"response": {"response_status": "success", "checkout_url": ["https://pay.payme.uz/x"]}}]
        cases = [{"side_effect": e} for e in effects] + [{"return_value": a} for a in answers]
        for case in cases:
            with main._rate_lock:
                main._rate_buckets.clear()
            with mock.patch.object(payme, "_http_post_json", **case):
                res = self.create_deposit(100000)
            self.assertEqual(res.status_code, 502, case)
            self.assertNotIn("checkout_url", res.get_json() or {})
        statuses = {r[0] for r in main.db.q("SELECT status FROM wallet_deposits WHERE user_id=?", (self.uid,)).fetchall()}
        self.assertEqual(statuses, {"failed"})
        self.assertEqual(self.balance(), 0)

    def test_checkout_request_matches_docs_reference_signature_with_unicode(self):
        dep = self.create_deposit(1000).get_json()
        req = self.sent[0][1]["request"]
        self.assertIn("‘", req["order_desc"])  # non-ASCII text is part of the signed string
        self.assertEqual(req["signature"], _docs_reference_signature(PAYME_KEY, req))
        self.assertEqual(req["amount"], 100000)  # 1000 UZS = 100 000 tiyin
        self.assertEqual((req["currency"], req["merchant_id"], req["order_id"]), ("UZS", 4056281, dep["deposit_id"]))
        self.assertEqual(req["server_callback_url"], PAYME_TEST_ENV["PAYME_CALLBACK_URL"])
        self.assertTrue(req["response_url"].startswith(PAYME_TEST_ENV["PAYME_RESPONSE_URL"] + "?deposit="))
        self.assertEqual(self.sent[0][0], "https://pay.payme.uz/api/checkout/url")

    def test_http_client_sends_utf8_json_envelope_and_reads_error_bodies(self):
        import urllib.error
        captured = {}

        class FakeResponse:
            def __init__(self, body):
                self.body = body

            def read(self, n=-1):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout):
            captured["data"], captured["headers"], captured["timeout"] = req.data, dict(req.header_items()), timeout
            return FakeResponse('{"response": {"response_status": "success", "checkout_url": "https://pay.payme.uz/c"}}'.encode())

        body = {"request": {"order_desc": "FinJob hamyonini to‘ldirish", "amount": 100000}}
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            answer = _REAL_HTTP_POST_JSON("https://pay.payme.uz/api/checkout/url", body, timeout=7)
        self.assertEqual(answer["response"]["checkout_url"], "https://pay.payme.uz/c")
        self.assertEqual(_json.loads(captured["data"].decode("utf-8")), body)
        self.assertIn("‘".encode("utf-8"), captured["data"])  # raw UTF-8, the same bytes that were signed
        self.assertIn("application/json", captured["headers"]["Content-type"])
        self.assertEqual(captured["timeout"], 7)

        def http_error(body_bytes):
            return urllib.error.HTTPError("https://pay.payme.uz", 400, "Bad", {}, BytesIO(body_bytes))

        with mock.patch("urllib.request.urlopen", side_effect=http_error(b'{"response": {"response_status": "failure", "error_code": 1008}}')):
            self.assertEqual(_REAL_HTTP_POST_JSON("https://pay.payme.uz/x", {})["response"]["error_code"], 1008)
        with mock.patch("urllib.request.urlopen", side_effect=http_error(b"<html>bad gateway</html>")):
            with self.assertRaises(payme.PaymeAPIError):
                _REAL_HTTP_POST_JSON("https://pay.payme.uz/x", {})

    # =====================================================================================================
    # signature, against documentation-shaped payloads
    # =====================================================================================================
    def test_sig_equals_docs_reference_on_documented_callback_shape(self):
        payload = _docs_shaped_callback("a" * 32, 100020, 805243692)
        self.assertEqual(payme.payme_signature(PAYME_KEY, payload), _docs_reference_signature(PAYME_KEY, payload))
        string = payme.payme_signature_string("K", payload)
        self.assertIn("|" + payload["additional_info"] + "|", string)  # unused-by-FinJob fields are still signed
        self.assertIn("|100020|", string)                        # tiyin amount as Payme sends it
        self.assertIn("|FinJob hamyoni — to‘ldirish|", string)  # unicode merchant_data
        self.assertEqual(string.count("|0|"), 3)                 # fee_oplata, reversal_amount, settlement_amount "0" kept
        # zero values are kept, empty / None are skipped, signature fields are excluded
        self.assertEqual(payme.payme_signature_string("k", {"a": 0, "b": "0", "c": "", "d": None}), "k|0|0")
        with_diag = dict(payload, response_signature_string="k|whatever", signature="f" * 40)
        self.assertEqual(payme.payme_signature(PAYME_KEY, with_diag), payme.payme_signature(PAYME_KEY, payload))

    def test_sig_verification_edge_cases(self):
        payload = _docs_shaped_callback("b" * 32, 100000, 1)
        sig = payme.payme_signature(PAYME_KEY, payload)
        self.assertTrue(payme.verify_signature(PAYME_KEY, dict(payload, signature=sig)))
        self.assertTrue(payme.verify_signature(PAYME_KEY, dict(payload, signature=sig.upper())))  # hex case-insensitive
        self.assertTrue(payme.verify_signature(PAYME_KEY, dict(payload, signature=sig, response_signature_string="x")))
        for bad in ("", None, sig[:-1], sig + "0", "g" * 40, " " * 40):
            self.assertFalse(payme.verify_signature(PAYME_KEY, dict(payload, signature=bad)), bad)
        self.assertFalse(payme.verify_signature("", dict(payload, signature=sig)))
        # a field Payme adds in the future is signed too: dropping or adding it breaks the signature
        extended = dict(payload, new_payme_field="x")
        self.assertFalse(payme.verify_signature(PAYME_KEY, dict(extended, signature=sig)))
        # changing a "0" to "" (or 0 to missing) changes the signature
        self.assertFalse(payme.verify_signature(PAYME_KEY, dict(payload, fee_oplata="", signature=sig)))

    # =====================================================================================================
    # callbacks
    # =====================================================================================================
    def post_raw_json(self, payload):
        return self.client.post("/payments/payme/callback", data=_json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                content_type="application/json; charset=UTF-8")

    def test_callback_documentation_shaped_approved_credits_exactly_once(self):
        dep = self.create_deposit(1000).get_json()["deposit_id"]
        payload = _docs_shaped_callback(dep, 100000, self._next_payment_id())
        payload["response_signature_string"] = "**********|diagnostic only"
        payload["signature"] = _docs_reference_signature(PAYME_KEY, {k: v for k, v in payload.items()
                                                                     if k != "response_signature_string"})
        res = self.post_raw_json(payload)
        self.assertEqual((res.status_code, res.get_json()["status"]), (200, "credited"))
        self.assertEqual(self.balance(), 1000)  # 100 000 tiyin = 1000 UZS
        self.assertEqual(self.post_raw_json(payload).get_json()["status"], "already_credited")
        self.assertEqual(len(self.deposit_txs()), 1)
        row = main.db.q("SELECT provider_payment_id,status,review_required FROM wallet_deposits WHERE deposit_uuid=?",
                        (dep,)).fetchone()
        self.assertEqual(tuple(row), (str(payload["payment_id"]), "credited", 0))

    def test_callback_tiyin_precision_is_exact(self):
        # 100020 tiyin = 1000 UZS 20 tiyin: FinJob never creates such an order, so it must not match 1000 UZS
        dep = self.create_deposit(1000).get_json()["deposit_id"]
        payload = _docs_shaped_callback(dep, 100020, self._next_payment_id())
        payload["signature"] = payme.payme_signature(PAYME_KEY, payload)
        self.assertEqual(self.post_raw_json(payload).get_json()["status"], "amount_mismatch")
        for float_amount in (1000.0, 100000.0):
            p = dict(payload, amount=float_amount, actual_amount=float_amount)
            p["signature"] = payme.payme_signature(PAYME_KEY, p)
            self.assertEqual(self.post_raw_json(p).get_json()["status"], "amount_mismatch")
        self.assertEqual(self.balance(), 0)

    def test_callback_form_encoded_is_accepted(self):
        dep, body = self.pay(100000)
        res = self.client.post("/payments/payme/callback", data={k: str(v) for k, v in body.items()})
        self.assertEqual((res.status_code, res.get_json()["status"]), (200, "credited"))
        self.assertEqual(self.balance(), 100000)

    def test_callback_wrapped_in_response_envelope_is_accepted(self):
        dep, body = self.pay(100000)
        res = self.client.post("/payments/payme/callback", json={"response": body})
        self.assertEqual(res.get_json()["status"], "credited")

    def test_callback_missing_or_forged_signature_never_credits(self):
        dep, body = self.pay(100000)
        for forged in ({k: v for k, v in body.items() if k != "signature"}, dict(body, signature=""),
                       dict(body, signature=None), dict(body, order_status="approved", amount="1", actual_amount="1")):
            self.assertEqual(self.send_callback(forged).status_code, 403)
        replay_other = self.callback_payload(self.create_deposit(100000).get_json()["deposit_id"], 100000)
        replay_other["order_id"] = dep  # signed for another order, replayed against this one
        self.assertEqual(self.send_callback(replay_other).status_code, 403)
        self.assertEqual(self.balance(), 0)
        self.assertEqual(self.deposit_status(dep), "pending")

    def test_callback_live_mode_rejects_payment_marked_as_test(self):
        with mock.patch.dict(os.environ, self.LIVE_ENV):
            dep = self.create_deposit(1000).get_json()["deposit_id"]
            payload = _docs_shaped_callback(dep, 100000, self._next_payment_id(), merchant_id=123456, is_test=True)
            payload["signature"] = payme.payme_signature(PAYME_KEY, payload)
            res = self.post_raw_json(payload)
            self.assertEqual((res.status_code, res.get_json()["status"]), (200, "test_payment_in_live_mode"))
            self.assertTrue(res.get_json()["flagged"])
            self.assertEqual(self.balance(), 0)
            genuine = _docs_shaped_callback(dep, 100000, payload["payment_id"], merchant_id=123456, is_test=False)
            genuine["signature"] = payme.payme_signature(PAYME_KEY, genuine)
            self.assertEqual(self.post_raw_json(genuine).get_json()["status"], "credited")
        self.assertEqual(self.balance(), 1000)

    def test_callback_test_deposit_in_live_mode_and_live_deposit_in_test_mode_never_mix(self):
        test_dep, test_body = self.pay(100000)
        with mock.patch.dict(os.environ, self.LIVE_ENV):
            live_dep = self.create_deposit(100000).get_json()["deposit_id"]
            res = self.send_callback(self.callback_payload(test_dep, 100000, merchant_id=123456,
                                                           payment_id=test_body["payment_id"]))
            self.assertEqual((res.status_code, res.get_json()["status"]), (400, "mode_mismatch"))
        res = self.send_callback(self.callback_payload(live_dep, 100000, payment_id=self._next_payment_id()))
        self.assertEqual((res.status_code, res.get_json()["status"]), (400, "mode_mismatch"))
        self.assertEqual(self.balance(), 0)

    def test_callback_reversed_before_credit_closes_deposit_without_money(self):
        dep, body = self.pay(100000)
        rev = self.callback_payload(dep, 100000, status="reversed", payment_id=body["payment_id"],
                                    actual_amount="10000000", reversal_amount="10000000")
        res = self.send_callback(rev)
        self.assertEqual((res.status_code, res.get_json()["status"]), (200, "reversed"))
        self.assertEqual(self.send_callback(rev).get_json()["status"], "already_reversed")
        self.assertEqual(self.deposit_status(dep), "reversed")
        late = self.send_callback(body)  # a late "approved" must not credit a reversed order
        self.assertEqual((late.status_code, late.get_json()["status"]), (200, "invalid_transition"))
        self.assertEqual(self.balance(), 0)
        self.assertEqual(self.deposit_txs(), [])

    def test_callback_declined_expired_processing_states(self):
        for status in ("declined", "expired"):
            dep, body = self.pay(100000)
            p = _docs_shaped_callback(dep, 10000000, body["payment_id"], status=status)
            p["response_description"] = "General decline" if status == "declined" else ""
            p["signature"] = payme.payme_signature(PAYME_KEY, p)
            self.assertEqual(self.post_raw_json(p).get_json()["status"], status)
            view = self.client.get(f"/wallet/deposits/{dep}", headers=self.auth()).get_json()
            self.assertEqual((view["status"], view["deposit_status"]), (status, status))  # frontend reads deposit_status
            self.assertNotIn("checkout_url", view)
        dep, body = self.pay(100000)
        p = _docs_shaped_callback(dep, 10000000, body["payment_id"], status="processing")
        p["signature"] = payme.payme_signature(PAYME_KEY, p)
        self.assertEqual(self.post_raw_json(p).get_json()["status"], "noted")
        view = self.client.get(f"/wallet/deposits/{dep}", headers=self.auth()).get_json()
        self.assertEqual(view["status"], "processing")
        self.assertTrue(view["checkout_url"].startswith("https://pay.payme.uz/"))
        self.assertEqual(self.balance(), 0)

    def test_callback_database_failure_is_retryable_and_leaves_nothing_half_done(self):
        import sqlite3
        dep, body = self.pay(100000)
        with mock.patch.object(main.db, "get_connection", side_effect=sqlite3.OperationalError("database is locked")), \
                self.assertLogs(app.logger, level="ERROR"):
            res = self.send_callback(body)
        self.assertEqual((res.status_code, res.get_json()["status"]), (500, "temporary_error"))
        self.assertNotIn("flagged", res.get_json())
        self.assertEqual(self.deposit_status(dep), "pending")
        self.assertEqual(self.balance(), 0)
        self.assertEqual(self.send_callback(body).get_json()["status"], "credited")  # Payme's retry
        self.assertEqual(len(self.deposit_txs()), 1)

    def test_callback_ip_allowlist(self):
        dep, body = self.pay(100000)
        with mock.patch.dict(os.environ, {"PAYME_CALLBACK_IP_ALLOWLIST": "54.154.216.60,3.75.125.89"}):
            self.assertEqual(self.send_callback(body).status_code, 403)
            res = self.client.post("/payments/payme/callback", json=body, environ_base={"REMOTE_ADDR": "3.75.125.89"})
            self.assertEqual(res.get_json()["status"], "credited")

    def test_callback_concurrent_different_valid_payloads_credit_once(self):
        dep, body = self.pay(200000)
        docs = _docs_shaped_callback(dep, 20000000, body["payment_id"])
        docs["signature"] = payme.payme_signature(PAYME_KEY, docs)
        results = []

        def hit(payload):
            with app.test_client() as c:
                r = c.post("/payments/payme/callback", json=payload)
                results.append((r.status_code, r.get_json()["status"]))

        threads = [threading.Thread(target=hit, args=(body if i % 2 else docs,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(1 for r in results if r == (200, "credited")), 1, results)
        self.assertTrue(all(code in (200, 500) for code, _ in results), results)
        self.assertEqual(self.balance(), 200000)
        self.assertEqual(len(self.deposit_txs()), 1)

    # =====================================================================================================
    # status endpoint / reconciliation / review state
    # =====================================================================================================
    def signed_status(self, payload):
        resp = {k: v for k, v in payload.items() if k != "signature"}
        resp["signature"] = payme.payme_signature(PAYME_KEY, resp)
        return {"response": resp}

    def test_status_reconcile_declined_expired_and_reversed(self):
        for status in ("declined", "expired", "reversed"):
            dep, body = self.pay(100000)
            p = _docs_shaped_callback(dep, 10000000, body["payment_id"], status=status)
            self.status_answer = lambda order_id, p=p: self.signed_status(p)
            self.assertEqual(self.client.get(f"/wallet/deposits/{dep}", headers=self.auth()).get_json()["status"], status)
        self.assertEqual(self.balance(), 0)

    def test_status_network_failure_keeps_deposit_pending(self):
        import socket
        dep, body = self.pay(100000)

        def boom(order_id):
            raise socket.timeout("timed out")

        self.status_answer = boom
        res = self.client.get(f"/wallet/deposits/{dep}", headers=self.auth())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "pending")
        self.assertEqual(self.balance(), 0)

    def test_status_answer_for_other_order_is_ignored(self):
        dep, body = self.pay(100000)
        other_dep, other_body = self.pay(100000)
        self.status_answer = lambda order_id: self.signed_status(other_body)
        self.assertEqual(self.client.get(f"/wallet/deposits/{dep}", headers=self.auth()).get_json()["status"], "pending")
        self.assertEqual(self.balance(), 0)

    def test_flagged_deposit_is_shown_under_review_and_stops_polling_payme(self):
        dep, body = self.pay(100000)
        self.send_callback(self.callback_payload(dep, 100000, amount="1", payment_id=body["payment_id"]))
        sent_before = len(self.sent)
        view = self.client.get(f"/wallet/deposits/{dep}", headers=self.auth()).get_json()
        self.assertTrue(view["under_review"])
        self.assertNotIn("checkout_url", view)
        self.assertEqual(len(self.sent), sent_before)  # no status request for a deposit waiting on an operator
        listed = self.client.get("/admin/wallet-deposits?review=1", headers=self.auth(self.admin_token())).get_json()
        self.assertIn(dep, [d["deposit_id"] for d in listed])
        self.assertEqual(self.balance(), 0)

    def test_deposit_list_and_status_are_private_and_hide_internal_fields(self):
        other_token, _ = self.make_user(f"payme_private_{PaymeWalletTopUpTests._seq}")
        dep, body = self.pay(100000)
        self.send_callback(body)
        mine = self.client.get("/wallet/deposits", headers=self.auth()).get_json()
        self.assertEqual([d["deposit_id"] for d in mine], [dep])
        for field in ("user_id", "provider_payment_id", "review_note", "checkout_url"):
            self.assertNotIn(field, mine[0])
        self.assertEqual(self.client.get("/wallet/deposits", headers=self.auth(other_token)).get_json(), [])
        self.assertEqual(self.client.get(f"/wallet/deposits/{dep}", headers=self.auth(other_token)).status_code, 404)
        from urllib.parse import quote
        self.assertEqual(self.client.get("/wallet/deposits/" + quote("1' OR 1=1--"), headers=self.auth()).status_code, 404)
        other_wallet = self.client.get("/wallet", headers=self.auth(other_token)).get_json()
        self.assertEqual((other_wallet["balance"], other_wallet["transactions"]), (0, []))

    def test_browser_return_with_payme_query_params_never_credits(self):
        dep, body = self.pay(100000)
        res = self.client.get(f"/wallet/deposits/return?deposit={dep}&" + urlencode_body(body))
        self.assertEqual(res.status_code, 303)
        self.assertEqual(self.deposit_status(dep), "pending")
        self.assertEqual(self.balance(), 0)
        with mock.patch.dict(os.environ, {"PAYME_FRONTEND_RETURN_URL": ""}):
            self.assertEqual(self.client.get(f"/wallet/deposits/return?deposit={dep}").status_code, 404)

    # =====================================================================================================
    # SQLite: existing databases, repeated start-up, admin user deletion
    # =====================================================================================================
    def test_existing_database_gets_payme_tables_without_touching_data(self):
        import sqlite3
        from flask import Flask
        legacy = "test_payme_legacy.db"
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(legacy + suffix):
                os.remove(legacy + suffix)
        DB(legacy)  # an existing FinJob database created before Payme existed
        conn = sqlite3.connect(legacy)
        conn.execute("INSERT INTO users(username,password,balance) VALUES('legacy_user','x',123456.5)")
        uid = conn.execute("SELECT id FROM users WHERE username='legacy_user'").fetchone()[0]
        conn.execute("INSERT INTO wallet_transactions(user_id,type,amount,balance_after,job_id,description,created_at) "
                     "VALUES(?,'payment_release',123456.5,123456.5,NULL,'old','2025-01-01T00:00:00')", (uid,))
        conn.execute("UPDATE platform_settings SET value='10' WHERE key='commission_percent'")
        conn.commit()
        self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='wallet_deposits'").fetchone())
        conn.close()

        stub = DB.__new__(DB)
        stub.db_name = legacy
        for _ in range(2):  # repeated application start-ups
            payme.register_payme_routes(Flask(f"legacy{_}"), stub, auth=lambda f: f, create_notification=lambda *a: None)
            DB(legacy)
        conn = sqlite3.connect(legacy)
        try:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','index')")}
            self.assertTrue({"wallet_deposits", "wallet_deposit_events", "ux_wallet_deposits_provider_payment"} <= names)
            self.assertEqual(conn.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0], 123456.5)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM wallet_transactions WHERE user_id=?", (uid,)).fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT value FROM platform_settings WHERE key='commission_percent'").fetchone()[0], "10")
            conn.execute("INSERT INTO wallet_deposits(deposit_uuid,user_id,amount_uzs,amount_minor,created_at,expires_at) "
                         "VALUES(?,?,1000,100000,'t','t')", ("c" * 32, uid))
            conn.commit()
        finally:
            conn.close()
        payme.register_payme_routes(Flask("legacy3"), stub, auth=lambda f: f, create_notification=lambda *a: None)
        conn = sqlite3.connect(legacy)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM wallet_deposits").fetchone()[0], 1)  # kept on restart
        finally:
            conn.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(legacy + suffix)
            except OSError:
                pass

    def test_admin_user_deletion_keeps_payme_financial_records(self):
        admin = self.auth(self.admin_token())
        # user whose only deposit failed (no money moved) can still be deleted
        tok1, uid1 = self.make_user(f"payme_del_a_{PaymeWalletTopUpTests._seq}")
        with mock.patch.object(payme, "_http_post_json", side_effect=OSError("down")):
            self.create_deposit(100000, token=tok1)
        res = self.client.delete(f"/admin/user/{uid1}", headers=admin)
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertEqual(main.db.q("SELECT COUNT(*) FROM wallet_deposits WHERE user_id=?", (uid1,)).fetchone()[0], 0)
        # users with a pending or credited deposit get a clear 409 instead of a 500 / lost records
        tok2, uid2 = self.make_user(f"payme_del_b_{PaymeWalletTopUpTests._seq}")
        dep = self.create_deposit(100000, token=tok2).get_json()["deposit_id"]
        self.assertEqual(self.client.delete(f"/admin/user/{uid2}", headers=admin).status_code, 409)
        self.send_callback(self.callback_payload(dep, 100000, payment_id=self._next_payment_id()))
        self.assertEqual(self.client.delete(f"/admin/user/{uid2}", headers=admin).status_code, 409)
        self.assertEqual(self.balance(uid2), 100000)
        self.assertEqual(main.db.q("SELECT status FROM wallet_deposits WHERE deposit_uuid=?", (dep,)).fetchone()[0], "credited")


def urlencode_body(body):
    from urllib.parse import urlencode
    return urlencode({k: str(v) for k, v in body.items()})


if __name__ == "__main__":
    unittest.main()

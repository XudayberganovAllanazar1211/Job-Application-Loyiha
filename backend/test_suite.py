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

        owner_proposals = self.client.get(
            f"/jobs/{job_id}/proposals",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        self.assertEqual(owner_proposals.status_code, 200)
        proposal_items = owner_proposals.get_json()
        self.assertEqual(len(proposal_items), 1)
        self.assertEqual(proposal_items[0]["price"], 750000.0)
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
        self.assertEqual(detail_data["price"], 750000.0)
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
        self.assertEqual(float(overview.get_json()["settings"]["commission_percent"]), 10.0)

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
            json={"commission_percent": 10}
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

        worker_attachment = self.client.get(
            f"/admin/report/{item['id']}/attachment",
            headers={"Authorization": f"Bearer {worker_token}"}
        )
        self.assertEqual(worker_attachment.status_code, 403)

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
            f"/presence/{worker_id}",
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


if __name__ == "__main__":
    unittest.main()

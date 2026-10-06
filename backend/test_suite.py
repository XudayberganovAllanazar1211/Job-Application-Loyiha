import os
import unittest
import time
from main import app, DB, pending_verifications
import main

class JobPlatformTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db_name = "test_app.db"
        if os.path.exists(cls.test_db_name):
            os.remove(cls.test_db_name)
        main.db = DB(cls.test_db_name)
        app.config["TESTING"] = True
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db_name):
            try:
                os.remove(cls.test_db_name)
            except Exception:
                pass

    def test_01_registration_flow(self):
        # 1. Send code (First registered user becomes admin)
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
        # First user is admin
        self.assertEqual(res_verify.get_json().get("role"), "admin")

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
        self.assertEqual(prof_data["role"], "admin")
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
        # Login creator (Admin)
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

        # Creator requests finish
        res_fin = self.client.post("/finish_job", headers={"Authorization": f"Bearer {token_creator}"}, json={"job_id": job_id})
        self.assertEqual(res_fin.status_code, 200)

        # Worker confirms finish
        res_conf = self.client.post("/confirm_finish", headers={"Authorization": f"Bearer {token_worker}"}, json={
            "job_id": job_id,
            "choice": "yes"
        })
        self.assertEqual(res_conf.status_code, 200)
        self.assertEqual(res_conf.get_json()["status"], "finished")

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
            "/service",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={"name": "Konditsioner Ta'mirlash"}
        )
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.get_json()["msg"], "ok")

if __name__ == "__main__":
    unittest.main()

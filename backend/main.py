@admin_required
def update_report(report_id):
    status=(request.json or {}).get("status")
    if status not in ("open","reviewing","resolved","rejected"):
        return jsonify({"msg":"Report holati noto‘g‘ri"}),400

    report=db.q(
        "SELECT reporter_id, reported_user_id, job_id, status FROM reports WHERE id=?",
        (report_id,)
    ).fetchone()
    if not report:
        return jsonify({"msg":"Shikoyat topilmadi"}),404

    reporter_id, reported_user_id, job_id, old_status = report
    result=db.q("UPDATE reports SET status=? WHERE id=?",(status,report_id))
    if result.rowcount!=1:
        result.close()
        return jsonify({"msg":"Shikoyat topilmadi"}),404
    result.close()

    if status in ("resolved", "rejected") and old_status != status:
        if status == "resolved":
            if job_id:
                db.q(
                    "UPDATE jobs SET status='blocked', finished_at=NULL WHERE id=?",
                    (job_id,)
                ).close()

            create_notification(
                reporter_id,
                "report_resolved",
                "Shikoyat hal qilindi",
                "Siz yuborgan shikoyat admin tomonidan ko‘rib chiqildi va ish bloklandi.",
                "/jobs"
            )
            create_notification(
                reported_user_id,
                "report_resolved",
                "Shikoyat bo‘yicha qaror",
                "Siz qatnashgan ish bo‘yicha shikoyat admin tomonidan ko‘rib chiqildi va ish bloklandi.",
                "/jobs"
            )
        else:
            create_notification(
                reporter_id,
                "report_rejected",
                "Shikoyat rad etildi",
                "Siz yuborgan shikoyat admin tomonidan ko‘rib chiqildi va rad etildi.",
                "/jobs"
            )
            create_notification(
                reported_user_id,
                "report_rejected",
                "Shikoyat rad etildi",
                "Siz qatnashgan ish bo‘yicha berilgan shikoyat admin tomonidan rad etildi.",
                "/jobs"
            )

    return jsonify({"msg":"Shikoyat holati yangilandi","status":status})


# -------- ADMIN --------
@app.route("/admin/overview")
@admin_required
def admin_overview():
    users = db.q(
        """SELECT id, username, first_name, last_name, email, birthday, bio, skills, role, created_at, average_rating
           FROM users ORDER BY id DESC"""
    ).fetchall()
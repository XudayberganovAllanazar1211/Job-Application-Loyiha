from getpass import getpass
from werkzeug.security import generate_password_hash
from main import db


username = input("Admin username: ").strip()
email = input("Admin email: ").strip().lower()
password = getpass("Admin password: ")

if not username or not email or not password:
    print("Barcha maydonlarni to'ldiring.")
    raise SystemExit(1)

existing = db.q(
    "SELECT id FROM users WHERE username=? OR email=?",
    (username, email)
).fetchone()

if not existing:
    print("Bu username yoki email bilan foydalanuvchi topilmadi.")
    print("Avval FinJob orqali oddiy account yarating, keyin bu scriptni ishga tushiring.")
    raise SystemExit(1)

db.q(
    "UPDATE users SET role='admin', password=? WHERE id=?",
    (generate_password_hash(password), existing[0])
)

print("Admin huquqi berildi.")
print("Endi shu username/email va yangi parol bilan FinJob'ga kiring.")

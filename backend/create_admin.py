from getpass import getpass
from werkzeug.security import generate_password_hash
from main import db


username = input("Admin username: ").strip()
email = input("Admin email: ").strip().lower()
password = getpass("Admin password: ")

if not username or not email or not password:
    print("Barcha maydonlarni to'ldiring.")
    raise SystemExit(1)

existing_username = db.q(
    "SELECT id,username,email FROM users WHERE username=?",
    (username,)
).fetchone()
existing_email = db.q(
    "SELECT id,username,email FROM users WHERE email=?",
    (email,)
).fetchone()

if not existing_username or not existing_email or existing_username[0] != existing_email[0]:
    print("Kiritilgan username va email bitta mavjud accountga tegishli bo‘lishi kerak.")
    print("Avval FinJob orqali oddiy account yarating va username/emailni aynan o‘sha accountniki qilib kiriting.")
    raise SystemExit(1)

user_id = existing_username[0]
db.q(
    "UPDATE users SET role='admin', password=?, token_version=COALESCE(token_version,0)+1 WHERE id=?",
    (generate_password_hash(password), user_id)
).close()

print("Admin huquqi berildi.")
print("Endi shu username/email va yangi parol bilan FinJob'ga kiring.")

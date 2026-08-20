import hashlib
import hmac
import os
import random
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import pymysql
import pymysql.cursors
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, field_validator

MYSQL_HOST = os.environ.get("MYSQL_HOST", "fhem-db")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "housemeetsbeach")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "change-me")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "housemeetsbeach")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-too").encode()
TOKEN_TTL_SECONDS = 12 * 3600
MIN_SUBMIT_SECONDS = 3
CAPTCHA_TTL_SECONDS = 15 * 60
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="Party RSVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextmanager
def get_conn():
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(retries: int = 10, delay: float = 3.0):
    for attempt in range(retries):
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS guests (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            first_name VARCHAR(100) NOT NULL,
                            last_name VARCHAR(100) NOT NULL,
                            email VARCHAR(255) NOT NULL UNIQUE,
                            phone VARCHAR(32) NOT NULL UNIQUE,
                            adults INT NOT NULL DEFAULT 1,
                            children INT NOT NULL DEFAULT 0,
                            notes TEXT,
                            food_order TEXT,
                            status VARCHAR(20) NOT NULL DEFAULT 'zugesagt',
                            created_at VARCHAR(40) NOT NULL,
                            updated_at VARCHAR(40) NOT NULL
                        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                        """
                    )
                    cur.execute(
                        "ALTER TABLE guests ADD COLUMN IF NOT EXISTS food_order TEXT AFTER notes"
                    )
            return
        except pymysql.err.OperationalError:
            if attempt == retries - 1:
                raise
            time.sleep(delay)


@app.on_event("startup")
def on_startup():
    init_db()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(phone: str) -> str:
    return re.sub(r"[^\d+]", "", phone)


def sign(msg: str) -> str:
    return hmac.new(SECRET_KEY, msg.encode(), hashlib.sha256).hexdigest()


# ---------- Anti-bot: Rechen-Captcha ----------

@app.get("/api/captcha")
def get_captcha():
    a, b = random.randint(1, 9), random.randint(1, 9)
    issued = int(time.time())
    payload = f"{a}:{b}:{issued}"
    token = f"{payload}:{sign(payload)}"
    return {"question": f"{a} + {b}", "token": token}


def verify_captcha(token: str, answer: int):
    try:
        a_s, b_s, issued_s, sig = token.split(":")
        a, b, issued = int(a_s), int(b_s), int(issued_s)
    except (ValueError, AttributeError):
        raise HTTPException(400, "Ungueltige Sicherheitsfrage, bitte Seite neu laden.")
    if not hmac.compare_digest(sig, sign(f"{a}:{b}:{issued}")):
        raise HTTPException(400, "Ungueltige Sicherheitsfrage, bitte Seite neu laden.")
    age = time.time() - issued
    if age > CAPTCHA_TTL_SECONDS:
        raise HTTPException(400, "Sicherheitsfrage abgelaufen, bitte Seite neu laden.")
    if age < MIN_SUBMIT_SECONDS:
        raise HTTPException(400, "Bitte versuche es erneut.")
    if answer != a + b:
        raise HTTPException(400, "Sicherheitsfrage falsch beantwortet.")


# ---------- Oeffentliche Anmeldung ----------

class RSVPIn(BaseModel):
    firstName: str
    lastName: str
    email: str
    phone: str
    adults: int = 1
    children: int = 0
    notes: str = ""
    foodOrder: str = ""
    website: str = ""  # Honeypot - muss leer bleiben
    captchaToken: str
    captchaAnswer: int

    @field_validator("firstName", "lastName")
    @classmethod
    def not_blank(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("required")
        return v

    @field_validator("adults", "children")
    @classmethod
    def non_negative(cls, v):
        if v < 0:
            raise ValueError("invalid")
        return v


@app.post("/api/rsvp")
def submit_rsvp(payload: RSVPIn):
    if payload.website:
        # Honeypot ausgeloest - Bots nicht durchschauen lassen, einfach "erfolgreich" antworten
        return {"status": "ok", "message": "Danke fuer deine Anmeldung!"}

    verify_captcha(payload.captchaToken, payload.captchaAnswer)

    email = normalize_email(payload.email)
    phone = normalize_phone(payload.phone)
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Bitte eine gueltige E-Mail-Adresse angeben.")
    if len(phone) < 6:
        raise HTTPException(400, "Bitte eine gueltige Telefonnummer angeben.")

    now = datetime.now(timezone.utc).isoformat()
    notes = payload.notes.strip()
    food_order = payload.foodOrder.strip()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM guests WHERE email = %s OR phone = %s", (email, phone)
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """UPDATE guests SET first_name=%s, last_name=%s, email=%s, phone=%s,
                       adults=%s, children=%s, notes=%s, food_order=%s, status='zugesagt', updated_at=%s
                       WHERE id=%s""",
                    (payload.firstName.strip(), payload.lastName.strip(), email, phone,
                     payload.adults, payload.children, notes, food_order, now, existing["id"]),
                )
                message = "Deine Anmeldung wurde aktualisiert. Bis bald am Strand!"
            else:
                cur.execute(
                    """INSERT INTO guests
                       (first_name, last_name, email, phone, adults, children, notes, food_order, status, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'zugesagt', %s, %s)""",
                    (payload.firstName.strip(), payload.lastName.strip(), email, phone,
                     payload.adults, payload.children, notes, food_order, now, now),
                )
                message = "Danke fuer deine Anmeldung! Bis bald am Strand!"

    return {"status": "ok", "message": message}


# ---------- Admin ----------

class LoginIn(BaseModel):
    password: str


def make_token() -> str:
    expiry = int(time.time()) + TOKEN_TTL_SECONDS
    return f"{expiry}:{sign(str(expiry))}"


def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Nicht angemeldet")
    token = authorization.removeprefix("Bearer ")
    try:
        expiry_s, sig = token.split(":")
        expiry = int(expiry_s)
    except ValueError:
        raise HTTPException(401, "Ungueltiges Token")
    if not hmac.compare_digest(sig, sign(str(expiry))) or time.time() > expiry:
        raise HTTPException(401, "Sitzung abgelaufen, bitte erneut anmelden")


@app.post("/api/admin/login")
def admin_login(payload: LoginIn):
    if not hmac.compare_digest(payload.password, ADMIN_PASSWORD):
        raise HTTPException(401, "Falsches Passwort")
    return {"token": make_token()}


@app.get("/api/admin/guests", dependencies=[Depends(verify_token)])
def list_guests():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM guests ORDER BY created_at DESC")
            return cur.fetchall()


class GuestUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    foodOrder: Optional[str] = None
    adults: Optional[int] = None
    children: Optional[int] = None


@app.patch("/api/admin/guests/{guest_id}", dependencies=[Depends(verify_token)])
def update_guest(guest_id: int, payload: GuestUpdate):
    fields, values = [], []
    for col, val in [
        ("status", payload.status),
        ("notes", payload.notes),
        ("food_order", payload.foodOrder),
        ("adults", payload.adults),
        ("children", payload.children),
    ]:
        if val is not None:
            fields.append(f"{col} = %s")
            values.append(val)
    if not fields:
        return {"status": "ok"}
    fields.append("updated_at = %s")
    values.append(datetime.now(timezone.utc).isoformat())
    values.append(guest_id)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE guests SET {', '.join(fields)} WHERE id = %s", values)
    return {"status": "ok"}


@app.delete("/api/admin/guests/{guest_id}", dependencies=[Depends(verify_token)])
def delete_guest(guest_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM guests WHERE id = %s", (guest_id,))
    return {"status": "ok"}


@app.get("/api/admin/export.csv", dependencies=[Depends(verify_token)])
def export_csv():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM guests ORDER BY created_at")
            rows = cur.fetchall()
    lines = ["Vorname;Nachname;E-Mail;Telefon;Erwachsene;Kinder;Status;Essenswunsch;Notiz"]
    for r in rows:
        notiz = (r["notes"] or "").replace(";", ",")
        essen = (r["food_order"] or "").replace(";", ",")
        lines.append(
            f'{r["first_name"]};{r["last_name"]};{r["email"]};{r["phone"]};'
            f'{r["adults"]};{r["children"]};{r["status"]};{essen};{notiz}'
        )
    return PlainTextResponse("\n".join(lines), media_type="text/csv")


@app.get("/api/health")
def health():
    return {"status": "ok"}

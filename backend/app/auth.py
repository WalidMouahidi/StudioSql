import hashlib
import os
import secrets
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.database import state


USERNAME = os.environ.get("STUDIOSQL_ADMIN_USERNAME", "admin")
PASSWORD = os.environ.get("STUDIOSQL_ADMIN_PASSWORD", "")
if not USERNAME or len(PASSWORD) < 12:
    raise RuntimeError("Définir STUDIOSQL_ADMIN_PASSWORD (12 caractères minimum) dans .env.")

COOKIE = "studiosql_session"
SESSION_SECONDS = 12 * 60 * 60
HASH_ITERATIONS = 300_000
SALT = secrets.token_bytes(16)
PASSWORD_HASH = hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), SALT, HASH_ITERATIONS)
del PASSWORD

attempts = defaultdict(deque)
attempts_lock = Lock()
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class ProfileBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


def initialize_auth():
    with state() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                csrf_token TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )
        """)
        db.execute("DELETE FROM auth_sessions")
        db.execute("""
            CREATE TABLE IF NOT EXISTS auth_profiles (
                username TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)
        now = int(time.time())
        db.execute(
            "INSERT OR IGNORE INTO auth_profiles (username, display_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (USERNAME, USERNAME, now, now),
        )


def profile_details(username: str, expires_at: int):
    with state() as db:
        profile = db.execute(
            "SELECT display_name, created_at, updated_at FROM auth_profiles WHERE username = ?",
            (username,),
        ).fetchone()
        sessions = db.execute(
            "SELECT count(*) FROM auth_sessions WHERE username = ? AND expires_at > ?",
            (username, int(time.time())),
        ).fetchone()[0]
    return {
        "username": username,
        "display_name": profile["display_name"],
        "role": "Administrateur",
        "created_at": profile["created_at"],
        "updated_at": profile["updated_at"],
        "session_expires_at": expires_at,
        "active_sessions": sessions,
    }


def session_for(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with state() as db:
        session = db.execute(
            "SELECT username, csrf_token, expires_at FROM auth_sessions WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if session and session["expires_at"] <= int(time.time()):
            db.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))
            return None
    return session


def client_key(request: Request):
    return request.client.host if request.client else "unknown"


def rate_limited(key: str):
    with attempts_lock:
        recent = attempts[key]
        now = time.monotonic()
        while recent and now - recent[0] >= 300:
            recent.popleft()
        return len(recent) >= 10


def failed_attempt(key: str):
    with attempts_lock:
        attempts[key].append(time.monotonic())


def clear_attempts(key: str):
    with attempts_lock:
        attempts.pop(key, None)


def json_error(status: int, message: str):
    return JSONResponse({"detail": message}, status_code=status, headers={"Cache-Control": "no-store"})


@router.post("/login")
def login(body: LoginBody, request: Request):
    key = client_key(request)
    if rate_limited(key):
        return json_error(429, "Trop de tentatives. Réessayez dans cinq minutes.")
    candidate = hashlib.pbkdf2_hmac("sha256", body.password.encode(), SALT, HASH_ITERATIONS)
    username_valid = secrets.compare_digest(body.username, USERNAME)
    password_valid = secrets.compare_digest(candidate, PASSWORD_HASH)
    valid = username_valid and password_valid
    if not valid:
        failed_attempt(key)
        return json_error(401, "Identifiant ou mot de passe incorrect.")

    clear_attempts(key)
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + SESSION_SECONDS
    with state() as db:
        db.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (int(time.time()),))
        db.execute(
            "INSERT INTO auth_sessions (token_hash, username, csrf_token, expires_at) VALUES (?, ?, ?, ?)",
            (hashlib.sha256(token.encode()).hexdigest(), USERNAME, csrf_token,
             expires_at),
        )
    response = JSONResponse({**profile_details(USERNAME, expires_at), "csrf_token": csrf_token},
                            headers={"Cache-Control": "no-store"})
    response.set_cookie(
        COOKIE, token, max_age=SESSION_SECONDS, path="/", httponly=True,
        samesite="strict", secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
    )
    return response


@router.get("/session")
def current_session(request: Request):
    return JSONResponse(
        {**profile_details(request.state.username, request.state.expires_at),
         "csrf_token": request.state.csrf_token},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/profile")
def get_profile(request: Request):
    return profile_details(request.state.username, request.state.expires_at)


@router.post("/profile")
def update_profile(body: ProfileBody, request: Request):
    name = body.display_name.strip()
    if not name:
        return json_error(422, "Le nom affiché ne peut pas être vide.")
    with state() as db:
        db.execute(
            "UPDATE auth_profiles SET display_name = ?, updated_at = ? WHERE username = ?",
            (name, int(time.time()), request.state.username),
        )
    return profile_details(request.state.username, request.state.expires_at)


@router.post("/sessions/revoke-others")
def revoke_other_sessions(request: Request):
    token_hash = hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest()
    with state() as db:
        db.execute(
            "DELETE FROM auth_sessions WHERE username = ? AND token_hash != ?",
            (request.state.username, token_hash),
        )
    return {"active_sessions": 1}


@router.post("/logout")
def logout(request: Request):
    token = request.cookies.get(COOKIE)
    if token:
        with state() as db:
            db.execute("DELETE FROM auth_sessions WHERE token_hash = ?",
                       (hashlib.sha256(token.encode()).hexdigest(),))
    response = JSONResponse({"status": "signed_out"}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(COOKIE, path="/")
    return response

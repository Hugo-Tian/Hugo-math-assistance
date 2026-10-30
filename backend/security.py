import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pwdlib import PasswordHash
from sqlalchemy import delete
from .db import get_db
from .models import User, AuthToken, utcnow

passwords = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 15 * 60

def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def issue_token(db, user):
    # Expired tokens are never valid again; drop this user's leftovers on each login.
    db.execute(delete(AuthToken).where(AuthToken.user_id == user.id, AuthToken.expires_at <= utcnow()))
    token = secrets.token_urlsafe(40)
    db.add(AuthToken(digest=token_digest(token), user_id=user.id, expires_at=utcnow() + timedelta(hours=12)))
    return token

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(get_db)):
    auth = db.get(AuthToken, token_digest(credentials.credentials)) if credentials else None
    user = db.get(User, auth.user_id) if auth and auth.expires_at > utcnow() else None
    if not user:
        raise HTTPException(401, '请登录，或登录已过期')
    return user

def administrator(user=Depends(current_user)):
    if user.role != 'admin':
        raise HTTPException(403, '需要管理员权限')
    return user

class LoginThrottle:
    """In-process failure counter per username; a single-instance demo, not a distributed limiter."""
    def __init__(self, limit=LOGIN_MAX_FAILURES, window=LOGIN_WINDOW_SECONDS):
        self.limit, self.window = limit, window
        self.failures = defaultdict(deque)
        self.lock = threading.Lock()

    def _recent(self, key, now):
        q = self.failures[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        return q

    def check(self, username):
        with self.lock:
            q = self._recent(username.lower(), time.monotonic())
            if len(q) >= self.limit:
                raise HTTPException(429, f'登录失败次数过多，请 {int(q[0] + self.window - time.monotonic()) // 60 + 1} 分钟后再试')

    def failed(self, username):
        with self.lock:
            now = time.monotonic()
            self._recent(username.lower(), now).append(now)

    def succeeded(self, username):
        with self.lock:
            self.failures.pop(username.lower(), None)

login_throttle = LoginThrottle()

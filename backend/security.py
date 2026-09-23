import hashlib
import secrets
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pwdlib import PasswordHash
from .db import get_db
from .models import User, AuthToken

passwords = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)

def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def issue_token(db, user):
    token = secrets.token_urlsafe(40)
    db.add(AuthToken(digest=token_digest(token), user_id=user.id, expires_at=datetime.utcnow() + timedelta(hours=12)))
    return token

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(get_db)):
    auth = db.get(AuthToken, token_digest(credentials.credentials)) if credentials else None
    if not auth or auth.expires_at <= datetime.utcnow():
        raise HTTPException(401, '请登录，或登录已过期')
    return db.get(User, auth.user_id)

def administrator(user=Depends(current_user)):
    if user.role != 'admin':
        raise HTTPException(403, '需要管理员权限')
    return user

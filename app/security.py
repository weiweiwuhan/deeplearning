"""密码仅保存加盐 PBKDF2 摘要；浏览器只持有不透明的 HttpOnly 会话 cookie。"""
import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600_000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split('$')
        computed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(computed, digest)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

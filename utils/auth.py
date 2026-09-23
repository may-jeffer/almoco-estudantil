from flask import session

def is_logged_in_aluno():
    return 'aluno_id' in session

def is_logged_in_admin():
    return session.get('is_admin') == True

def tem_permissao(p):
    if not is_logged_in_admin():
        return False
    # O superadministrador do sistema sempre tem acesso total
    if session.get('admin_usuario') == 'admin':
        return True
    perms = session.get('admin_permissoes', [])
    if isinstance(perms, str):
        try:
            import json
            perms = json.loads(perms)
        except Exception:
            perms = []
    if not isinstance(perms, (list, set, tuple)):
        return False
    return 'all' in perms or p in perms

def is_admin_mestre():
    if session.get('admin_usuario') == 'admin':
        return True
    return tem_permissao('all')



from collections import defaultdict
import time
import threading

class SimpleRateLimiter:
    def __init__(self, limit=5, window=60):
        self.limit = limit
        self.window = window
        self.attempts = defaultdict(list)
        self.lock = threading.Lock()
        
    def is_blocked(self, ip):
        with self.lock:
            now = time.time()
            self.attempts[ip] = [t for t in self.attempts[ip] if now - t < self.window]
            if len(self.attempts[ip]) >= self.limit:
                return True
            return False
            
    def record_attempt(self, ip):
        with self.lock:
            now = time.time()
            self.attempts[ip].append(now)

login_limiter = SimpleRateLimiter(limit=5, window=60)

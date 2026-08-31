import os

def get_secure_secret_key():
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    
    # Fallback: tenta ler uma chave persistente do arquivo .secret_key no servidor
    base_path = os.path.dirname(os.path.abspath(__file__))
    key_filepath = os.path.join(base_path, '.secret_key')
    if os.path.exists(key_filepath):
        try:
            with open(key_filepath, 'r') as f:
                return f.read().strip()
        except:
            pass
            
    # Caso não exista, gera uma chave aleatória de 32 bytes e salva
    import secrets
    fallback_key = secrets.token_hex(32)
    try:
        with open(key_filepath, 'w') as f:
            f.write(fallback_key)
    except:
        pass
    return fallback_key

SECRET_KEY = get_secure_secret_key()
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
UPLOAD_FOLDER = os.path.join('static', 'uploads')

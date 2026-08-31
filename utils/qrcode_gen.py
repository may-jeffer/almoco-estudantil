import hashlib
import qrcode
import base64
from io import BytesIO
from config import SECRET_KEY

def generate_badge_code(evento_id, aluno_id):
    """Gera um código único para o crachá do evento."""
    base = f"EVT-{evento_id}-{aluno_id}-{SECRET_KEY}"
    short_hash = hashlib.md5(base.encode()).hexdigest()[:6].upper()
    return f"EVT-{evento_id}-{aluno_id}-{short_hash}"

def generate_std_badge_code(aluno_id):
    """Gera um código único para o crachá fixo do aluno regular."""
    base = f"STD-{aluno_id}-{SECRET_KEY}"
    short_hash = hashlib.md5(base.encode()).hexdigest()[:6].upper()
    return f"STD-{aluno_id}-{short_hash}"

def generate_qr_b64(data):
    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return img_str

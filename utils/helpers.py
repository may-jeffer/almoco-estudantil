from datetime import datetime, timedelta

def datetime_now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def get_agora():
    return datetime.now()

def date_hoje_str():
    return datetime.now().strftime('%Y-%m-%d')

def pode_reservar(data_cardapio_str, horario_limite_str):
    agora = get_agora()
    data_cardapio = datetime.strptime(data_cardapio_str, '%Y-%m-%d')
    hora, minuto = map(int, horario_limite_str.split(':'))
    
    data_limite = data_cardapio - timedelta(days=1)
    momento_limite = data_limite.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    
    return agora <= momento_limite

def sanitize_field(value):
    if value is None:
        return ''
    return str(value).strip()

def registrar_auditoria(acao, detalhes=""):
    from flask import session, request
    from database import get_db_connection, closing
    
    admin_id = session.get('admin_id')
    usuario = session.get('admin_usuario')
    ip = request.remote_addr
    data_criacao = datetime_now_str()
    
    try:
        with closing(get_db_connection()) as conn:
            conn.execute(
                "INSERT INTO logs_auditoria (admin_id, usuario, acao, detalhes, ip, data_criacao) VALUES (?, ?, ?, ?, ?, ?)",
                (admin_id, usuario, acao, detalhes, ip, data_criacao)
            )
            conn.commit()
    except Exception as e:
        print(f"Erro ao registrar auditoria: {e}")

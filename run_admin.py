# Arquivo para iniciar APENAS a porta do Administrador (HTTPS para o Leitor de QR Code)
# Uso: python run_admin.py
# No seu run_admin.py, prefira caminhos absolutos:
import os
base_path = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_path, "database.db")

from app import app

if __name__ == '__main__':
    print("INICIANDO PORTAL DA ROVETA / ADMIN (HTTPS na porta 5443)")
    try:
        # Por segurança, desabilitamos o modo debug por padrão em produção para evitar a exposição do console interativo do Werkzeug.
        # Caso precise ativá-lo para desenvolvimento local, defina a variável de ambiente FLASK_DEBUG=1.
        debug_mode = os.environ.get('FLASK_DEBUG', '0') in ('1', 'true', 'True')
        
        # Roda com criptografia auto-assinada para permitir acesso à Camera (HTML5 getUserMedia)
        app.run(host='0.0.0.0', port=5443, ssl_context='adhoc', debug=debug_mode)
    except Exception as e:
        print(f"Erro critico iniciando o HTTPS: Instale o 'pyopenssl' ou 'cryptography'\n{e}")

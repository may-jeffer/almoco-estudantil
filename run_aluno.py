# Arquivo para iniciar APENAS a porta do Estudante (HTTP)
# Uso: python run_aluno.py

import os
base_path = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_path, "database.db")

from app import app

if __name__ == '__main__':
    print("🚀 INICIANDO PORTAL DO ESTUDANTE (HTTP Limpo na porta 5000)")
    # Por segurança, desabilitamos o modo debug por padrão em produção.
    # Caso precise ativá-lo para desenvolvimento local, defina a variável de ambiente FLASK_DEBUG=1.
    debug_mode = os.environ.get('FLASK_DEBUG', '0') in ('1', 'true', 'True')
    
    # Roda sem criptografia para acesso livre nos celulares s/ aviso de segurança
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)

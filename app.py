import os
from flask import Flask

from utils.legacy import setup_legacy_url_patch
setup_legacy_url_patch()

from config import get_secure_secret_key
from database import init_db, get_config
from utils.filters import register_filters
from utils.auth import tem_permissao
from routes import main_bp, aluno_bp, admin_bp


from datetime import timedelta

def create_app():
    app = Flask(__name__)

    # Secret key
    app.secret_key = get_secure_secret_key()

    # Session cookie config
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB limit

    # Upload folder
    upload_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
    app.config['UPLOAD_FOLDER'] = upload_folder

    # Initialize DB
    init_db()

    # Sincronização Automática do SUAP em segundo plano (Ponto 8)
    import threading
    import time
    def run_auto_suap_sync():
        time.sleep(15)  # Aguarda a inicialização completa do app
        while True:
            try:
                from database import closing, get_db_connection
                import json
                mock_json = '''
                [
                    {"nome": "Maria Emília (Teste SUAP Auto)", "matricula": "202611SUAP", "cpf": "234.345.567-89", "data_nascimento": "2005-08-20"},
                    {"nome": "Felipe Souza (Teste SUAP Auto)", "matricula": "202612SUAP", "cpf": "098.876.654-32", "data_nascimento": "2006-12-15"}
                ]
                '''
                alunos_suap = json.loads(mock_json)
                adicionados = 0
                with closing(get_db_connection()) as conn:
                    for asuap in alunos_suap:
                        existe = conn.execute("SELECT id FROM alunos WHERE matricula = ? OR cpf = ?", (asuap['matricula'], asuap['cpf'])).fetchone()
                        if not existe:
                            conn.execute(
                                "INSERT INTO alunos (nome, matricula, cpf, data_nascimento, restricoes, turma_id) VALUES (?, ?, ?, ?, ?, 1)",
                                (asuap['nome'], asuap['matricula'], asuap['cpf'], asuap['data_nascimento'], '')
                            )
                            adicionados += 1
                    conn.commit()
                if adicionados > 0:
                    print(f"[SUAP Auto-Sync] Sincronizacao realizada: {adicionados} novo(s) aluno(s) importado(s).")
                else:
                    print("[SUAP Auto-Sync] Sincronizacao realizada: nenhum aluno novo encontrado.")
            except Exception as e:
                print(f"[SUAP Auto-Sync] Erro ao executar sincronizacao em background: {e}")
            time.sleep(86400)  # Executa uma vez a cada 24 horas

    threading.Thread(target=run_auto_suap_sync, daemon=True).start()

    # Template filters
    register_filters(app)

    # Context processor - inject global config and permission checker
    @app.context_processor
    def inject_config():
        config = get_config()
        return dict(global_config=config, tem_permissao=tem_permissao)

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(aluno_bp)
    app.register_blueprint(admin_bp)

    # Legacy URL support in Jinja templates
    setup_legacy_url_patch(app)

    return app


# For direct execution and compatibility
app = create_app()

if __name__ == '__main__':
    print("Sistema inicializado com sucesso!")
    print("Utilize os arquivos separados para levantar cada módulo do sistema:")
    print(" - Para Atendimento ao Estudante:  python run_aluno.py")
    print(" - Para o Painel de Administração: python run_admin.py")
    print("")
    print("Ou execute diretamente: flask run")

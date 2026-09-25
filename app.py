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

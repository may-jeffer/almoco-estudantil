from flask import Blueprint

admin_bp = Blueprint('admin', __name__)

# Importações diferidas dos submódulos para evitar importação circular
from . import dashboard
from . import alunos
from . import turmas
from . import eventos
from . import cardapios
from . import fila
from . import relatorios
from . import base_conhecimento
from . import pesquisas
from . import qualidade

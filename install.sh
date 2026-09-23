#!/usr/bin/env bash
# ==============================================================================
# INSTALADOR AUTOMATIZADO - SISTEMA DE ALMOÇO ESTUDANTIL (LINUX)
# ==============================================================================
set -e

# Cores para o terminal
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
BOLD='\033[1m'

echo -e "${CYAN}${BOLD}"
echo "=================================================================="
echo "    INSTALADOR AUTOMATIZADO - ALMOÇO ESTUDANTIL (LINUX)"
echo "=================================================================="
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Verificar versão do Python
echo -e "${CYAN}[1/6] Verificando versão do Python...${NC}"
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Erro: Python 3 não está instalado no sistema.${NC}"
    echo "Instale com: sudo apt update && sudo apt install python3 python3-venv python3-pip -y"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_VALID=$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')

if [ "$PYTHON_VALID" != "1" ]; then
    echo -e "${RED}Erro: É necessário Python 3.10 ou superior. Versão detectada: $PYTHON_VERSION${NC}"
    exit 1
fi
echo -e "${GREEN}✔ Python $PYTHON_VERSION detectado com sucesso.${NC}"

# 2. Criar ambiente virtual
echo -e "\n${CYAN}[2/6] Configurando ambiente virtual Python (venv)...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv || {
        echo -e "${RED}Falha ao criar o venv. Verifique se o pacote python3-venv está instalado.${NC}"
        echo "Execute: sudo apt install python3-venv -y"
        exit 1
    }
fi
source venv/bin/activate
echo -e "${GREEN}✔ Ambiente virtual ativado.${NC}"

# 3. Instalar Dependências (Suporte Offline e Online)
echo -e "\n${CYAN}[3/6] Instalando dependências da aplicação...${NC}"
pip install --upgrade pip --quiet 2>/dev/null || true

if [ -d "wheels" ] && [ "$(ls -A wheels/*.whl 2>/dev/null)" ]; then
    echo -e "${YELLOW}Modo Offline detectado: Instalando pacotes locais a partir da pasta wheels/...${NC}"
    pip install --no-index --find-links=wheels/ -r requirements.txt
    pip install --no-index --find-links=wheels/ gunicorn || true
else
    echo -e "Instalando pacotes via PyPI (requisições de rede)..."
    pip install -r requirements.txt
    pip install gunicorn
fi
echo -e "${GREEN}✔ Dependências instaladas com sucesso.${NC}"

# 4. Gerar arquivo .env caso não exista
echo -e "\n${CYAN}[4/6] Verificando variáveis de ambiente (.env)...${NC}"
if [ ! -f ".env" ]; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat <<EOF > .env
SECRET_KEY=$SECRET_KEY
PORT=5000
HOST=0.0.0.0
EOF
    echo -e "${GREEN}✔ Arquivo .env gerado com SECRET_KEY criptográfica segura.${NC}"
else
    echo -e "${GREEN}✔ Arquivo .env já existente mantido.${NC}"
fi

# 5. Inicialização do Banco Limpo e Criação do Administrador
echo -e "\n${CYAN}[5/6] Inicializando Banco de Dados e Administrador Mestre...${NC}"
echo "Selecione como deseja configurar o Administrador Inicial:"
echo "  1) Configuração Interativa (Digitar Nome, Usuário e Senha agora)"
echo "  2) Administrador Padrão Provisório (Cria 'admin' com senha 'admin123' - alterar depois)"
read -rp "Opção [1/2] (Padrão: 1): " OPCAO_ADMIN
OPCAO_ADMIN=${OPCAO_ADMIN:-1}

if [ "$OPCAO_ADMIN" = "2" ]; then
    python init_admin.py --default
else
    python init_admin.py
fi

# 6. Configuração de Inicialização Automática no Boot (Systemd)
echo -e "\n${CYAN}[6/6] Configuração de Serviço em Produção (Systemd)...${NC}"
SERVICE_FILE="/etc/systemd/system/almoco-estudantil.service"
CURRENT_USER=$(id -un)
CURRENT_GROUP=$(id -gn)

# Gerar arquivo de serviço local
cat <<EOF > almoco-estudantil.service
[Unit]
Description=Servidor do Sistema de Almoco Estudantil (Gunicorn)
After=network.target

[Service]
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$SCRIPT_DIR
Environment="PATH=$SCRIPT_DIR/venv/bin"
ExecStart=$SCRIPT_DIR/venv/bin/gunicorn --workers 4 --bind 127.0.0.1:5000 --access-logfile - app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo -e "Arquivo ${BOLD}almoco-estudantil.service${NC} gerado localmente."

read -rp "Deseja instalar e ativar o serviço no Systemd agora? (Requer sudo) [S/n]: " ATIVAR_SERVICO
ATIVAR_SERVICO=${ATIVAR_SERVICO:-S}

if [[ "$ATIVAR_SERVICO" =~ ^[Ss]$ ]]; then
    if command -v sudo &>/dev/null; then
        sudo cp almoco-estudantil.service /etc/systemd/system/almoco-estudantil.service
        sudo systemctl daemon-reload
        sudo systemctl enable almoco-estudantil.service
        sudo systemctl restart almoco-estudantil.service
        echo -e "${GREEN}✔ Serviço almoco-estudantil iniciado e ativado no boot!${NC}"
    else
        echo -e "${YELLOW}Aviso: 'sudo' não encontrado. Execute manualmente como root:${NC}"
        echo "  cp almoco-estudantil.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now almoco-estudantil"
    fi
else
    echo -e "${YELLOW}Para ativar o serviço manualmente mais tarde, execute:${NC}"
    echo "  sudo cp almoco-estudantil.service /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload && sudo systemctl enable --now almoco-estudantil"
fi

# Gerar arquivo Nginx customizado com o caminho atual
sed "s|/var/www/almoco-estudantil|$SCRIPT_DIR|g" nginx_template.conf > nginx_almoco.conf

echo -e "\n${GREEN}${BOLD}==================================================================${NC}"
echo -e "${GREEN}${BOLD}        INSTALAÇÃO CONCLUÍDA COM SUCESSO!${NC}"
echo -e "${GREEN}${BOLD}==================================================================${NC}"
echo -e "A aplicação está configurada e escutando em: ${CYAN}http://127.0.0.1:5000${NC}"
echo ""
echo -e "${BOLD}Comandos úteis do serviço:${NC}"
echo -e "  - Verificar status:  ${CYAN}sudo systemctl status almoco-estudantil${NC}"
echo -e "  - Reiniciar serviço: ${CYAN}sudo systemctl restart almoco-estudantil${NC}"
echo -e "  - Ver logs em tempo real: ${CYAN}sudo journalctl -u almoco-estudantil -f${NC}"
echo ""
echo -e "${BOLD}Configuração do Nginx e SSL:${NC}"
echo -e "  Um arquivo ${CYAN}nginx_almoco.conf${NC} foi criado com os caminhos corretos deste servidor."
echo -e "  Para publicar na internet:"
echo -e "  1. sudo cp nginx_almoco.conf /etc/nginx/sites-available/almoco-estudantil.conf"
echo -e "  2. sudo ln -s /etc/nginx/sites-available/almoco-estudantil.conf /etc/nginx/sites-enabled/"
echo -e "  3. sudo certbot --nginx -d seu-dominio.escola.edu.br"
echo -e "${GREEN}==================================================================${NC}\n"

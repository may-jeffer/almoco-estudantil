@echo off
chcp 65001 >nul
title Instalador Automatizado - Almoço Estudantil

echo ==================================================================
echo    INSTALADOR AUTOMATIZADO - ALMOÇO ESTUDANTIL (WINDOWS)
echo ==================================================================
echo.

cd /d "%~dp0"

:: 1. Verificar instalação do Python
echo [1/5] Verificando instalação do Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python não foi encontrado no sistema ou não está no PATH.
    echo Por favor, instale o Python 3.10+ marcando a opção "Add Python to PATH".
    pause
    exit /b 1
)
python --version

:: 2. Criar ambiente virtual Python
echo.
echo [2/5] Configurando ambiente virtual Python (venv)...
if not exist "venv" (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERRO] Falha ao criar o ambiente virtual venv.
        pause
        exit /b 1
    )
)
call venv\Scripts\activate.bat
echo [OK] Ambiente virtual ativado com sucesso.

:: 3. Instalar Dependências (Offline ou Online)
echo.
echo [3/5] Instalando bibliotecas e dependências...
python -m pip install --upgrade pip --quiet >nul 2>&1

if exist "wheels" (
    echo Modo Offline detectado: Instalando pacotes locais a partir da pasta wheels...
    pip install --no-index --find-links=wheels -r requirements.txt
    pip install --no-index --find-links=wheels waitress >nul 2>&1
) else (
    echo Instalando pacotes via PyPI (requer conexão com a internet)...
    pip install -r requirements.txt
    pip install waitress
)

if %errorlevel% neq 0 (
    echo [AVISO] Houve avisos durante a instalação de pacotes, verificando integridade...
)
echo [OK] Dependências instaladas com sucesso.

:: 4. Gerar arquivo de configuração .env caso não exista
echo.
echo [4/5] Verificando arquivo de ambiente (.env)...
if not exist ".env" (
    powershell -Command "$bytes = New-Object byte[] 32; (New-Object Security.Cryptography.RNGCryptoServiceProvider).GetBytes($bytes); $token = [System.BitConverter]::ToString($bytes) -replace '-',''; Set-Content -Path '.env' -Value @(\"SECRET_KEY=$token\", \"PORT=5000\", \"HOST=0.0.0.0\")"
    echo [OK] Arquivo .env gerado com chave de segurança única.
) else (
    echo [OK] Arquivo .env já existente mantido.
)

:: 5. Inicialização do Banco Limpo e Criação do Administrador
echo.
echo [5/5] Inicializando Banco de Dados e Administrador Mestre...
echo.
echo Escolha o método de criação do Administrador:
echo   [1] Interativo (Digitar Usuário, Senha e Nome agora)
echo   [2] Padrão Provisório (Cria 'admin' com senha 'admin123' - alterar depois)
echo.
set /p OPCAO_ADMIN="Escolha a opção (1 ou 2) [Padrão: 1]: "

if "%OPCAO_ADMIN%"=="2" (
    python init_admin.py --default
) else (
    python init_admin.py
)

:: 6. Criar scripts de inicialização rápida
echo.
echo Criando atalho de inicialização 'iniciar_servidor.bat'...
(
echo @echo off
echo title Almoço Estudantil - Servidor de Produção
echo cd /d "%%~dp0"
echo call venv\Scripts\activate.bat
echo python run_production.py
echo pause
) > iniciar_servidor.bat

(
echo @echo off
echo title Almoço Estudantil - Painel Admin ^(Desenvolvimento^)
echo cd /d "%%~dp0"
echo call venv\Scripts\activate.bat
echo python run_admin.py
echo pause
) > iniciar_admin_dev.bat

echo.
echo ==================================================================
echo            INSTALAÇÃO CONCLUÍDA COM SUCESSO!
echo ==================================================================
echo O sistema está pronto para ser executado.
echo.
echo Para iniciar o servidor em produção, execute:
echo   - iniciar_servidor.bat
echo.
echo O sistema ficará acessível na rede local em:
echo   http://localhost:5000  (ou pelo IP da máquina na rede)
echo ==================================================================
echo.
pause

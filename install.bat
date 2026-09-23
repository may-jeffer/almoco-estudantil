@echo off
title Instalador Automatizado - Almoco Estudantil

echo ==================================================================
echo    INSTALADOR AUTOMATIZADO - ALMOCO ESTUDANTIL (WINDOWS)
echo ==================================================================
echo.

cd /d "%~dp0"

:: 1. Verificar presenca dos arquivos essenciais ou extrair do zip automaticamente
if not exist "requirements.txt" (
    if exist "dist\almoco-estudantil-dist.zip" (
        echo [*] Detectado pacote dist\almoco-estudantil-dist.zip.
        echo [*] Extraindo arquivos da aplicacao automaticamente...
        tar -xf "dist\almoco-estudantil-dist.zip" 2>nul
    ) else if exist "almoco-estudantil-dist.zip" (
        echo [*] Detectado pacote almoco-estudantil-dist.zip.
        echo [*] Extraindo arquivos da aplicacao automaticamente...
        tar -xf "almoco-estudantil-dist.zip" 2>nul
    )
)

if not exist "requirements.txt" (
    echo.
    echo [ERRO] Os arquivos do sistema nao foram encontrados nesta pasta!
    echo.
    echo Voce precisa extrair todo o conteudo do arquivo:
    echo   almoco-estudantil-dist.zip
    echo dentro desta pasta antes de executar o instalador.
    echo.
    echo Arquivos que devem estar presentes:
    echo   - app.py
    echo   - requirements.txt
    echo   - init_admin.py
    echo   - pastas database, routes, templates, etc.
    echo.
    pause
    exit /b 1
)

:: 2. Verificar instalacao do Python
echo [1/5] Verificando instalacao do Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERRO] Python nao foi encontrado no sistema ou nao esta no PATH.
    echo Por favor, instale o Python 3.10+ marcando a opcao "Add Python to PATH".
    echo.
    pause
    exit /b 1
)
python --version

:: 3. Criar ambiente virtual Python
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

:: 4. Instalar Dependencias (Offline ou Online)
echo.
echo [3/5] Instalando bibliotecas e dependencias...
python -m pip install --upgrade pip --quiet >nul 2>&1

if exist "wheels" (
    echo Modo Offline detectado: Instalando pacotes a partir da pasta wheels...
    pip install --no-index --find-links=wheels -r requirements.txt
    pip install --no-index --find-links=wheels waitress >nul 2>&1
) else (
    echo Instalando pacotes via PyPI (requer conexao com a internet)...
    pip install -r requirements.txt
    pip install waitress
)
echo [OK] Dependencias instaladas com sucesso.

:: 5. Gerar arquivo de configuracao .env caso nao exista
echo.
echo [4/5] Verificando arquivo de ambiente (.env)...
if not exist ".env" (
    python -c "import secrets; f=open('.env','w'); f.write('SECRET_KEY=' + secrets.token_hex(32) + '\nPORT=5000\nHOST=0.0.0.0\n'); f.close()"
    echo [OK] Arquivo .env gerado com chave de seguranca criptografica unica.
) else (
    echo [OK] Arquivo .env ja existente mantido.
)

:: 6. Inicializacao do Banco Limpo e Criacao do Administrador
echo.
echo [5/5] Inicializando Banco de Dados e Administrador Mestre...
echo.
echo Escolha o metodo de criacao do Administrador:
echo   [1] Interativo (Digitar Usuario, Senha e Nome agora)
echo   [2] Padrao Provisorio (Cria admin com senha admin123 - alterar depois)
echo.
set /p OPCAO_ADMIN="Escolha a opcao (1 ou 2) [Padrao: 1]: "

if "%OPCAO_ADMIN%"=="2" (
    python init_admin.py --default
) else (
    python init_admin.py
)

:: 7. Criar atalhos de inicializacao rapida
echo.
echo Criando scripts de inicializacao...
> iniciar_servidor.bat echo @echo off
>> iniciar_servidor.bat echo title Almoco Estudantil - Servidor de Producao
>> iniciar_servidor.bat echo cd /d "%%~dp0"
>> iniciar_servidor.bat echo call venv\Scripts\activate.bat
>> iniciar_servidor.bat echo python run_production.py
>> iniciar_servidor.bat echo pause

> iniciar_admin_dev.bat echo @echo off
>> iniciar_admin_dev.bat echo title Almoco Estudantil - Painel Admin (Dev)
>> iniciar_admin_dev.bat echo cd /d "%%~dp0"
>> iniciar_admin_dev.bat echo call venv\Scripts\activate.bat
>> iniciar_admin_dev.bat echo python run_admin.py
>> iniciar_admin_dev.bat echo pause

echo.
echo ==================================================================
echo            INSTALACAO CONCLUIDA COM SUCESSO!
echo ==================================================================
echo O sistema esta pronto para ser executado.
echo.
echo Para iniciar o servidor em producao, execute:
echo   - iniciar_servidor.bat
echo.
echo O sistema ficara acessivel na rede local em:
echo   http://localhost:5000  (ou pelo IP da maquina na rede)
echo ==================================================================
echo.
pause

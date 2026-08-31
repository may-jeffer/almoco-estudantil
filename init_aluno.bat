@echo off
:: Navega para a pasta do projeto
cd /d "C:\app_almoco\almoco-estudantil"

:: Executa o Python do ambiente virtual no script
"C:\app_almoco\almoco-estudantil\venv\Scripts\python.exe" run_aluno.py

:: Se o python fechar por erro, o pause abaixo ajuda voce a ler o erro no log
pause
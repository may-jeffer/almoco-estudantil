#!/usr/bin/env python3
"""
Script de Empacotamento para Distribuição (Build Package) - Almoço Estudantil
=============================================================================
Gera um pacote limpo e pronto para distribuição (.zip ou .tar.gz) contendo
apenas os arquivos essenciais de produção, excluindo:
 - Bancos de dados (database.db, *.sqlite) -> GARANTIA DE INSTALAÇÃO LIMPA/ZERO
 - Arquivos sensíveis (.env, credenciais)
 - Versionamento (.git)
 - Caches (__pycache__, *.pyc)
 - Ambientes virtuais (venv/)
 - Arquivos de testes (test_*.py, tests/)

Suporta o modo '--offline', que realiza o download antecipado das dependências
Python (arquivos .whl) e as embute dentro da pasta 'wheels/' no arquivo gerado.
"""

import os
import sys
import shutil
import zipfile
import tarfile
import argparse
import subprocess

# Diretórios e extensões estritamente proibidos de entrar no pacote
EXCLUDE_DIRS = {
    '.git', '.github', 'venv', '.venv', 'env', '__pycache__',
    'dist', 'build', '.idea', '.vscode', '.gemini', '.agent',
    '.system_generated', 'tests', 'scratch'
}

EXCLUDE_FILES = {
    'database.db', 'database.db-journal', 'database.db-wal', 'database.db-shm',
    '.env', '.env.local', '.env.production',
    '.gitignore', '.gitattributes'
}

EXCLUDE_EXTENSIONS = (
    '.pyc', '.pyo', '.pyd', '.db', '.sqlite', '.sqlite3', '.log', '.tmp'
)

def should_exclude(rel_path):
    parts = rel_path.replace('\\', '/').split('/')
    
    # Verifica pastas proibidas
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True

    # Verifica testes unitários / temporários
    filename = parts[-1]
    if filename.startswith('test_') and filename.endswith('.py'):
        return True

    # Verifica arquivos de banco de dados e sensíveis
    if filename in EXCLUDE_FILES:
        return True

    # Verifica extensões proibidas
    if any(filename.endswith(ext) for ext in EXCLUDE_EXTENSIONS):
        return True

    # Em static/uploads/, não empacotar arquivos enviados por usuários no ambiente de desenvolvimento
    if len(parts) > 2 and parts[0] == 'static' and parts[1] == 'uploads':
        if filename != '.gitkeep':
            return True

    return False

def download_offline_wheels(wheels_dir):
    print("\n[*] Modo Offline ativado: Baixando wheels das dependências...")
    os.makedirs(wheels_dir, exist_ok=True)
    
    cmd = [
        sys.executable, "-m", "pip", "download",
        "-r", "requirements.txt",
        "-d", wheels_dir
    ]
    
    print(f"[*] Executando: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("[!] Aviso: Houve erros ao baixar alguns pacotes wheels. Verifique a conexão com a internet.")
    else:
        wheel_count = len([f for f in os.listdir(wheels_dir) if f.endswith('.whl')])
        print(f"[✔] Download concluído: {wheel_count} arquivo(s) .whl salvos em '{wheels_dir}'.")

def create_package(output_dir="dist", package_name="almoco-estudantil-dist", offline=False, fmt="zip"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(output_dir, exist_ok=True)
    
    # Se offline, baixar as bibliotecas temporariamente para incluir no zip
    temp_wheels_dir = os.path.join(base_dir, "dist_temp_wheels")
    if offline:
        download_offline_wheels(temp_wheels_dir)

    target_archive = os.path.join(output_dir, f"{package_name}.{fmt}")
    if os.path.exists(target_archive):
        os.remove(target_archive)

    print(f"\n[*] Iniciando empacotamento em: {target_archive}")
    total_files = 0

    if fmt == "zip":
        with zipfile.ZipFile(target_archive, 'w', zipfile.ZIP_DEFLATED) as zip_out:
            # 1. Empacotar arquivos do projeto
            for root, dirs, files in os.walk(base_dir):
                # Modificar dirs in-place para não percorrer pastas ignoradas
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and d != "dist_temp_wheels"]
                
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, base_dir)
                    
                    if not should_exclude(rel_path):
                        if rel_path.endswith(('.bat', '.cmd')):
                            with open(full_path, 'rb') as f_in:
                                b_data = f_in.read().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
                            zip_out.writestr(rel_path, b_data)
                        elif rel_path.endswith('.sh'):
                            with open(full_path, 'rb') as f_in:
                                b_data = f_in.read().replace(b'\r\n', b'\n')
                            zip_out.writestr(rel_path, b_data)
                        else:
                            zip_out.write(full_path, rel_path)
                        total_files += 1

            # 2. Empacotar wheels se modo offline foi acionado
            if offline and os.path.exists(temp_wheels_dir):
                for file in os.listdir(temp_wheels_dir):
                    if file.endswith('.whl'):
                        full_path = os.path.join(temp_wheels_dir, file)
                        rel_path = os.path.join("wheels", file)
                        zip_out.write(full_path, rel_path)
                        total_files += 1
                        
            # Garantir existência da pasta uploads vazia com .gitkeep
            zip_out.writestr("static/uploads/.gitkeep", "")

    elif fmt == "tar.gz":
        with tarfile.open(target_archive, "w:gz") as tar_out:
            for root, dirs, files in os.walk(base_dir):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and d != "dist_temp_wheels"]
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, base_dir)
                    if not should_exclude(rel_path):
                        if rel_path.endswith(('.bat', '.cmd')):
                            with open(full_path, 'rb') as f_in:
                                b_data = f_in.read().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
                            ti = tarfile.TarInfo(name=rel_path)
                            ti.size = len(b_data)
                            import io
                            tar_out.addfile(ti, io.BytesIO(b_data))
                        elif rel_path.endswith('.sh'):
                            with open(full_path, 'rb') as f_in:
                                b_data = f_in.read().replace(b'\r\n', b'\n')
                            ti = tarfile.TarInfo(name=rel_path)
                            ti.size = len(b_data)
                            import io
                            tar_out.addfile(ti, io.BytesIO(b_data))
                        else:
                            tar_out.add(full_path, arcname=rel_path)
                        total_files += 1

            if offline and os.path.exists(temp_wheels_dir):
                for file in os.listdir(temp_wheels_dir):
                    if file.endswith('.whl'):
                        full_path = os.path.join(temp_wheels_dir, file)
                        rel_path = os.path.join("wheels", file)
                        tar_out.add(full_path, arcname=rel_path)
                        total_files += 1

    # Limpeza dos wheels temporários
    if os.path.exists(temp_wheels_dir):
        shutil.rmtree(temp_wheels_dir, ignore_errors=True)

    size_mb = os.path.getsize(target_archive) / (1024 * 1024)

    print("\n" + "=" * 60)
    print("      PACOTE GERADO COM SUCESSO!")
    print("=" * 60)
    print(f"  Arquivo:       {target_archive}")
    print(f"  Tamanho:       {size_mb:.2f} MB")
    print(f"  Total itens:   {total_files} arquivos")
    print(f"  Modo Offline:  {'SIM (com wheels incluídos)' if offline else 'NÃO (requer internet no servidor destino)'}")
    print(f"  Banco de Dados: LIMPO (Nenhum database.db incluído)")
    print("=" * 60 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Empacotador Oficial para Distribuição do Sistema de Almoço Estudantil.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Baixa os arquivos .whl das dependências e inclui no pacote para instalação sem acesso à internet."
    )
    parser.add_argument(
        "--format",
        choices=["zip", "tar.gz"],
        default="zip",
        help="Formato do arquivo compactado (padrão: zip)."
    )
    parser.add_argument(
        "--output-dir",
        default="dist",
        help="Diretório de saída para o pacote gerado (padrão: dist/)."
    )
    parser.add_argument(
        "--name",
        default="almoco-estudantil-dist",
        help="Nome do arquivo final sem extensão (padrão: almoco-estudantil-dist)."
    )
    args = parser.parse_args()

    create_package(
        output_dir=args.output_dir,
        package_name=args.name,
        offline=args.offline,
        fmt=args.format
    )

if __name__ == "__main__":
    main()

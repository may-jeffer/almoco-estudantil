import sys
import os
import json
import getpass
import argparse
from werkzeug.security import generate_password_hash
from database import init_db, closing, get_db_connection

# Cores ANSI para o terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

def parse_args():
    parser = argparse.ArgumentParser(
        description="Inicializador e Cadastro de Administrador Mestre do Sistema de Cantina Estudantil."
    )
    parser.add_argument(
        "--default",
        action="store_true",
        help="Cria um administrador inicial padrão (admin / admin123) com alerta de troca no primeiro acesso."
    )
    parser.add_argument("-u", "--user", type=str, help="Nome de usuário para o novo Administrador.")
    parser.add_argument("-p", "--password", type=str, help="Senha para o novo Administrador.")
    parser.add_argument("--nome", type=str, default="", help="Nome completo do Administrador.")
    parser.add_argument("--cpf", type=str, default="", help="CPF do Administrador.")
    parser.add_argument("--setor", type=str, default="", help="Setor (ex: Nutrição, TI, Direção).")
    parser.add_argument("--email", type=str, default="", help="E-mail de recuperação do Administrador.")
    parser.add_argument("--force", action="store_true", help="Ignora verificação de administradores já existentes.")
    return parser.parse_args()

def criar_admin_no_banco(conn, usuario, senha, nome="", cpf="", setor="", email=""):
    hash_senha = generate_password_hash(senha)
    perms = json.dumps(["all"])
    conn.execute("""
        INSERT INTO administradores 
        (usuario, senha, nome, cpf, setor, email, perfil, permissoes) 
        VALUES (?, ?, ?, ?, ?, ?, 'admin_mestre', ?)
    """, (usuario, hash_senha, nome, cpf, setor, email, perms))
    conn.commit()

def main():
    args = parse_args()
    print(f"\n{BOLD}{GREEN}--- Inicializador de Administrador (Deploy Seguro) ---{RESET}")
    init_db()

    with closing(get_db_connection()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM administradores").fetchone()[0]

        # Caso já existam administradores
        if count > 0 and not args.force:
            if args.default:
                print(f"{YELLOW}AVISO: Já existem {count} administrador(es) cadastrado(s). O usuário padrão não será sobrescrito.{RESET}")
                return
            if not args.user:
                print(f"{YELLOW}AVISO: Já existem {count} administradores cadastrados neste banco.{RESET}")
                continuar = input("Deseja criar mais um acesso mestre? (s/n): ")
                if continuar.lower() != 's':
                    print(f"{RED}Operação cancelada.{RESET}")
                    sys.exit(0)

        # MODO 1: Padrão Provisório (--default)
        if args.default:
            usuario = "admin"
            senha = "admin123"
            nome = "Administrador Geral"
            email = "admin@cantina.local"
            try:
                criar_admin_no_banco(conn, usuario, senha, nome=nome, email=email)
                print(f"\n{BOLD}{CYAN}=================================================================={RESET}")
                print(f"{BOLD}{GREEN}✔ ADMINISTRADOR PADRÃO CRIADO COM SUCESSO!{RESET}")
                print(f"  {BOLD}Usuário:{RESET} {usuario}")
                print(f"  {BOLD}Senha:{RESET}   {senha}")
                print(f"{BOLD}{YELLOW}⚠ ATENÇÃO: Por segurança, acesse o painel e altere a senha imediatamente.{RESET}")
                print(f"{BOLD}{CYAN}=================================================================={RESET}\n")
            except Exception as e:
                print(f"{RED}Erro ao criar administrador padrão: {e}{RESET}")
            return

        # MODO 2: Não Interativo com Argumentos (--user e --password)
        if args.user and args.password:
            usuario = args.user.strip()
            senha = args.password
            if len(senha) < 6:
                print(f"{RED}Erro: A senha precisa ter no mínimo 6 caracteres.{RESET}")
                sys.exit(1)
            try:
                criar_admin_no_banco(conn, usuario, senha, nome=args.nome, cpf=args.cpf, setor=args.setor, email=args.email.lower())
                print(f"\n{GREEN}{BOLD}SUCESSO!{RESET} {GREEN}O administrador '{usuario}' foi criado com acesso total.{RESET}\n")
            except Exception as e:
                print(f"{RED}Erro ao inserir no banco: {e}{RESET}")
                sys.exit(1)
            return

        # MODO 3: Interativo (Padrão quando chamado sem argumentos)
        usuario = input("Digite o nome de USUÁRIO para o Admin: ").strip()
        if not usuario:
            print(f"{RED}Erro: Usuário não pode ser vazio.{RESET}")
            return

        senha = getpass.getpass("Digite a SENHA para este Admin: ")
        if len(senha) < 6:
            print(f"{RED}Erro: A senha precisa ter no mínimo 6 caracteres.{RESET}")
            return

        confirma = getpass.getpass("Confirme a SENHA: ")
        if senha != confirma:
            print(f"{RED}Erro: As senhas não conferem.{RESET}")
            return

        nome = input("Digite o NOME COMPLETO do Admin (opcional): ").strip()
        cpf = input("Digite o CPF do Admin (opcional, 000.000.000-00): ").strip()
        setor = input("Digite o SETOR do Admin (opcional, ex: Nutrição, TI, Direção): ").strip()
        email = input("Digite o E-MAIL institucional para recuperação (recomendado): ").strip().lower()

        try:
            criar_admin_no_banco(conn, usuario, senha, nome=nome, cpf=cpf, setor=setor, email=email)
            print(f"\n{GREEN}{BOLD}SUCESSO!{RESET} {GREEN}O administrador '{usuario}' foi criado com acesso total.{RESET}\n")
        except Exception as e:
            print(f"{RED}Erro ao inserir no banco: {e}{RESET}")

if __name__ == "__main__":
    main()


import sys
import getpass
from werkzeug.security import generate_password_hash
from database import init_db, closing, get_db_connection

# Cores ANSI para o terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

def main():
    print(f"\n{BOLD}{GREEN}--- Inicializador de Administrador (Deploy Seguro) ---{RESET}")
    init_db()
    
    with closing(get_db_connection()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM administradores").fetchone()[0]
        if count > 0:
            print(f"{YELLOW}AVISO: Já existem administradores cadastrados neste banco.{RESET}")
            continuar = input("Deseja criar mais um acesso mestre? (s/n): ")
            if continuar.lower() != 's':
                print(f"{RED}Operação cancelada.{RESET}")
                sys.exit(0)

        usuario = input("Digite o nome de USUÁRIO para o Admin: ").strip()
        if not usuario:
            print(f"{RED}Erro: Usuário não pode ser vazio.{RESET}")
            return

        senha = getpass.getpass("Digite a SENHA para este Admin: ")
        if len(senha) < 4:
            print(f"{RED}Erro: A senha precisa ter no mínimo 4 caracteres.{RESET}")
            return

        confirma = getpass.getpass("Confirme a SENHA: ")
        if senha != confirma:
            print(f"{RED}Erro: As senhas não conferem.{RESET}")
            return

        nome = input("Digite o NOME COMPLETO do Admin (opcional): ").strip()
        cpf = input("Digite o CPF do Admin (opcional, 000.000.000-00): ").strip()
        setor = input("Digite o SETOR do Admin (opcional, ex: Nutrição, TI, Direção): ").strip()
        email = input("Digite o E-MAIL institucional para recuperação (recomendado): ").strip().lower()

        hash_senha = generate_password_hash(senha)
        
        try:
            import json
            perms = json.dumps(["all"])
            conn.execute("""
                INSERT INTO administradores 
                (usuario, senha, nome, cpf, setor, email, perfil, permissoes) 
                VALUES (?, ?, ?, ?, ?, ?, 'admin_mestre', ?)
            """, (usuario, hash_senha, nome, cpf, setor, email, perms))
            conn.commit()
            print(f"\n{GREEN}{BOLD}SUCESSO!{RESET} {GREEN}O administrador '{usuario}' foi criado com acesso total.{RESET}\n")
        except Exception as e:
            print(f"{RED}Erro ao inserir no banco: {e}{RESET}")

if __name__ == "__main__":
    main()

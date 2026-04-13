import sqlite3
import random
import string
from contextlib import closing

DB_FILE = 'database.db'

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with closing(get_db_connection()) as conn:
        with conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS turmas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alunos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    matricula TEXT UNIQUE NOT NULL,
                    cpf TEXT UNIQUE NOT NULL,
                    data_nascimento TEXT NOT NULL,
                    restricoes TEXT,
                    email TEXT,
                    senha_hash TEXT,
                    reset_token TEXT,
                    reset_expiracao TEXT,
                    turma_id INTEGER NOT NULL,
                    FOREIGN KEY (turma_id) REFERENCES turmas (id)
                );

                CREATE TABLE IF NOT EXISTS cardapios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT UNIQUE NOT NULL, -- formato YYYY-MM-DD
                    descricao TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reservas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aluno_id INTEGER,
                    cardapio_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'ATIVA', -- ATIVA, CANCELADA, CONSUMIDA
                    codigo_unico TEXT UNIQUE NOT NULL,
                    data_registro TEXT NOT NULL,
                    FOREIGN KEY(aluno_id) REFERENCES alunos(id),
                    FOREIGN KEY(cardapio_id) REFERENCES cardapios(id)
                );

                CREATE TABLE IF NOT EXISTS configuracoes (
                    id INTEGER PRIMARY KEY CHECK (id = 1), -- Apenas uma linha
                    horario_limite TEXT NOT NULL DEFAULT '18:00',
                    nome_sistema TEXT DEFAULT 'Cantina Estudantil',
                    modo_login_aluno TEXT DEFAULT 'DATA_NASC',
                    smtp_host TEXT,
                    smtp_porta INTEGER,
                    smtp_user TEXT,
                    smtp_senha TEXT,
                    smtp_ativo INTEGER DEFAULT 0,
                    logo_path TEXT,
                    sigla_instituicao TEXT DEFAULT 'IFAP'
                );

                CREATE TABLE IF NOT EXISTS administradores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE NOT NULL,
                    senha TEXT NOT NULL,
                    perfil TEXT DEFAULT 'admin_mestre',
                    permissoes TEXT DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS avisos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    titulo TEXT,
                    mensagem TEXT NOT NULL,
                    tipo TEXT DEFAULT 'info', -- info, warning, danger
                    data_criacao TEXT NOT NULL
                );
            ''')
            
            # Garantir que exista uma configuração inicial
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM configuracoes")
            if cur.fetchone()[0] == 0:
                cur.execute("INSERT INTO configuracoes (id, horario_limite, nome_sistema, modo_login_aluno) VALUES (1, '18:00', 'Cantina Estudantil', 'DATA_NASC')")
                
            # Migração automática 1: nome_sistema
            try:
                cur.execute("SELECT nome_sistema FROM configuracoes LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE configuracoes ADD COLUMN nome_sistema TEXT DEFAULT 'Cantina Estudantil'")
                conn.commit()
                
            # Migração automática 2: modo_login_aluno
            try:
                cur.execute("SELECT modo_login_aluno FROM configuracoes LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE configuracoes ADD COLUMN modo_login_aluno TEXT DEFAULT 'DATA_NASC'")
                conn.commit()
                
            # Migração automática 3: perfil em administradores
            try:
                cur.execute("SELECT perfil FROM administradores LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE administradores ADD COLUMN perfil TEXT DEFAULT 'admin_mestre'")
                conn.commit()
                
            # Migração automática 4: emails e senhas nos alunos
            try:
                cur.execute("ALTER TABLE alunos ADD COLUMN email TEXT")
                cur.execute("ALTER TABLE alunos ADD COLUMN senha_hash TEXT")
            except sqlite3.OperationalError:
                pass
            conn.commit()
                
            # Migração automática 5: SMTP Global e Branding
            try:
                cur.execute("SELECT smtp_host FROM configuracoes LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE configuracoes ADD COLUMN smtp_host TEXT")
                cur.execute("ALTER TABLE configuracoes ADD COLUMN smtp_porta INTEGER")
                cur.execute("ALTER TABLE configuracoes ADD COLUMN smtp_user TEXT")
                cur.execute("ALTER TABLE configuracoes ADD COLUMN smtp_senha TEXT")
                cur.execute("ALTER TABLE configuracoes ADD COLUMN smtp_ativo INTEGER DEFAULT 0")
            
            try:
                cur.execute("SELECT sigla_instituicao FROM configuracoes LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE configuracoes ADD COLUMN sigla_instituicao TEXT DEFAULT 'IFAP'")
                cur.execute("ALTER TABLE configuracoes ADD COLUMN logo_path TEXT")
            
            conn.commit()
                
            # Migração automática 6: Tokens de Segurança do Aluno
            try:
                cur.execute("SELECT reset_token FROM alunos LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE alunos ADD COLUMN reset_expiracao TEXT")
                conn.commit()

            # Migração automática 7: Permissões Granulares (ACL)
            try:
                cur.execute("SELECT permissoes FROM administradores LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE administradores ADD COLUMN permissoes TEXT DEFAULT '[]'")
                # Se for mestre antigo, dar permissão total logo de cara:
                cur.execute("UPDATE administradores SET permissoes = '[\"all\"]' WHERE perfil = 'admin_mestre'")
                cur.execute("UPDATE administradores SET permissoes = '[\"fila\"]' WHERE perfil = 'operador_fila'")
                conn.commit()

            # Migração automática 8: Alunos Extra (Sobras na Fila)
            try:
                cur.execute("SELECT tipo_consumo FROM reservas LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE reservas ADD COLUMN tipo_consumo TEXT DEFAULT 'NORMAL'")
                conn.commit()

            # O admin inicial NÃO é mais criado automaticamente no models.py por motivos de segurança cibernética.
            # O administrador deve rodar o script 'init_admin.py' no momento do deploy para definir sua senha proprietária.
            pass

def generate_unique_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# Funções auxiliares baseadas nas necessidades do projeto
def get_config():
    with closing(get_db_connection()) as conn:
        return conn.execute("SELECT * FROM configuracoes WHERE id = 1").fetchone()

def get_proximos_cardapios(data_atual_str):
    with closing(get_db_connection()) as conn:
        return conn.execute("SELECT * FROM cardapios WHERE data >= ? ORDER BY data ASC", (data_atual_str,)).fetchall()

def get_proximo_cardapio(data_atual_str):
    with closing(get_db_connection()) as conn:
        return conn.execute("SELECT * FROM cardapios WHERE data >= ? ORDER BY data ASC LIMIT 1", (data_atual_str,)).fetchone()

import sqlite3
from contextlib import closing
import os
import unicodedata

# Determinar o caminho absoluto do banco de dados na raiz do projeto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, 'database.db')

def remove_accents(text):
    if text is None:
        return ""
    # Decompõe os caracteres acentuados em caractere + acento, depois remove os acentos (Mn = Mark, Nonspacing)
    return "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn').lower()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.create_function("remove_accents", 1, remove_accents)
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
                    permitido_almoco INTEGER DEFAULT 1,
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
                    sigla_instituicao TEXT DEFAULT 'SIGLA',
                    tempo_autologout INTEGER DEFAULT 60
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

                CREATE TABLE IF NOT EXISTS eventos_participantes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aluno_id INTEGER NOT NULL,
                    turma_id INTEGER NOT NULL,
                    FOREIGN KEY(aluno_id) REFERENCES alunos(id),
                    FOREIGN KEY(turma_id) REFERENCES turmas(id),
                    UNIQUE(aluno_id, turma_id)
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
                cur.execute("ALTER TABLE configuracoes ADD COLUMN sigla_instituicao TEXT DEFAULT 'SIGLA'")
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

            # Migração automática 9: Opção de liberar/bloquear pedidos de almoço dos alunos
            try:
                cur.execute("SELECT permitido_almoco FROM alunos LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE alunos ADD COLUMN permitido_almoco INTEGER DEFAULT 1")
                conn.commit()

            # Migração automática 10: Limite de reservas ativas simultâneas
            try:
                cur.execute("SELECT max_reservas_ativas FROM configuracoes LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE configuracoes ADD COLUMN max_reservas_ativas INTEGER DEFAULT 1")
                conn.commit()

            # Migração automática 11: is_evento na tabela turmas
            try:
                cur.execute("SELECT is_evento FROM turmas LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE turmas ADD COLUMN is_evento INTEGER DEFAULT 0")
                conn.commit()
                
            # Migração automática 12: instituicao na tabela alunos
            try:
                cur.execute("SELECT instituicao FROM alunos LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE alunos ADD COLUMN instituicao TEXT")
                conn.commit()

            # Migração automática 13: data_inicio e data_fim na tabela turmas
            try:
                cur.execute("SELECT data_inicio FROM turmas LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE turmas ADD COLUMN data_inicio TEXT")
                cur.execute("ALTER TABLE turmas ADD COLUMN data_fim TEXT")
                conn.commit()

            # Migração automática 14: turma_id (contexto) na tabela reservas
            try:
                cur.execute("SELECT turma_id FROM reservas LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE reservas ADD COLUMN turma_id INTEGER REFERENCES turmas(id)")
                conn.commit()

            # Migração automática 15: codigo_cracha na tabela eventos_participantes
            try:
                cur.execute("SELECT codigo_cracha FROM eventos_participantes LIMIT 1")
            except sqlite3.OperationalError:
                # SQLite não permite adicionar coluna UNIQUE diretamente via ALTER TABLE
                cur.execute("ALTER TABLE eventos_participantes ADD COLUMN codigo_cracha TEXT")
                cur.execute("CREATE UNIQUE INDEX idx_codigo_cracha ON eventos_participantes(codigo_cracha)")
                conn.commit()

            # Migração automática 16: tipo_refeicao na tabela cardapios e ajuste de UNIQUE
            try:
                cur.execute("SELECT tipo_refeicao FROM cardapios LIMIT 1")
            except sqlite3.OperationalError:
                # Precisamos recriar a tabela para mudar a restrição UNIQUE
                cur.execute("ALTER TABLE cardapios RENAME TO cardapios_old")
                cur.execute('''
                    CREATE TABLE cardapios (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        data TEXT NOT NULL,
                        descricao TEXT NOT NULL,
                        tipo_refeicao TEXT DEFAULT 'Almoço',
                        UNIQUE(data, tipo_refeicao)
                    )
                ''')
                cur.execute("INSERT INTO cardapios (id, data, descricao, tipo_refeicao) SELECT id, data, descricao, 'Almoço' FROM cardapios_old")
                cur.execute("DROP TABLE cardapios_old")
                conn.commit()

            # Migração automática 17: permitir_reserva na tabela cardapios
            try:
                cur.execute("SELECT permitir_reserva FROM cardapios LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE cardapios ADD COLUMN permitir_reserva INTEGER DEFAULT 1")
                conn.commit()

            # Migração automática 18: codigo_cracha na tabela alunos (crachá fixo para regulares)
            try:
                cur.execute("SELECT codigo_cracha FROM alunos LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE alunos ADD COLUMN codigo_cracha TEXT")
                cur.execute("CREATE UNIQUE INDEX idx_codigo_cracha_alunos ON alunos(codigo_cracha)")
                conn.commit()

            # Migração automática 19: campos detalhados na tabela cardapios
            try:
                cur.execute("SELECT acompanhamento FROM cardapios LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE cardapios ADD COLUMN acompanhamento TEXT")
                cur.execute("ALTER TABLE cardapios ADD COLUMN salada TEXT")
                cur.execute("ALTER TABLE cardapios ADD COLUMN proteinas TEXT")
                cur.execute("ALTER TABLE cardapios ADD COLUMN sobremesa TEXT")
                cur.execute("ALTER TABLE cardapios ADD COLUMN outros TEXT")
                conn.commit()

            # Migração automática 23: qtd_solicitada na tabela cardapios (quantidade solicitada ao fornecedor)
            try:
                cur.execute("SELECT qtd_solicitada FROM cardapios LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE cardapios ADD COLUMN qtd_solicitada INTEGER")
                conn.commit()

            # Migração automática 20: opção de enviar QR Code por e-mail ao confirmar reserva
            try:
                cur.execute("SELECT email_qr_reserva FROM configuracoes LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE configuracoes ADD COLUMN email_qr_reserva INTEGER DEFAULT 0")
                conn.commit()

            # Migração automática 22: tempo de autologout do aluno
            try:
                cur.execute("SELECT tempo_autologout FROM configuracoes LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE configuracoes ADD COLUMN tempo_autologout INTEGER DEFAULT 60")
                conn.commit()

            # O admin inicial NÃO é mais criado automaticamente no models.py por motivos de segurança cibernética.
            # O administrador deve rodar o script 'init_admin.py' no momento do deploy para definir sua senha proprietária.
            
            # Migração automática 21: normalizar data_nascimento dos alunos de DD/MM/AAAA para YYYY-MM-DD
            try:
                cur.execute("SELECT id, data_nascimento FROM alunos")
                alunos_rows = cur.fetchall()
                for row in alunos_rows:
                    dt = row['data_nascimento']
                    if dt and '/' in dt:
                        parts = dt.split('/')
                        if len(parts) == 3 and len(parts[2]) == 4:
                            new_dt = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                            cur.execute("UPDATE alunos SET data_nascimento = ? WHERE id = ?", (new_dt, row['id']))
                conn.commit()
            except Exception as e:
                print(f"Erro ao migrar datas de nascimento: {e}")

            # Migração automática 23: criar tabela de logs de auditoria se não existir
            try:
                cur.execute("SELECT COUNT(*) FROM logs_auditoria")
            except sqlite3.OperationalError:
                cur.execute('''
                    CREATE TABLE logs_auditoria (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        admin_id INTEGER,
                        usuario TEXT,
                        acao TEXT NOT NULL,
                        detalhes TEXT,
                        ip TEXT,
                        data_criacao TEXT NOT NULL,
                        FOREIGN KEY(admin_id) REFERENCES administradores(id)
                    )
                ''')
                conn.commit()

            # Migração automática 24: campos de avaliação de refeições (satisfação)
            try:
                cur.execute("SELECT avaliacao_nota FROM reservas LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE reservas ADD COLUMN avaliacao_nota INTEGER")
                cur.execute("ALTER TABLE reservas ADD COLUMN avaliacao_comentario TEXT")
                conn.commit()

            # Migração automática 25: tabelas de Base de Conhecimento
            try:
                cur.execute("SELECT COUNT(*) FROM bc_categorias")
            except sqlite3.OperationalError:
                cur.execute('''
                    CREATE TABLE bc_categorias (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT NOT NULL,
                        descricao TEXT,
                        icone TEXT DEFAULT 'folder',
                        ordem INTEGER DEFAULT 0,
                        criado_por TEXT,
                        data_criacao TEXT NOT NULL
                    )
                ''')
                cur.execute('''
                    CREATE TABLE bc_materiais (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        categoria_id INTEGER NOT NULL,
                        titulo TEXT NOT NULL,
                        descricao TEXT,
                        nome_arquivo TEXT,
                        caminho_arquivo TEXT,
                        tipo_arquivo TEXT,
                        tamanho_bytes INTEGER,
                        total_downloads INTEGER DEFAULT 0,
                        criado_por TEXT,
                        data_criacao TEXT NOT NULL,
                        FOREIGN KEY (categoria_id) REFERENCES bc_categorias(id)
                    )
                ''')
                conn.commit()

            # Migração automática 26: tabelas de Formulários de Pesquisa Estudantil
            try:
                cur.execute("SELECT COUNT(*) FROM formularios_pesquisa")
            except sqlite3.OperationalError:
                cur.execute('''
                    CREATE TABLE formularios_pesquisa (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        titulo TEXT NOT NULL,
                        descricao TEXT,
                        slug TEXT UNIQUE NOT NULL,
                        is_anonimo INTEGER DEFAULT 1,
                        ativo INTEGER DEFAULT 1,
                        data_inicio TEXT,
                        data_fim TEXT,
                        criado_por TEXT,
                        data_criacao TEXT NOT NULL
                    )
                ''')
                cur.execute('''
                    CREATE TABLE formulario_perguntas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        formulario_id INTEGER NOT NULL,
                        titulo_pergunta TEXT NOT NULL,
                        tipo_pergunta TEXT NOT NULL,
                        opcoes_json TEXT,
                        obrigatoria INTEGER DEFAULT 1,
                        ordem INTEGER DEFAULT 0,
                        FOREIGN KEY (formulario_id) REFERENCES formularios_pesquisa(id) ON DELETE CASCADE
                    )
                ''')
                cur.execute('''
                    CREATE TABLE formulario_respostas_envios (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        formulario_id INTEGER NOT NULL,
                        aluno_id INTEGER,
                        aluno_identificacao TEXT,
                        ip_origem TEXT,
                        data_envio TEXT NOT NULL,
                        FOREIGN KEY (formulario_id) REFERENCES formularios_pesquisa(id) ON DELETE CASCADE,
                        FOREIGN KEY (aluno_id) REFERENCES alunos(id)
                    )
                ''')
                cur.execute('''
                    CREATE TABLE formulario_respostas_itens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        envio_id INTEGER NOT NULL,
                        pergunta_id INTEGER NOT NULL,
                        resposta_texto TEXT,
                        FOREIGN KEY (envio_id) REFERENCES formulario_respostas_envios(id) ON DELETE CASCADE,
                        FOREIGN KEY (pergunta_id) REFERENCES formulario_perguntas(id) ON DELETE CASCADE
                    )
                ''')
                conn.commit()
            pass


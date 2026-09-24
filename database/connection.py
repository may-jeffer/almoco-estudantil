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
                    turma_id INTEGER,
                    curso TEXT,
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
                    tempo_autologout INTEGER DEFAULT 60,
                    tema_admin TEXT DEFAULT 'padrao',
                    permitir_reserva_recorrente INTEGER DEFAULT 0
                );


                CREATE TABLE IF NOT EXISTS administradores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE NOT NULL,
                    senha TEXT NOT NULL,
                    nome TEXT,
                    cpf TEXT,
                    setor TEXT,
                    email TEXT,
                    perfil TEXT DEFAULT 'operador',
                    permissoes TEXT DEFAULT '[]',
                    reset_token TEXT,
                    reset_expiracao TEXT,
                    modo_escuro INTEGER DEFAULT 0,
                    tema_preferido TEXT DEFAULT 'padrao'
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

            # Migração automática 24: tema_admin na tabela configuracoes (paleta de cores do painel admin)
            try:
                cur.execute("SELECT tema_admin FROM configuracoes LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE configuracoes ADD COLUMN tema_admin TEXT DEFAULT 'padrao'")
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

            # Migração automática 27: Controle de Recebimento, Temperatura e Qualidade das Refeições
            try:
                cur.execute("SELECT COUNT(*) FROM controle_qualidade")
            except sqlite3.OperationalError:
                cur.execute('''
                    CREATE TABLE controle_qualidade (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cardapio_id INTEGER NOT NULL,
                        campus TEXT NOT NULL,
                        data_recebimento TEXT NOT NULL,
                        horario_recebimento TEXT NOT NULL,
                        fornecedor TEXT NOT NULL,
                        criado_em TEXT NOT NULL,
                        atualizado_em TEXT,
                        criado_por TEXT,
                        atualizado_por TEXT,
                        FOREIGN KEY (cardapio_id) REFERENCES cardapios(id)
                    )
                ''')
                cur.execute('''
                    CREATE TABLE controle_qualidade_itens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        controle_id INTEGER NOT NULL,
                        tipo_preparo TEXT NOT NULL,
                        tipo_preparo_outro TEXT,
                        temperatura REAL,
                        conformidade TEXT NOT NULL,
                        aspecto_sensorial TEXT NOT NULL,
                        profissional_medicao TEXT NOT NULL,
                        responsavel_recebimento TEXT NOT NULL,
                        responsavel_fornecedor TEXT NOT NULL,
                        observacoes TEXT,
                        ordem INTEGER DEFAULT 0,
                        FOREIGN KEY (controle_id) REFERENCES controle_qualidade(id) ON DELETE CASCADE
                    )
                ''')
                conn.commit()
            except sqlite3.OperationalError:
                pass

            # Migração automática 28: padrao_qualidade_texto na tabela configuracoes
            try:
                cur.execute("SELECT padrao_qualidade_texto FROM configuracoes LIMIT 1")
            except sqlite3.OperationalError:
                cur.execute("ALTER TABLE configuracoes ADD COLUMN padrao_qualidade_texto TEXT")
                padrao_inicial = (
                    "• Preparações Quentes: Devem ser mantidas e recebidas a 60°C ou mais por no máximo 6 horas.\n"
                    "• Preparações Frias: Devem ser mantidas e recebidas abaixo de 10°C (ou abaixo de 5°C para carnes e sobremesas lácteas).\n"
                    "• Aspecto Sensorial: Avaliação de cor, odor, sabor e textura característicos de alimento próprio para consumo."
                )
                cur.execute("UPDATE configuracoes SET padrao_qualidade_texto = ? WHERE id = 1", (padrao_inicial,))
                conn.commit()

            # Migração automática 29: rastreabilidade e recuperação em administradores
            novas_colunas_admin = [
                ('nome', 'TEXT'),
                ('cpf', 'TEXT'),
                ('setor', 'TEXT'),
                ('email', 'TEXT'),
                ('reset_token', 'TEXT'),
                ('reset_expiracao', 'TEXT')
            ]
            for col_nome, col_tipo in novas_colunas_admin:
                try:
                    cur.execute(f"ALTER TABLE administradores ADD COLUMN {col_nome} {col_tipo}")
                except sqlite3.OperationalError:
                    pass
            # Migração automática 30: modo_escuro, tema_preferido e saneamento de perfis de administradores
            novas_colunas_preferencias = [
                ('modo_escuro', 'INTEGER DEFAULT 0'),
                ('tema_preferido', "TEXT DEFAULT 'padrao'")
            ]
            for col_nome, col_tipo in novas_colunas_preferencias:
                try:
                    cur.execute(f"ALTER TABLE administradores ADD COLUMN {col_nome} {col_tipo}")
                except sqlite3.OperationalError:
                    pass

            # Saneamento: administradores não-root sem 'all' explícito nas permissões são 'operador'
            cur.execute("""
                UPDATE administradores 
                SET perfil = 'operador' 
                WHERE usuario != 'admin' AND (permissoes IS NULL OR permissoes NOT LIKE '%"all"%')
            """)
            conn.commit()

            # Migração automática 31: modo_escuro em alunos
            try:
                cur.execute("ALTER TABLE alunos ADD COLUMN modo_escuro INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            conn.commit()

            # Migração automática 32: Metadados na tabela turmas (Curso, Ano, Série, etc.)
            novas_colunas_turmas = [
                ('curso', 'TEXT'),
                ('ano_letivo', 'INTEGER'),
                ('periodo_letivo', 'INTEGER DEFAULT 1'),
                ('serie_ano', 'INTEGER'),
                ('turno', 'TEXT'),
                ('modalidade', 'TEXT'),
                ('ativa', 'INTEGER DEFAULT 1'),
                ('dias_bloqueados', "TEXT DEFAULT ''")
            ]
            for col_nome, col_tipo in novas_colunas_turmas:
                try:
                    cur.execute(f"ALTER TABLE turmas ADD COLUMN {col_nome} {col_tipo}")
                except sqlite3.OperationalError:
                    pass
            conn.commit()

            # Migração automática 33: Metadados SUAP na tabela alunos
            novas_colunas_alunos = [
                ('serie_ano_atual', 'INTEGER'),
                ('ano_ingresso', 'INTEGER'),
                ('situacao_matricula', "TEXT DEFAULT 'Matriculado'")
            ]
            for col_nome, col_tipo in novas_colunas_alunos:
                try:
                    cur.execute(f"ALTER TABLE alunos ADD COLUMN {col_nome} {col_tipo}")
                except sqlite3.OperationalError:
                    pass
            conn.commit()

            # Migração automática 34: Tabela aluno_turma_historico
            cur.execute('''
                CREATE TABLE IF NOT EXISTS aluno_turma_historico (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aluno_id INTEGER NOT NULL,
                    turma_id INTEGER,
                    ano_letivo INTEGER,
                    periodo_letivo INTEGER DEFAULT 1,
                    serie_ano INTEGER,
                    situacao TEXT DEFAULT 'Cursando',
                    data_inicio TEXT NOT NULL,
                    data_fim TEXT,
                    observacao TEXT,
                    FOREIGN KEY (aluno_id) REFERENCES alunos(id),
                    FOREIGN KEY (turma_id) REFERENCES turmas(id),
                    UNIQUE(aluno_id, turma_id, ano_letivo, periodo_letivo)
                )
            ''')
            conn.commit()

            # Seed inicial de histórico para alunos existentes com turma_id vinculada
            try:
                from utils.helpers import date_hoje_str
                data_hoje = date_hoje_str()
            except Exception:
                from datetime import date
                data_hoje = date.today().strftime('%Y-%m-%d')

            cur.execute("""
                INSERT OR IGNORE INTO aluno_turma_historico 
                    (aluno_id, turma_id, ano_letivo, periodo_letivo, serie_ano, situacao, data_inicio, observacao)
                SELECT 
                    a.id, 
                    a.turma_id, 
                    t.ano_letivo, 
                    COALESCE(t.periodo_letivo, 1), 
                    COALESCE(a.serie_ano_atual, t.serie_ano), 
                    COALESCE(a.situacao_matricula, 'Cursando'), 
                    ?, 
                    'Histórico inicial registrado na migração'
                FROM alunos a
                LEFT JOIN turmas t ON a.turma_id = t.id
                WHERE a.turma_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM aluno_turma_historico h WHERE h.aluno_id = a.id
                  )
            """, (data_hoje,))
            conn.commit()

            # Migração automática 35: Colunas de motivo e autoria de cancelamento na tabela reservas
            novas_colunas_reservas = [
                ('motivo_cancelamento', 'TEXT'),
                ('cancelado_por', 'TEXT'),
                ('data_cancelamento', 'TEXT')
            ]
            for col_nome, col_tipo in novas_colunas_reservas:
                try:
                    cur.execute(f"ALTER TABLE reservas ADD COLUMN {col_nome} {col_tipo}")
                except sqlite3.OperationalError:
                    pass
            conn.commit()

            # Migração automática 36: Tabela config_janelas_reserva (Janelas Manuais por Dia da Semana)
            cur.execute('''
                CREATE TABLE IF NOT EXISTS config_janelas_reserva (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dia_refeicao INTEGER UNIQUE NOT NULL,
                    dia_nome TEXT NOT NULL,
                    ativo INTEGER DEFAULT 1,
                    abertura_dia_semana INTEGER DEFAULT 0,
                    abertura_semana_offset INTEGER DEFAULT 1,
                    abertura_horario TEXT DEFAULT '08:00',
                    fechamento_dia_semana INTEGER NOT NULL,
                    fechamento_semana_offset INTEGER NOT NULL,
                    fechamento_horario TEXT NOT NULL
                )
            ''')
            conn.commit()

            # Seed padrão inicial para cada dia da semana (0=Segunda ... 6=Domingo)
            janelas_padrao = [
                (0, 'Segunda-feira', 1, 0, 1, '08:00', 4, 1, '14:00'),
                (1, 'Terça-feira',   1, 0, 1, '08:00', 0, 0, '10:00'),
                (2, 'Quarta-feira',  1, 0, 1, '08:00', 1, 0, '10:00'),
                (3, 'Quinta-feira',  1, 0, 1, '08:00', 2, 0, '10:00'),
                (4, 'Sexta-feira',   1, 0, 1, '08:00', 3, 0, '10:00'),
                (5, 'Sábado',        0, 0, 1, '08:00', 4, 0, '10:00'),
                (6, 'Domingo',       0, 0, 1, '08:00', 4, 0, '10:00')
            ]
            for jp in janelas_padrao:
                cur.execute("""
                    INSERT OR IGNORE INTO config_janelas_reserva 
                    (dia_refeicao, dia_nome, ativo, abertura_dia_semana, abertura_semana_offset, abertura_horario, fechamento_dia_semana, fechamento_semana_offset, fechamento_horario)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, jp)
            conn.commit()

            # Migração automática 37: Controle de Recorrência e Tabela aluno_recorrencia_dias
            try:
                cur.execute("ALTER TABLE configuracoes ADD COLUMN permitir_reserva_recorrente INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

            cur.execute('''
                CREATE TABLE IF NOT EXISTS aluno_recorrencia_dias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aluno_id INTEGER NOT NULL,
                    dia_semana INTEGER NOT NULL,
                    ativo INTEGER DEFAULT 1,
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT,
                    FOREIGN KEY(aluno_id) REFERENCES alunos(id),
                    UNIQUE(aluno_id, dia_semana)
                )
            ''')
            # Migração automática 38: Campo curso na tabela alunos, remoção de NOT NULL em turma_id e backfill inteligente
            try:
                cur.execute("ALTER TABLE alunos ADD COLUMN curso TEXT")
            except sqlite3.OperationalError:
                pass

            # Garante que turma_id possa ser NULL (para alunos em regime de dependência / avulsos)
            aluno_info = cur.execute("PRAGMA table_info(alunos)").fetchall()
            turma_id_col = next((c for c in aluno_info if c[1] == 'turma_id'), None)
            if turma_id_col and turma_id_col[3] == 1:  # notnull == 1
                cur.execute("PRAGMA foreign_keys = OFF")
                cur.execute("ALTER TABLE alunos RENAME TO alunos_old")
                cur.execute('''
                    CREATE TABLE alunos (
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
                        turma_id INTEGER,
                        instituicao TEXT,
                        codigo_cracha TEXT,
                        modo_escuro INTEGER DEFAULT 0,
                        serie_ano_atual INTEGER,
                        ano_ingresso INTEGER,
                        situacao_matricula TEXT DEFAULT 'Matriculado',
                        curso TEXT,
                        FOREIGN KEY (turma_id) REFERENCES turmas (id)
                    )
                ''')
                cur.execute('''
                    INSERT INTO alunos (
                        id, nome, matricula, cpf, data_nascimento, restricoes, email, senha_hash, reset_token, reset_expiracao,
                        permitido_almoco, turma_id, instituicao, codigo_cracha, modo_escuro, serie_ano_atual, ano_ingresso,
                        situacao_matricula, curso
                    ) SELECT 
                        id, nome, matricula, cpf, data_nascimento, restricoes, email, senha_hash, reset_token, reset_expiracao,
                        permitido_almoco, turma_id, instituicao, codigo_cracha, modo_escuro, serie_ano_atual, ano_ingresso,
                        situacao_matricula, curso
                    FROM alunos_old
                ''')
                cur.execute("DROP TABLE alunos_old")
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_codigo_cracha_alunos ON alunos(codigo_cracha)")
                cur.execute("PRAGMA foreign_keys = ON")
                conn.commit()

            # Backfill para turmas legadas onde o nome da turma era o próprio curso
            cur.execute("""
                UPDATE turmas
                SET curso = nome
                WHERE (curso IS NULL OR TRIM(curso) = '') 
                  AND COALESCE(is_evento, 0) = 0 
                  AND nome NOT LIKE '20%'
            """)

            # Backfill automático: sincroniza curso dos alunos a partir da turma atual
            cur.execute("""
                UPDATE alunos 
                SET curso = (
                    SELECT t.curso FROM turmas t 
                    WHERE t.id = alunos.turma_id AND t.curso IS NOT NULL AND TRIM(t.curso) != ''
                )
                WHERE (curso IS NULL OR TRIM(curso) = '') AND turma_id IS NOT NULL
            """)

            # Backfill a partir do histórico acadêmico caso ainda esteja sem curso
            cur.execute("""
                UPDATE alunos 
                SET curso = (
                    SELECT t.curso FROM aluno_turma_historico h
                    JOIN turmas t ON h.turma_id = t.id
                    WHERE h.aluno_id = alunos.id AND t.curso IS NOT NULL AND TRIM(t.curso) != ''
                    ORDER BY h.id DESC LIMIT 1
                )
                WHERE (curso IS NULL OR TRIM(curso) = '')
            """)
            conn.commit()

            # Migração automática 39: Saneamento e unificação definitiva de CPFs duplicados
            try:
                from utils.filters import format_cpf
                rows_alunos = cur.execute("SELECT id, matricula, cpf, codigo_cracha FROM alunos").fetchall()
                cpf_map = {}
                for r in rows_alunos:
                    c_dig = ''.join(filter(str.isdigit, str(r['cpf'] or '')))
                    if c_dig:
                        cpf_map.setdefault(c_dig, []).append(r)
                
                for c_dig, r_list in cpf_map.items():
                    if len(r_list) > 1:
                        def score_al(al):
                            tem_cracha = 1 if al['codigo_cracha'] else 0
                            return (tem_cracha, -al['id'])
                        r_list_sorted = sorted(r_list, key=score_al, reverse=True)
                        principal = r_list_sorted[0]
                        duplicatas = r_list_sorted[1:]
                        cpf_padrao = format_cpf(c_dig)
                        
                        for dup in duplicatas:
                            dup_id = dup['id']
                            cur.execute("UPDATE OR IGNORE reservas SET aluno_id = ? WHERE aluno_id = ?", (principal['id'], dup_id))
                            cur.execute("DELETE FROM reservas WHERE aluno_id = ?", (dup_id,))
                            cur.execute("UPDATE OR IGNORE aluno_turma_historico SET aluno_id = ? WHERE aluno_id = ?", (principal['id'], dup_id))
                            cur.execute("DELETE FROM aluno_turma_historico WHERE aluno_id = ?", (dup_id,))
                            cur.execute("UPDATE OR IGNORE aluno_recorrencia_dias SET aluno_id = ? WHERE aluno_id = ?", (principal['id'], dup_id))
                            cur.execute("DELETE FROM aluno_recorrencia_dias WHERE aluno_id = ?", (dup_id,))
                            cur.execute("DELETE FROM alunos WHERE id = ?", (dup_id,))
                            
                        cur.execute("UPDATE alunos SET cpf = ? WHERE id = ?", (cpf_padrao, principal['id']))
                conn.commit()
            except Exception as e:
                print(f"Aviso migração 39: {e}")

            # Migração automática 40: Bloqueio de reservas por turma em dias da semana específicos
            try:
                cur.execute("ALTER TABLE turmas ADD COLUMN dias_bloqueados TEXT DEFAULT ''")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            # Migração automática 41: Atualizar participantes de evento que foram lançados como EXTRA
            try:
                cur.execute("""
                    UPDATE reservas
                    SET tipo_consumo = 'EVENTO',
                        turma_id = COALESCE(
                            reservas.turma_id,
                            (SELECT a.turma_id FROM alunos a WHERE a.id = reservas.aluno_id),
                            (SELECT ep.turma_id FROM eventos_participantes ep WHERE ep.aluno_id = reservas.aluno_id LIMIT 1)
                        )
                    WHERE tipo_consumo = 'EXTRA'
                      AND aluno_id IN (
                          SELECT id FROM alunos 
                          WHERE matricula LIKE 'EVT-%' 
                             OR turma_id IN (SELECT id FROM turmas WHERE is_evento = 1)
                      )
                """)
                conn.commit()
            except Exception as e:
                print(f"Aviso migração 41: {e}")


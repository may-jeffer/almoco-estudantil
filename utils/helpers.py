from datetime import datetime, timedelta

def datetime_now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def get_agora():
    return datetime.now()

def date_hoje_str():
    return datetime.now().strftime('%Y-%m-%d')

DIAS_SEMANA_NOMES = [
    'Segunda-feira', 'Terça-feira', 'Quarta-feira', 
    'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo'
]

DIAS_SEMANA_ABREV = [
    'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'
]

def parse_dias_bloqueados(dias_str):
    """
    Recebe string como '0,2,4' ou lista/conjunto e retorna conjunto (set) de inteiros {0, 2, 4}.
    """
    if not dias_str:
        return set()
    if isinstance(dias_str, (set, list, tuple)):
        return {int(x) for x in dias_str if str(x).isdigit()}
    res = set()
    for part in str(dias_str).split(','):
        part = part.strip()
        if part.isdigit():
            res.add(int(part))
    return res

def formatar_dias_bloqueados(dias_str, abrev=False):
    """
    Formata string de dias bloqueados para exibição textual amigável.
    Ex: '2,4' -> 'Qua, Sex' (se abrev) ou 'Quarta-feira, Sexta-feira'
    """
    dias_set = parse_dias_bloqueados(dias_str)
    if not dias_set:
        return ""
    nomes = DIAS_SEMANA_ABREV if abrev else DIAS_SEMANA_NOMES
    dias_ordenados = sorted(dias_set)
    return ", ".join(nomes[d] for d in dias_ordenados if 0 <= d < len(nomes))

def calcular_janela_reserva(data_cardapio_str, conn=None):
    """
    Calcula a janela exata de abertura e fechamento da reserva para o dia da semana do cardápio,
    consultando a tabela config_janelas_reserva.
    Retorna dicionário com:
      - status: 'ABERTA' | 'NAO_INICIADA' | 'ENCERRADA' | 'INATIVO'
      - pode_reservar: bool
      - momento_abertura: datetime
      - momento_fechamento: datetime
      - abertura_formatada: str
      - fechamento_formatado: str
      - mensagem: str
    """
    agora = get_agora()
    data_cardapio = datetime.strptime(data_cardapio_str, '%Y-%m-%d')
    dia_refeicao = data_cardapio.weekday() # 0=Segunda ... 6=Domingo
    
    close_conn = False
    if conn is None:
        from database import get_db_connection
        conn = get_db_connection()
        close_conn = True
        
    try:
        regra = conn.execute(
            "SELECT * FROM config_janelas_reserva WHERE dia_refeicao = ?", 
            (dia_refeicao,)
        ).fetchone()
        
        if not regra or regra['ativo'] == 0:
            return {
                'status': 'INATIVO',
                'pode_reservar': False,
                'momento_abertura': None,
                'momento_fechamento': None,
                'abertura_formatada': '—',
                'fechamento_formatado': '—',
                'mensagem': f"Refeições não disponíveis para {DIAS_SEMANA_NOMES[dia_refeicao]}."
            }
            
        # Segunda-feira da semana da refeição (00:00:00)
        segunda_da_semana = (data_cardapio - timedelta(days=dia_refeicao)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 1. Momento de Abertura
        ab_offset = int(regra['abertura_semana_offset'] if regra['abertura_semana_offset'] is not None else 1)
        ab_dia = int(regra['abertura_dia_semana'] if regra['abertura_dia_semana'] is not None else 0)
        ab_hora, ab_min = map(int, (regra['abertura_horario'] or '08:00').split(':'))
        data_abertura = (segunda_da_semana - timedelta(weeks=ab_offset)) + timedelta(days=ab_dia)
        momento_abertura = data_abertura.replace(hour=ab_hora, minute=ab_min, second=0, microsecond=0)
        
        # 2. Momento de Fechamento (Corte do Fornecedor)
        fe_offset = int(regra['fechamento_semana_offset'] if regra['fechamento_semana_offset'] is not None else 1)
        fe_dia = int(regra['fechamento_dia_semana'] if regra['fechamento_dia_semana'] is not None else 4)
        fe_hora, fe_min = map(int, (regra['fechamento_horario'] or '14:00').split(':'))
        data_fechamento = (segunda_da_semana - timedelta(weeks=fe_offset)) + timedelta(days=fe_dia)
        momento_fechamento = data_fechamento.replace(hour=fe_hora, minute=fe_min, second=0, microsecond=0)
        
        abertura_fmt = momento_abertura.strftime('%d/%m às %H:%M')
        fechamento_fmt = momento_fechamento.strftime('%d/%m às %H:%M')
        
        if agora < momento_abertura:
            return {
                'status': 'NAO_INICIADA',
                'pode_reservar': False,
                'momento_abertura': momento_abertura,
                'momento_fechamento': momento_fechamento,
                'abertura_formatada': abertura_fmt,
                'fechamento_formatado': fechamento_fmt,
                'mensagem': f"Reservas iniciam em {abertura_fmt}."
            }
        elif agora > momento_fechamento:
            return {
                'status': 'ENCERRADA',
                'pode_reservar': False,
                'momento_abertura': momento_abertura,
                'momento_fechamento': momento_fechamento,
                'abertura_formatada': abertura_fmt,
                'fechamento_formatado': fechamento_fmt,
                'mensagem': f"Prazo encerrado em {fechamento_fmt}."
            }
        else:
            return {
                'status': 'ABERTA',
                'pode_reservar': True,
                'momento_abertura': momento_abertura,
                'momento_fechamento': momento_fechamento,
                'abertura_formatada': abertura_fmt,
                'fechamento_formatado': fechamento_fmt,
                'mensagem': f"Aberta até {fechamento_fmt}."
            }
    except Exception as e:
        hora, minuto = (18, 0)
        data_limite = data_cardapio - timedelta(days=1)
        momento_limite = data_limite.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        pode = agora <= momento_limite
        return {
            'status': 'ABERTA' if pode else 'ENCERRADA',
            'pode_reservar': pode,
            'momento_abertura': data_cardapio - timedelta(days=7),
            'momento_fechamento': momento_limite,
            'abertura_formatada': '—',
            'fechamento_formatado': momento_limite.strftime('%d/%m às %H:%M'),
            'mensagem': 'Aberta' if pode else 'Encerrada'
        }
    finally:
        if close_conn and conn:
            conn.close()

def pode_reservar(data_cardapio_str, horario_limite_str=None):
    """
    Mantém compatibilidade com chamadas anteriores:
    Consulta a janela configurada para o dia da semana do cardápio e retorna True se ABERTA.
    """
    info = calcular_janela_reserva(data_cardapio_str)
    return info['pode_reservar']

def sincronizar_reservas_recorrentes(aluno_id=None):
    """
    Gera automaticamente as reservas para estudantes com dias de recorrência ativos.
    SÓ EXECUTA se a configuração mestre 'permitir_reserva_recorrente' estiver ATIVA (1).
    """
    from database import get_db_connection, generate_unique_code
    
    with get_db_connection() as conn:
        cfg = conn.execute("SELECT permitir_reserva_recorrente FROM configuracoes WHERE id = 1").fetchone()
        if not cfg or not cfg['permitir_reserva_recorrente']:
            return 0
            
        hoje_str = date_hoje_str()
        
        cardapios = conn.execute(
            "SELECT * FROM cardapios WHERE data >= ? AND permitir_reserva = 1 ORDER BY data ASC",
            (hoje_str,)
        ).fetchall()
        
        if not cardapios:
            return 0
            
        query_recorrencias = """
            SELECT r.aluno_id, r.dia_semana, a.turma_id, a.permitido_almoco, a.situacao_matricula,
                   t.dias_bloqueados as turma_dias_bloqueados
            FROM aluno_recorrencia_dias r
            JOIN alunos a ON r.aluno_id = a.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.ativo = 1 AND a.permitido_almoco = 1 
              AND (a.situacao_matricula IS NULL OR a.situacao_matricula = 'Matriculado')
        """
        params = []
        if aluno_id:
            query_recorrencias += " AND r.aluno_id = ?"
            params.append(aluno_id)
            
        recorrencias = conn.execute(query_recorrencias, params).fetchall()
        if not recorrencias:
            return 0
            
        from collections import defaultdict
        alunos_por_dia = defaultdict(list)
        for rec in recorrencias:
            alunos_por_dia[rec['dia_semana']].append(rec)
            
        total_geradas = 0
        now_str = datetime_now_str()
        
        for c in cardapios:
            c_data = datetime.strptime(c['data'], '%Y-%m-%d')
            c_dia_semana = c_data.weekday()
            
            alunos_do_dia = alunos_por_dia.get(c_dia_semana, [])
            if not alunos_do_dia:
                continue
                
            janela = calcular_janela_reserva(c['data'], conn=conn)
            if janela['status'] == 'ENCERRADA':
                continue
                
            for aluno_rec in alunos_do_dia:
                # Se a turma do aluno bloqueia este dia da semana, não gera reserva recorrente
                turma_dias_bloq = parse_dias_bloqueados(aluno_rec['turma_dias_bloqueados'])
                if c_dia_semana in turma_dias_bloq:
                    continue

                aid = aluno_rec['aluno_id']
                res_existente = conn.execute(
                    "SELECT id, status FROM reservas WHERE aluno_id = ? AND cardapio_id = ?",
                    (aid, c['id'])
                ).fetchone()
                
                if res_existente:
                    continue
                    
                novo_cod = generate_unique_code()
                conn.execute("""
                    INSERT INTO reservas (aluno_id, cardapio_id, status, codigo_unico, data_registro, turma_id, tipo_consumo)
                    VALUES (?, ?, 'ATIVA', ?, ?, ?, 'NORMAL')
                """, (aid, c['id'], novo_cod, now_str, aluno_rec['turma_id']))
                total_geradas += 1
                
        if total_geradas > 0:
            conn.commit()
            
        return total_geradas

def sanitize_field(value):
    if value is None:
        return ''
    return str(value).strip()

def registrar_auditoria(acao, detalhes=""):
    from flask import session, request
    from database import get_db_connection, closing
    
    admin_id = session.get('admin_id')
    usuario = session.get('admin_usuario')
    ip = request.remote_addr
    data_criacao = datetime_now_str()
    
    try:
        with closing(get_db_connection()) as conn:
            conn.execute(
                "INSERT INTO logs_auditoria (admin_id, usuario, acao, detalhes, ip, data_criacao) VALUES (?, ?, ?, ?, ?, ?)",
                (admin_id, usuario, acao, detalhes, ip, data_criacao)
            )
            conn.commit()
    except Exception as e:
        print(f"Erro ao registrar auditoria: {e}")

def extrair_serie_e_curso(curso, serie_ano=None):
    """
    Extrai o nome base do curso e a série/ano (como int).
    Suporta formatos como:
      - curso="Curso Técnico...", serie_ano=2 -> ("Curso Técnico...", 2)
      - curso="2º - Curso Técnico...", serie_ano=None -> ("Curso Técnico...", 2)
      - curso="2º - Curso Técnico...", serie_ano=3 -> ("Curso Técnico...", 3)
      - curso="10º - Curso Superior...", serie_ano=None -> ("Curso Superior...", 10)
    """
    import re
    curso = (curso or '').strip()
    serie_int = None
    if serie_ano is not None and str(serie_ano).strip():
        try:
            serie_int = int(str(serie_ano).strip())
        except (ValueError, TypeError):
            pass

    m = re.match(r'^(\d+)\s*[ºª°o.]?\s*[-–—]\s*(.+)$', curso, re.IGNORECASE)
    if m:
        if serie_int is None:
            serie_int = int(m.group(1))
        curso = m.group(2).strip()

    return curso, serie_int

def formatar_nome_turma(curso, serie_ano=None):
    """
    Padroniza o nome da turma no formato estrito: SerieAno + Curso
    Exemplos:
      - '2º - Curso Técnico em Agroecologia - Integrado/Integral- PTG'
      - '3º - Curso Técnico em Agroecologia - Integrado/Integral- PTG'
      - '10º - Curso Superior de Bacharelado em Engenharia Agronômica - PTG'
    """
    curso_limpo, serie_int = extrair_serie_e_curso(curso, serie_ano)
    if not curso_limpo:
        return f"{serie_int}º Ano" if serie_int else "Sem Curso"

    if serie_int:
        return f"{serie_int}º - {curso_limpo}"
    return curso_limpo

def obter_ou_criar_turma(conn, curso, serie_ano=None, turno=None, ano_letivo=None, criar_se_nao_existir=False):
    """
    Localiza ou cria automaticamente uma turma com base na combinação de Curso e Série/Ano.
    Retorna o turma_id (int) ou None se não existir e criar_se_nao_existir for False.
    """
    curso_limpo, serie_int = extrair_serie_e_curso(curso, serie_ano)
    if not curso_limpo and not serie_int:
        return None

    nome_turma = formatar_nome_turma(curso_limpo, serie_int)

    # 1. Tenta buscar por nome exato da turma
    t = conn.execute("SELECT id, serie_ano, ano_letivo, periodo_letivo, curso FROM turmas WHERE LOWER(nome) = LOWER(?)", (nome_turma,)).fetchone()
    if t:
        return t['id']

    # 2. Tenta buscar por curso e série
    if curso_limpo and serie_int:
        t = conn.execute("SELECT id, serie_ano, ano_letivo, periodo_letivo, curso FROM turmas WHERE (LOWER(curso) = LOWER(?) OR LOWER(nome) = LOWER(?)) AND serie_ano = ?", (curso_limpo, nome_turma, serie_int)).fetchone()
        if t:
            return t['id']

    # 3. Tenta buscar se só tem curso
    if curso_limpo and not serie_int:
        t = conn.execute("SELECT id, serie_ano, ano_letivo, periodo_letivo, curso FROM turmas WHERE LOWER(nome) = LOWER(?) OR LOWER(curso) = LOWER(?)", (curso_limpo, curso_limpo)).fetchone()
        if t:
            return t['id']

    # 4. Cria se solicitado
    if criar_se_nao_existir:
        ano_let = ano_letivo or int(datetime.now().strftime('%Y'))
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO turmas (nome, curso, serie_ano, turno, ano_letivo, ativa)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (nome_turma, curso_limpo, serie_int, turno, ano_let))
        return cur.lastrowid

    return None


def parse_data_nascimento(val):
    """
    Normaliza e valida data de nascimento para o formato ISO 'YYYY-MM-DD'.
    Converte automaticamente anos abreviados com 2 dígitos (ex: '26' -> '2026', '98' -> '1998').
    Suporta separadores comuns ('/', '-', '.') e formatos:
      - DD/MM/AAAA, DD/MM/AA
      - AAAA-MM-DD
      - DDMMAAAA, DDMMAA
    Retorna a string formatada em ISO 'YYYY-MM-DD' se válida, ou None se inválida.
    """
    if not val:
        return None
    s = str(val).strip()
    if not s:
        return None

    ano_atual = datetime.now().year
    limite_2d = (ano_atual % 100) + 5  # se ano atual for 2026, limite é 31

    def expand_ano(a_str):
        if not a_str.isdigit():
            return None
        if len(a_str) == 2:
            a_int = int(a_str)
            return (2000 + a_int) if a_int <= limite_2d else (1900 + a_int)
        elif len(a_str) == 4:
            return int(a_str)
        return None

    # Tenta quebrar por delimitadores /, -, .
    for sep in ['/', '-', '.']:
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            if len(parts) == 3:
                p1, p2, p3 = parts[0], parts[1], parts[2]
                if not (p1.isdigit() and p2.isdigit() and p3.isdigit()):
                    return None
                if len(p1) == 4:  # Formato ISO: AAAA/MM/DD ou AAAA-MM-DD
                    ano = int(p1)
                    mes = int(p2)
                    dia = int(p3)
                else:  # Formato BR: DD/MM/AAAA ou DD/MM/AA
                    dia = int(p1)
                    mes = int(p2)
                    ano = expand_ano(p3)
                    if ano is None:
                        return None
                try:
                    dt = datetime(ano, mes, dia)
                    if 1900 <= dt.year <= (ano_atual + 5):
                        return dt.strftime('%Y-%m-%d')
                except (ValueError, TypeError):
                    return None
            break

    # Se forem apenas dígitos sem separador
    digits = ''.join(c for c in s if c.isdigit())
    if len(digits) == 8:
        # 1. Tenta DDMMAAAA
        try:
            dia, mes, ano = int(digits[:2]), int(digits[2:4]), int(digits[4:])
            dt = datetime(ano, mes, dia)
            if 1900 <= dt.year <= (ano_atual + 5):
                return dt.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            pass
        # 2. Tenta AAAAMMDD
        try:
            ano, mes, dia = int(digits[:4]), int(digits[4:6]), int(digits[6:])
            dt = datetime(ano, mes, dia)
            if 1900 <= dt.year <= (ano_atual + 5):
                return dt.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            pass
    elif len(digits) == 6:
        # DDMMAA
        dia, mes = int(digits[:2]), int(digits[2:4])
        ano = expand_ano(digits[4:])
        if ano:
            try:
                dt = datetime(ano, mes, dia)
                if 1900 <= dt.year <= (ano_atual + 5):
                    return dt.strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                pass

    return None



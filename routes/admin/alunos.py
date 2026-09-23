# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, session, flash, jsonify, Response
import csv
import io
import json
import re
import qrcode
import base64
from io import BytesIO
from database import closing, get_db_connection
from utils.auth import is_logged_in_admin, tem_permissao
from utils.helpers import datetime_now_str, date_hoje_str, sanitize_field, registrar_auditoria, formatar_nome_turma, obter_ou_criar_turma
from utils.filters import format_cpf
from utils.qrcode_gen import generate_std_badge_code
from . import admin_bp

ALUNOS_POR_PAGINA = 20

@admin_bp.route('/admin/alunos', methods=['GET', 'POST'])
def admin_alunos():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('alunos'): return redirect(url_for('admin.admin_dashboard'))
    
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        matricula = request.form.get('matricula', '').strip()
        cpf = request.form.get('cpf', '').strip()
        data_nascimento = request.form.get('data_nascimento', '').strip()
        email = request.form.get('email', '').strip() or None
        restricoes = request.form.get('restricoes', '').strip() or None
        
        turma_id_str = request.form.get('turma_id', '').strip()
        turma_id = int(turma_id_str) if turma_id_str.isdigit() else None
        curso = request.form.get('curso', '').strip() or None
        
        situacao_matricula = request.form.get('situacao_matricula', 'Matriculado').strip() or 'Matriculado'
        permitido_almoco = int(request.form.get('permitido_almoco', '1'))
        if situacao_matricula != 'Matriculado':
            permitido_almoco = 0  # Bloqueio automático de refeição para alunos desligados/formados

        serie_str = request.form.get('serie_ano_atual', '').strip()
        serie_ano_atual = int(serie_str) if serie_str.isdigit() else None

        ingresso_str = request.form.get('ano_ingresso', '').strip()
        ano_ingresso = int(ingresso_str) if ingresso_str.isdigit() else None
        
        try:
            with closing(get_db_connection()) as conn:
                # Auto-vincula/cria a turma correspondente a SerieAno + Curso
                from utils.helpers import extrair_serie_e_curso
                curso, serie_extraida = extrair_serie_e_curso(curso, serie_ano_atual)
                if serie_ano_atual is None and serie_extraida is not None:
                    serie_ano_atual = serie_extraida

                if curso or serie_ano_atual:
                    turma_id = obter_ou_criar_turma(conn, curso, serie_ano_atual, criar_se_nao_existir=True)

                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO alunos (
                        nome, matricula, cpf, data_nascimento, email, restricoes, 
                        turma_id, permitido_almoco, serie_ano_atual, ano_ingresso, situacao_matricula, curso
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    nome, matricula, cpf, data_nascimento, email, restricoes, 
                    turma_id, permitido_almoco, serie_ano_atual, ano_ingresso, situacao_matricula, curso
                ))
                novo_aluno_id = cur.lastrowid

                # Se possui turma, inicializa a trajetória em aluno_turma_historico
                if turma_id:
                    turma_row = conn.execute("SELECT ano_letivo, periodo_letivo, serie_ano FROM turmas WHERE id = ?", (turma_id,)).fetchone()
                    ano_letivo_t = turma_row['ano_letivo'] if turma_row else None
                    periodo_t = turma_row['periodo_letivo'] if turma_row and turma_row['periodo_letivo'] else 1
                    serie_t = serie_ano_atual or (turma_row['serie_ano'] if turma_row else None)
                    
                    data_hoje = date_hoje_str()
                    conn.execute("""
                        INSERT OR IGNORE INTO aluno_turma_historico (
                            aluno_id, turma_id, ano_letivo, periodo_letivo, serie_ano, situacao, data_inicio, observacao
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Cadastro inicial do estudante')
                    """, (
                        novo_aluno_id, turma_id, ano_letivo_t, periodo_t, serie_t,
                        'Cursando' if situacao_matricula == 'Matriculado' else situacao_matricula,
                        data_hoje
                    ))

                conn.commit()
                registrar_auditoria("Criar Aluno", f"Cadastrou aluno: {nome} (Matrícula: {matricula}, Curso: {curso or 'Não informado'}, Turma: {turma_id or 'Sem Turma'})")
                flash('Aluno cadastrado com sucesso!', 'success')
        except sqlite3.IntegrityError:
            flash('Erro ao cadastrar: CPF ou Matrícula já existente no sistema.', 'error')
        except Exception as e:
            flash(f'Erro ao cadastrar aluno: {str(e)}', 'error')
        return redirect(url_for('admin.admin_alunos'))

    busca = request.args.get('q', '').strip()
    filtro_turma = request.args.get('turma_id', '').strip()
    filtro_serie = request.args.get('serie_ano', '').strip()
    filtro_situacao = request.args.get('situacao_matricula', '').strip()
    
    pagina = request.args.get('page', 1, type=int)
    offset = (pagina - 1) * ALUNOS_POR_PAGINA

    with closing(get_db_connection()) as conn:
        turmas = conn.execute("""
            SELECT *, nome as nome_exibicao
            FROM turmas 
            WHERE (is_evento = 0 OR is_evento IS NULL) 
            ORDER BY COALESCE(ano_letivo, 0) DESC, nome ASC
        """).fetchall()

        cursos_raw = conn.execute("""
            SELECT DISTINCT curso FROM (
                SELECT curso FROM turmas WHERE curso IS NOT NULL AND TRIM(curso) != '' AND COALESCE(is_evento, 0) = 0
                UNION
                SELECT curso FROM alunos WHERE curso IS NOT NULL AND TRIM(curso) != ''
            ) ORDER BY 1 ASC
        """).fetchall()
        cursos_disponiveis = [r['curso'] for r in cursos_raw]
        
        base_query = "FROM alunos a LEFT JOIN turmas t ON a.turma_id = t.id"
        conditions = ["a.matricula NOT LIKE 'EVT-%'"]
        params = []
            
        if busca:
            like = f'%{busca}%'
            conditions.append("(a.nome LIKE ? OR a.matricula LIKE ? OR a.cpf LIKE ? OR a.curso LIKE ?)")
            params.extend([like, like, like, like])

        if filtro_turma == 'sem_turma':
            conditions.append("a.turma_id IS NULL")
        elif filtro_turma and filtro_turma.isdigit():
            conditions.append("a.turma_id = ?")
            params.append(int(filtro_turma))

        if filtro_serie and filtro_serie.isdigit():
            conditions.append("COALESCE(a.serie_ano_atual, t.serie_ano) = ?")
            params.append(int(filtro_serie))

        if filtro_situacao:
            conditions.append("a.situacao_matricula = ?")
            params.append(filtro_situacao)
            
        where_clause = " WHERE " + " AND ".join(conditions)
            
        total = conn.execute(f"SELECT COUNT(*) {base_query} {where_clause}", params).fetchone()[0]
        
        alunos = conn.execute(
            f"""SELECT a.*, 
                       COALESCE(a.curso, t.curso) as curso_efetivo,
                       t.nome as turma_nome, t.curso as turma_curso, 
                       t.ano_letivo as turma_ano, t.serie_ano as turma_serie
                {base_query} {where_clause} 
                ORDER BY a.nome ASC LIMIT ? OFFSET ?""",
            params + [ALUNOS_POR_PAGINA, offset]
        ).fetchall()

    total_paginas = max(1, (total + ALUNOS_POR_PAGINA - 1) // ALUNOS_POR_PAGINA)
    return render_template('admin/alunos.html',
        alunos=alunos, turmas=turmas, cursos_disponiveis=cursos_disponiveis,
        busca=busca, 
        filtro_turma=filtro_turma,
        filtro_serie=filtro_serie,
        filtro_situacao=filtro_situacao,
        pagina=pagina, 
        total_paginas=total_paginas, 
        total=total
    )

@admin_bp.route('/admin/alunos/editar/<int:id>', methods=['POST'])
def admin_alunos_editar(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('alunos'): return redirect(url_for('admin.admin_dashboard'))
    
    nome = request.form.get('nome', '').strip()
    matricula = request.form.get('matricula', '').strip()
    cpf = request.form.get('cpf', '').strip()
    data_nascimento = request.form.get('data_nascimento', '').strip()
    email = request.form.get('email', '').strip() or None
    restricoes = request.form.get('restricoes', '').strip() or None
    
    turma_id_str = request.form.get('turma_id', '').strip()
    turma_id = int(turma_id_str) if turma_id_str.isdigit() else None
    curso = request.form.get('curso', '').strip() or None
    
    situacao_matricula = request.form.get('situacao_matricula', 'Matriculado').strip() or 'Matriculado'
    permitido_almoco = int(request.form.get('permitido_almoco', '1'))
    if situacao_matricula != 'Matriculado':
        permitido_almoco = 0

    serie_str = request.form.get('serie_ano_atual', '').strip()
    serie_ano_atual = int(serie_str) if serie_str.isdigit() else None

    ingresso_str = request.form.get('ano_ingresso', '').strip()
    ano_ingresso = int(ingresso_str) if ingresso_str.isdigit() else None
    
    try:
        data_hoje = date_hoje_str()
        with closing(get_db_connection()) as conn:
            aluno_antigo = conn.execute("SELECT * FROM alunos WHERE id = ?", (id,)).fetchone()
            if not aluno_antigo:
                flash('Aluno não encontrado.', 'error')
                return redirect(url_for('admin.admin_alunos'))

            # Auto-vincula/atualiza turma correspondente a SerieAno + Curso
            from utils.helpers import extrair_serie_e_curso
            curso, serie_extraida = extrair_serie_e_curso(curso, serie_ano_atual)
            if serie_ano_atual is None and serie_extraida is not None:
                serie_ano_atual = serie_extraida

            if curso or serie_ano_atual:
                turma_id = obter_ou_criar_turma(conn, curso, serie_ano_atual, criar_se_nao_existir=True)

            # Atualiza tabela principal alunos
            conn.execute("""
                UPDATE alunos 
                SET nome = ?, matricula = ?, cpf = ?, data_nascimento = ?, email = ?, 
                    restricoes = ?, turma_id = ?, permitido_almoco = ?, 
                    serie_ano_atual = ?, ano_ingresso = ?, situacao_matricula = ?, curso = ?
                WHERE id = ?
            """, (
                nome, matricula, cpf, data_nascimento, email, restricoes, 
                turma_id, permitido_almoco, serie_ano_atual, ano_ingresso, situacao_matricula, curso, id
            ))

            # Trata mudanças de turma ou situação no histórico acadêmico
            turma_antiga_id = aluno_antigo['turma_id']
            situacao_antiga = aluno_antigo['situacao_matricula']

            if turma_id != turma_antiga_id:
                # Encerra o histórico da turma antiga
                if turma_antiga_id:
                    conn.execute("""
                        UPDATE aluno_turma_historico 
                        SET data_fim = ?, situacao = 'Transferido' 
                        WHERE aluno_id = ? AND turma_id = ? AND data_fim IS NULL
                    """, (data_hoje, id, turma_antiga_id))

                # Abre novo histórico na nova turma
                if turma_id:
                    t_nova = conn.execute("SELECT ano_letivo, periodo_letivo, serie_ano FROM turmas WHERE id = ?", (turma_id,)).fetchone()
                    ano_let = t_nova['ano_letivo'] if t_nova else None
                    per_let = t_nova['periodo_letivo'] if t_nova and t_nova['periodo_letivo'] else 1
                    ser_let = serie_ano_atual or (t_nova['serie_ano'] if t_nova else None)

                    conn.execute("""
                        INSERT INTO aluno_turma_historico (
                            aluno_id, turma_id, ano_letivo, periodo_letivo, serie_ano, situacao, data_inicio, observacao
                        ) VALUES (?, ?, ?, ?, ?, 'Cursando', ?, 'Transferência manual de turma')
                        ON CONFLICT(aluno_id, turma_id, ano_letivo, periodo_letivo)
                        DO UPDATE SET 
                            situacao = 'Cursando',
                            data_inicio = excluded.data_inicio,
                            data_fim = NULL,
                            serie_ano = excluded.serie_ano
                    """, (id, turma_id, ano_let, per_let, ser_let, data_hoje))

            elif situacao_matricula != situacao_antiga:
                # Atualiza a situação no histórico ativo
                if situacao_matricula != 'Matriculado':
                    conn.execute("""
                        UPDATE aluno_turma_historico 
                        SET situacao = ?, data_fim = ? 
                        WHERE aluno_id = ? AND data_fim IS NULL
                    """, (situacao_matricula, data_hoje, id))
                    
                    # Cancela reservas futuras
                    conn.execute("""
                        UPDATE reservas 
                        SET status = 'CANCELADA' 
                        WHERE aluno_id = ? AND status = 'ATIVA' 
                          AND cardapio_id IN (SELECT id FROM cardapios WHERE data >= ?)
                    """, (id, data_hoje))

            conn.commit()
            registrar_auditoria("Editar Aluno", f"Editou dados do aluno ID {id}: {nome} (Turma: {turma_id}, Situação: {situacao_matricula})")
            flash('Aluno atualizado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao atualizar aluno: {str(e)}', 'error')
        
    return redirect(url_for('admin.admin_alunos'))

@admin_bp.route('/admin/alunos/excluir/<int:id>', methods=['POST'])
def admin_alunos_excluir(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('alunos'): return redirect(url_for('admin.admin_dashboard'))
    try:
        with closing(get_db_connection()) as conn:
            aluno = conn.execute("SELECT nome, matricula FROM alunos WHERE id = ?", (id,)).fetchone()
            aluno_txt = f"{aluno['nome']} (Matrícula: {aluno['matricula']})" if aluno else f"ID {id}"
            
            conn.execute("DELETE FROM aluno_turma_historico WHERE aluno_id = ?", (id,))
            conn.execute("DELETE FROM reservas WHERE aluno_id = ?", (id,))
            conn.execute("DELETE FROM alunos WHERE id = ?", (id,))
            conn.commit()
            registrar_auditoria("Excluir Aluno", f"Excluiu o aluno: {aluno_txt}")
            flash('Aluno excluído com sucesso!', 'success')
    except Exception as e:
        flash('Erro ao excluir aluno.', 'error')
    return redirect(url_for('admin.admin_alunos'))

@admin_bp.route('/admin/alunos/historico/<int:id>')
def admin_alunos_historico(id):
    """Retorna a trajetória acadêmica completa do estudante no campus."""
    if not is_logged_in_admin(): return jsonify({"error": "Não autenticado"}), 401
    if not tem_permissao('alunos'): return jsonify({"error": "Acesso negado"}), 403

    with closing(get_db_connection()) as conn:
        aluno = conn.execute("""
            SELECT a.id, a.nome, a.matricula, a.cpf, a.serie_ano_atual, a.ano_ingresso, 
                   a.situacao_matricula, a.permitido_almoco, t.nome as turma_atual_nome
            FROM alunos a 
            LEFT JOIN turmas t ON a.turma_id = t.id 
            WHERE a.id = ?
        """, (id,)).fetchone()

        if not aluno:
            return jsonify({"error": "Aluno não encontrado"}), 404

        historico = conn.execute("""
            SELECT h.*, t.nome as turma_nome, t.curso as turma_curso, t.turno as turma_turno
            FROM aluno_turma_historico h
            LEFT JOIN turmas t ON h.turma_id = t.id
            WHERE h.aluno_id = ?
            ORDER BY COALESCE(h.ano_letivo, 0) DESC, COALESCE(h.periodo_letivo, 1) DESC, h.data_inicio DESC
        """, (id,)).fetchall()

    return jsonify({
        "aluno": dict(aluno),
        "historico": [dict(h) for h in historico]
    })

@admin_bp.route('/admin/alunos/imprimir')
def admin_alunos_imprimir():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('alunos'): return redirect(url_for('admin.admin_dashboard'))
    
    turma_id = request.args.get('turma_id')
    aluno_id = request.args.get('aluno_id')
    ids_selecionados = request.args.getlist('ids[]')
    
    with closing(get_db_connection()) as conn:
        query = """
            SELECT a.*, t.nome as turma_nome, t.curso as turma_curso, 
                   t.ano_letivo as turma_ano, COALESCE(a.serie_ano_atual, t.serie_ano) as serie_ano_efetiva,
                   COALESCE(a.curso, t.curso) as curso_efetivo
            FROM alunos a 
            LEFT JOIN turmas t ON a.turma_id = t.id 
            WHERE (t.is_evento = 0 OR t.id IS NULL)
        """
        params = []
        
        if ids_selecionados:
            placeholders = ','.join(['?'] * len(ids_selecionados))
            query += f" AND a.id IN ({placeholders})"
            params.extend([int(i) for i in ids_selecionados if i.isdigit()])
        elif aluno_id:
            query += " AND a.id = ?"
            params.append(aluno_id)
        elif turma_id:
            if turma_id == 'sem_turma':
                query += " AND a.turma_id IS NULL"
            else:
                query += " AND a.turma_id = ?"
                params.append(turma_id)
            
        alunos = conn.execute(query, params).fetchall()
        
        for a in alunos:
            if not a['codigo_cracha']:
                codigo = generate_std_badge_code(a['id'])
                conn.execute("UPDATE alunos SET codigo_cracha = ? WHERE id = ?", (codigo, a['id']))
        conn.commit()
        
        alunos_final = conn.execute(query, params).fetchall()

        crachas = []
        for a in alunos_final:
            qr = qrcode.QRCode(version=1, box_size=10, border=2)
            qr.add_data(a['codigo_cracha'])
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            qr_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            crachas.append({
                'nome': a['nome'],
                'matricula': a['matricula'],
                'curso_efetivo': a['curso_efetivo'],
                'turma': a['turma_nome'] or 'Geral/Sem Turma',
                'turma_curso': a['turma_curso'],
                'turma_ano': a['turma_ano'],
                'serie_ano': a['serie_ano_efetiva'],
                'qr_code': qr_base64,
                'codigo': a['codigo_cracha']
            })
            
    label = f"{len(crachas)} aluno(s) selecionado(s)" if ids_selecionados else "todos os alunos"
    registrar_auditoria("Imprimir Crachás Alunos", f"Gerou visualização de impressão de crachás de alunos ({label})")
    return render_template('admin/alunos_imprimir.html', crachas=crachas)

@admin_bp.route('/admin/alunos/csv_template')
def admin_alunos_csv_template():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    output = (
        "Nome;Matricula;CPF;DataNascimento;Curso;SerieAno;Turno;Situacao;AnoIngresso;Email;Restricoes;LiberadoAlmoco\n"
        "Exemplo da Silva;2026001;11122233344;20/05/2007;Curso Técnico em Agroecologia - Integrado/Integral- PTG;2;Matutino;Matriculado;2026;aluno@escola.edu.br;Vegano (opcional);S\n"
        "Maria de Souza;2026002;22233344455;15/03/2005;Curso Superior de Bacharelado em Engenharia Agronômica - PTG;10;Integral;Matriculado;2022;maria@escola.edu.br;;S"
    )
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=modelo_importacao_alunos.csv"}
    )
    
@admin_bp.route('/admin/alunos/importar', methods=['POST'])
def admin_alunos_importar():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('alunos'): return redirect(url_for('admin.admin_dashboard'))
    
    if 'arquivo_csv' not in request.files:
        flash('Nenhum arquivo enviado.', 'error')
        return redirect(url_for('admin.admin_alunos'))
        
    file = request.files['arquivo_csv']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('admin.admin_alunos'))

    criar_turmas_novas = request.form.get('criar_turmas_novas') == '1'
    bloquear_ausentes = request.form.get('bloquear_ausentes') == '1'
        
    try:
        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        csv_input = csv.reader(stream, delimiter=';')
        
        first_row = next(csv_input, None)
        delimiter_used = ';'
        if first_row and len(first_row) == 1 and ',' in first_row[0]:
            delimiter_used = ','
            
        stream.seek(0)
        csv_input = csv.reader(stream, delimiter=delimiter_used)
        
        header_row = next(csv_input, None)
        col_map = {}
        if header_row:
            from database.connection import remove_accents
            for col_idx, col_text in enumerate(header_row):
                norm = remove_accents(col_text or '').replace(' ', '').replace('_', '').replace('-', '').replace('/', '').lower().strip()
                if norm in ['nome', 'estudante', 'aluno']: col_map['nome'] = col_idx
                elif norm in ['matricula', 'matr', 'mat']: col_map['matricula'] = col_idx
                elif norm in ['cpf']: col_map['cpf'] = col_idx
                elif norm in ['datanascimento', 'nascimento', 'datanasc', 'dtnasc']: col_map['data_nascimento'] = col_idx
                elif norm in ['curso', 'descricaocurso', 'nomecurso']: col_map['curso'] = col_idx
                elif norm in ['serieano', 'serie', 'ano', 'semestre', 'periodo', 'serieanoatual']: col_map['serie_ano'] = col_idx
                elif norm in ['turma', 'nometurma']: col_map['turma'] = col_idx
                elif norm in ['turno']: col_map['turno'] = col_idx
                elif norm in ['situacao', 'situacaomatricula', 'status']: col_map['situacao'] = col_idx
                elif norm in ['anoingresso', 'ingresso']: col_map['ano_ingresso'] = col_idx
                elif norm in ['email', 'correioeletronico']: col_map['email'] = col_idx
                elif norm in ['restricoes', 'restricao', 'dieta', 'observacoes']: col_map['restricoes'] = col_idx
                elif norm in ['liberadoalmoco', 'permitidoalmoco', 'almoco', 'acessoalmoco']: col_map['permitido_almoco'] = col_idx
        
        adicionados = 0
        erros = 0
        mensagens_erro = []
        data_hoje = date_hoje_str()
        alunos_processados_ids = set()
        
        with closing(get_db_connection()) as conn:
            for idx, row in enumerate(csv_input, start=2):
                if len(row) < 4:
                    continue

                def get_f(key, fallback_idx=None, default=''):
                    if col_map and key in col_map:
                        col_i = col_map[key]
                        if col_i < len(row):
                            return sanitize_field(row[col_i])
                    if fallback_idx is not None and fallback_idx < len(row):
                        return sanitize_field(row[fallback_idx])
                    return default

                nome = get_f('nome', 0)
                matricula = get_f('matricula', 1)
                cpf = get_f('cpf', 2)
                data_nascimento = get_f('data_nascimento', 3)

                if not nome or not cpf:
                    continue
                
                # Trata data de nascimento
                if '/' in data_nascimento:
                    try:
                        parts = data_nascimento.split('/')
                        if len(parts) == 3 and len(parts[2]) == 4:
                            data_nascimento = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                    except:
                        pass

                # Resolução inteligente de Curso, Série e Turma
                curso_val = None
                serie_val = None
                turma_str = ''

                if col_map and 'curso' in col_map:
                    # Mapeado por cabeçalho
                    curso_val = get_f('curso') or None
                    serie_str = get_f('serie_ano')
                    serie_val = int(serie_str) if serie_str.isdigit() else None
                    turno_val = get_f('turno') or None
                    situacao_val = get_f('situacao') or 'Matriculado'
                    ingr_str = get_f('ano_ingresso')
                    ano_ingresso_val = int(ingr_str) if ingr_str.isdigit() else None
                    email_val = get_f('email') or None
                    restricoes_val = get_f('restricoes') or None
                    permitido_str = get_f('permitido_almoco', default='S') or 'S'
                elif len(row) == 12:
                    # Modelo padrão oficial (12 colunas sem Turma)
                    curso_val = sanitize_field(row[4]) or None
                    serie_str = sanitize_field(row[5])
                    serie_val = int(serie_str) if serie_str.isdigit() else None
                    turno_val = sanitize_field(row[6]) or None
                    situacao_val = sanitize_field(row[7]) or 'Matriculado'
                    ingr_str = sanitize_field(row[8])
                    ano_ingresso_val = int(ingr_str) if ingr_str.isdigit() else None
                    email_val = sanitize_field(row[9]) or None
                    restricoes_val = sanitize_field(row[10]) or None
                    permitido_str = sanitize_field(row[11]) or 'S'
                elif len(row) >= 13:
                    # Formato clássico SUAP de 13 colunas (Turma na col 4, Série na col 5, Curso na col 6)
                    serie_str = sanitize_field(row[5])
                    serie_val = int(serie_str) if serie_str.isdigit() else None
                    curso_val = sanitize_field(row[6]) or None
                    turno_val = sanitize_field(row[7]) or None
                    situacao_val = sanitize_field(row[8]) or 'Matriculado'
                    ingr_str = sanitize_field(row[9])
                    ano_ingresso_val = int(ingr_str) if ingr_str.isdigit() else None
                    email_val = sanitize_field(row[10]) or None
                    restricoes_val = sanitize_field(row[11]) or None
                    permitido_str = sanitize_field(row[12]) or 'S'
                else:
                    # Formato compacto (8 colunas)
                    curso_val = sanitize_field(row[4]) if len(row) > 4 else None
                    serie_val = None
                    email_val = sanitize_field(row[5]) if len(row) > 5 else None
                    restricoes_val = sanitize_field(row[6]) if len(row) > 6 else None
                    permitido_str = sanitize_field(row[7]) if len(row) > 7 else 'S'
                    turno_val = None
                    situacao_val = 'Matriculado'
                    ano_ingresso_val = None

                from utils.helpers import extrair_serie_e_curso
                curso_val, serie_extraida = extrair_serie_e_curso(curso_val, serie_val)
                if serie_val is None and serie_extraida is not None:
                    serie_val = serie_extraida

                # Identificação flexível de matrícula ativa no SUAP/SIGAA
                situacoes_ativas = {'matriculado', 'cursando', 'ativo', 'regular', 'em curso', 'em andamento'}
                sit_norm = situacao_val.lower().strip() if situacao_val else 'matriculado'
                is_matriculado_ativo = (sit_norm in situacoes_ativas)

                permitido_almoco = 0 if (permitido_str.strip().upper() == 'N' or not is_matriculado_ativo) else 1

                # ─── Resolução da Turma Automatizada por SerieAno + Curso ───
                nome_turma_alvo = formatar_nome_turma(curso_val, serie_val)
                
                turma_id = obter_ou_criar_turma(
                    conn, curso_val, serie_val, 
                    turno=turno_val, 
                    ano_letivo=ano_ingresso_val or int(data_hoje[:4]), 
                    criar_se_nao_existir=criar_turmas_novas
                )

                if not turma_id:
                    erros += 1
                    mensagens_erro.append(f"Linha {idx} ({nome}): Turma '{nome_turma_alvo}' não existe no sistema. Marque a opção 'Criar turmas inexistentes automaticamente' para criá-la.")
                    continue

                cpf_digitos = ''.join(filter(str.isdigit, str(cpf or '')))
                cpf_padrao = format_cpf(cpf_digitos) if len(cpf_digitos) == 11 else cpf

                try:
                    # 1. Procura primeiro pela matrícula (identificador acadêmico único)
                    row_matr = conn.execute("SELECT id, turma_id, serie_ano_atual, curso, codigo_cracha, matricula, cpf, situacao_matricula FROM alunos WHERE matricula = ?", (matricula,)).fetchone()

                    # 2. Procura pelo CPF (formatado ou apenas dígitos)
                    row_cpf = None
                    if cpf_digitos:
                        row_cpf = conn.execute("""
                            SELECT id, turma_id, serie_ano_atual, curso, codigo_cracha, matricula, cpf, situacao_matricula 
                            FROM alunos 
                            WHERE cpf = ? OR cpf = ? OR REPLACE(REPLACE(cpf, '.', ''), '-', '') = ?
                        """, (cpf, cpf_padrao, cpf_digitos)).fetchone()

                    if row_matr and row_cpf and row_matr['id'] != row_cpf['id']:
                        # Consolida duplicatas anteriores na linha com crachá/histórico ou row_matr
                        id_principal = row_matr['id']
                        id_duplicado = row_cpf['id']
                        if row_cpf['codigo_cracha'] and not row_matr['codigo_cracha']:
                            id_principal, id_duplicado = id_duplicado, id_principal

                        conn.execute("UPDATE OR IGNORE reservas SET aluno_id = ? WHERE aluno_id = ?", (id_principal, id_duplicado))
                        conn.execute("DELETE FROM reservas WHERE aluno_id = ?", (id_duplicado,))
                        conn.execute("UPDATE OR IGNORE aluno_turma_historico SET aluno_id = ? WHERE aluno_id = ?", (id_principal, id_duplicado))
                        conn.execute("DELETE FROM aluno_turma_historico WHERE aluno_id = ?", (id_duplicado,))
                        conn.execute("UPDATE OR IGNORE aluno_recorrencia_dias SET aluno_id = ? WHERE aluno_id = ?", (id_principal, id_duplicado))
                        conn.execute("DELETE FROM aluno_recorrencia_dias WHERE aluno_id = ?", (id_duplicado,))
                        conn.execute("DELETE FROM alunos WHERE id = ?", (id_duplicado,))

                        existente = conn.execute("SELECT id, turma_id, serie_ano_atual, curso, codigo_cracha, matricula, cpf, situacao_matricula FROM alunos WHERE id = ?", (id_principal,)).fetchone()
                    elif row_matr:
                        existente = row_matr
                    elif row_cpf:
                        existente = row_cpf
                    else:
                        existente = None

                    if existente:
                        aluno_id = existente['id']
                        turma_antiga_id = existente['turma_id']
                        serie_antiga = existente['serie_ano_atual']
                        curso_antigo = existente['curso']
                        situacao_antiga = existente['situacao_matricula']

                        mudou_turma = (turma_id != turma_antiga_id)
                        mudou_serie_ou_curso = (serie_val is not None and serie_val != serie_antiga) or (curso_val and curso_val != curso_antigo)

                        conn.execute("""
                            UPDATE alunos SET 
                                nome = ?, matricula = ?, cpf = ?, data_nascimento = ?, 
                                turma_id = ?, email = ?, restricoes = ?, 
                                permitido_almoco = ?, serie_ano_atual = COALESCE(?, serie_ano_atual),
                                ano_ingresso = COALESCE(?, ano_ingresso),
                                situacao_matricula = ?,
                                curso = COALESCE(?, curso)
                            WHERE id = ?
                        """, (
                            nome, matricula, cpf_padrao, data_nascimento, turma_id, email_val, restricoes_val, 
                            permitido_almoco, serie_val, ano_ingresso_val, situacao_val, curso_val, aluno_id
                        ))

                        # Se a situação veio como não-ativo (ou permitido_almoco == 0), bloqueia reservas futuras e desativa recorrência
                        if permitido_almoco == 0 or not is_matriculado_ativo:
                            conn.execute("""
                                UPDATE reservas 
                                SET status = 'CANCELADA',
                                    motivo_cancelamento = ?
                                WHERE aluno_id = ? AND status = 'ATIVA'
                                  AND cardapio_id IN (SELECT id FROM cardapios WHERE data >= ?)
                            """, (f"Situação acadêmica no CSV: {situacao_val}", aluno_id, data_hoje))
                            conn.execute("UPDATE aluno_recorrencia_dias SET ativo = 0 WHERE aluno_id = ?", (aluno_id,))


                        # Se o aluno mudou de serieAno ou Curso, migra para a nova turma e registra na trajetória acadêmica!
                        if mudou_turma or mudou_serie_ou_curso:
                            if turma_antiga_id:
                                conn.execute("""
                                    UPDATE aluno_turma_historico 
                                    SET data_fim = ?, situacao = 'Transferido' 
                                    WHERE aluno_id = ? AND turma_id = ? AND data_fim IS NULL
                                """, (data_hoje, aluno_id, turma_antiga_id))

                            t_row = conn.execute("SELECT ano_letivo, periodo_letivo, serie_ano, nome FROM turmas WHERE id = ?", (turma_id,)).fetchone()
                            ano_let = t_row['ano_letivo'] if t_row else None
                            per_let = t_row['periodo_letivo'] if t_row and t_row['periodo_letivo'] else 1
                            ser_let = serie_val or (t_row['serie_ano'] if t_row else None)
                            nome_t_destino = t_row['nome'] if t_row else nome_turma_alvo

                            conn.execute("""
                                INSERT INTO aluno_turma_historico (
                                    aluno_id, turma_id, ano_letivo, periodo_letivo, serie_ano, situacao, data_inicio, observacao
                                ) VALUES (?, ?, ?, ?, ?, 'Cursando', ?, ?)
                                ON CONFLICT(aluno_id, turma_id, ano_letivo, periodo_letivo) 
                                DO UPDATE SET 
                                    situacao = 'Cursando', 
                                    data_inicio = excluded.data_inicio, 
                                    data_fim = NULL, 
                                    serie_ano = excluded.serie_ano,
                                    observacao = excluded.observacao
                            """, (aluno_id, turma_id, ano_let, per_let, ser_let, data_hoje, f"Migrado automaticamente para {nome_t_destino} via importação CSV"))

                        elif situacao_val != 'Matriculado' and situacao_antiga != situacao_val:
                            conn.execute("""
                                UPDATE aluno_turma_historico 
                                SET situacao = ?, data_fim = ?
                                WHERE aluno_id = ? AND data_fim IS NULL
                            """, (situacao_val, data_hoje, aluno_id))

                        adicionados += 1
                        alunos_processados_ids.add(aluno_id)
                    else:
                        cur_a = conn.cursor()
                        cur_a.execute("""
                            INSERT INTO alunos (
                                nome, matricula, cpf, data_nascimento, email, restricoes, 
                                turma_id, permitido_almoco, serie_ano_atual, ano_ingresso, situacao_matricula, curso
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            nome, matricula, cpf_padrao, data_nascimento, email_val, restricoes_val, 
                            turma_id, permitido_almoco, serie_val, ano_ingresso_val, situacao_val, curso_val
                        ))
                        aluno_id = cur_a.lastrowid
                        alunos_processados_ids.add(aluno_id)

                        if turma_id:
                            t_row = conn.execute("SELECT ano_letivo, periodo_letivo, serie_ano FROM turmas WHERE id = ?", (turma_id,)).fetchone()
                            ano_let = t_row['ano_letivo'] if t_row else None
                            per_let = t_row['periodo_letivo'] if t_row and t_row['periodo_letivo'] else 1
                            ser_let = serie_val or (t_row['serie_ano'] if t_row else None)

                            conn.execute("""
                                INSERT OR IGNORE INTO aluno_turma_historico (
                                    aluno_id, turma_id, ano_letivo, periodo_letivo, serie_ano, situacao, data_inicio, observacao
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Criação via importação CSV')
                            """, (aluno_id, turma_id, ano_let, per_let, ser_let, 'Cursando' if situacao_val == 'Matriculado' else situacao_val, data_hoje))

                        adicionados += 1
                except Exception as e:
                    erros += 1
                    mensagens_erro.append(f"Linha {idx} ({nome}): {str(e)}")

            # ─── Bloqueio de Estudantes Regulares Ausentes na Planilha ───
            # "quem não estiver na listagem de alunos de importação via csv pode bloquear a reserva pois não está mais matriculado"
            total_bloqueados_ausentes = 0
            if bloquear_ausentes and alunos_processados_ids:
                placeholders = ','.join(['?'] * len(alunos_processados_ids))
                query_ausentes = f"""
                    SELECT id, nome, matricula, situacao_matricula, permitido_almoco 
                    FROM alunos 
                    WHERE id NOT IN ({placeholders})
                      AND matricula NOT LIKE 'EVT-%'
                      AND (turma_id NOT IN (SELECT id FROM turmas WHERE is_evento = 1) OR turma_id IS NULL)
                """
                alunos_ausentes = conn.execute(query_ausentes, list(alunos_processados_ids)).fetchall()
                if alunos_ausentes:
                    ids_ausentes = [a['id'] for a in alunos_ausentes]
                    ph_aus = ','.join(['?'] * len(ids_ausentes))

                    # Bloqueia reservas e atualiza situação
                    conn.execute(f"""
                        UPDATE alunos 
                        SET permitido_almoco = 0,
                            situacao_matricula = CASE WHEN situacao_matricula = 'Matriculado' THEN 'Não Matriculado' ELSE situacao_matricula END
                        WHERE id IN ({ph_aus})
                    """, ids_ausentes)

                    # Desativa recorrências semanais ativas
                    conn.execute(f"""
                        UPDATE aluno_recorrencia_dias 
                        SET ativo = 0 
                        WHERE aluno_id IN ({ph_aus}) AND ativo = 1
                    """, ids_ausentes)

                    # Cancela reservas futuras pendentes
                    conn.execute(f"""
                        UPDATE reservas 
                        SET status = 'CANCELADA',
                            motivo_cancelamento = 'Não consta na listagem de matrícula ativa (importação CSV)'
                        WHERE aluno_id IN ({ph_aus}) AND status = 'ATIVA'
                          AND cardapio_id IN (SELECT id FROM cardapios WHERE data >= ?)
                    """, ids_ausentes + [data_hoje])

                    # Encerra histórico na turma anterior
                    conn.execute(f"""
                        UPDATE aluno_turma_historico 
                        SET data_fim = ?,
                            situacao = 'Não Matriculado',
                            observacao = 'Encerrado: ausente da listagem de matrícula ativa'
                        WHERE aluno_id IN ({ph_aus}) AND data_fim IS NULL
                    """, [data_hoje] + ids_ausentes)

                    total_bloqueados_ausentes = len([a for a in alunos_ausentes if a['permitido_almoco'] == 1 or a['situacao_matricula'] == 'Matriculado'])

            conn.commit()
            registrar_auditoria("Importar Alunos CSV", f"Processou planilha: {adicionados} atualizados/criados, {total_bloqueados_ausentes} ausentes bloqueados, {erros} erros.")
            
        resumo_msgs = [f"{adicionados} aluno(s) processado(s)"]
        if total_bloqueados_ausentes > 0:
            resumo_msgs.append(f"{total_bloqueados_ausentes} aluno(s) ausente(s) da planilha tiveram o acesso a reservas bloqueado (não matriculados)")

        if erros > 0 and len(mensagens_erro) <= 5:
            flash(f"Importação: {', '.join(resumo_msgs)}. Avisos: " + " | ".join(mensagens_erro), 'warning')
        elif erros > 0:
            flash(f"Importação: {', '.join(resumo_msgs)}. {erros} linha(s) rejeitada(s) por erros de validação ou turmas inexistentes.", 'warning')
        else:
            flash(f"Importação concluída com sucesso! {', '.join(resumo_msgs)}.", 'success')
        
    except Exception as e:
        flash(f'Erro inesperado lendo arquivo CSV: {str(e)}', 'error')
        
    return redirect(url_for('admin.admin_alunos'))

@admin_bp.route('/admin/alunos/reset_senha/<int:id>', methods=['POST'])
def admin_alunos_resetar_senha(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('alunos'): return redirect(url_for('admin.admin_dashboard'))
    
    with closing(get_db_connection()) as conn:
        aluno = conn.execute("SELECT nome, matricula FROM alunos WHERE id = ?", (id,)).fetchone()
        aluno_txt = f"{aluno['nome']} (Matrícula: {aluno['matricula']})" if aluno else f"ID {id}"
        
        conn.execute("UPDATE alunos SET senha_hash = NULL WHERE id = ?", (id,))
        conn.commit()
        registrar_auditoria("Resetar Senha Aluno", f"Resetou a senha do aluno: {aluno_txt}")
        flash('Senha do aluno resetada! O próximo acesso voltará a ser feito pela Data de Nascimento provisoriamente.', 'success')
    return redirect(url_for('admin.admin_alunos'))

@admin_bp.route('/admin/alunos/suap_sync', methods=['POST'])
def admin_alunos_suap_sync():
    """
    Sincronização com o modelo SUAP:
    Mapeia serie_ano, situacao e ano_ingresso e alimenta o histórico acadêmico.
    """
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('alunos'): return redirect(url_for('admin.admin_dashboard'))
    
    api_url = request.form.get('api_url')
    token = request.form.get('token')
    turma_id = request.form.get('turma_id')
    
    mock_json = '''
    [
        {"nome": "Maria Emília (Teste SUAP)", "matricula": "202611SUAP", "cpf": "234.345.567-89", "data_nascimento": "2005-08-20", "serie_ano": 2, "ano_ingresso": 2025, "situacao": "Matriculado"},
        {"nome": "Felipe Souza (Teste SUAP)", "matricula": "202612SUAP", "cpf": "098.876.654-32", "data_nascimento": "2006-12-15", "serie_ano": 1, "ano_ingresso": 2026, "situacao": "Matriculado"}
    ]
    '''
    try:
        alunos_suap = json.loads(mock_json)
        adicionados = 0
        data_hoje = date_hoje_str()

        with closing(get_db_connection()) as conn:
            turma_row = conn.execute("SELECT ano_letivo, periodo_letivo, serie_ano FROM turmas WHERE id = ?", (turma_id,)).fetchone()
            ano_let = turma_row['ano_letivo'] if turma_row else None
            per_let = turma_row['periodo_letivo'] if turma_row and turma_row['periodo_letivo'] else 1

            for asuap in alunos_suap:
                existe = conn.execute("SELECT id FROM alunos WHERE matricula = ? OR cpf = ?", (asuap['matricula'], asuap['cpf'])).fetchone()
                if not existe:
                    cur_a = conn.cursor()
                    cur_a.execute("""
                        INSERT INTO alunos (
                            nome, matricula, cpf, data_nascimento, restricoes, 
                            turma_id, serie_ano_atual, ano_ingresso, situacao_matricula, permitido_almoco
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """, (
                        asuap['nome'], asuap['matricula'], asuap['cpf'], asuap['data_nascimento'], '', 
                        turma_id, asuap.get('serie_ano'), asuap.get('ano_ingresso'), asuap.get('situacao', 'Matriculado')
                    ))
                    aluno_id = cur_a.lastrowid

                    conn.execute("""
                        INSERT OR IGNORE INTO aluno_turma_historico (
                            aluno_id, turma_id, ano_letivo, periodo_letivo, serie_ano, situacao, data_inicio, observacao
                        ) VALUES (?, ?, ?, ?, ?, 'Cursando', ?, 'Sincronização via SUAP API')
                    """, (aluno_id, turma_id, ano_let, per_let, asuap.get('serie_ano'), data_hoje))
                    
                    adicionados += 1
            conn.commit()
            registrar_auditoria("Sincronizar SUAP", f"Sincronizou/adicionou {adicionados} alunos com metadados SUAP")
            
        flash(f'Simulação SUAP Executada! {adicionados} aluno(s) injetado(s) com metadados de série e histórico acadêmico.', 'success')
    except Exception as e:
        flash(f'Erro na Simulação SUAP: {str(e)}', 'error')
        
    return redirect(url_for('admin.admin_alunos'))

@admin_bp.route('/admin/api/alunos/buscar')
def admin_api_buscar_alunos():
    if not is_logged_in_admin(): return {"error": "Unauthorized"}, 401
    q = request.args.get('q', '').strip()
    if len(q) < 2: return {"alunos": []}
    
    from database.connection import remove_accents
    q_clean = re.sub(r'\D', '', q)
    like_norm = f"%{remove_accents(q)}%"
    
    with closing(get_db_connection()) as conn:
        query = "SELECT id, nome, matricula, cpf FROM alunos WHERE (remove_accents(nome) LIKE ? OR remove_accents(matricula) LIKE ? OR remove_accents(cpf) LIKE ?)"
        params = [like_norm, like_norm, like_norm]
        
        if q_clean:
            query += " OR remove_accents(cpf) LIKE ?"
            params.append(f'%{remove_accents(q_clean)}%')
            
        query += " LIMIT 10"
        alunos = conn.execute(query, params).fetchall()
        
    return {"alunos": [dict(a) for a in alunos]}

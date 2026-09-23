# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from database import closing, get_db_connection
from utils.auth import is_logged_in_admin, tem_permissao
from utils.helpers import (
    registrar_auditoria, date_hoje_str, datetime_now_str, formatar_nome_turma,
    parse_dias_bloqueados, formatar_dias_bloqueados, DIAS_SEMANA_NOMES, DIAS_SEMANA_ABREV
)
from datetime import datetime
from . import admin_bp

TURMAS_POR_PAGINA = 20

@admin_bp.route('/admin/turmas', methods=['GET', 'POST'])
def admin_turmas():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('turmas'): return redirect(url_for('admin.admin_dashboard'))
    
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        curso = request.form.get('curso', '').strip() or None
        
        ano_letivo_str = request.form.get('ano_letivo', '').strip()
        ano_letivo = int(ano_letivo_str) if ano_letivo_str.isdigit() else None
        
        periodo_letivo_str = request.form.get('periodo_letivo', '').strip()
        periodo_letivo = int(periodo_letivo_str) if periodo_letivo_str.isdigit() else 1
        
        serie_ano_str = request.form.get('serie_ano', '').strip()
        serie_ano = int(serie_ano_str) if serie_ano_str.isdigit() else None
        
        turno = request.form.get('turno', '').strip() or None
        modalidade = request.form.get('modalidade', '').strip() or None
        ativa = 1 if request.form.get('ativa', '1') == '1' else 0

        dias_bloqueados_lista = request.form.getlist('dias_bloqueados')
        dias_bloqueados = ','.join(sorted([d for d in dias_bloqueados_lista if d.isdigit()]))

        if curso or serie_ano:
            nome = formatar_nome_turma(curso or nome, serie_ano)

        if nome:
            with closing(get_db_connection()) as conn:
                conn.execute("""
                    INSERT INTO turmas (
                        nome, curso, ano_letivo, periodo_letivo, 
                        serie_ano, turno, modalidade, ativa, dias_bloqueados
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (nome, curso, ano_letivo, periodo_letivo, serie_ano, turno, modalidade, ativa, dias_bloqueados))
                conn.commit()
                detalhes = f"Criou a turma: {nome} (Curso: {curso or '---'}, Ano: {ano_letivo or '---'}, Série: {serie_ano or '---'})"
                if dias_bloqueados:
                    detalhes += f" [Dias Bloqueados: {formatar_dias_bloqueados(dias_bloqueados)}]"
                registrar_auditoria("Criar Turma", detalhes)
                flash('Turma cadastrada com sucesso!', 'success')
        return redirect(url_for('admin.admin_turmas'))

    busca = request.args.get('q', '').strip()
    filtro_ano = request.args.get('ano_letivo', '').strip()
    filtro_curso = request.args.get('curso', '').strip()
    filtro_ativa = request.args.get('ativa', '1').strip()
    
    pagina = request.args.get('page', 1, type=int)
    offset = (pagina - 1) * TURMAS_POR_PAGINA

    with closing(get_db_connection()) as conn:
        anos_existentes = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT ano_letivo FROM turmas WHERE ano_letivo IS NOT NULL ORDER BY ano_letivo DESC"
            ).fetchall()
        ]
        cursos_existentes = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT curso FROM turmas WHERE curso IS NOT NULL AND curso != '' ORDER BY curso ASC"
            ).fetchall()
        ]

        conditions = ["(is_evento = 0 OR is_evento IS NULL)"]
        params = []

        if busca:
            like = f'%{busca}%'
            conditions.append("(nome LIKE ? OR curso LIKE ?)")
            params.extend([like, like])

        if filtro_ano and filtro_ano.isdigit():
            conditions.append("ano_letivo = ?")
            params.append(int(filtro_ano))

        if filtro_curso:
            conditions.append("curso = ?")
            params.append(filtro_curso)

        if filtro_ativa in ('0', '1'):
            conditions.append("COALESCE(ativa, 1) = ?")
            params.append(int(filtro_ativa))

        where_clause = " WHERE " + " AND ".join(conditions)

        total = conn.execute(f"SELECT COUNT(*) FROM turmas {where_clause}", params).fetchone()[0]
        
        turmas = conn.execute(f"""
            SELECT t.*,
                   (SELECT COUNT(*) FROM alunos a WHERE a.turma_id = t.id) AS total_alunos,
                   (SELECT COUNT(*) FROM alunos a WHERE a.turma_id = t.id AND a.situacao_matricula = 'Matriculado') AS total_matriculados
            FROM turmas t
            {where_clause}
            ORDER BY COALESCE(t.ano_letivo, 0) DESC, t.nome ASC
            LIMIT ? OFFSET ?
        """, params + [TURMAS_POR_PAGINA, offset]).fetchall()

        # Lista de turmas ativas para o assistente de virada de ano
        turmas_ativas_todas = conn.execute("""
            SELECT id, nome, curso, ano_letivo, serie_ano, turno 
            FROM turmas 
            WHERE COALESCE(ativa, 1) = 1 AND (is_evento = 0 OR is_evento IS NULL)
            ORDER BY COALESCE(ano_letivo, 0) DESC, nome ASC
        """).fetchall()

    total_paginas = max(1, (total + TURMAS_POR_PAGINA - 1) // TURMAS_POR_PAGINA)
    return render_template('admin/turmas.html', 
        turmas=turmas, 
        turmas_ativas_todas=turmas_ativas_todas,
        anos_existentes=anos_existentes,
        cursos_existentes=cursos_existentes,
        busca=busca,
        filtro_ano=filtro_ano,
        filtro_curso=filtro_curso,
        filtro_ativa=filtro_ativa,
        pagina=pagina, 
        total_paginas=total_paginas, 
        total=total,
        formatar_dias_bloqueados=formatar_dias_bloqueados,
        parse_dias_bloqueados=parse_dias_bloqueados
    )

@admin_bp.route('/admin/turmas/editar/<int:id>', methods=['POST'])
def admin_turmas_editar(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('turmas'): return redirect(url_for('admin.admin_dashboard'))

    nome = request.form.get('nome', '').strip()
    if not nome:
        flash('O nome da turma não pode ser vazio.', 'error')
        return redirect(url_for('admin.admin_turmas'))

    curso = request.form.get('curso', '').strip() or None

    ano_letivo_str = request.form.get('ano_letivo', '').strip()
    ano_letivo = int(ano_letivo_str) if ano_letivo_str.isdigit() else None

    periodo_letivo_str = request.form.get('periodo_letivo', '').strip()
    periodo_letivo = int(periodo_letivo_str) if periodo_letivo_str.isdigit() else 1

    serie_ano_str = request.form.get('serie_ano', '').strip()
    serie_ano = int(serie_ano_str) if serie_ano_str.isdigit() else None

    turno = request.form.get('turno', '').strip() or None
    modalidade = request.form.get('modalidade', '').strip() or None
    ativa = 1 if request.form.get('ativa', '1') == '1' else 0

    dias_bloqueados_lista = request.form.getlist('dias_bloqueados')
    dias_bloqueados = ','.join(sorted([d for d in dias_bloqueados_lista if d.isdigit()]))

    with closing(get_db_connection()) as conn:
        turma = conn.execute("SELECT id, nome, dias_bloqueados FROM turmas WHERE id = ?", (id,)).fetchone()
        if not turma:
            flash('Turma não encontrada.', 'error')
            return redirect(url_for('admin.admin_turmas'))
        
        if curso or serie_ano:
            nome = formatar_nome_turma(curso or nome, serie_ano)
        
        conn.execute("""
            UPDATE turmas 
            SET nome = ?, curso = ?, ano_letivo = ?, periodo_letivo = ?,
                serie_ano = ?, turno = ?, modalidade = ?, ativa = ?, dias_bloqueados = ?
            WHERE id = ?
        """, (nome, curso, ano_letivo, periodo_letivo, serie_ano, turno, modalidade, ativa, dias_bloqueados, id))

        total_canceladas = 0
        dias_bloq_set = parse_dias_bloqueados(dias_bloqueados)
        if dias_bloq_set:
            hoje_str = date_hoje_str()
            agora_str = datetime_now_str()
            reservas_futuras = conn.execute("""
                SELECT r.id, r.aluno_id, c.data
                FROM reservas r
                JOIN alunos a ON r.aluno_id = a.id
                JOIN cardapios c ON r.cardapio_id = c.id
                WHERE a.turma_id = ? AND r.status = 'ATIVA' AND c.data >= ?
            """, (id, hoje_str)).fetchall()

            for rf in reservas_futuras:
                rf_w = datetime.strptime(rf['data'], '%Y-%m-%d').weekday()
                if rf_w in dias_bloq_set:
                    nome_dia = DIAS_SEMANA_NOMES[rf_w]
                    conn.execute("""
                        UPDATE reservas
                        SET status = 'CANCELADA',
                            motivo_cancelamento = ?,
                            cancelado_por = ?,
                            data_cancelamento = ?
                        WHERE id = ?
                    """, (f"Turma com reserva de almoço bloqueada neste dia da semana ({nome_dia})",
                          f"ADMIN: {session.get('admin_usuario', 'admin')}",
                          agora_str, rf['id']))
                    total_canceladas += 1

            # Desativa dias de recorrência bloqueados para alunos da turma
            placeholders = ','.join(['?'] * len(dias_bloq_set))
            conn.execute(f"""
                UPDATE aluno_recorrencia_dias
                SET ativo = 0, atualizado_em = ?
                WHERE dia_semana IN ({placeholders})
                  AND aluno_id IN (SELECT id FROM alunos WHERE turma_id = ?)
            """, [agora_str] + sorted(list(dias_bloq_set)) + [id])

        conn.commit()

        detalhes_dias = formatar_dias_bloqueados(dias_bloqueados)
        msg_auditoria = f"Atualizou turma ID {id} ({nome}). Dias bloqueados: {detalhes_dias or 'Nenhum'}."
        if total_canceladas > 0:
            msg_auditoria += f" Canceladas {total_canceladas} reserva(s) futura(s) coincidentes."
        registrar_auditoria("Editar Turma", msg_auditoria)
        
        flash_msg = 'Turma atualizada com sucesso!'
        if total_canceladas > 0:
            flash_msg += f' ({total_canceladas} reserva(s) futura(s) em dias bloqueados foram canceladas automaticamente).'
        flash(flash_msg, 'success')

    return redirect(url_for('admin.admin_turmas'))

@admin_bp.route('/admin/turmas/excluir/<int:id>', methods=['POST'])
def admin_turmas_excluir(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('turmas'): return redirect(url_for('admin.admin_dashboard'))

    with closing(get_db_connection()) as conn:
        alunos_vinculados = conn.execute(
            "SELECT COUNT(*) FROM alunos WHERE turma_id = ?", (id,)
        ).fetchone()[0]

        if alunos_vinculados > 0:
            flash(f'Não é possível excluir: há {alunos_vinculados} aluno(s) vinculado(s) a esta turma. Transfira ou desvincule os alunos primeiro.', 'error')
            return redirect(url_for('admin.admin_turmas'))

        turma = conn.execute("SELECT nome FROM turmas WHERE id = ?", (id,)).fetchone()
        turma_nome = turma['nome'] if turma else f"ID {id}"
        
        conn.execute("DELETE FROM turmas WHERE id = ?", (id,))
        conn.commit()
        registrar_auditoria("Excluir Turma", f"Excluiu a turma: {turma_nome}")
        flash('Turma excluída com sucesso.', 'success')

    return redirect(url_for('admin.admin_turmas'))

@admin_bp.route('/admin/turmas/virada_ano/dados')
def admin_turmas_virada_ano_dados():
    """Retorna alunos da turma de origem e turmas disponíveis para o assistente de virada de ano."""
    if not is_logged_in_admin(): return jsonify({"error": "Não autenticado"}), 401
    if not tem_permissao('turmas'): return jsonify({"error": "Acesso negado"}), 403

    turma_origem_id = request.args.get('turma_origem_id', type=int)
    if not turma_origem_id:
        return jsonify({"error": "Turma de origem não informada"}), 400

    with closing(get_db_connection()) as conn:
        turma_origem = conn.execute(
            "SELECT id, nome, curso, ano_letivo, periodo_letivo, serie_ano, turno FROM turmas WHERE id = ?",
            (turma_origem_id,)
        ).fetchone()

        if not turma_origem:
            return jsonify({"error": "Turma de origem não encontrada"}), 404

        alunos = conn.execute("""
            SELECT id, nome, matricula, cpf, serie_ano_atual, situacao_matricula, permitido_almoco
            FROM alunos 
            WHERE turma_id = ?
            ORDER BY nome ASC
        """, (turma_origem_id,)).fetchall()

        turmas_destino = conn.execute("""
            SELECT id, nome, curso, ano_letivo, periodo_letivo, serie_ano, turno,
                   CASE 
                       WHEN curso IS NOT NULL AND TRIM(curso) != '' THEN 
                           curso || CASE WHEN serie_ano IS NOT NULL THEN ' - ' || serie_ano || 'º Ano' ELSE '' END || ' (' || nome || ')'
                       ELSE nome 
                   END as nome_exibicao
            FROM turmas 
            WHERE COALESCE(ativa, 1) = 1 AND (is_evento = 0 OR is_evento IS NULL)
            ORDER BY COALESCE(ano_letivo, 0) DESC, curso ASC, nome ASC
        """).fetchall()

    return jsonify({
        "turma_origem": dict(turma_origem),
        "alunos": [dict(a) for a in alunos],
        "turmas_destino": [dict(t) for t in turmas_destino]
    })

@admin_bp.route('/admin/turmas/virada_ano', methods=['POST'])
def admin_turmas_virada_ano():
    """Executa a virada de ano / conselho de classe de forma atômica e segura."""
    if not is_logged_in_admin(): return jsonify({"error": "Não autenticado"}), 401
    if not tem_permissao('turmas'): return jsonify({"error": "Acesso negado"}), 403

    dados = request.get_json(silent=True) or request.form
    turma_origem_id = dados.get('turma_origem_id')
    movimentacoes = dados.get('movimentacoes')

    if not turma_origem_id or not movimentacoes:
        return jsonify({"error": "Dados incompletos para a virada de ano."}), 400

    data_hoje = date_hoje_str()
    admin_usuario = session.get('admin_user', 'desconhecido')

    contadores = {
        'PROMOVIDO': 0,
        'RETIDO': 0,
        'TRANSFERIDO': 0,
        'EVADIDO': 0,
        'FORMADO': 0
    }

    with closing(get_db_connection()) as conn:
        turma_origem = conn.execute(
            "SELECT id, nome, ano_letivo, serie_ano FROM turmas WHERE id = ?", 
            (turma_origem_id,)
        ).fetchone()

        if not turma_origem:
            return jsonify({"error": "Turma de origem inválida."}), 400

        # Processamento em lote atômico
        with conn:
            for item in movimentacoes:
                aluno_id = item.get('aluno_id')
                resultado = item.get('resultado', '').upper().strip()
                turma_destino_id = item.get('turma_destino_id')

                if resultado not in contadores:
                    continue

                contadores[resultado] += 1

                # 1. Encerra o histórico ativo do aluno na turma de origem
                conn.execute("""
                    UPDATE aluno_turma_historico 
                    SET data_fim = ?, situacao = ? 
                    WHERE aluno_id = ? AND turma_id = ? AND data_fim IS NULL
                """, (data_hoje, resultado.capitalize(), aluno_id, turma_origem_id))

                # 2. Aplica as regras específicas por resultado
                if resultado in ('PROMOVIDO', 'RETIDO'):
                    if not turma_destino_id:
                        raise ValueError(f"Turma de destino obrigatória para aluno ID {aluno_id} com resultado {resultado}")

                    turma_destino = conn.execute(
                        "SELECT id, nome, ano_letivo, periodo_letivo, serie_ano FROM turmas WHERE id = ?",
                        (turma_destino_id,)
                    ).fetchone()

                    if not turma_destino:
                        raise ValueError(f"Turma destino ID {turma_destino_id} não encontrada.")

                    # A Turma de Destino é a Fonte da Verdade da série do estudante!
                    nova_serie = turma_destino['serie_ano']
                    ano_letivo_dest = turma_destino['ano_letivo']
                    periodo_letivo_dest = turma_destino['periodo_letivo'] or 1

                    conn.execute("""
                        UPDATE alunos 
                        SET turma_id = ?, 
                            serie_ano_atual = ?, 
                            situacao_matricula = 'Matriculado'
                        WHERE id = ?
                    """, (turma_destino_id, nova_serie, aluno_id))

                    # Insere ou atualiza o novo registro em aluno_turma_historico respeitando a constraint UNIQUE
                    conn.execute("""
                        INSERT INTO aluno_turma_historico (
                            aluno_id, turma_id, ano_letivo, periodo_letivo, 
                            serie_ano, situacao, data_inicio, observacao
                        ) VALUES (?, ?, ?, ?, ?, 'Cursando', ?, ?)
                        ON CONFLICT(aluno_id, turma_id, ano_letivo, periodo_letivo) 
                        DO UPDATE SET 
                            situacao = 'Cursando', 
                            data_inicio = excluded.data_inicio, 
                            data_fim = NULL,
                            serie_ano = excluded.serie_ano
                    """, (
                        aluno_id, turma_destino_id, ano_letivo_dest, periodo_letivo_dest,
                        nova_serie, data_hoje, f"Virada de Turma a partir de {turma_origem['nome']}"
                    ))

                elif resultado in ('TRANSFERIDO', 'EVADIDO', 'FORMADO'):
                    nova_situacao = resultado.capitalize()

                    # Mantém a turma de origem como referência de saída, mas bloqueia o acesso ao almoço
                    conn.execute("""
                        UPDATE alunos 
                        SET situacao_matricula = ?, 
                            permitido_almoco = 0 
                        WHERE id = ?
                    """, (nova_situacao, aluno_id))

                    # Cancela eventuais reservas futuras já agendadas
                    conn.execute("""
                        UPDATE reservas 
                        SET status = 'CANCELADA' 
                        WHERE aluno_id = ? AND status = 'ATIVA' 
                          AND cardapio_id IN (SELECT id FROM cardapios WHERE data >= ?)
                    """, (aluno_id, data_hoje))

            # Resumo da operação
            turma_origem_nome = turma_origem['nome']
            resumo_texto = (
                f"Virada de Turma executada por '{admin_usuario}' na turma '{turma_origem_nome}'. "
                f"Resultados: {contadores['PROMOVIDO']} Promovido(s), {contadores['RETIDO']} Retido(s), "
                f"{contadores['TRANSFERIDO']} Transferido(s), {contadores['EVADIDO']} Evadido(s), "
                f"{contadores['FORMADO']} Formado(s)."
            )

    registrar_auditoria("Virada de Ano Letivo", resumo_texto)

    return jsonify({
        "success": True, 
        "mensagem": "Virada de Ano / Conselho de Turma processada com sucesso!",
        "resumo": contadores
    })

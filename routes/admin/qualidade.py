# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
from database import closing, get_db_connection, get_config
from utils.auth import is_logged_in_admin, tem_permissao
from utils.helpers import registrar_auditoria, datetime_now_str, date_hoje_str
from . import admin_bp

QUALIDADE_POR_PAGINA = 15

def tem_acesso_qualidade():
    return tem_permissao('qualidade')

@admin_bp.route('/admin/qualidade', methods=['GET'])
def admin_qualidade():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_acesso_qualidade(): return redirect(url_for('admin.admin_dashboard'))

    busca = request.args.get('q', '').strip()
    data_inicio = request.args.get('data_inicio', '').strip()
    data_fim = request.args.get('data_fim', '').strip()
    conformidade_filtro = request.args.get('conformidade', '').strip()
    cardapio_filtro = request.args.get('cardapio_id', '').strip()
    pagina = request.args.get('page', 1, type=int)
    offset = (pagina - 1) * QUALIDADE_POR_PAGINA

    query_where = []
    params = []

    if busca:
        query_where.append("(cq.campus LIKE ? OR cq.fornecedor LIKE ? OR cq.criado_por LIKE ? OR EXISTS (SELECT 1 FROM controle_qualidade_itens cqi WHERE cqi.controle_id = cq.id AND (cqi.tipo_preparo LIKE ? OR cqi.tipo_preparo_outro LIKE ? OR cqi.observacoes LIKE ? OR cqi.profissional_medicao LIKE ?)))")
        term = f"%{busca}%"
        params.extend([term, term, term, term, term, term, term])

    if data_inicio:
        query_where.append("cq.data_recebimento >= ?")
        params.append(data_inicio)

    if data_fim:
        query_where.append("cq.data_recebimento <= ?")
        params.append(data_fim)

    if cardapio_filtro:
        query_where.append("cq.cardapio_id = ?")
        params.append(cardapio_filtro)

    if conformidade_filtro == 'sim':
        query_where.append("NOT EXISTS (SELECT 1 FROM controle_qualidade_itens cqi WHERE cqi.controle_id = cq.id AND cqi.conformidade = 'Não')")
    elif conformidade_filtro == 'nao':
        query_where.append("EXISTS (SELECT 1 FROM controle_qualidade_itens cqi WHERE cqi.controle_id = cq.id AND cqi.conformidade = 'Não')")

    where_sql = ("WHERE " + " AND ".join(query_where)) if query_where else ""

    with closing(get_db_connection()) as conn:
        # Estatísticas Gerais (KPIs)
        total_inspecoes = conn.execute("SELECT COUNT(*) FROM controle_qualidade").fetchone()[0]
        
        stats_itens = conn.execute("""
            SELECT 
                COUNT(*) as total_itens,
                SUM(CASE WHEN conformidade = 'Sim' THEN 1 ELSE 0 END) as total_conformes,
                SUM(CASE WHEN conformidade = 'Não' THEN 1 ELSE 0 END) as total_nao_conformes,
                AVG(CASE WHEN temperatura IS NOT NULL AND temperatura > 0 THEN temperatura ELSE NULL END) as media_temp
            FROM controle_qualidade_itens
        """).fetchone()

        total_itens = stats_itens['total_itens'] or 0
        total_conformes = stats_itens['total_conformes'] or 0
        total_nao_conformes = stats_itens['total_nao_conformes'] or 0
        media_temp = round(stats_itens['media_temp'], 1) if stats_itens['media_temp'] else 0.0
        taxa_conformidade = round((total_conformes / total_itens * 100), 1) if total_itens > 0 else 100.0

        # Contagem da consulta filtrada
        count_sql = f"SELECT COUNT(*) FROM controle_qualidade cq {where_sql}"
        total_filtrados = conn.execute(count_sql, params).fetchone()[0]

        # Lista de inspeções paginada com dados do cardápio
        list_sql = f"""
            SELECT 
                cq.*,
                c.data as cardapio_data,
                c.tipo_refeicao as cardapio_tipo,
                c.descricao as cardapio_descricao,
                (SELECT COUNT(*) FROM controle_qualidade_itens cqi WHERE cqi.controle_id = cq.id) as total_preparos,
                (SELECT COUNT(*) FROM controle_qualidade_itens cqi WHERE cqi.controle_id = cq.id AND cqi.conformidade = 'Não') as itens_nao_conformes
            FROM controle_qualidade cq
            JOIN cardapios c ON cq.cardapio_id = c.id
            {where_sql}
            ORDER BY cq.data_recebimento DESC, cq.horario_recebimento DESC
            LIMIT ? OFFSET ?
        """
        registros = conn.execute(list_sql, params + [QUALIDADE_POR_PAGINA, offset]).fetchall()

        # Carrega itens para cada registro exibido para pré-visualização rápida
        itens_por_registro = {}
        for r in registros:
            itens = conn.execute("""
                SELECT * FROM controle_qualidade_itens 
                WHERE controle_id = ? 
                ORDER BY ordem ASC, id ASC
            """, (r['id'],)).fetchall()
            itens_por_registro[r['id']] = itens

        # Lista de cardápios recentes para seleção rápida na impressão em branco
        cardapios_recentes = conn.execute("""
            SELECT id, data, tipo_refeicao, descricao 
            FROM cardapios 
            ORDER BY data DESC 
            LIMIT 35
        """).fetchall()

    total_paginas = max(1, (total_filtrados + QUALIDADE_POR_PAGINA - 1) // QUALIDADE_POR_PAGINA)
    config = get_config()

    return render_template(
        'admin/qualidade_lista.html',
        registros=registros,
        itens_por_registro=itens_por_registro,
        cardapios=cardapios_recentes,
        config=config,
        total=total_filtrados,
        pagina=pagina,
        total_paginas=total_paginas,
        busca=busca,
        data_inicio=data_inicio,
        data_fim=data_fim,
        conformidade_filtro=conformidade_filtro,
        cardapio_filtro=cardapio_filtro,
        total_inspecoes=total_inspecoes,
        total_itens=total_itens,
        taxa_conformidade=taxa_conformidade,
        total_nao_conformes=total_nao_conformes,
        media_temp=media_temp
    )

@admin_bp.route('/admin/qualidade/novo', methods=['GET', 'POST'])
def admin_qualidade_novo():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_acesso_qualidade(): return redirect(url_for('admin.admin_dashboard'))

    if request.method == 'POST':
        cardapio_id = request.form.get('cardapio_id')
        campus = request.form.get('campus', '').strip()
        data_recebimento = request.form.get('data_recebimento', '').strip()
        horario_recebimento = request.form.get('horario_recebimento', '').strip()
        fornecedor = request.form.get('fornecedor', '').strip()

        if not cardapio_id or not campus or not data_recebimento or not horario_recebimento or not fornecedor:
            flash('Por favor, preencha todos os dados obrigatórios do cabeçalho (Cardápio, Campus, Data, Horário e Fornecedor).', 'error')
            return redirect(request.url)

        # Captura dos itens dinâmicos
        tipos_preparo = request.form.getlist('tipo_preparo[]') or request.form.getlist('tipo_preparo')
        tipos_preparo_outro = request.form.getlist('tipo_preparo_outro[]') or request.form.getlist('tipo_preparo_outro')
        temperaturas = request.form.getlist('temperatura[]') or request.form.getlist('temperatura')
        conformidades = request.form.getlist('conformidade[]') or request.form.getlist('conformidade')
        aspectos_sensoriais = request.form.getlist('aspecto_sensorial[]') or request.form.getlist('aspecto_sensorial')
        profissionais = request.form.getlist('profissional_medicao[]') or request.form.getlist('profissional_medicao')
        responsaveis_recebimento = request.form.getlist('responsavel_recebimento[]') or request.form.getlist('responsavel_recebimento')
        responsaveis_fornecedor = request.form.getlist('responsavel_fornecedor[]') or request.form.getlist('responsavel_fornecedor')
        observacoes_list = request.form.getlist('observacoes[]') or request.form.getlist('observacoes')

        num_itens = len(tipos_preparo)
        if num_itens == 0:
            flash('É necessário adicionar ao menos um item de preparo para o controle de qualidade.', 'error')
            return redirect(request.url)

        criado_em = datetime_now_str()
        criado_por = session.get('admin_usuario', 'admin')

        try:
            with closing(get_db_connection()) as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO controle_qualidade 
                    (cardapio_id, campus, data_recebimento, horario_recebimento, fornecedor, criado_em, criado_por)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (cardapio_id, campus, data_recebimento, horario_recebimento, fornecedor, criado_em, criado_por))
                controle_id = cur.lastrowid

                for idx in range(num_itens):
                    t_preparo = tipos_preparo[idx].strip() if idx < len(tipos_preparo) else 'Outros'
                    t_outro = tipos_preparo_outro[idx].strip() if idx < len(tipos_preparo_outro) else ''
                    
                    # Normalizar temperatura
                    temp_raw = temperaturas[idx].strip().replace(',', '.') if idx < len(temperaturas) else ''
                    try:
                        temp_val = float(temp_raw) if temp_raw else None
                    except ValueError:
                        temp_val = None

                    conf = conformidades[idx].strip() if idx < len(conformidades) else 'Sim'
                    asp = aspectos_sensoriais[idx].strip() if idx < len(aspectos_sensoriais) else 'Adequado'
                    prof = profissionais[idx].strip() if idx < len(profissionais) else ''
                    resp_rec = responsaveis_recebimento[idx].strip() if idx < len(responsaveis_recebimento) else ''
                    resp_forn = responsaveis_fornecedor[idx].strip() if idx < len(responsaveis_fornecedor) else ''
                    obs = observacoes_list[idx].strip() if idx < len(observacoes_list) else ''

                    cur.execute("""
                        INSERT INTO controle_qualidade_itens
                        (controle_id, tipo_preparo, tipo_preparo_outro, temperatura, conformidade, aspecto_sensorial, profissional_medicao, responsavel_recebimento, responsavel_fornecedor, observacoes, ordem)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (controle_id, t_preparo, t_outro, temp_val, conf, asp, prof, resp_rec, resp_forn, obs, idx))

                conn.commit()

            registrar_auditoria(
                "Criar Controle de Qualidade",
                f"Registrou recebimento ID #{controle_id} | Data: {data_recebimento} {horario_recebimento} | Campus: {campus} | Fornecedor: {fornecedor} | {num_itens} preparo(s) avaliado(s)"
            )
            flash('Registro de recebimento e controle de qualidade salvo com sucesso!', 'success')
            return redirect(url_for('admin.admin_qualidade'))

        except Exception as e:
            flash(f'Erro ao salvar registro de qualidade: {str(e)}', 'error')
            return redirect(request.url)

    # GET:
    cardapio_id_param = request.args.get('cardapio_id', type=int)

    with closing(get_db_connection()) as conn:
        cardapios = conn.execute("""
            SELECT id, data, tipo_refeicao, descricao, proteinas, acompanhamento, salada, sobremesa, outros
            FROM cardapios 
            ORDER BY data DESC 
            LIMIT 50
        """).fetchall()

        cardapio_selecionado = None
        if cardapio_id_param:
            cardapio_selecionado = conn.execute("SELECT * FROM cardapios WHERE id = ?", (cardapio_id_param,)).fetchone()

    hoje = date_hoje_str()
    data_padrao = cardapio_selecionado['data'] if cardapio_selecionado else hoje
    horario_padrao = datetime.now().strftime('%H:%M')

    return render_template(
        'admin/qualidade_form.html',
        modo='novo',
        registro=None,
        itens=[],
        cardapios=cardapios,
        cardapio_selecionado_id=cardapio_id_param,
        data_padrao=data_padrao,
        horario_padrao=horario_padrao
    )

@admin_bp.route('/admin/qualidade/editar/<int:id>', methods=['GET', 'POST'])
def admin_qualidade_editar(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_acesso_qualidade(): return redirect(url_for('admin.admin_dashboard'))

    with closing(get_db_connection()) as conn:
        registro = conn.execute("SELECT * FROM controle_qualidade WHERE id = ?", (id,)).fetchone()
        if not registro:
            flash('Registro de controle de qualidade não encontrado.', 'error')
            return redirect(url_for('admin.admin_qualidade'))

    if request.method == 'POST':
        cardapio_id = request.form.get('cardapio_id')
        campus = request.form.get('campus', '').strip()
        data_recebimento = request.form.get('data_recebimento', '').strip()
        horario_recebimento = request.form.get('horario_recebimento', '').strip()
        fornecedor = request.form.get('fornecedor', '').strip()

        if not cardapio_id or not campus or not data_recebimento or not horario_recebimento or not fornecedor:
            flash('Por favor, preencha todos os dados obrigatórios do cabeçalho.', 'error')
            return redirect(request.url)

        tipos_preparo = request.form.getlist('tipo_preparo[]') or request.form.getlist('tipo_preparo')
        tipos_preparo_outro = request.form.getlist('tipo_preparo_outro[]') or request.form.getlist('tipo_preparo_outro')
        temperaturas = request.form.getlist('temperatura[]') or request.form.getlist('temperatura')
        conformidades = request.form.getlist('conformidade[]') or request.form.getlist('conformidade')
        aspectos_sensoriais = request.form.getlist('aspecto_sensorial[]') or request.form.getlist('aspecto_sensorial')
        profissionais = request.form.getlist('profissional_medicao[]') or request.form.getlist('profissional_medicao')
        responsaveis_recebimento = request.form.getlist('responsavel_recebimento[]') or request.form.getlist('responsavel_recebimento')
        responsaveis_fornecedor = request.form.getlist('responsavel_fornecedor[]') or request.form.getlist('responsavel_fornecedor')
        observacoes_list = request.form.getlist('observacoes[]') or request.form.getlist('observacoes')

        num_itens = len(tipos_preparo)
        if num_itens == 0:
            flash('É necessário ao menos um item de preparo.', 'error')
            return redirect(request.url)

        atualizado_em = datetime_now_str()
        atualizado_por = session.get('admin_usuario', 'admin')

        try:
            with closing(get_db_connection()) as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE controle_qualidade SET
                        cardapio_id = ?,
                        campus = ?,
                        data_recebimento = ?,
                        horario_recebimento = ?,
                        fornecedor = ?,
                        atualizado_em = ?,
                        atualizado_por = ?
                    WHERE id = ?
                """, (cardapio_id, campus, data_recebimento, horario_recebimento, fornecedor, atualizado_em, atualizado_por, id))

                cur.execute("DELETE FROM controle_qualidade_itens WHERE controle_id = ?", (id,))

                for idx in range(num_itens):
                    t_preparo = tipos_preparo[idx].strip() if idx < len(tipos_preparo) else 'Outros'
                    t_outro = tipos_preparo_outro[idx].strip() if idx < len(tipos_preparo_outro) else ''
                    
                    temp_raw = temperaturas[idx].strip().replace(',', '.') if idx < len(temperaturas) else ''
                    try:
                        temp_val = float(temp_raw) if temp_raw else None
                    except ValueError:
                        temp_val = None

                    conf = conformidades[idx].strip() if idx < len(conformidades) else 'Sim'
                    asp = aspectos_sensoriais[idx].strip() if idx < len(aspectos_sensoriais) else 'Adequado'
                    prof = profissionais[idx].strip() if idx < len(profissionais) else ''
                    resp_rec = responsaveis_recebimento[idx].strip() if idx < len(responsaveis_recebimento) else ''
                    resp_forn = responsaveis_fornecedor[idx].strip() if idx < len(responsaveis_fornecedor) else ''
                    obs = observacoes_list[idx].strip() if idx < len(observacoes_list) else ''

                    cur.execute("""
                        INSERT INTO controle_qualidade_itens
                        (controle_id, tipo_preparo, tipo_preparo_outro, temperatura, conformidade, aspecto_sensorial, profissional_medicao, responsavel_recebimento, responsavel_fornecedor, observacoes, ordem)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (id, t_preparo, t_outro, temp_val, conf, asp, prof, resp_rec, resp_forn, obs, idx))

                conn.commit()

            registrar_auditoria(
                "Editar Controle de Qualidade",
                f"Atualizou vistoria ID #{id} | Data: {data_recebimento} {horario_recebimento} | Campus: {campus} | Fornecedor: {fornecedor} | {num_itens} item(ns)"
            )
            flash('Controle de qualidade atualizado com sucesso!', 'success')
            return redirect(url_for('admin.admin_qualidade'))

        except Exception as e:
            flash(f'Erro ao atualizar registro: {str(e)}', 'error')
            return redirect(request.url)

    # GET:
    with closing(get_db_connection()) as conn:
        itens = conn.execute("""
            SELECT * FROM controle_qualidade_itens 
            WHERE controle_id = ? 
            ORDER BY ordem ASC, id ASC
        """, (id,)).fetchall()

        cardapios = conn.execute("""
            SELECT id, data, tipo_refeicao, descricao, proteinas, acompanhamento, salada, sobremesa, outros
            FROM cardapios 
            ORDER BY data DESC 
            LIMIT 50
        """).fetchall()

    return render_template(
        'admin/qualidade_form.html',
        modo='editar',
        registro=registro,
        itens=itens,
        cardapios=cardapios,
        cardapio_selecionado_id=registro['cardapio_id']
    )

@admin_bp.route('/admin/qualidade/excluir/<int:id>', methods=['POST'])
def admin_qualidade_excluir(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_acesso_qualidade(): return redirect(url_for('admin.admin_dashboard'))

    with closing(get_db_connection()) as conn:
        registro = conn.execute("SELECT * FROM controle_qualidade WHERE id = ?", (id,)).fetchone()
        if not registro:
            flash('Registro não encontrado.', 'error')
            return redirect(url_for('admin.admin_qualidade'))

        conn.execute("DELETE FROM controle_qualidade_itens WHERE controle_id = ?", (id,))
        conn.execute("DELETE FROM controle_qualidade WHERE id = ?", (id,))
        conn.commit()

    registrar_auditoria(
        "Excluir Controle de Qualidade",
        f"Excluiu registro ID #{id} ({registro['data_recebimento']} - Campus: {registro['campus']} - Fornecedor: {registro['fornecedor']})"
    )
    flash('Registro de controle de qualidade excluído com sucesso.', 'success')
    return redirect(url_for('admin.admin_qualidade'))

@admin_bp.route('/admin/qualidade/detalhes/<int:id>', methods=['GET'])
def admin_qualidade_detalhes(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_acesso_qualidade(): return redirect(url_for('admin.admin_dashboard'))

    with closing(get_db_connection()) as conn:
        registro = conn.execute("""
            SELECT 
                cq.*,
                c.data as cardapio_data,
                c.tipo_refeicao as cardapio_tipo,
                c.descricao as cardapio_descricao
            FROM controle_qualidade cq
            JOIN cardapios c ON cq.cardapio_id = c.id
            WHERE cq.id = ?
        """, (id,)).fetchone()

        if not registro:
            flash('Registro não encontrado.', 'error')
            return redirect(url_for('admin.admin_qualidade'))

        itens = conn.execute("""
            SELECT * FROM controle_qualidade_itens 
            WHERE controle_id = ? 
            ORDER BY ordem ASC, id ASC
        """, (id,)).fetchall()

    return render_template('admin/qualidade_detalhes.html', registro=registro, itens=itens)

@admin_bp.route('/admin/qualidade/imprimir/<int:id>', methods=['GET'])
def admin_qualidade_imprimir(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_acesso_qualidade(): return redirect(url_for('admin.admin_dashboard'))

    with closing(get_db_connection()) as conn:
        registro = conn.execute("""
            SELECT 
                cq.*,
                c.data as cardapio_data,
                c.tipo_refeicao as cardapio_tipo,
                c.descricao as cardapio_descricao
            FROM controle_qualidade cq
            JOIN cardapios c ON cq.cardapio_id = c.id
            WHERE cq.id = ?
        """, (id,)).fetchone()

        if not registro:
            flash('Registro não encontrado.', 'error')
            return redirect(url_for('admin.admin_qualidade'))

        itens = conn.execute("""
            SELECT * FROM controle_qualidade_itens 
            WHERE controle_id = ? 
            ORDER BY ordem ASC, id ASC
        """, (id,)).fetchall()

    config = get_config()
    return render_template('admin/qualidade_imprimir.html', registro=registro, itens=itens, config=config)

@admin_bp.route('/admin/qualidade/api/cardapio/<int:cardapio_id>', methods=['GET'])
def admin_qualidade_api_cardapio(cardapio_id):
    if not is_logged_in_admin():
        return jsonify({'error': 'Acesso não autorizado'}), 401
    
    with closing(get_db_connection()) as conn:
        c = conn.execute("SELECT * FROM cardapios WHERE id = ?", (cardapio_id,)).fetchone()
        if not c:
            return jsonify({'error': 'Cardápio não encontrado'}), 404

        return jsonify({
            'id': c['id'],
            'data': c['data'],
            'tipo_refeicao': c['tipo_refeicao'],
            'descricao': c['descricao'],
            'proteinas': c['proteinas'] or '',
            'acompanhamento': c['acompanhamento'] or '',
            'salada': c['salada'] or '',
            'sobremesa': c['sobremesa'] or '',
            'outros': c['outros'] or ''
        })

@admin_bp.route('/admin/qualidade/imprimir-em-branco', methods=['GET'])
def admin_qualidade_imprimir_em_branco():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_acesso_qualidade(): return redirect(url_for('admin.admin_dashboard'))

    cardapio_id = request.args.get('cardapio_id', type=int)
    cardapio = None

    if cardapio_id:
        with closing(get_db_connection()) as conn:
            cardapio = conn.execute("SELECT * FROM cardapios WHERE id = ?", (cardapio_id,)).fetchone()

    config = get_config()
    return render_template('admin/qualidade_imprimir_branco.html', cardapio=cardapio, config=config)

@admin_bp.route('/admin/qualidade/salvar-padrao', methods=['POST'])
def admin_qualidade_salvar_padrao():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_acesso_qualidade(): return redirect(url_for('admin.admin_dashboard'))

    novo_texto = request.form.get('padrao_qualidade_texto', '').strip()
    if not novo_texto:
        flash('O texto de referência sanitária não pode ficar vazio.', 'error')
        return redirect(url_for('admin.admin_qualidade'))

    with closing(get_db_connection()) as conn:
        conn.execute("UPDATE configuracoes SET padrao_qualidade_texto = ? WHERE id = 1", (novo_texto,))
        conn.commit()

    registrar_auditoria("Alterar Padrões Sanitários", "Atualizou o texto de padrões sanitários e referências técnicas (RDC 216)")
    flash('Padrões de referência sanitária atualizados com sucesso!', 'success')
    return redirect(url_for('admin.admin_qualidade'))

# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, session, flash, Response, send_file
from datetime import datetime, timedelta
import csv
import io
from io import BytesIO
import json
from database import closing, get_db_connection, get_config
from utils.auth import is_logged_in_admin, tem_permissao
from utils.helpers import registrar_auditoria, calcular_janela_reserva
from . import admin_bp

CARDAPIOS_POR_PAGINA = 20
RELATORIO_POR_PAGINA = 30

@admin_bp.route('/admin/relatorios')
def admin_relatorios():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))
    
    # Parâmetros de filtro de cardápios
    tipo_filtro = request.args.get('tipo', 'todos')  # todos | dia | mes | ano | periodo
    data_dia    = request.args.get('data_dia', '')       # YYYY-MM-DD
    data_mes    = request.args.get('data_mes', '')       # YYYY-MM  (input month)
    data_ano    = request.args.get('data_ano', '')       # YYYY
    data_inicio = request.args.get('data_inicio', '')    # YYYY-MM-DD
    data_fim    = request.args.get('data_fim', '')       # YYYY-MM-DD
    busca       = request.args.get('q', '').strip()      # texto livre
    pagina      = request.args.get('page', 1, type=int)
    offset      = (pagina - 1) * CARDAPIOS_POR_PAGINA

    # Parâmetros de filtro de opiniões
    aba_ativa       = request.args.get('aba', 'charts')   # charts | feedback | nutrition | students
    op_nota         = request.args.get('op_nota', '', type=str).strip()
    op_turma        = request.args.get('op_turma', '', type=str).strip()
    op_data_inicio  = request.args.get('op_data_inicio', '').strip()
    op_data_fim     = request.args.get('op_data_fim', '').strip()
    op_busca        = request.args.get('op_q', '').strip()
    op_pagina       = request.args.get('op_page', 1, type=int)
    op_offset       = (op_pagina - 1) * RELATORIO_POR_PAGINA

    with closing(get_db_connection()) as conn:
        base_query = """
            SELECT c.*, 
                   (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status != 'CANCELADA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL)) as total_reservas,
                   (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status = 'CONSUMIDA') as total_consumidas,
                   (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status = 'CONSUMIDA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL)) as consumo_normal,
                   (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EXTRA') as consumo_extra,
                   (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EVENTO') as consumo_evento
            FROM cardapios c
        """
        conditions = []
        params = []

        # Filtro por tipo de data
        if tipo_filtro == 'dia' and data_dia:
            conditions.append("c.data = ?")
            params.append(data_dia)
        elif tipo_filtro == 'mes' and data_mes:
            # data_mes vem como YYYY-MM
            conditions.append("strftime('%Y-%m', c.data) = ?")
            params.append(data_mes)
        elif tipo_filtro == 'ano' and data_ano:
            conditions.append("strftime('%Y', c.data) = ?")
            params.append(data_ano)
        elif tipo_filtro == 'periodo' and data_inicio and data_fim:
            conditions.append("c.data BETWEEN ? AND ?")
            params.extend([data_inicio, data_fim])

        # Filtro texto livre
        if busca:
            conditions.append("(c.descricao LIKE ? OR c.data LIKE ?)")
            like = f'%{busca}%'
            params.extend([like, like])

        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)

        count_query = f"SELECT COUNT(*) FROM ({base_query})"
        total = conn.execute(count_query, params).fetchone()[0]

        final_query = base_query + " ORDER BY c.data DESC LIMIT ? OFFSET ?"
        params_page = params + [CARDAPIOS_POR_PAGINA, offset]
        cardapios = conn.execute(final_query, params_page).fetchall()

        # Obter dados dos últimos 7 cardápios para os gráficos
        chart_rows = conn.execute("""
            SELECT c.data,
                   (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status != 'CANCELADA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL)) as reservas,
                   (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status = 'CONSUMIDA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL)) as consumidas,
                   (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EXTRA') as extras,
                   (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EVENTO') as eventos
            FROM cardapios c
            ORDER BY c.data DESC LIMIT 7
        """).fetchall()

        chart_data = []
        for r in reversed(chart_rows):
            wasted = max(0, r['reservas'] - r['consumidas'])
            chart_data.append({
                'data': r['data'],
                'reservas': r['reservas'],
                'consumidas': r['consumidas'],
                'wasted': wasted,
                'extras': r['extras'],
                'eventos': r['eventos']
            })
        chart_json = json.dumps(chart_data)
        
        # Carregar Serviços de BI, IA e Nutricional (Pontos 10, 11, 18)
        from utils.services import calcular_previsao_demanda_ia, get_avaliacoes_refeicoes, get_perfil_nutricional
        previsao = calcular_previsao_demanda_ia(conn)
        avaliacoes = get_avaliacoes_refeicoes(conn)
        perfil_nutricional = get_perfil_nutricional(conn)
        turmas = conn.execute("SELECT * FROM turmas WHERE is_evento = 0 ORDER BY nome").fetchall()

        # ── Carregar opiniões com filtros e paginação ────────────────────────
        op_query = """
            SELECT r.avaliacao_nota, r.avaliacao_comentario,
                   a.nome as aluno_nome, a.matricula,
                   t.nome as turma_nome, c.data, c.tipo_refeicao
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            JOIN cardapios c ON r.cardapio_id = c.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.avaliacao_nota IS NOT NULL
        """
        op_params = []
        if op_nota:
            op_query += " AND r.avaliacao_nota = ?"
            op_params.append(int(op_nota))
        if op_turma:
            op_query += " AND t.id = ?"
            op_params.append(int(op_turma))
        if op_data_inicio:
            op_query += " AND c.data >= ?"
            op_params.append(op_data_inicio)
        if op_data_fim:
            op_query += " AND c.data <= ?"
            op_params.append(op_data_fim)
        if op_busca:
            op_query += " AND (a.nome LIKE ? OR r.avaliacao_comentario LIKE ?)"
            like_op = f'%{op_busca}%'
            op_params.extend([like_op, like_op])

        op_total = conn.execute(f"SELECT COUNT(*) FROM ({op_query})", op_params).fetchone()[0]
        op_query_paginada = op_query + f" ORDER BY r.rowid DESC LIMIT {RELATORIO_POR_PAGINA} OFFSET {op_offset}"
        opinioes_lista = conn.execute(op_query_paginada, op_params).fetchall()
        op_total_paginas = max(1, (op_total + RELATORIO_POR_PAGINA - 1) // RELATORIO_POR_PAGINA)

    total_paginas = max(1, (total + CARDAPIOS_POR_PAGINA - 1) // CARDAPIOS_POR_PAGINA)

    return render_template('admin/relatorios_filtro.html',
                           cardapios=cardapios,
                           busca=busca,
                           tipo_filtro=tipo_filtro,
                           data_dia=data_dia,
                           data_mes=data_mes,
                           data_ano=data_ano,
                           data_inicio=data_inicio,
                           data_fim=data_fim,
                           pagina=pagina,
                           total_paginas=total_paginas,
                           total=total,
                           chart_data=chart_json,
                           previsao=previsao,
                           avaliacoes=avaliacoes,
                           perfil_nutricional=perfil_nutricional,
                           turmas=turmas,
                           aba_ativa=aba_ativa,
                           opinioes_lista=opinioes_lista,
                           op_nota=op_nota,
                           op_turma=op_turma,
                           op_data_inicio=op_data_inicio,
                           op_data_fim=op_data_fim,
                           op_busca=op_busca,
                           op_pagina=op_pagina,
                           op_total_paginas=op_total_paginas,
                           op_total=op_total)

@admin_bp.route('/admin/relatorios/opinioes/excel')
def admin_relatorios_opinioes_excel():
    """Exporta todas as opiniões (com filtros) para Excel."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))

    op_nota        = request.args.get('op_nota', '').strip()
    op_turma       = request.args.get('op_turma', '').strip()
    op_data_inicio = request.args.get('op_data_inicio', '').strip()
    op_data_fim    = request.args.get('op_data_fim', '').strip()
    op_busca       = request.args.get('op_q', '').strip()

    with closing(get_db_connection()) as conn:
        op_query = """
            SELECT r.avaliacao_nota, r.avaliacao_comentario,
                   a.nome as aluno_nome, a.matricula,
                   t.nome as turma_nome, c.data, c.tipo_refeicao
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            JOIN cardapios c ON r.cardapio_id = c.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.avaliacao_nota IS NOT NULL
        """
        op_params = []
        if op_nota:
            op_query += " AND r.avaliacao_nota = ?"
            op_params.append(int(op_nota))
        if op_turma:
            op_query += " AND t.id = ?"
            op_params.append(int(op_turma))
        if op_data_inicio:
            op_query += " AND c.data >= ?"
            op_params.append(op_data_inicio)
        if op_data_fim:
            op_query += " AND c.data <= ?"
            op_params.append(op_data_fim)
        if op_busca:
            op_query += " AND (a.nome LIKE ? OR r.avaliacao_comentario LIKE ?)"
            like_op = f'%{op_busca}%'
            op_params.extend([like_op, like_op])
        op_query += " ORDER BY r.rowid DESC"
        opinioes = conn.execute(op_query, op_params).fetchall()
        config = get_config()

    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    thin_side = Side(style='thin', color='D3D3D3')
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    wb = Workbook()
    ws = wb.active
    ws.title = "Opinioes Estudantes"
    ws.views.sheetView[0].showGridLines = True

    ws['A1'] = f"OPINIÕES DOS ESTUDANTES — {config['sigla_instituicao']}"
    ws['A1'].font = Font(name='Segoe UI', bold=True, size=14, color='2F9E41')
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A1:F1')
    ws.row_dimensions[1].height = 35

    ws['A2'] = f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')} | Total: {len(opinioes)} avaliações"
    ws['A2'].font = Font(name='Segoe UI', italic=True, size=10, color='6B7280')
    ws['A2'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A2:F2')
    ws.row_dimensions[2].height = 20

    headers = ["Estudante", "Matrícula", "Turma", "Refeição", "Data", "Nota (★)", "Comentário"]
    ws.append([])
    ws.append(headers)
    ws.row_dimensions[4].height = 26

    header_fill = PatternFill(start_color="2F9E41", end_color="2F9E41", fill_type="solid")
    header_font = Font(name='Segoe UI', bold=True, color='FFFFFF', size=11)
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='center')

    for col_idx in range(1, 8):
        cell = ws.cell(row=4, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align if col_idx in (2, 5, 6) else left_align
        cell.border = thin_border

    row_idx = 5
    zebra_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
    for op in opinioes:
        try:
            data_fmt = datetime.strptime(op['data'], '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            data_fmt = op['data']
        estrelas = '★' * (op['avaliacao_nota'] or 0)
        ws.append([op['aluno_nome'], op['matricula'], op['turma_nome'] or '---',
                   op['tipo_refeicao'] or '---', data_fmt, estrelas,
                   op['avaliacao_comentario'] or '---'])
        ws.row_dimensions[row_idx].height = 20
        for col_idx in range(1, 8):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(name='Segoe UI', size=10)
            cell.border = thin_border
            cell.alignment = center_align if col_idx in (2, 5, 6) else left_align
            if row_idx % 2 == 0:
                cell.fill = zebra_fill
        row_idx += 1

    from openpyxl.utils import get_column_letter
    for col in ws.columns:
        max_len = 0
        for cell in col:
            if cell.row in (1, 2, 3): continue
            val_str = str(cell.value or "")
            if len(val_str) > max_len: max_len = len(val_str)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(min(max_len + 4, 50), 12)

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    registrar_auditoria("Exportar Opiniões Excel", f"Exportou {len(opinioes)} opiniões de estudantes")
    return send_file(output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"Opinioes_Estudantes_{datetime.now().strftime('%Y%m%d')}.xlsx")

@admin_bp.route('/admin/relatorios/periodo')
def admin_relatorio_periodo():
    """Relatório consolidado para um intervalo de datas (mês, ano ou período customizado)."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))

    data_inicio = request.args.get('data_inicio', '')
    data_fim    = request.args.get('data_fim', '')
    turma_id    = request.args.get('turma_id', type=int)
    status_filter = request.args.get('status')

    if not data_inicio or not data_fim:
        flash('Informe o período corretamente.', 'error')
        return redirect(url_for('admin.admin_relatorios'))

    pagina = request.args.get('page', 1, type=int)
    offset = (pagina - 1) * RELATORIO_POR_PAGINA

    with closing(get_db_connection()) as conn:
        # Listar cardápios do período para referência
        cardapios = conn.execute(
            "SELECT * FROM cardapios WHERE data BETWEEN ? AND ? ORDER BY data ASC",
            (data_inicio, data_fim)
        ).fetchall()

        cardapio_ids = [c['id'] for c in cardapios]

        if not cardapio_ids:
            flash('Nenhum cardápio encontrado no período informado.', 'warning')
            return redirect(url_for('admin.admin_relatorios'))

        placeholders = ','.join(['?'] * len(cardapio_ids))

        # Lista nominal com filtros
        query = f"""
            SELECT a.nome, a.matricula, a.restricoes, t.nome as turma_nome,
                   r.status, r.tipo_consumo, t.id as turma_id, c.data as data_cardapio
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            JOIN cardapios c ON r.cardapio_id = c.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.cardapio_id IN ({placeholders}) AND r.status != 'CANCELADA'
        """
        params = list(cardapio_ids)

        if turma_id:
            query += " AND t.id = ?"
            params.append(turma_id)
        if status_filter:
            query += " AND r.status = ?"
            params.append(status_filter)

        query += " ORDER BY c.data ASC, a.nome ASC"

        # Total para paginação
        count_query = f"SELECT COUNT(*) FROM ({query})"
        total = conn.execute(count_query, params).fetchone()[0]

        query_paginada = query + f" LIMIT {RELATORIO_POR_PAGINA} OFFSET {offset}"
        reservas = conn.execute(query_paginada, params).fetchall()
        total_paginas = max(1, (total + RELATORIO_POR_PAGINA - 1) // RELATORIO_POR_PAGINA)

        # Resumo geral (sem filtros de turma/status para manter coerência)
        resumo_geral = conn.execute(f"""
            SELECT
                COUNT(CASE WHEN r.status != 'CANCELADA' AND (r.tipo_consumo IN ('NORMAL', 'EVENTO') OR r.tipo_consumo IS NULL) THEN 1 END) as total_previstos,
                COUNT(CASE WHEN r.status = 'CONSUMIDA' AND (r.tipo_consumo IN ('NORMAL', 'EVENTO') OR r.tipo_consumo IS NULL) THEN 1 END) as consumidas_normais,
                COUNT(CASE WHEN r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EXTRA' THEN 1 END) as consumidas_extras,
                COUNT(CASE WHEN r.status = 'ATIVA' AND (r.tipo_consumo IN ('NORMAL', 'EVENTO') OR r.tipo_consumo IS NULL) THEN 1 END) as total_sobras,
                COUNT(CASE WHEN r.status = 'CONSUMIDA' THEN 1 END) as total_consumidas
            FROM reservas r
            JOIN cardapios c ON r.cardapio_id = c.id
            WHERE r.cardapio_id IN ({placeholders}) AND r.status != 'CANCELADA'
        """, list(cardapio_ids)).fetchone()

        # Resumo por turma
        resumo_turmas = conn.execute(f"""
            SELECT t.nome as turma_nome,
                   SUM(CASE WHEN r.tipo_consumo IN ('NORMAL', 'EVENTO') OR r.tipo_consumo IS NULL THEN 1 ELSE 0 END) as total,
                   SUM(CASE WHEN r.status = 'CONSUMIDA' AND (r.tipo_consumo IN ('NORMAL', 'EVENTO') OR r.tipo_consumo IS NULL) THEN 1 ELSE 0 END) as consumidas_normais,
                   SUM(CASE WHEN r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EXTRA' THEN 1 ELSE 0 END) as consumidas_extras
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.cardapio_id IN ({placeholders}) AND r.status != 'CANCELADA'
            GROUP BY t.id
            ORDER BY t.nome ASC
        """, list(cardapio_ids)).fetchall()

        # Resumo por dia
        resumo_dias = conn.execute(f"""
            SELECT c.data,
                   COUNT(CASE WHEN r.status != 'CANCELADA' THEN 1 END) as total_reservas,
                   COUNT(CASE WHEN r.status = 'CONSUMIDA' THEN 1 END) as total_consumidas,
                   COUNT(CASE WHEN r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EXTRA' THEN 1 END) as extras
            FROM cardapios c
            LEFT JOIN reservas r ON r.cardapio_id = c.id
            WHERE c.data BETWEEN ? AND ?
            GROUP BY c.id
            ORDER BY c.data ASC
        """, (data_inicio, data_fim)).fetchall()

        turmas = conn.execute("SELECT * FROM turmas ORDER BY nome ASC").fetchall()

    # Formatar label do período
    try:
        label_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').strftime('%d/%m/%Y')
        label_fim = datetime.strptime(data_fim, '%Y-%m-%d').strftime('%d/%m/%Y')
    except:
        label_inicio = data_inicio
        label_fim = data_fim

    return render_template('admin/relatorio_periodo.html',
        data_inicio=data_inicio,
        data_fim=data_fim,
        label_inicio=label_inicio,
        label_fim=label_fim,
        cardapios=cardapios,
        reservas=reservas,
        resumo_geral=resumo_geral,
        resumo_turmas=resumo_turmas,
        resumo_dias=resumo_dias,
        turmas=turmas,
        filtro_turma=turma_id,
        filtro_status=status_filter,
        pagina=pagina,
        total_paginas=total_paginas,
        total=total
    )

@admin_bp.route('/admin/relatorios/eventos')
def admin_relatorio_eventos():
    """Relatório detalhado de consumo por evento."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))
    
    evento_id = request.args.get('evento_id', type=int)
    
    with closing(get_db_connection()) as conn:
        eventos = conn.execute("SELECT * FROM turmas WHERE is_evento = 1 ORDER BY nome").fetchall()
        
        relatorio = []
        evento_selecionado = None
        
        if evento_id:
            evento_selecionado = conn.execute("SELECT * FROM turmas WHERE id = ? AND is_evento = 1", (evento_id,)).fetchone()
            
            # Buscar todos os participantes do evento e seus consumos
            query = """
                SELECT 
                    a.nome, a.cpf, a.instituicao, a.email,
                    COUNT(r.id) as total_refeicoes,
                    GROUP_CONCAT(c.data || ' (' || c.tipo_refeicao || ')', ', ') as datas_consumo
                FROM alunos a
                JOIN eventos_participantes ep ON a.id = ep.aluno_id
                LEFT JOIN reservas r ON a.id = r.aluno_id AND r.status = 'CONSUMIDA'
                LEFT JOIN cardapios c ON r.cardapio_id = c.id
                WHERE ep.turma_id = ?
            """
            
            # Se o evento tem data, filtra os consumos apenas dentro do período do evento
            if evento_selecionado and evento_selecionado['data_inicio'] and evento_selecionado['data_fim']:
                query += " AND (c.data IS NULL OR (c.data >= ? AND c.data <= ?))"
                query += " GROUP BY a.id ORDER BY total_refeicoes DESC, a.nome ASC"
                relatorio = conn.execute(query, (evento_id, evento_selecionado['data_inicio'], evento_selecionado['data_fim'])).fetchall()
            else:
                query += " GROUP BY a.id ORDER BY total_refeicoes DESC, a.nome ASC"
                relatorio = conn.execute(query, (evento_id,)).fetchall()

    return render_template('admin/relatorio_eventos.html', 
                           eventos=eventos, 
                           relatorio=relatorio, 
                           evento_id=evento_id, 
                           evento_selecionado=evento_selecionado)

@admin_bp.route('/admin/relatorios/eventos/<int:evento_id>/imprimir')
@admin_bp.route('/admin/relatorios/eventos/imprimir')
def admin_relatorio_eventos_imprimir(evento_id=None):
    """Página dedicada para impressão oficial do relatório de consumo por evento."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))
    
    if evento_id is None:
        evento_id = request.args.get('evento_id', type=int)
        
    if not evento_id:
        flash('Selecione um evento válido para imprimir.', 'warning')
        return redirect(url_for('admin.admin_relatorio_eventos'))
        
    with closing(get_db_connection()) as conn:
        evento_selecionado = conn.execute("SELECT * FROM turmas WHERE id = ? AND is_evento = 1", (evento_id,)).fetchone()
        if not evento_selecionado:
            flash('Evento não encontrado.', 'error')
            return redirect(url_for('admin.admin_relatorio_eventos'))
            
        query = """
            SELECT 
                a.nome, a.cpf, a.instituicao, a.email,
                COUNT(r.id) as total_refeicoes,
                GROUP_CONCAT(c.data || ' (' || c.tipo_refeicao || ')', ', ') as datas_consumo
            FROM alunos a
            JOIN eventos_participantes ep ON a.id = ep.aluno_id
            LEFT JOIN reservas r ON a.id = r.aluno_id AND r.status = 'CONSUMIDA'
            LEFT JOIN cardapios c ON r.cardapio_id = c.id
            WHERE ep.turma_id = ?
        """
        if evento_selecionado['data_inicio'] and evento_selecionado['data_fim']:
            query += " AND (c.data IS NULL OR (c.data >= ? AND c.data <= ?))"
            query += " GROUP BY a.id ORDER BY total_refeicoes DESC, a.nome ASC"
            relatorio = conn.execute(query, (evento_id, evento_selecionado['data_inicio'], evento_selecionado['data_fim'])).fetchall()
        else:
            query += " GROUP BY a.id ORDER BY total_refeicoes DESC, a.nome ASC"
            relatorio = conn.execute(query, (evento_id,)).fetchall()
            
        total_participantes = len(relatorio)
        participantes_atendidos = sum(1 for item in relatorio if (item['total_refeicoes'] or 0) > 0)
        total_refeicoes_servidas = sum((item['total_refeicoes'] or 0) for item in relatorio)
        media_refeicoes = round(total_refeicoes_servidas / participantes_atendidos, 1) if participantes_atendidos > 0 else 0
        data_emissao = datetime.now().strftime('%d/%m/%Y às %H:%M')
        config = get_config()
        admin_user = session.get('admin_usuario', 'admin')
        adm_row = conn.execute("SELECT nome FROM administradores WHERE usuario = ?", (admin_user,)).fetchone()
        emissor_nome = (adm_row['nome'] if (adm_row and adm_row['nome']) else None) or session.get('admin_nome') or admin_user
        
    return render_template('admin/relatorio_eventos_imprimir.html',
                           evento_selecionado=evento_selecionado,
                           relatorio=relatorio,
                           total_participantes=total_participantes,
                           participantes_atendidos=participantes_atendidos,
                           total_refeicoes_servidas=total_refeicoes_servidas,
                           media_refeicoes=media_refeicoes,
                           data_emissao=data_emissao,
                           emissor_nome=emissor_nome,
                           config=config)

@admin_bp.route('/admin/relatorios/periodo/excel')
def admin_relatorio_periodo_excel():
    """Exporta relatório consolidado do período para Excel."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))

    data_inicio = request.args.get('data_inicio', '')
    data_fim    = request.args.get('data_fim', '')

    if not data_inicio or not data_fim:
        flash('Período inválido.', 'error')
        return redirect(url_for('admin.admin_relatorios'))

    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    # Border styles
    thin_side = Side(style='thin', color='D3D3D3')
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    with closing(get_db_connection()) as conn:
        cardapio_ids = [c['id'] for c in conn.execute(
            "SELECT id FROM cardapios WHERE data BETWEEN ? AND ? ORDER BY data ASC",
            (data_inicio, data_fim)
        ).fetchall()]

        if not cardapio_ids:
            flash('Nenhum dado no período.', 'error')
            return redirect(url_for('admin.admin_relatorios'))

        placeholders = ','.join(['?'] * len(cardapio_ids))

        reservas = conn.execute(f"""
            SELECT a.nome, a.matricula, a.restricoes, t.nome as turma_nome,
                   r.status, r.tipo_consumo, c.data as data_cardapio
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            JOIN cardapios c ON r.cardapio_id = c.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.cardapio_id IN ({placeholders}) AND r.status != 'CANCELADA'
            ORDER BY c.data ASC, t.nome, a.nome ASC
        """, list(cardapio_ids)).fetchall()

    config = get_config()
    wb = Workbook()
    ws = wb.active
    ws.title = "Relatorio Periodo"

    # Ensure Excel grid lines are visible
    ws.views.sheetView[0].showGridLines = True

    # Cabeçalho
    try:
        label_i = datetime.strptime(data_inicio, '%Y-%m-%d').strftime('%d/%m/%Y')
        label_f = datetime.strptime(data_fim, '%Y-%m-%d').strftime('%d/%m/%Y')
    except:
        label_i, label_f = data_inicio, data_fim

    # Title row
    ws['A1'] = f"RELATÓRIO CONSOLIDADO — {config['sigla_instituicao']}"
    ws['A1'].font = Font(name='Segoe UI', bold=True, size=14, color='2F9E41')
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A1:G1')
    ws.row_dimensions[1].height = 35

    # Subtitle info row
    ws['A2'] = f"Período: {label_i} a {label_f} | Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws['A2'].font = Font(name='Segoe UI', italic=True, size=10, color='6B7280')
    ws['A2'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A2:G2')
    ws.row_dimensions[2].height = 20

    headers = ["Data", "Estudante", "Matrícula", "Turma", "Situação", "Tipo", "Restrição"]
    ws.append([]) # Row 3 empty
    ws.append(headers) # Row 4
    ws.row_dimensions[4].height = 26

    header_fill = PatternFill(start_color="2F9E41", end_color="2F9E41", fill_type="solid")
    header_font = Font(name='Segoe UI', bold=True, color='FFFFFF', size=11)
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='center')

    for col_idx in range(1, 8):
        cell = ws.cell(row=4, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align if col_idx in (1, 3, 5, 6) else left_align
        cell.border = thin_border

    row_idx = 5
    zebra_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
    for r in reservas:
        status_txt = "Entregue" if r['status'] == 'CONSUMIDA' else "Pendente"
        if r['tipo_consumo'] == 'EXTRA':
            tipo_txt = "Sobra/Extra"
        elif r['tipo_consumo'] == 'EVENTO':
            tipo_txt = "Evento"
        else:
            tipo_txt = "Reserva Normal"
        try:
            data_fmt = datetime.strptime(r['data_cardapio'], '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            data_fmt = r['data_cardapio']
        ws.append([data_fmt, r['nome'], r['matricula'], r['turma_nome'] or "---", status_txt, tipo_txt, r['restricoes'] or "---"])
        ws.row_dimensions[row_idx].height = 20

        # Style row data
        for col_idx in range(1, 8):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(name='Segoe UI', size=10)
            cell.border = thin_border
            cell.alignment = center_align if col_idx in (1, 3, 5, 6) else left_align
            if row_idx % 2 == 0:
                cell.fill = zebra_fill
        row_idx += 1

    from openpyxl.utils import get_column_letter
    for col in ws.columns:
        max_len = 0
        for cell in col:
            # Skip title, subtitle and empty row
            if cell.row in (1, 2, 3):
                continue
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"Relatorio_Periodo_{data_inicio}_a_{data_fim}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )

@admin_bp.route('/admin/relatorios/<int:cardapio_id>')
def admin_relatorio_dia(cardapio_id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))
    
    turma_id = request.args.get('turma_id', type=int)
    status_filter = request.args.get('status')
    tipo_consumo_filter = request.args.get('tipo_consumo')
    sem_paginacao = (request.args.get('sem_paginacao') == '1' or request.args.get('todas') == '1')
    auto_print = request.args.get('print') == '1'
    
    with closing(get_db_connection()) as conn:
        cardapio = conn.execute("SELECT * FROM cardapios WHERE id = ?", (cardapio_id,)).fetchone()
        
        query = """
            SELECT a.nome, a.matricula, a.restricoes, t.nome as turma_nome, r.status, r.tipo_consumo, t.id as turma_id
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.cardapio_id = ? AND r.status != 'CANCELADA'
        """
        params = [cardapio_id]
        
        if turma_id:
            query += " AND t.id = ?"
            params.append(turma_id)
        if status_filter:
            query += " AND r.status = ?"
            params.append(status_filter)
        if tipo_consumo_filter:
            if tipo_consumo_filter == 'NORMAL':
                query += " AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL)"
            else:
                query += " AND r.tipo_consumo = ?"
                params.append(tipo_consumo_filter)
            
        query += " ORDER BY a.nome ASC"
        
        # Total para os filtros atuais
        count_query = f"SELECT COUNT(*) FROM ({query})"
        total = conn.execute(count_query, params).fetchone()[0]

        # Paginação
        pagina = request.args.get('page', 1, type=int)
        offset = (pagina - 1) * RELATORIO_POR_PAGINA
        
        # Total para os filtros atuais
        count_query = f"SELECT COUNT(*) FROM ({query})"
        total = conn.execute(count_query, params).fetchone()[0]
        
        query += f" LIMIT {RELATORIO_POR_PAGINA} OFFSET {offset}"
        reservas = conn.execute(query, params).fetchall()
        
        total_paginas = max(1, (total + RELATORIO_POR_PAGINA - 1) // RELATORIO_POR_PAGINA)
        
        # Dados para Filtros e Resumo
        turmas = conn.execute("SELECT * FROM turmas ORDER BY nome ASC").fetchall()
        
        # Cálculo de Resumo por Turma (Consolidado)
        resumo_query = """
            SELECT t.nome as turma_nome, 
                   SUM(CASE WHEN (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL) THEN 1 ELSE 0 END) as total,
                   SUM(CASE WHEN r.status = 'CONSUMIDA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL) THEN 1 ELSE 0 END) as consumidas_normais,
                   SUM(CASE WHEN r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EVENTO' THEN 1 ELSE 0 END) as consumidas_eventos,
                   SUM(CASE WHEN r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EXTRA' THEN 1 ELSE 0 END) as consumidas_extras
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.cardapio_id = ? AND r.status != 'CANCELADA'
            GROUP BY t.id
            ORDER BY t.nome ASC
        """
        resumo_turmas = conn.execute(resumo_query, (cardapio_id,)).fetchall()
        
        # Totais Globais (Sem Paginação) para os cards do topo (Respeitando filtros de turma/status)
        totais_query = """
            SELECT 
                SUM(CASE WHEN r.status = 'ATIVA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL) THEN 1 ELSE 0 END) as total_ativas,
                SUM(CASE WHEN r.status = 'CONSUMIDA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL) THEN 1 ELSE 0 END) as consumidas_normal,
                SUM(CASE WHEN r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EVENTO' THEN 1 ELSE 0 END) as consumidas_evento,
                SUM(CASE WHEN r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EXTRA' THEN 1 ELSE 0 END) as consumidas_extra
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.cardapio_id = ? AND r.status != 'CANCELADA'
        """
        params_totais = [cardapio_id]
        if turma_id:
            totais_query += " AND t.id = ?"
            params_totais.append(turma_id)
        
        row_totais = conn.execute(totais_query, params_totais).fetchone()
        total_ativas = row_totais['total_ativas'] or 0
        consumidas_normal = row_totais['consumidas_normal'] or 0
        consumidas_evento = row_totais['consumidas_evento'] or 0
        consumidas_extra = row_totais['consumidas_extra'] or 0
        
        total_consumidas = consumidas_normal + consumidas_evento + consumidas_extra
        total_geral = total_ativas + consumidas_normal
        total_sobras = total_ativas
        
    return render_template('admin/relatorio_dia.html', 
                           cardapio=cardapio, 
                           reservas=reservas, 
                           total_geral=total_geral, 
                           total_consumidas=total_consumidas,
                           consumidas_normal=consumidas_normal,
                           consumidas_evento=consumidas_evento,
                           consumidas_extra=consumidas_extra,
                           total_sobras=total_sobras,
                           turmas=turmas,
                           resumo_turmas=resumo_turmas,
                           filtro_turma=turma_id,
                           filtro_status=status_filter,
                           filtro_tipo=tipo_consumo_filter,
                           pagina=pagina,
                           total_paginas=total_paginas,
                           total=total)

@admin_bp.route('/admin/relatorios/<int:cardapio_id>/imprimir')
def admin_relatorio_dia_imprimir(cardapio_id):
    """Página dedicada para impressão oficial do relatório diário de refeições."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))
    
    turma_id = request.args.get('turma_id', type=int)
    status_filter = request.args.get('status')
    tipo_consumo_filter = request.args.get('tipo_consumo')
    
    with closing(get_db_connection()) as conn:
        cardapio = conn.execute("SELECT * FROM cardapios WHERE id = ?", (cardapio_id,)).fetchone()
        if not cardapio:
            flash('Cardápio não encontrado.', 'error')
            return redirect(url_for('admin.admin_relatorios'))
            
        query = """
            SELECT a.nome, a.matricula, a.restricoes, t.nome as turma_nome, r.status, r.tipo_consumo, t.id as turma_id
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.cardapio_id = ? AND r.status != 'CANCELADA'
        """
        params = [cardapio_id]
        
        if turma_id:
            query += " AND t.id = ?"
            params.append(turma_id)
        if status_filter:
            query += " AND r.status = ?"
            params.append(status_filter)
        if tipo_consumo_filter:
            if tipo_consumo_filter == 'NORMAL':
                query += " AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL)"
            else:
                query += " AND r.tipo_consumo = ?"
                params.append(tipo_consumo_filter)
            
        query += " ORDER BY a.nome ASC"
        reservas = conn.execute(query, params).fetchall()
        total = len(reservas)
        
        # Resumo por Turma
        resumo_query = """
            SELECT t.nome as turma_nome, 
                   SUM(CASE WHEN (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL) THEN 1 ELSE 0 END) as total,
                   SUM(CASE WHEN r.status = 'CONSUMIDA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL) THEN 1 ELSE 0 END) as consumidas_normais,
                   SUM(CASE WHEN r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EVENTO' THEN 1 ELSE 0 END) as consumidas_eventos,
                   SUM(CASE WHEN r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EXTRA' THEN 1 ELSE 0 END) as consumidas_extras
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.cardapio_id = ? AND r.status != 'CANCELADA'
            GROUP BY t.id
            ORDER BY t.nome ASC
        """
        resumo_turmas = conn.execute(resumo_query, (cardapio_id,)).fetchall()
        
        # Totais Globais
        totais_query = """
            SELECT 
                SUM(CASE WHEN r.status = 'ATIVA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL) THEN 1 ELSE 0 END) as total_ativas,
                SUM(CASE WHEN r.status = 'CONSUMIDA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL) THEN 1 ELSE 0 END) as consumidas_normal,
                SUM(CASE WHEN r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EVENTO' THEN 1 ELSE 0 END) as consumidas_evento,
                SUM(CASE WHEN r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EXTRA' THEN 1 ELSE 0 END) as consumidas_extra
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.cardapio_id = ? AND r.status != 'CANCELADA'
        """
        params_totais = [cardapio_id]
        if turma_id:
            totais_query += " AND t.id = ?"
            params_totais.append(turma_id)
            
        row_totais = conn.execute(totais_query, params_totais).fetchone()
        total_ativas = row_totais['total_ativas'] or 0
        consumidas_normal = row_totais['consumidas_normal'] or 0
        consumidas_evento = row_totais['consumidas_evento'] or 0
        consumidas_extra = row_totais['consumidas_extra'] or 0
        
        total_consumidas = consumidas_normal + consumidas_evento + consumidas_extra
        total_geral = total_ativas + consumidas_normal
        total_sobras = total_ativas
        
        data_emissao = datetime.now().strftime('%d/%m/%Y às %H:%M')
        config = get_config()
        admin_user = session.get('admin_usuario', 'admin')
        adm_row = conn.execute("SELECT nome FROM administradores WHERE usuario = ?", (admin_user,)).fetchone()
        emissor_nome = (adm_row['nome'] if (adm_row and adm_row['nome']) else None) or session.get('admin_nome') or admin_user
        
    return render_template('admin/relatorio_dia_imprimir.html',
                           cardapio=cardapio,
                           reservas=reservas,
                           total_geral=total_geral,
                           total_consumidas=total_consumidas,
                           consumidas_normal=consumidas_normal,
                           consumidas_evento=consumidas_evento,
                           consumidas_extra=consumidas_extra,
                           total_sobras=total_sobras,
                           resumo_turmas=resumo_turmas,
                           total=total,
                           data_emissao=data_emissao,
                           emissor_nome=emissor_nome,
                           config=config)


@admin_bp.route('/admin/relatorios/<int:cardapio_id>/excel')
def admin_relatorio_excel(cardapio_id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))
    
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    
    # Border styles
    thin_side = Side(style='thin', color='D3D3D3')
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    
    with closing(get_db_connection()) as conn:
        cardapio = conn.execute("SELECT * FROM cardapios WHERE id = ?", (cardapio_id,)).fetchone()
        reservas = conn.execute("""
            SELECT a.nome, a.matricula, a.restricoes, t.nome as turma_nome, r.status, r.tipo_consumo
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE r.cardapio_id = ? AND r.status != 'CANCELADA'
            ORDER BY t.nome, a.nome ASC
        """, (cardapio_id,)).fetchall()
        
    wb = Workbook()
    ws = wb.active
    ws.title = "Relatorio de Refeicoes"
    
    # Ensure Excel grid lines are visible
    ws.views.sheetView[0].showGridLines = True
    
    # Cabeçalho
    config = get_config()
    
    # Title row
    ws['A1'] = f"RELATÓRIO DE CONSUMO — {config['sigla_instituicao']}"
    ws['A1'].font = Font(name='Segoe UI', bold=True, size=14, color='2F9E41')
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A1:F1')
    ws.row_dimensions[1].height = 35
    
    # Subtitle data row
    try:
        data_fmt = datetime.strptime(cardapio['data'], '%Y-%m-%d').strftime('%d/%m/%Y')
    except:
        data_fmt = cardapio['data']
        
    ws['A2'] = f"Data da Distribuição: {data_fmt} | Cardápio: {cardapio['descricao']}"
    ws['A2'].font = Font(name='Segoe UI', italic=True, size=10, color='6B7280')
    ws['A2'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A2:F2')
    ws.row_dimensions[2].height = 20
    
    # Tabela headers
    headers = ["Estudante", "Matrícula", "Turma", "Situação", "Tipo", "Obser. Dieta"]
    ws.append([]) # Row 3 empty
    ws.append(headers) # Row 4
    ws.row_dimensions[4].height = 26
    
    header_fill = PatternFill(start_color="2F9E41", end_color="2F9E41", fill_type="solid")
    header_font = Font(name='Segoe UI', bold=True, color='FFFFFF', size=11)
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='center')
    
    for col_idx in range(1, 7):
        cell = ws.cell(row=4, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align if col_idx in (2, 4, 5) else left_align
        cell.border = thin_border
        
    row_idx = 5
    zebra_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
    for r in reservas:
        status_txt = "Entregue" if r['status'] == 'CONSUMIDA' else "Pendente"
        if r['tipo_consumo'] == 'EXTRA':
            tipo_txt = "Sobra/Extra"
        elif r['tipo_consumo'] == 'EVENTO':
            tipo_txt = "Evento"
        else:
            tipo_txt = "Reserva Normal"
        ws.append([r['nome'], r['matricula'], r['turma_nome'] or "---", status_txt, tipo_txt, r['restricoes'] or "---"])
        ws.row_dimensions[row_idx].height = 20
        
        # Style row data
        for col_idx in range(1, 7):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(name='Segoe UI', size=10)
            cell.border = thin_border
            cell.alignment = center_align if col_idx in (2, 4, 5) else left_align
            if row_idx % 2 == 0:
                cell.fill = zebra_fill
        row_idx += 1
        
    from openpyxl.utils import get_column_letter
    for col in ws.columns:
        max_len = 0
        for cell in col:
            # Skip title, subtitle, and empty rows
            if cell.row in (1, 2, 3):
                continue
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
        
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    filename = f"Relatorio_Refeicao_{cardapio['data']}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )

@admin_bp.route('/admin/auditoria')
def admin_auditoria():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not (tem_permissao('all') or tem_permissao('admins')):
        return redirect(url_for('admin.admin_dashboard'))
    
    busca = request.args.get('q', '').strip()
    data_inicio = request.args.get('data_inicio', '').strip()
    data_fim = request.args.get('data_fim', '').strip()
    pagina = request.args.get('page', 1, type=int)
    offset = (pagina - 1) * RELATORIO_POR_PAGINA
    
    with closing(get_db_connection()) as conn:
        query = "SELECT * FROM logs_auditoria"
        conditions = []
        params = []
        
        if busca:
            conditions.append("(usuario LIKE ? OR acao LIKE ? OR detalhes LIKE ?)")
            like = f"%{busca}%"
            params.extend([like, like, like])
        if data_inicio:
            conditions.append("data_criacao >= ?")
            params.append(f"{data_inicio} 00:00:00")
        if data_fim:
            conditions.append("data_criacao <= ?")
            params.append(f"{data_fim} 23:59:59")
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        total_query = f"SELECT COUNT(*) FROM ({query})"
        total = conn.execute(total_query, params).fetchone()[0]
        
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([RELATORIO_POR_PAGINA, offset])
        logs = conn.execute(query, params).fetchall()
        
    total_paginas = max(1, (total + RELATORIO_POR_PAGINA - 1) // RELATORIO_POR_PAGINA)
    
    return render_template('admin/auditoria.html',
                           logs=logs,
                           busca=busca,
                           data_inicio=data_inicio,
                           data_fim=data_fim,
                           pagina=pagina,
                           total_paginas=total_paginas,
                           total=total)

@admin_bp.route('/admin/api/relatorios/estudantes/buscar')
def api_relatorios_estudantes_buscar():
    if not is_logged_in_admin():
        return {"success": False, "message": "Não autorizado"}, 401
    q = request.args.get('q', '').strip()
    turma_id = request.args.get('turma_id', '').strip()
    if not q and not turma_id:
        return {"success": True, "alunos": []}
    with closing(get_db_connection()) as conn:
        from utils.services import buscar_estudantes_frequencia
        alunos = buscar_estudantes_frequencia(conn, q, turma_id)
    return {"success": True, "alunos": alunos}

@admin_bp.route('/admin/api/relatorios/estudante/<int:aluno_id>')
def api_relatorios_estudante_detalhes(aluno_id):
    if not is_logged_in_admin():
        return {"success": False, "message": "Não autorizado"}, 401
    with closing(get_db_connection()) as conn:
        from utils.services import obter_detalhes_frequencia_estudante
        detalhes = obter_detalhes_frequencia_estudante(conn, aluno_id)
    if not detalhes:
        return {"success": False, "message": "Estudante não encontrado"}, 404
    return {"success": True, **detalhes}

@admin_bp.route('/admin/api/relatorios/sem_atividade')
def api_relatorios_sem_atividade():
    if not is_logged_in_admin():
        return {"success": False, "message": "Não autorizado"}, 401
    with closing(get_db_connection()) as conn:
        from utils.services import obter_alunos_sem_consumo, obter_alunos_sem_reserva
        nunca_consumiram = obter_alunos_sem_consumo(conn)
        nunca_reservaram = obter_alunos_sem_reserva(conn)
    return {
        "success": True,
        "nunca_consumiram": nunca_consumiram,
        "nunca_reservaram": nunca_reservaram
    }

@admin_bp.route('/admin/api/relatorios/restricao')
def api_relatorios_restricao_detalhe():
    """Retorna os alunos que possuem uma determinada restrição alimentar."""
    if not is_logged_in_admin():
        return {"success": False, "message": "Não autorizado"}, 401
    tipo = request.args.get('tipo', '')
    if not tipo:
        return {"success": False, "message": "Tipo de restrição não informado"}, 400
    with closing(get_db_connection()) as conn:
        alunos = conn.execute("""
            SELECT a.nome, a.matricula, a.restricoes, t.nome as turma_nome
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE a.restricoes = ?
              AND a.turma_id IS NOT NULL
              AND (t.is_evento = 0 OR t.is_evento IS NULL)
            ORDER BY a.nome ASC
        """, (tipo,)).fetchall()
    return {"success": True, "tipo": tipo, "alunos": [dict(a) for a in alunos]}

@admin_bp.route('/admin/relatorios/inativos/exportar')
def admin_relatorios_inativos_exportar():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))
    
    tipo = request.args.get('tipo', 'consumo') # consumo | reserva
    
    with closing(get_db_connection()) as conn:
        from utils.services import obter_alunos_sem_consumo, obter_alunos_sem_reserva
        if tipo == 'consumo':
            alunos = obter_alunos_sem_consumo(conn)
            titulo = "Estudantes que Nunca Consumiram"
            filename = "Estudantes_Sem_Consumo.xlsx"
        else:
            alunos = obter_alunos_sem_reserva(conn)
            titulo = "Estudantes que Nunca Reservaram"
            filename = "Estudantes_Sem_Reserva.xlsx"
            
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    
    # Border styles
    thin_side = Side(style='thin', color='D3D3D3')
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Alunos Inativos"
    
    # Ensure Excel grid lines are visible
    ws.views.sheetView[0].showGridLines = True
    
    config = get_config()
    
    # Title row
    ws['A1'] = f"{titulo.upper()}"
    ws['A1'].font = Font(name='Segoe UI', bold=True, size=14, color='2F9E41')
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A1:C1')
    ws.row_dimensions[1].height = 35
    
    # Subtitle info row
    ws['A2'] = f"Instituição: {config['sigla_instituicao']} | Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws['A2'].font = Font(name='Segoe UI', italic=True, size=10, color='6B7280')
    ws['A2'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A2:C2')
    ws.row_dimensions[2].height = 20
    
    # Table headers row
    headers = ["Estudante", "Matrícula", "Turma"]
    ws.append(headers) # A3, B3, C3
    ws.row_dimensions[3].height = 26
    
    header_fill = PatternFill(start_color="2F9E41", end_color="2F9E41", fill_type="solid")
    header_font = Font(name='Segoe UI', bold=True, color='FFFFFF', size=11)
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='center')
    
    for col_idx in range(1, 4):
        cell = ws.cell(row=3, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align if col_idx > 1 else left_align
        cell.border = thin_border
        
    row_idx = 4
    zebra_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
    for a in alunos:
        ws.append([a['nome'], a['matricula'], a['turma_nome'] or "Sem turma"])
        ws.row_dimensions[row_idx].height = 20
        
        # Style row data
        for col_idx in range(1, 4):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(name='Segoe UI', size=10)
            cell.border = thin_border
            cell.alignment = center_align if col_idx > 1 else left_align
            if row_idx % 2 == 0:
                cell.fill = zebra_fill
        row_idx += 1
        
    # Auto-adjust column widths
    from openpyxl.utils import get_column_letter
    for col in ws.columns:
        max_len = 0
        for cell in col:
            # Skip title and subtitle row length checks
            if cell.row in (1, 2):
                continue
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
        
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


CANCELAMENTOS_POR_PAGINA = 30

@admin_bp.route('/admin/relatorios/cancelamentos')
def admin_relatorios_cancelamentos():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))
    
    data_inicio = request.args.get('data_inicio', '').strip()
    data_fim = request.args.get('data_fim', '').strip()
    origem = request.args.get('origem', 'TODOS').strip()
    turma_id = request.args.get('turma_id', '', type=str).strip()
    busca = request.args.get('q', '').strip()
    pagina = request.args.get('page', 1, type=int)
    offset = (pagina - 1) * CANCELAMENTOS_POR_PAGINA

    with closing(get_db_connection()) as conn:
        turmas = conn.execute("SELECT id, nome FROM turmas ORDER BY nome ASC").fetchall()
        
        where_clauses = ["r.status = 'CANCELADA'"]
        params = []
        
        if data_inicio:
            where_clauses.append("c.data >= ?")
            params.append(data_inicio)
        if data_fim:
            where_clauses.append("c.data <= ?")
            params.append(data_fim)
            
        if origem == 'ALUNO':
            where_clauses.append("(r.cancelado_por = 'ALUNO' OR r.cancelado_por IS NULL OR r.cancelado_por = '')")
        elif origem == 'ADMIN':
            where_clauses.append("r.cancelado_por LIKE 'ADMIN%'")
            
        if turma_id and turma_id.isdigit():
            where_clauses.append("a.turma_id = ?")
            params.append(int(turma_id))
            
        if busca:
            like = f"%{busca}%"
            where_clauses.append("(a.nome LIKE ? OR a.matricula LIKE ? OR r.motivo_cancelamento LIKE ? OR r.codigo_unico LIKE ?)")
            params.extend([like, like, like, like])
            
        where_sql = " AND ".join(where_clauses)
        
        kpi_total = conn.execute(f"""
            SELECT COUNT(*) FROM reservas r 
            JOIN alunos a ON r.aluno_id = a.id
            JOIN cardapios c ON r.cardapio_id = c.id
            WHERE {where_sql}
        """, params).fetchone()[0]

        kpi_aluno = conn.execute(f"""
            SELECT COUNT(*) FROM reservas r 
            JOIN alunos a ON r.aluno_id = a.id
            JOIN cardapios c ON r.cardapio_id = c.id
            WHERE {where_sql} AND (r.cancelado_por = 'ALUNO' OR r.cancelado_por IS NULL OR r.cancelado_por = '')
        """, params).fetchone()[0]

        kpi_admin = conn.execute(f"""
            SELECT COUNT(*) FROM reservas r 
            JOIN alunos a ON r.aluno_id = a.id
            JOIN cardapios c ON r.cardapio_id = c.id
            WHERE {where_sql} AND r.cancelado_por LIKE 'ADMIN%'
        """, params).fetchone()[0]
        
        total_paginas = max(1, (kpi_total + CANCELAMENTOS_POR_PAGINA - 1) // CANCELAMENTOS_POR_PAGINA)
        
        query_rows = f"""
            SELECT r.id, r.codigo_unico, r.motivo_cancelamento, r.cancelado_por, 
                   r.data_cancelamento, r.data_registro, r.status,
                   a.id as aluno_id, a.nome as aluno_nome, a.matricula as aluno_mat,
                   t.nome as turma_nome,
                   c.id as cardapio_id, c.data as cardapio_data, c.tipo_refeicao, c.descricao as cardapio_descricao
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            JOIN cardapios c ON r.cardapio_id = c.id
            WHERE {where_sql}
            ORDER BY COALESCE(r.data_cancelamento, c.data) DESC, r.id DESC
            LIMIT ? OFFSET ?
        """
        cancelamentos = conn.execute(query_rows, params + [CANCELAMENTOS_POR_PAGINA, offset]).fetchall()

    return render_template(
        'admin/relatorios_cancelamentos.html',
        cancelamentos=cancelamentos,
        turmas=turmas,
        data_inicio=data_inicio,
        data_fim=data_fim,
        origem=origem,
        turma_id=turma_id,
        busca=busca,
        pagina=pagina,
        total_paginas=total_paginas,
        kpi_total=kpi_total,
        kpi_aluno=kpi_aluno,
        kpi_admin=kpi_admin
    )

@admin_bp.route('/admin/relatorios/cancelamentos/excel')
def admin_relatorios_cancelamentos_excel():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))
    
    data_inicio = request.args.get('data_inicio', '').strip()
    data_fim = request.args.get('data_fim', '').strip()
    origem = request.args.get('origem', 'TODOS').strip()
    turma_id = request.args.get('turma_id', '', type=str).strip()
    busca = request.args.get('q', '').strip()

    with closing(get_db_connection()) as conn:
        where_clauses = ["r.status = 'CANCELADA'"]
        params = []
        
        if data_inicio:
            where_clauses.append("c.data >= ?")
            params.append(data_inicio)
        if data_fim:
            where_clauses.append("c.data <= ?")
            params.append(data_fim)
            
        if origem == 'ALUNO':
            where_clauses.append("(r.cancelado_por = 'ALUNO' OR r.cancelado_por IS NULL OR r.cancelado_por = '')")
        elif origem == 'ADMIN':
            where_clauses.append("r.cancelado_por LIKE 'ADMIN%'")
            
        if turma_id and turma_id.isdigit():
            where_clauses.append("a.turma_id = ?")
            params.append(int(turma_id))
            
        if busca:
            like = f"%{busca}%"
            where_clauses.append("(a.nome LIKE ? OR a.matricula LIKE ? OR r.motivo_cancelamento LIKE ? OR r.codigo_unico LIKE ?)")
            params.extend([like, like, like, like])
            
        where_sql = " AND ".join(where_clauses)
        
        query_rows = f"""
            SELECT r.id, r.codigo_unico, r.motivo_cancelamento, r.cancelado_por, 
                   r.data_cancelamento, r.data_registro,
                   a.nome as aluno_nome, a.matricula as aluno_mat,
                   t.nome as turma_nome,
                   c.data as cardapio_data, c.tipo_refeicao, c.descricao as cardapio_descricao
            FROM reservas r
            JOIN alunos a ON r.aluno_id = a.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            JOIN cardapios c ON r.cardapio_id = c.id
            WHERE {where_sql}
            ORDER BY COALESCE(r.data_cancelamento, c.data) DESC, r.id DESC
        """
        registros = conn.execute(query_rows, params).fetchall()

    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Cancelamentos"
    ws.views.sheetView[0].showGridLines = True

    config = get_config()
    thin_side = Side(style='thin', color='D3D3D3')
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    ws['A1'] = "RELATÓRIO DE RESERVAS CANCELADAS"
    ws['A1'].font = Font(name='Segoe UI', bold=True, size=14, color='DC2626')
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A1:H1')
    ws.row_dimensions[1].height = 35

    sub = f"Instituição: {config['sigla_instituicao']} | Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    if data_inicio or data_fim:
        sub += f" | Período: {data_inicio or 'Início'} até {data_fim or 'Hoje'}"
    if origem != 'TODOS':
        sub += f" | Origem: {origem}"
    ws['A2'] = sub
    ws['A2'].font = Font(name='Segoe UI', italic=True, size=10, color='6B7280')
    ws['A2'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A2:H2')
    ws.row_dimensions[2].height = 20

    headers = [
        "Data Refeição", "Tipo", "Estudante", "Matrícula", 
        "Turma", "Cancelado Por", "Data do Cancelamento", "Motivo do Cancelamento"
    ]
    ws.append(headers)
    ws.row_dimensions[3].height = 26

    header_fill = PatternFill(start_color="DC2626", end_color="DC2626", fill_type="solid")
    header_font = Font(name='Segoe UI', bold=True, color='FFFFFF', size=11)
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='center')

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=3, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border

    zebra_fill = PatternFill(start_color="FFF5F5", end_color="FFF5F5", fill_type="solid")
    row_idx = 4
    for r in registros:
        ws.append([
            r['cardapio_data'] or '—',
            r['tipo_refeicao'] or 'Almoço',
            r['aluno_nome'] or '—',
            r['aluno_mat'] or '—',
            r['turma_nome'] or 'Sem turma',
            r['cancelado_por'] or 'ALUNO',
            r['data_cancelamento'] or '—',
            r['motivo_cancelamento'] or '—'
        ])
        ws.row_dimensions[row_idx].height = 22
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(name='Segoe UI', size=10)
            cell.border = thin_border
            cell.alignment = center_align if col_idx in (1, 2, 4, 6, 7) else left_align
            if row_idx % 2 == 0:
                cell.fill = zebra_fill
        row_idx += 1

    for col in ws.columns:
        max_len = 0
        for cell in col:
            if cell.row in (1, 2):
                continue
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"Relatorio_Cancelamentos_{timestamp}.xlsx"
    )


@admin_bp.route('/admin/relatorios/fornecedor')
def admin_relatorios_fornecedor():
    """Relatório semanal de pedidos e demandas para acionamento do fornecedor de alimentação."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))

    semana_opcao = request.args.get('semana', 'atual')  # 'atual', 'proxima', 'custom'
    data_inicio_custom = request.args.get('data_inicio', '').strip()

    hoje = datetime.now().date()
    if data_inicio_custom:
        try:
            data_base = datetime.strptime(data_inicio_custom, '%Y-%m-%d').date()
            semana_opcao = 'custom'
        except:
            data_base = hoje
    elif semana_opcao == 'proxima':
        data_base = hoje + timedelta(days=7)
    else:
        data_base = hoje

    # Segunda-feira da semana de referência
    segunda_feira = data_base - timedelta(days=data_base.weekday())
    sexta_feira = segunda_feira + timedelta(days=4)

    DIAS_NOMES = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    dias_semana = []
    total_refeicoes_semana = 0
    total_normais_semana = 0
    total_extras_semana = 0
    total_eventos_semana = 0
    total_canceladas_semana = 0
    dias_fechados_count = 0
    dias_abertos_count = 0
    restricoes_consolidadas = {}

    with closing(get_db_connection()) as conn:
        for i in range(7):
            dia_date = segunda_feira + timedelta(days=i)
            dia_str = dia_date.strftime('%Y-%m-%d')
            dia_nome = DIAS_NOMES[i]

            cardapio = conn.execute(
                "SELECT * FROM cardapios WHERE data = ?", (dia_str,)
            ).fetchone()

            if i >= 5 and not cardapio:
                continue

            janela = calcular_janela_reserva(dia_str, conn=conn)

            total_normais = 0
            total_extras = 0
            total_eventos = 0
            total_canceladas = 0
            restricoes_dia = []

            if cardapio:
                normais_row = conn.execute("""
                    SELECT COUNT(*) as qtd FROM reservas
                    WHERE cardapio_id = ? AND status != 'CANCELADA' AND (tipo_consumo = 'NORMAL' OR tipo_consumo IS NULL)
                """, (cardapio['id'],)).fetchone()
                total_normais = normais_row['qtd'] if normais_row else 0

                extras_row = conn.execute("""
                    SELECT COUNT(*) as qtd FROM reservas
                    WHERE cardapio_id = ? AND status != 'CANCELADA' AND tipo_consumo = 'EXTRA'
                """, (cardapio['id'],)).fetchone()
                total_extras = extras_row['qtd'] if extras_row else 0

                eventos_row = conn.execute("""
                    SELECT COUNT(*) as qtd FROM reservas
                    WHERE cardapio_id = ? AND status != 'CANCELADA' AND tipo_consumo = 'EVENTO'
                """, (cardapio['id'],)).fetchone()
                total_eventos = eventos_row['qtd'] if eventos_row else 0

                cancel_row = conn.execute("""
                    SELECT COUNT(*) as qtd FROM reservas
                    WHERE cardapio_id = ? AND status = 'CANCELADA'
                """, (cardapio['id'],)).fetchone()
                total_canceladas = cancel_row['qtd'] if cancel_row else 0

                restricoes_rows = conn.execute("""
                    SELECT a.restricoes, COUNT(*) as qtd
                    FROM reservas r
                    JOIN alunos a ON r.aluno_id = a.id
                    WHERE r.cardapio_id = ? AND r.status != 'CANCELADA'
                      AND a.restricoes IS NOT NULL AND TRIM(a.restricoes) != ''
                    GROUP BY a.restricoes
                    ORDER BY qtd DESC
                """, (cardapio['id'],)).fetchall()

                for r in restricoes_rows:
                    restricoes_dia.append({
                        'restricao': r['restricoes'],
                        'qtd': r['qtd']
                    })
                    restricoes_consolidadas[r['restricoes']] = restricoes_consolidadas.get(r['restricoes'], 0) + r['qtd']

            total_dia = total_normais + total_extras + total_eventos
            total_refeicoes_semana += total_dia
            total_normais_semana += total_normais
            total_extras_semana += total_extras
            total_eventos_semana += total_eventos
            total_canceladas_semana += total_canceladas

            if janela['status'] == 'ENCERRADA':
                dias_fechados_count += 1
            elif janela['status'] == 'ABERTA':
                dias_abertos_count += 1

            dias_semana.append({
                'data': dia_str,
                'data_fmt': dia_date.strftime('%d/%m/%Y'),
                'dia_curto': dia_date.strftime('%d/%m'),
                'dia_nome': dia_nome,
                'dia_semana_num': i,
                'tem_cardapio': cardapio is not None,
                'cardapio': cardapio,
                'janela': janela,
                'total_normais': total_normais,
                'total_extras': total_extras,
                'total_eventos': total_eventos,
                'total_confirmadas': total_dia,
                'total_canceladas': total_canceladas,
                'restricoes': restricoes_dia
            })

    config = get_config()
    sigla = config.get('sigla_instituicao', 'IFRN')
    segunda_fmt = segunda_feira.strftime('%d/%m/%Y')
    fim_fmt = (dias_semana[-1]['data_fmt']) if dias_semana else sexta_feira.strftime('%d/%m/%Y')

    texto_whatsapp = [
        f"📋 *PEDIDO DE ALMOÇO AO FORNECEDOR — {sigla}*",
        f"📅 *Semana:* {segunda_fmt} a {fim_fmt}",
        f"🍽️ *Total Previsto da Semana:* {total_refeicoes_semana} refeições\n"
    ]

    for d in dias_semana:
        if not d['tem_cardapio']:
            texto_whatsapp.append(f"• *{d['dia_nome']} ({d['dia_curto']})*: Sem refeição programada.")
            continue
        
        status_txt = "🔴 Prazo Encerrado" if d['janela']['status'] == 'ENCERRADA' else ("🟢 Reservas Abertas" if d['janela']['status'] == 'ABERTA' else "🟡 Não Iniciada")
        corte_txt = f" (Corte: {d['janela']['fechamento_formatado']})" if d['janela']['fechamento_formatado'] != '—' else ""
        linha = f"• *{d['dia_nome']} ({d['dia_curto']})*: *{d['total_confirmadas']} refeições* [{status_txt}{corte_txt}]"
        if d['total_extras'] > 0:
            linha += f" (inclui {d['total_extras']} extras)"
        if d['restricoes']:
            restr_list = ", ".join([f"{r['qtd']}x {r['restricao']}" for r in d['restricoes']])
            linha += f"\n   ↳ Restrições: {restr_list}"
        texto_whatsapp.append(linha)

    if restricoes_consolidadas:
        texto_whatsapp.append("\n🥗 *Total de Restrições na Semana:*")
        for restr, qtd in sorted(restricoes_consolidadas.items(), key=lambda x: x[1], reverse=True):
            texto_whatsapp.append(f"  - {restr}: {qtd} porções")

    texto_whatsapp.append(f"\n_Gerado pelo sistema em {datetime.now().strftime('%d/%m/%Y às %H:%M')}_")
    msg_whatsapp_pronta = "\n".join(texto_whatsapp)

    return render_template(
        'admin/relatorios_fornecedor.html',
        semana_opcao=semana_opcao,
        segunda_feira=segunda_feira.strftime('%Y-%m-%d'),
        data_inicio_custom=data_inicio_custom,
        segunda_fmt=segunda_fmt,
        fim_fmt=fim_fmt,
        dias_semana=dias_semana,
        total_refeicoes_semana=total_refeicoes_semana,
        total_normais_semana=total_normais_semana,
        total_extras_semana=total_extras_semana,
        total_eventos_semana=total_eventos_semana,
        total_canceladas_semana=total_canceladas_semana,
        dias_fechados_count=dias_fechados_count,
        dias_abertos_count=dias_abertos_count,
        restricoes_consolidadas=restricoes_consolidadas,
        msg_whatsapp_pronta=msg_whatsapp_pronta
    )


@admin_bp.route('/admin/relatorios/fornecedor/excel')
def admin_relatorios_fornecedor_excel():
    """Exporta para Excel o pedido semanal detalhado para o fornecedor."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('relatorios'): return redirect(url_for('admin.admin_dashboard'))

    semana_opcao = request.args.get('semana', 'atual')
    data_inicio_custom = request.args.get('data_inicio', '').strip()

    hoje = datetime.now().date()
    if data_inicio_custom:
        try:
            data_base = datetime.strptime(data_inicio_custom, '%Y-%m-%d').date()
        except:
            data_base = hoje
    elif semana_opcao == 'proxima':
        data_base = hoje + timedelta(days=7)
    else:
        data_base = hoje

    segunda_feira = data_base - timedelta(days=data_base.weekday())
    DIAS_NOMES = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    dias_semana = []
    with closing(get_db_connection()) as conn:
        for i in range(7):
            dia_date = segunda_feira + timedelta(days=i)
            dia_str = dia_date.strftime('%Y-%m-%d')
            cardapio = conn.execute("SELECT * FROM cardapios WHERE data = ?", (dia_str,)).fetchone()
            if i >= 5 and not cardapio:
                continue

            janela = calcular_janela_reserva(dia_str, conn=conn)
            total_normais = 0
            total_extras = 0
            total_eventos = 0
            total_canceladas = 0
            restricoes_str = "—"

            if cardapio:
                normais_row = conn.execute("""
                    SELECT COUNT(*) as qtd FROM reservas
                    WHERE cardapio_id = ? AND status != 'CANCELADA' AND (tipo_consumo = 'NORMAL' OR tipo_consumo IS NULL)
                """, (cardapio['id'],)).fetchone()
                total_normais = normais_row['qtd'] if normais_row else 0

                extras_row = conn.execute("""
                    SELECT COUNT(*) as qtd FROM reservas
                    WHERE cardapio_id = ? AND status != 'CANCELADA' AND tipo_consumo = 'EXTRA'
                """, (cardapio['id'],)).fetchone()
                total_extras = extras_row['qtd'] if extras_row else 0

                eventos_row = conn.execute("""
                    SELECT COUNT(*) as qtd FROM reservas
                    WHERE cardapio_id = ? AND status != 'CANCELADA' AND tipo_consumo = 'EVENTO'
                """, (cardapio['id'],)).fetchone()
                total_eventos = eventos_row['qtd'] if eventos_row else 0

                cancel_row = conn.execute("""
                    SELECT COUNT(*) as qtd FROM reservas
                    WHERE cardapio_id = ? AND status = 'CANCELADA'
                """, (cardapio['id'],)).fetchone()
                total_canceladas = cancel_row['qtd'] if cancel_row else 0

                restricoes_rows = conn.execute("""
                    SELECT a.restricoes, COUNT(*) as qtd
                    FROM reservas r
                    JOIN alunos a ON r.aluno_id = a.id
                    WHERE r.cardapio_id = ? AND r.status != 'CANCELADA'
                      AND a.restricoes IS NOT NULL AND TRIM(a.restricoes) != ''
                    GROUP BY a.restricoes
                    ORDER BY qtd DESC
                """, (cardapio['id'],)).fetchall()
                if restricoes_rows:
                    restricoes_str = ", ".join([f"{r['qtd']}x {r['restricoes']}" for r in restricoes_rows])

            dias_semana.append({
                'data': dia_str,
                'data_fmt': dia_date.strftime('%d/%m/%Y'),
                'dia_nome': DIAS_NOMES[i],
                'descricao': cardapio['descricao'] if cardapio else 'Sem cardápio cadastrado',
                'tipo_refeicao': cardapio['tipo_refeicao'] if cardapio else '—',
                'status_janela': 'Encerrada' if janela['status'] == 'ENCERRADA' else ('Aberta' if janela['status'] == 'ABERTA' else 'Não Iniciada'),
                'fechamento_fmt': janela['fechamento_formatado'],
                'normais': total_normais,
                'extras': total_extras,
                'eventos': total_eventos,
                'total': total_normais + total_extras + total_eventos,
                'canceladas': total_canceladas,
                'restricoes': restricoes_str
            })

    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Pedido Fornecedor"
    ws.views.sheetView[0].showGridLines = True

    config = get_config()
    thin_side = Side(style='thin', color='D3D3D3')
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    ws['A1'] = f"PEDIDO DE REFEIÇÕES AO FORNECEDOR — {config['sigla_instituicao']}"
    ws['A1'].font = Font(name='Segoe UI', bold=True, size=14, color='1E40AF')
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A1:J1')
    ws.row_dimensions[1].height = 35

    segunda_fmt = segunda_feira.strftime('%d/%m/%Y')
    fim_fmt = dias_semana[-1]['data_fmt'] if dias_semana else segunda_fmt
    ws['A2'] = f"Semana: {segunda_fmt} a {fim_fmt} | Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws['A2'].font = Font(name='Segoe UI', italic=True, size=10, color='6B7280')
    ws['A2'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A2:J2')
    ws.row_dimensions[2].height = 20

    headers = [
        "Data", "Dia da Semana", "Refeição / Descrição", "Status Prazo", "Corte Fornecedor",
        "Regulares", "Extras", "Eventos", "TOTAL CONFIRMADO", "Restrições Alimentares"
    ]
    ws.append([])
    ws.append(headers)
    ws.row_dimensions[4].height = 26

    header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
    header_font = Font(name='Segoe UI', bold=True, color='FFFFFF', size=11)
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='center')

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=4, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border

    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    row_idx = 5
    tot_norm = 0
    tot_ext = 0
    tot_eve = 0
    tot_geral = 0

    for d in dias_semana:
        tot_norm += d['normais']
        tot_ext += d['extras']
        tot_eve += d['eventos']
        tot_geral += d['total']

        ws.append([
            d['data_fmt'],
            d['dia_nome'],
            f"{d['tipo_refeicao']} - {d['descricao']}",
            d['status_janela'],
            d['fechamento_fmt'],
            d['normais'],
            d['extras'],
            d['eventos'],
            d['total'],
            d['restricoes']
        ])
        ws.row_dimensions[row_idx].height = 22
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(name='Segoe UI', size=10, bold=(col_idx == 9))
            cell.border = thin_border
            if col_idx in (1, 2, 4, 5, 6, 7, 8, 9):
                cell.alignment = center_align
            else:
                cell.alignment = left_align

            if row_idx % 2 == 0:
                cell.fill = zebra_fill
        row_idx += 1

    ws.append(["TOTAIS", "", "", "", "", tot_norm, tot_ext, tot_eve, tot_geral, ""])
    ws.row_dimensions[row_idx].height = 24
    total_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=row_idx, column=col_idx)
        cell.font = Font(name='Segoe UI', bold=True, size=11, color='1E40AF')
        cell.fill = total_fill
        cell.border = thin_border
        cell.alignment = center_align

    for col in ws.columns:
        max_len = 0
        for cell in col:
            if cell.row in (1, 2):
                continue
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(min(max_len + 4, 45), 12)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    registrar_auditoria("Exportar Pedido Fornecedor Excel", f"Exportou semana {segunda_fmt} a {fim_fmt}")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"Pedido_Fornecedor_{segunda_feira.strftime('%Y%m%d')}_{timestamp}.xlsx"
    )



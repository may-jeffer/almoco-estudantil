# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, session, flash
from datetime import datetime
from database import closing, get_db_connection
from utils.auth import is_logged_in_admin, tem_permissao
from utils.helpers import registrar_auditoria
from . import admin_bp

CARDAPIOS_POR_PAGINA = 20

@admin_bp.route('/admin/cardapios', methods=['GET', 'POST'])
def admin_cardapios():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('cardapios'): return redirect(url_for('admin.admin_dashboard'))
    
    if request.method == 'POST':
        data = request.form.get('data')
        tipo_refeicao = request.form.get('tipo_refeicao', 'Almoço')
        permitir_reserva = 1 if request.form.get('permitir_reserva') else 0
        
        acompanhamento = request.form.get('acompanhamento', '')
        salada = request.form.get('salada', '')
        proteinas = request.form.get('proteinas', '')
        sobremesa = request.form.get('sobremesa', '')
        outros = request.form.get('outros', '')
        
        # Constrói a descrição combinada para exibição em áreas legadas
        parts = []
        if acompanhamento: parts.append(f"Acomp.: {acompanhamento}")
        if salada: parts.append(f"Salada: {salada}")
        if proteinas: parts.append(f"Prot.: {proteinas}")
        if sobremesa: parts.append(f"Sobremesa: {sobremesa}")
        if outros: parts.append(f"Outros: {outros}")
        descricao = " | ".join(parts) if parts else request.form.get('descricao', 'Sem descrição detalhada')

        considerar_reservas = request.form.get('considerar_reservas_empresa')
        if not considerar_reservas:
            qtd_raw = request.form.get('qtd_solicitada', '').strip()
            qtd_solicitada = int(qtd_raw) if qtd_raw.isdigit() else None
        else:
            qtd_solicitada = None

        try:
            with closing(get_db_connection()) as conn:
                conn.execute("""
                    INSERT INTO cardapios 
                    (data, descricao, tipo_refeicao, permitir_reserva, acompanhamento, salada, proteinas, sobremesa, outros, qtd_solicitada) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (data, descricao, tipo_refeicao, permitir_reserva, acompanhamento, salada, proteinas, sobremesa, outros, qtd_solicitada))
                conn.commit()
                registrar_auditoria("Criar Cardápio", f"Cadastrou cardápio para a data {data} ({tipo_refeicao})")
                flash('Cardápio adicionado!', 'success')
        except Exception as e:
            flash(f'Erro ao salvar cardápio. Verifique se já existe este tipo de refeição para este dia.', 'error')
        return redirect(url_for('admin.admin_cardapios'))

    pagina = request.args.get('page', 1, type=int)
    offset = (pagina - 1) * CARDAPIOS_POR_PAGINA

    with closing(get_db_connection()) as conn:
        total = conn.execute("SELECT COUNT(*) FROM cardapios").fetchone()[0]
        cardapios = conn.execute("SELECT * FROM cardapios ORDER BY data DESC LIMIT ? OFFSET ?", (CARDAPIOS_POR_PAGINA, offset)).fetchall()

    total_paginas = max(1, (total + CARDAPIOS_POR_PAGINA - 1) // CARDAPIOS_POR_PAGINA)
    return render_template('admin/cardapios.html', cardapios=cardapios, pagina=pagina, total_paginas=total_paginas, total=total)

# Excluir Cardapio
@admin_bp.route('/admin/cardapios/excluir/<int:id>', methods=['POST'])
def admin_cardapios_excluir(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('cardapios'): return redirect(url_for('admin.admin_dashboard'))
    with closing(get_db_connection()) as conn:
        r = conn.execute("SELECT COUNT(*) FROM reservas WHERE cardapio_id = ? AND status IN ('ATIVA', 'CONSUMIDA')", (id,)).fetchone()[0]
        if r > 0:
            flash('Impossível excluir. Há reservas ativas ou entregues para este cardápio.', 'error')
        else:
            cardapio = conn.execute("SELECT data, tipo_refeicao FROM cardapios WHERE id = ?", (id,)).fetchone()
            cardapio_txt = f"{cardapio['data']} ({cardapio['tipo_refeicao']})" if cardapio else f"ID {id}"
            
            conn.execute("DELETE FROM reservas WHERE cardapio_id = ?", (id,))
            conn.execute("DELETE FROM cardapios WHERE id = ?", (id,))
            conn.commit()
            registrar_auditoria("Excluir Cardápio", f"Excluiu o cardápio: {cardapio_txt}")
            flash('Cardápio excluído com sucesso.', 'success')
    return redirect(url_for('admin.admin_cardapios'))

# Editar Cardapio
@admin_bp.route('/admin/cardapios/editar/<int:id>', methods=['POST'])
def admin_cardapios_editar(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('cardapios'): return redirect(url_for('admin.admin_dashboard'))
    
    tipo_refeicao = request.form.get('tipo_refeicao')
    permitir_reserva = int(request.form.get('permitir_reserva', 1))
    
    acompanhamento = request.form.get('acompanhamento', '')
    salada = request.form.get('salada', '')
    proteinas = request.form.get('proteinas', '')
    sobremesa = request.form.get('sobremesa', '')
    outros = request.form.get('outros', '')

    considerar_reservas = request.form.get('considerar_reservas_empresa')
    if not considerar_reservas:
        qtd_raw = request.form.get('qtd_solicitada', '').strip()
        qtd_solicitada = int(qtd_raw) if qtd_raw.isdigit() else None
    else:
        qtd_solicitada = None

    parts = []
    if acompanhamento: parts.append(f"Acomp.: {acompanhamento}")
    if salada: parts.append(f"Salada: {salada}")
    if proteinas: parts.append(f"Prot.: {proteinas}")
    if sobremesa: parts.append(f"Sobremesa: {sobremesa}")
    if outros: parts.append(f"Outros: {outros}")
    descricao = " | ".join(parts) if parts else request.form.get('descricao', 'Sem descrição detalhada')

    with closing(get_db_connection()) as conn:
        cardapio = conn.execute("SELECT data FROM cardapios WHERE id = ?", (id,)).fetchone()
        data_cardapio = cardapio['data'] if cardapio else ''
        
        conn.execute("""
            UPDATE cardapios SET 
            descricao = ?, tipo_refeicao = ?, permitir_reserva = ?, 
            acompanhamento = ?, salada = ?, proteinas = ?, sobremesa = ?, outros = ?,
            qtd_solicitada = ?
            WHERE id = ?
        """, (descricao, tipo_refeicao, permitir_reserva, acompanhamento, salada, proteinas, sobremesa, outros, qtd_solicitada, id))
        conn.commit()
        registrar_auditoria("Editar Cardápio", f"Editou cardápio do dia {data_cardapio} ({tipo_refeicao})")
        flash('Cardápio atualizado com sucesso.', 'success')
    return redirect(url_for('admin.admin_cardapios'))

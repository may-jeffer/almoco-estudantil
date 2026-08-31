# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, session, flash, Response, current_app
import time
import re
import uuid
from database import closing, get_db_connection, get_config, generate_unique_code
from utils.auth import is_logged_in_admin, tem_permissao
from utils.helpers import datetime_now_str, date_hoje_str, pode_reservar, sanitize_field, registrar_auditoria
from utils.qrcode_gen import generate_badge_code, generate_std_badge_code
from . import admin_bp

RESERVAS_POR_PAGINA = 30

@admin_bp.route('/admin/reservas', methods=['GET'])
def admin_reservas():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('fila'): return redirect(url_for('admin.admin_dashboard'))
    
    hoje_str = date_hoje_str()
    busca = request.args.get('q', '').strip()
    pagina = request.args.get('page', 1, type=int)
    offset = (pagina - 1) * RESERVAS_POR_PAGINA
    
    with closing(get_db_connection()) as conn:
        cardapios_futuros = conn.execute(
            "SELECT id, data, tipo_refeicao, descricao FROM cardapios WHERE data >= ? ORDER BY data ASC, id ASC",
            (hoje_str,)
        ).fetchall()

        if busca:
            like = f'%{busca}%'
            total = conn.execute(
                "SELECT COUNT(*) FROM reservas r JOIN alunos a ON r.aluno_id = a.id JOIN cardapios c ON r.cardapio_id = c.id WHERE (a.nome LIKE ? OR a.matricula LIKE ? OR a.cpf LIKE ?) AND r.status = 'ATIVA' AND c.data >= ?",
                (like, like, like, hoje_str)
            ).fetchone()[0]
            
            reservas = conn.execute(
                """SELECT r.*, a.nome as aluno_nome, a.matricula as aluno_mat, c.data as cardapio_data, c.tipo_refeicao
                   FROM reservas r 
                   JOIN alunos a ON r.aluno_id = a.id
                   JOIN cardapios c ON r.cardapio_id = c.id
                   WHERE (a.nome LIKE ? OR a.matricula LIKE ? OR a.cpf LIKE ?) AND r.status = 'ATIVA' AND c.data >= ?
                   ORDER BY c.data ASC, a.nome ASC LIMIT ? OFFSET ?""",
                (like, like, like, hoje_str, RESERVAS_POR_PAGINA, offset)
            ).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM reservas r JOIN cardapios c ON r.cardapio_id = c.id WHERE r.status = 'ATIVA' AND c.data >= ?", (hoje_str,)).fetchone()[0]
            reservas = conn.execute(
                """SELECT r.*, a.nome as aluno_nome, a.matricula as aluno_mat, c.data as cardapio_data, c.tipo_refeicao
                   FROM reservas r 
                   JOIN alunos a ON r.aluno_id = a.id
                   JOIN cardapios c ON r.cardapio_id = c.id
                   WHERE r.status = 'ATIVA' AND c.data >= ?
                   ORDER BY c.data ASC, a.nome ASC LIMIT ? OFFSET ?""",
                (hoje_str, RESERVAS_POR_PAGINA, offset)
            ).fetchall()
            
    total_paginas = max(1, (total + RESERVAS_POR_PAGINA - 1) // RESERVAS_POR_PAGINA)
    return render_template(
        'admin/reservas.html',
        reservas=reservas,
        busca=busca,
        pagina=pagina,
        total_paginas=total_paginas,
        total=total,
        cardapios_futuros=cardapios_futuros
    )

@admin_bp.route('/admin/reservas/manual', methods=['POST'])
def admin_reservas_manual():
    """Permite ao administrador criar reserva manual para um aluno, mesmo fora do prazo, com registro de auditoria."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('fila'): return redirect(url_for('admin.admin_dashboard'))
    
    aluno_id = request.form.get('aluno_id', type=int)
    cardapio_id = request.form.get('cardapio_id', type=int)
    
    if not aluno_id or not cardapio_id:
        flash('Selecione o estudante e a refeição para efetuar a reserva manual.', 'error')
        return redirect(url_for('admin.admin_reservas'))
        
    with closing(get_db_connection()) as conn:
        aluno = conn.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
        cardapio = conn.execute("SELECT * FROM cardapios WHERE id = ?", (cardapio_id,)).fetchone()
        
        if not aluno:
            flash('Estudante não encontrado.', 'error')
            return redirect(url_for('admin.admin_reservas'))
            
        if not cardapio:
            flash('Cardápio selecionado não existe.', 'error')
            return redirect(url_for('admin.admin_reservas'))
            
        # Verificar se o aluno já tem reserva
        reserva_existente = conn.execute(
            "SELECT id, status, codigo_unico FROM reservas WHERE aluno_id = ? AND cardapio_id = ?",
            (aluno_id, cardapio_id)
        ).fetchone()
        
        admin_user = session.get('admin_usuario', 'admin')
        
        if reserva_existente:
            if reserva_existente['status'] == 'ATIVA':
                flash(f"O estudante {aluno['nome']} já possui uma reserva ativa para esta data (Ticket: {reserva_existente['codigo_unico']}).", 'warning')
                return redirect(url_for('admin.admin_reservas'))
            elif reserva_existente['status'] == 'CONSUMIDA':
                flash(f"O estudante {aluno['nome']} já consumiu a refeição correspondente a este cardápio.", 'error')
                return redirect(url_for('admin.admin_reservas'))
            else:
                # Reativar reserva cancelada
                novo_ticket = generate_unique_code()
                conn.execute(
                    "UPDATE reservas SET status = 'ATIVA', codigo_unico = ?, data_registro = ?, turma_id = ? WHERE id = ?",
                    (novo_ticket, datetime_now_str(), aluno['turma_id'], reserva_existente['id'])
                )
                conn.commit()
                registrar_auditoria(
                    "Reserva Manual",
                    f"Admin '{admin_user}' reativou reserva manual para o aluno {aluno['nome']} (Matrícula: {aluno['matricula']}) para {cardapio['data']} ({cardapio['tipo_refeicao']}). Ticket: {novo_ticket}"
                )
                flash(f"Reserva manual reativada com sucesso para {aluno['nome']} (Ticket: {novo_ticket})!", 'success')
                return redirect(url_for('admin.admin_reservas'))
        else:
            # Criar nova reserva ativa
            novo_ticket = generate_unique_code()
            conn.execute(
                "INSERT INTO reservas (aluno_id, cardapio_id, codigo_unico, status, data_registro, turma_id) VALUES (?, ?, ?, 'ATIVA', ?, ?)",
                (aluno_id, cardapio_id, novo_ticket, datetime_now_str(), aluno['turma_id'])
            )
            conn.commit()
            registrar_auditoria(
                "Reserva Manual",
                f"Admin '{admin_user}' realizou reserva manual para o aluno {aluno['nome']} (Matrícula: {aluno['matricula']}) para {cardapio['data']} ({cardapio['tipo_refeicao']}). Ticket: {novo_ticket}"
            )
            flash(f"Reserva manual criada com sucesso para {aluno['nome']} (Ticket: {novo_ticket})!", 'success')
            
    return redirect(url_for('admin.admin_reservas'))

@admin_bp.route('/admin/reservas/cancelar/<int:id>', methods=['POST'])
def admin_reservas_cancelar(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('fila'): return redirect(url_for('admin.admin_dashboard'))
    
    hoje_str = date_hoje_str()
    
    with closing(get_db_connection()) as conn:
        reserva = conn.execute("""
            SELECT r.id, a.nome as aluno_nome, c.data as cardapio_data
            FROM reservas r 
            JOIN alunos a ON r.aluno_id = a.id
            JOIN cardapios c ON r.cardapio_id = c.id 
            WHERE r.id = ? AND r.status = 'ATIVA' AND c.data >= ?
        """, (id, hoje_str)).fetchone()
        if reserva:
            conn.execute("UPDATE reservas SET status = 'CANCELADA' WHERE id = ?", (id,))
            conn.commit()
            admin_user = session.get('admin_usuario', 'admin')
            registrar_auditoria("Cancelar Reserva", f"Admin '{admin_user}' cancelou reserva ID {id} do aluno {reserva['aluno_nome']} para {reserva['cardapio_data']}")
            flash('Reserva cancelada pelo administrador com sucesso.', 'success')
        else:
            flash('Reserva não encontrada ou já processada.', 'error')
            
    return redirect(request.referrer or url_for('admin.admin_reservas'))

@admin_bp.route('/admin/entrega')
def admin_entrega():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('fila'): return redirect(url_for('admin.admin_dashboard'))
    hoje_str = date_hoje_str()
    
    with closing(get_db_connection()) as conn:
        cardapios_hoje = conn.execute("SELECT * FROM cardapios WHERE data = ? ORDER BY id ASC", (hoje_str,)).fetchall()
        
        # Seleciona o cardapio ativo (se houver múltiplo, o primeiro por padrão, ou via query param)
        cardapio_id_ativo = request.args.get('cardapio_id', type=int)
        cardapio_hoje = None
        
        if cardapio_id_ativo:
            cardapio_hoje = conn.execute("SELECT * FROM cardapios WHERE id = ?", (cardapio_id_ativo,)).fetchone()
        elif cardapios_hoje:
            cardapio_hoje = cardapios_hoje[0]
            
        reservas_hoje = []
        total_reservas_sistema = 0
        total_entregues_reserva = 0
        total_extras = 0
        total_entregues = 0
        qtd_solicitada_empresa = 0
        
        if cardapio_hoje:
            reservas_hoje = conn.execute("""
                SELECT r.id, r.codigo_unico, r.status, r.tipo_consumo, a.nome, a.matricula, t.nome as turma_nome
                FROM reservas r
                JOIN alunos a ON r.aluno_id = a.id
                LEFT JOIN turmas t ON a.turma_id = t.id
                WHERE r.cardapio_id = ? AND r.status != 'CANCELADA' AND r.aluno_id IS NOT NULL
                ORDER BY a.nome ASC
            """, (cardapio_hoje['id'],)).fetchall()
            
            total_reservas_sistema = sum(1 for r in reservas_hoje if (r['tipo_consumo'] in ('NORMAL', 'EVENTO') or r['tipo_consumo'] is None))
            total_entregues_reserva = sum(1 for r in reservas_hoje if r['status'] == 'CONSUMIDA' and (r['tipo_consumo'] in ('NORMAL', 'EVENTO') or r['tipo_consumo'] is None))
            total_extras = sum(1 for r in reservas_hoje if r['status'] == 'CONSUMIDA' and r['tipo_consumo'] == 'EXTRA')
            total_entregues = sum(1 for r in reservas_hoje if r['status'] == 'CONSUMIDA')
            
            if cardapio_hoje['qtd_solicitada'] is not None and cardapio_hoje['qtd_solicitada'] > 0:
                qtd_solicitada_empresa = cardapio_hoje['qtd_solicitada']
            else:
                qtd_solicitada_empresa = total_reservas_sistema
        
    https_alert = not request.is_secure
        
    return render_template('admin/entrega.html', 
                           cardapios_hoje=cardapios_hoje,
                           cardapio_hoje=cardapio_hoje, 
                           reservas_hoje=reservas_hoje, 
                           total_reservas=total_reservas_sistema,
                           total_reservas_sistema=total_reservas_sistema,
                           total_extras=total_extras,
                           total_entregues=total_entregues, 
                           qtd_solicitada_empresa=qtd_solicitada_empresa,
                           https_alert=https_alert)

@admin_bp.route('/admin/entrega/baixar', methods=['POST'])
def baixar_reserva():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('fila'): return redirect(url_for('admin.admin_dashboard'))
    
    codigo = request.form.get('codigo_unico')
    cardapio_id = request.form.get('cardapio_id')
    
    if not codigo or not cardapio_id:
        flash('Código ou cardápio inválido', 'error')
        return redirect(url_for('admin.admin_entrega'))
        
    with closing(get_db_connection()) as conn:
        reserva = conn.execute(
            "SELECT r.*, a.nome as aluno_nome, t.nome as turma_nome FROM reservas r JOIN alunos a ON r.aluno_id = a.id LEFT JOIN turmas t ON a.turma_id = t.id WHERE r.codigo_unico = ? AND r.cardapio_id = ?", 
            (codigo, cardapio_id)
        ).fetchone()
        
        if not reserva:
            flash('Reserva não encontrada para este código!', 'error')
        else:
            turma_tag = f" ({reserva['turma_nome']})" if reserva['turma_nome'] else ""
            if reserva['status'] == 'CONSUMIDA':
                flash(f"Refeição já entregue para {reserva['aluno_nome']}{turma_tag}!", 'warning')
            elif reserva['status'] == 'CANCELADA':
                flash(f"A reserva de {reserva['aluno_nome']}{turma_tag} foi cancelada! Recuse a entrega.", 'error')
            else:
                conn.execute("UPDATE reservas SET status='CONSUMIDA' WHERE id = ?", (reserva['id'],))
                conn.commit()
                registrar_auditoria("Registrar Entrega", f"Liberou refeição de {reserva['aluno_nome']}{turma_tag} (Reserva ID {reserva['id']})")
                flash(f"Refeição liberada: {reserva['aluno_nome']}{turma_tag}", 'success')
            
    return redirect(url_for('admin.admin_entrega'))

# API para Baixa Rápida via AJAX (Evita sumiço da câmera)
@admin_bp.route('/admin/api/baixar', methods=['POST'])
def api_baixar_reserva():
    if not is_logged_in_admin(): 
        return {"success": False, "message": "Não autorizado"}, 401
    if not tem_permissao('fila'):
        return {"success": False, "message": "Sem permissão de acesso à fila", "type": "error"}, 403
    
    data = request.get_json()
    codigo = data.get('codigo_unico', '').upper()
    cardapio_id = data.get('cardapio_id')
    confirmado = data.get('confirmado', False)
    
    if not codigo or not cardapio_id:
        return {"success": False, "message": "Dados inválidos"}, 400
        
    with closing(get_db_connection()) as conn:
        # LÓGICA PARA CRACHÁ FIXO (REGULARES)
        if codigo.startswith('STD-'):
            try:
                parts = codigo.split('-')
                if len(parts) != 3: raise ValueError("Formato inválido")
                aluno_id = int(parts[1])
                
                # Valida o Hash: Checa no banco de dados primeiro
                aluno_db = conn.execute("SELECT a.id, a.nome, a.permitido_almoco, a.codigo_cracha, a.restricoes, t.nome as turma_nome FROM alunos a LEFT JOIN turmas t ON a.turma_id = t.id WHERE a.id = ?", (aluno_id,)).fetchone()
                if not aluno_db:
                    return {"success": False, "message": "Estudante não encontrado!", "type": "error"}
                
                turma_nome = aluno_db['turma_nome'] or 'Sem Turma'
                turma_tag = f" ({turma_nome})" if aluno_db['turma_nome'] else ""
                
                codigo_db = aluno_db['codigo_cracha']
                if codigo != codigo_db and codigo != generate_std_badge_code(aluno_id):
                    return {"success": False, "message": "Código de crachá inválido!", "type": "error"}
                
                # Verifica se o aluno tem reserva ATIVA para este cardapio_id
                reserva = conn.execute(
                    "SELECT id, status, codigo_unico FROM reservas WHERE aluno_id = ? AND cardapio_id = ?",
                    (aluno_id, cardapio_id)
                ).fetchone()
                
                if not (reserva and reserva['status'] == 'ATIVA'):
                    if reserva and reserva['status'] == 'CONSUMIDA':
                        return {"success": False, "message": f"{aluno_db['nome']}{turma_tag} já consumiu esta refeição hoje!", "type": "warning"}
                    
                    # Se não tem reserva ativa ou foi cancelada, podemos liberar como extra caso seja confirmado
                    if not confirmado:
                        msg = f"O aluno {aluno_db['nome']}{turma_tag} não possui reserva ativa para esta refeição. Deseja liberar o almoço mesmo assim (marcando como Extra)?"
                        if reserva and reserva['status'] == 'CANCELADA':
                            msg = f"A reserva de {aluno_db['nome']}{turma_tag} foi CANCELADA. Deseja liberar o almoço mesmo assim (marcando como Extra)?"
                        return {
                            "success": False,
                            "message": msg,
                            "requires_confirmation": True,
                            "type": "warning"
                        }
                    else:
                        # Se confirmado, cria registro de reserva EXTRA consumida
                        codigo_reserva = generate_unique_code()
                        conn.execute(
                            "INSERT INTO reservas (aluno_id, cardapio_id, status, codigo_unico, data_registro, tipo_consumo) VALUES (?, ?, 'CONSUMIDA', ?, ?, 'EXTRA')",
                            (aluno_id, cardapio_id, codigo_reserva, datetime_now_str())
                        )
                        conn.commit()
                        registrar_auditoria("Registrar Sobra API", f"Entregou sobra (refeição extra) para {aluno_db['nome']}{turma_tag} via crachá fixo")
                        return {
                            "success": True, 
                            "message": f"Sobra entregue: {aluno_db['nome']}{turma_tag} (Marcado como Extra)", 
                            "aluno": aluno_db['nome'],
                            "turma": turma_nome,
                            "tipo_consumo": "EXTRA",
                            "codigo_unico": codigo_reserva,
                            "restricoes": aluno_db['restricoes']
                        }
                
                # Aluno encontrado e tem reserva! Dar baixa.
                conn.execute("UPDATE reservas SET status='CONSUMIDA' WHERE id = ?", (reserva['id'],))
                conn.commit()
                registrar_auditoria("Registrar Entrega API", f"Validou crachá fixo e entregou refeição para {aluno_db['nome']}{turma_tag} (Reserva ID {reserva['id']})")
                return {
                    "success": True, 
                    "message": f"Crachá fixo validado! Liberado: {aluno_db['nome']}{turma_tag}", 
                    "aluno": aluno_db['nome'],
                    "turma": turma_nome,
                    "tipo_consumo": "NORMAL",
                    "codigo_unico": reserva['codigo_unico'],
                    "restricoes": aluno_db['restricoes']
                }
                
            except Exception as e:
                return {"success": False, "message": f"Erro no crachá fixo: {str(e)}", "type": "error"}
  
        # LÓGICA PARA CRACHÁ DE EVENTO (FIXO)
        if codigo.startswith('EVT-'):
            try:
                parts = codigo.split('-')
                if len(parts) != 4: raise ValueError("Formato inválido")
                evt_id = int(parts[1])
                aluno_id = int(parts[2])
                
                # Valida o Hash: Checa no banco de dados primeiro
                ep = conn.execute("SELECT codigo_cracha FROM eventos_participantes WHERE aluno_id = ? AND turma_id = ?", (aluno_id, evt_id)).fetchone()
                codigo_db = ep['codigo_cracha'] if ep else None
                if codigo != codigo_db and codigo != generate_badge_code(evt_id, aluno_id):
                    return {"success": False, "message": "Código de crachá inválido ou alterado!", "type": "error"}
                
                # Verifica validade do evento
                evento = conn.execute("SELECT * FROM turmas WHERE id = ? AND is_evento = 1", (evt_id,)).fetchone()
                if not evento:
                    return {"success": False, "message": "Evento não encontrado!", "type": "error"}
                
                hoje = date_hoje_str()
                if (evento['data_inicio'] and hoje < evento['data_inicio']) or (evento['data_fim'] and hoje > evento['data_fim']):
                    return {"success": False, "message": "Este crachá está fora da validade do evento!", "type": "warning"}
                
                # Busca o aluno
                aluno = conn.execute("SELECT a.nome, a.restricoes, t.nome as turma_nome FROM alunos a LEFT JOIN turmas t ON a.turma_id = t.id WHERE a.id = ?", (aluno_id,)).fetchone()
                if not aluno:
                    return {"success": False, "message": "Aluno não encontrado!", "type": "error"}
                
                turma_nome = evento['nome'] or aluno['turma_nome'] or 'Evento'
                turma_tag = f" ({turma_nome})"
                
                # Verifica se já comeu ESTA refeição hoje
                ja_comeu = conn.execute("SELECT id FROM reservas WHERE aluno_id = ? AND cardapio_id = ? AND status = 'CONSUMIDA'", (aluno_id, cardapio_id)).fetchone()
                if ja_comeu:
                    return {"success": False, "message": f"{aluno['nome']}{turma_tag} já consumiu esta refeição hoje!", "type": "warning"}
                
                # Cria registro de consumo
                codigo_reserva = "EVT-REG-" + uuid.uuid4().hex[:8].upper()
                conn.execute("""
                    INSERT INTO reservas (aluno_id, cardapio_id, status, codigo_unico, data_registro, tipo_consumo, turma_id)
                    VALUES (?, ?, 'CONSUMIDA', ?, ?, 'EVENTO', ?)
                """, (aluno_id, cardapio_id, codigo_reserva, datetime_now_str(), evt_id))
                conn.commit()
                registrar_auditoria("Registrar Entrega Evento API", f"Validou crachá de evento e entregou refeição para {aluno['nome']}{turma_tag}")
                
                return {
                    "success": True, 
                    "message": f"Crachá validado! Refeição liberada: {aluno['nome']}{turma_tag}", 
                    "aluno": aluno['nome'],
                    "turma": turma_nome,
                    "tipo_consumo": "EVENTO",
                    "codigo_unico": codigo_reserva,
                    "restricoes": aluno['restricoes']
                }
                
            except Exception as e:
                return {"success": False, "message": f"Erro ao processar crachá: {str(e)}", "type": "error"}
  
        # LÓGICA PARA RESERVA PADRÃO
        reserva = conn.execute(
            "SELECT r.*, a.nome as aluno_nome, a.restricoes as aluno_restricoes, t.nome as turma_nome FROM reservas r JOIN alunos a ON r.aluno_id = a.id LEFT JOIN turmas t ON a.turma_id = t.id WHERE r.codigo_unico = ? AND r.cardapio_id = ?", 
            (codigo, cardapio_id)
        ).fetchone()
        
        if not reserva:
            return {"success": False, "message": "Reserva não encontrada!", "type": "error"}
        
        turma_nome = reserva['turma_nome'] or 'Sem Turma'
        turma_tag = f" ({turma_nome})" if reserva['turma_nome'] else ""
        
        if reserva['status'] == 'CONSUMIDA':
            return {"success": False, "message": f"Refeição já entregue para {reserva['aluno_nome']}{turma_tag}!", "type": "warning"}
        elif reserva['status'] == 'CANCELADA':
            return {"success": False, "message": f"A reserva de {reserva['aluno_nome']}{turma_tag} foi cancelada!", "type": "error"}
        else:
            conn.execute("UPDATE reservas SET status='CONSUMIDA' WHERE id = ?", (reserva['id'],))
            conn.commit()
            registrar_auditoria("Registrar Entrega API", f"Entregou refeição via QR Code padrão para {reserva['aluno_nome']}{turma_tag} (Reserva ID {reserva['id']})")
            return {
                "success": True, 
                "message": f"Refeição liberada: {reserva['aluno_nome']}{turma_tag}", 
                "aluno": reserva['aluno_nome'],
                "turma": turma_nome,
                "tipo_consumo": reserva['tipo_consumo'] or "NORMAL",
                "codigo_unico": reserva['codigo_unico'],
                "restricoes": reserva['aluno_restricoes']
            }

@admin_bp.route('/admin/api/adicionar_extra', methods=['POST'])
def api_adicionar_extra():
    if not is_logged_in_admin(): 
        return {"success": False, "message": "Não autorizado"}, 401
    if not tem_permissao('fila'):
        return {"success": False, "message": "Sem permissão de acesso à fila", "type": "error"}, 403
    
    data = request.get_json()
    busca = data.get('aluno_busca') # Pode ser matrícula ou CPF
    cardapio_id = data.get('cardapio_id')
    
    if not busca or not cardapio_id:
        return {"success": False, "message": "Dados inválidos"}, 400
        
    with closing(get_db_connection()) as conn:
        aluno = conn.execute("SELECT a.id, a.nome, a.permitido_almoco, a.restricoes, t.nome as turma_nome FROM alunos a LEFT JOIN turmas t ON a.turma_id = t.id WHERE a.matricula = ? OR a.cpf = ?", (busca, busca)).fetchone()
        
        if not aluno:
            return {"success": False, "message": "Estudante não encontrado no sistema.", "type": "error"}

        turma_nome = aluno['turma_nome'] or 'Sem Turma'
        turma_tag = f" ({turma_nome})" if aluno['turma_nome'] else ""

        # Se o aluno estiver bloqueado no portal e o admin ainda não confirmou, pedir confirmação
        confirmado = data.get('confirmado_bloqueado', False)
        if aluno['permitido_almoco'] == 0 and not confirmado:
            return {
                "success": False, 
                "message": f"O aluno {aluno['nome']}{turma_tag} está BLOQUEADO para reservas no portal. Deseja entregar a sobra mesmo assim?", 
                "requires_confirmation": True,
                "type": "warning"
            }
            
        # Verificar se já comeu hoje (por reserva normal ou extra)
        ja_comeu = conn.execute("SELECT id, status, tipo_consumo FROM reservas WHERE aluno_id = ? AND cardapio_id = ? AND status = 'CONSUMIDA'", (aluno['id'], cardapio_id)).fetchone()
        if ja_comeu:
            return {"success": False, "message": f"Atenção: {aluno['nome']}{turma_tag} já consumiu refeição hoje!", "type": "warning"}
            
        # Verificar se ele tem uma reserva ATIVA e dar baixa normal para evitar duplicidade
        reserva_ativa = conn.execute("SELECT id, codigo_unico FROM reservas WHERE aluno_id = ? AND cardapio_id = ? AND status = 'ATIVA'", (aluno['id'], cardapio_id)).fetchone()
        if reserva_ativa:
            conn.execute("UPDATE reservas SET status='CONSUMIDA' WHERE id = ?", (reserva_ativa['id'],))
            conn.commit()
            registrar_auditoria("Registrar Entrega Extra", f"Deu baixa na reserva ativa de {aluno['nome']}{turma_tag} via adicionar_extra")
            return {
                "success": True, 
                "message": f"Foi dada baixa na reserva PADRÃO de {aluno['nome']}{turma_tag}.", 
                "aluno": aluno['nome'],
                "turma": turma_nome,
                "tipo_consumo": "NORMAL",
                "codigo_unico": reserva_ativa['codigo_unico'],
                "restricoes": aluno['restricoes']
            }
        
        # Se não comeu e não tem reserva ativa, insere a sobra
        codigo = generate_unique_code()
        conn.execute(
            "INSERT INTO reservas (aluno_id, cardapio_id, status, codigo_unico, data_registro, tipo_consumo) VALUES (?, ?, 'CONSUMIDA', ?, ?, 'EXTRA')",
            (aluno['id'], cardapio_id, codigo, datetime_now_str())
        )
        conn.commit()
        registrar_auditoria("Registrar Sobra", f"Registrou refeição extra (sobra) para {aluno['nome']}{turma_tag}")
        
        return {
            "success": True, 
            "message": f"Sobra entregue: {aluno['nome']}{turma_tag} (Marcado como Extra)", 
            "aluno": aluno['nome'],
            "turma": turma_nome,
            "tipo_consumo": "EXTRA",
            "codigo_unico": codigo,
            "restricoes": aluno['restricoes']
        }

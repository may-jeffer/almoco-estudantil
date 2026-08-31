# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, session, flash
from database import closing, get_db_connection
from utils.auth import is_logged_in_admin, tem_permissao
from utils.helpers import registrar_auditoria
from . import admin_bp

TURMAS_POR_PAGINA = 20

@admin_bp.route('/admin/turmas', methods=['GET', 'POST'])
def admin_turmas():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('turmas'): return redirect(url_for('admin.admin_dashboard'))
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        if nome:
            with closing(get_db_connection()) as conn:
                conn.execute("INSERT INTO turmas (nome) VALUES (?)", (nome,))
                conn.commit()
                registrar_auditoria("Criar Turma", f"Criou a turma: {nome}")
                flash('Turma adicionada', 'success')
        return redirect(url_for('admin.admin_turmas'))

    pagina = request.args.get('page', 1, type=int)
    offset = (pagina - 1) * TURMAS_POR_PAGINA

    with closing(get_db_connection()) as conn:
        total = conn.execute("SELECT COUNT(*) FROM turmas").fetchone()[0]
        turmas = conn.execute("SELECT * FROM turmas ORDER BY nome LIMIT ? OFFSET ?", (TURMAS_POR_PAGINA, offset)).fetchall()

    total_paginas = max(1, (total + TURMAS_POR_PAGINA - 1) // TURMAS_POR_PAGINA)
    return render_template('admin/turmas.html', turmas=turmas, pagina=pagina, total_paginas=total_paginas, total=total)

@admin_bp.route('/admin/turmas/editar/<int:id>', methods=['POST'])
def admin_turmas_editar(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('turmas'): return redirect(url_for('admin.admin_dashboard'))

    nome = request.form.get('nome', '').strip()
    if not nome:
        flash('O nome da turma não pode ser vazio.', 'error')
        return redirect(url_for('admin.admin_turmas'))

    with closing(get_db_connection()) as conn:
        turma = conn.execute("SELECT id FROM turmas WHERE id = ?", (id,)).fetchone()
        if not turma:
            flash('Turma não encontrada.', 'error')
            return redirect(url_for('admin.admin_turmas'))
        conn.execute("UPDATE turmas SET nome = ? WHERE id = ?", (nome, id))
        conn.commit()
        registrar_auditoria("Editar Turma", f"Renomeou a turma ID {id} para: {nome}")
        flash(f'Turma atualizada com sucesso!', 'success')

    return redirect(url_for('admin.admin_turmas'))

@admin_bp.route('/admin/turmas/excluir/<int:id>', methods=['POST'])
def admin_turmas_excluir(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('turmas'): return redirect(url_for('admin.admin_dashboard'))

    with closing(get_db_connection()) as conn:
        # Verificar se há alunos vinculados
        alunos_vinculados = conn.execute(
            "SELECT COUNT(*) FROM alunos WHERE turma_id = ?", (id,)
        ).fetchone()[0]

        if alunos_vinculados > 0:
            flash(f'Não é possível excluir: há {alunos_vinculados} aluno(s) vinculado(s) a esta turma. Transfira ou exclua os alunos primeiro.', 'error')
            return redirect(url_for('admin.admin_turmas'))

        turma = conn.execute("SELECT nome FROM turmas WHERE id = ?", (id,)).fetchone()
        turma_nome = turma['nome'] if turma else f"ID {id}"
        
        conn.execute("DELETE FROM turmas WHERE id = ?", (id,))
        conn.commit()
        registrar_auditoria("Excluir Turma", f"Excluiu a turma: {turma_nome}")
        flash('Turma excluída com sucesso.', 'success')

    return redirect(url_for('admin.admin_turmas'))

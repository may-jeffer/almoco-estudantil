# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, session, flash, Response
import csv
import io
import json
import re
import sqlite3
import qrcode
import base64
from io import BytesIO
from database import closing, get_db_connection
from utils.auth import is_logged_in_admin, tem_permissao
from utils.helpers import datetime_now_str, date_hoje_str, pode_reservar, sanitize_field, registrar_auditoria
from utils.qrcode_gen import generate_std_badge_code
from . import admin_bp

ALUNOS_POR_PAGINA = 20

@admin_bp.route('/admin/alunos', methods=['GET', 'POST'])
def admin_alunos():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('alunos'): return redirect(url_for('admin.admin_dashboard'))
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        matricula = request.form.get('matricula')
        cpf = request.form.get('cpf')
        data_nascimento = request.form.get('data_nascimento')
        email = request.form.get('email')
        restricoes = request.form.get('restricoes')
        turma_id = request.form.get('turma_id')
        permitido_almoco = int(request.form.get('permitido_almoco', '1'))
        
        try:
            with closing(get_db_connection()) as conn:
                conn.execute(
                    "INSERT INTO alunos (nome, matricula, cpf, data_nascimento, email, restricoes, turma_id, permitido_almoco) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (nome, matricula, cpf, data_nascimento, email, restricoes, turma_id, permitido_almoco)
                )
                conn.commit()
                registrar_auditoria("Criar Aluno", f"Cadastrou aluno: {nome} (Matrícula: {matricula})")
                flash('Aluno cadastrado!', 'success')
        except Exception:
            flash(f'Erro ao cadastrar. Talvez CPF já exista.', 'error')
        return redirect(url_for('admin.admin_alunos'))

    busca = request.args.get('q', '').strip()
    pagina = request.args.get('page', 1, type=int)
    tipo_lista = 'regulares'
    offset = (pagina - 1) * ALUNOS_POR_PAGINA

    with closing(get_db_connection()) as conn:
        turmas = conn.execute("SELECT * FROM turmas WHERE is_evento = 0 ORDER BY nome").fetchall()
        
        base_query = "FROM alunos a LEFT JOIN turmas t ON a.turma_id = t.id"
        conditions = ["a.matricula NOT LIKE 'EVT-%'"]
        params = []
            
        if busca:
            like = f'%{busca}%'
            conditions.append("(a.nome LIKE ? OR a.matricula LIKE ? OR a.cpf LIKE ?)")
            params.extend([like, like, like])
            
        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
            
        total = conn.execute(f"SELECT COUNT(*) {base_query} {where_clause}", params).fetchone()[0]
        
        alunos = conn.execute(
            f"SELECT a.*, t.nome as turma_nome {base_query} {where_clause} ORDER BY a.nome LIMIT ? OFFSET ?",
            params + [ALUNOS_POR_PAGINA, offset]
        ).fetchall()

    total_paginas = max(1, (total + ALUNOS_POR_PAGINA - 1) // ALUNOS_POR_PAGINA)
    return render_template('admin/alunos.html',
        alunos=alunos, turmas=turmas,
        busca=busca, pagina=pagina, tipo_lista=tipo_lista,
        total_paginas=total_paginas, total=total
    )

@admin_bp.route('/admin/alunos/editar/<int:id>', methods=['POST'])
def admin_alunos_editar(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('alunos'): return redirect(url_for('admin.admin_dashboard'))
    
    nome = request.form.get('nome')
    matricula = request.form.get('matricula')
    cpf = request.form.get('cpf')
    data_nascimento = request.form.get('data_nascimento')
    email = request.form.get('email')
    restricoes = request.form.get('restricoes')
    turma_id = request.form.get('turma_id')
    permitido_almoco = int(request.form.get('permitido_almoco', '1'))
    
    try:
        with closing(get_db_connection()) as conn:
            conn.execute(
                """UPDATE alunos 
                   SET nome=?, matricula=?, cpf=?, data_nascimento=?, email=?, restricoes=?, turma_id=?, permitido_almoco=? 
                   WHERE id=?""",
                (nome, matricula, cpf, data_nascimento, email, restricoes, turma_id, permitido_almoco, id)
            )
            conn.commit()
            registrar_auditoria("Editar Aluno", f"Editou dados do aluno ID {id}: {nome}")
            flash('Aluno atualizado com sucesso!', 'success')
    except Exception as e:
        flash('Erro ao atualizar aluno. Verifique cadastros duplicados.', 'error')
        
    return redirect(url_for('admin.admin_alunos'))

@admin_bp.route('/admin/alunos/excluir/<int:id>', methods=['POST'])
def admin_alunos_excluir(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('alunos'): return redirect(url_for('admin.admin_dashboard'))
    try:
        with closing(get_db_connection()) as conn:
            aluno = conn.execute("SELECT nome, matricula FROM alunos WHERE id = ?", (id,)).fetchone()
            aluno_txt = f"{aluno['nome']} (Matrícula: {aluno['matricula']})" if aluno else f"ID {id}"
            
            conn.execute("DELETE FROM reservas WHERE aluno_id = ?", (id,))
            conn.execute("DELETE FROM alunos WHERE id = ?", (id,))
            conn.commit()
            registrar_auditoria("Excluir Aluno", f"Excluiu o aluno: {aluno_txt}")
            flash('Aluno excluído com sucesso!', 'success')
    except Exception as e:
        flash('Erro ao excluir aluno.', 'error')
    return redirect(url_for('admin.admin_alunos'))

@admin_bp.route('/admin/alunos/imprimir')
def admin_alunos_imprimir():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('alunos'): return redirect(url_for('admin.admin_dashboard'))
    
    turma_id = request.args.get('turma_id')
    aluno_id = request.args.get('aluno_id')
    ids_selecionados = request.args.getlist('ids[]')  # múltiplos alunos selecionados
    
    with closing(get_db_connection()) as conn:
        query = "SELECT a.*, t.nome as turma_nome FROM alunos a LEFT JOIN turmas t ON a.turma_id = t.id WHERE (t.is_evento = 0 OR t.id IS NULL)"
        params = []
        
        if ids_selecionados:
            # Impressão de seleção específica de alunos
            placeholders = ','.join(['?'] * len(ids_selecionados))
            query += f" AND a.id IN ({placeholders})"
            params.extend([int(i) for i in ids_selecionados if i.isdigit()])
        elif aluno_id:
            query += " AND a.id = ?"
            params.append(aluno_id)
        elif turma_id:
            query += " AND a.turma_id = ?"
            params.append(turma_id)
            
        alunos = conn.execute(query, params).fetchall()
        
        # Garante que todos tenham codigo_cracha
        for a in alunos:
            if not a['codigo_cracha']:
                codigo = generate_std_badge_code(a['id'])
                conn.execute("UPDATE alunos SET codigo_cracha = ? WHERE id = ?", (codigo, a['id']))
        conn.commit()
        
        # Recarrega se algum foi atualizado
        alunos_final = conn.execute(query, params).fetchall()

        crachas = []
        for a in alunos_final:
            # Gerar QR Code
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
                'turma': a['turma_nome'] or 'Geral/Sem Turma',
                'qr_code': qr_base64,
                'codigo': a['codigo_cracha']
            })
            
    label = f"{len(crachas)} aluno(s) selecionado(s)" if ids_selecionados else "todos os alunos"
    registrar_auditoria("Imprimir Crachás Alunos", f"Gerou visualização de impressão de crachás de alunos ({label})")
    return render_template('admin/alunos_imprimir.html', crachas=crachas)

@admin_bp.route('/admin/alunos/csv_template')
def admin_alunos_csv_template():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    output = "Nome,Matricula,CPF,DataNascimento (DD/MM/AAAA),TurmaID,Email,Restricoes,LiberadoParaSolicitar(S/N)\nExemplo da Silva,2023001,11122233344,20/05/2005,1,teste@gmail.com,Vegano (opcional),S"
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=modelo_importacao_alunos.csv"}
    )
    
@admin_bp.route('/admin/alunos/importar', methods=['POST'])
def admin_alunos_importar():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    
    if 'arquivo_csv' not in request.files:
        flash('Nenhum arquivo enviado.', 'error')
        return redirect(url_for('admin.admin_alunos'))
        
    file = request.files['arquivo_csv']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('admin.admin_alunos'))
        
    try:
        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        csv_input = csv.reader(stream, delimiter=';')
        
        # Faz uma leitura caso use vírgula e retenta se apenas puxar 1 campo na row
        first_row = next(csv_input, None)
        delimiter_used = ';'
        if first_row and len(first_row) == 1 and ',' in first_row[0]:
            delimiter_used = ','
            
        # Re-set flow and re-read correctly
        stream.seek(0)
        csv_input = csv.reader(stream, delimiter=delimiter_used)
        next(csv_input, None) # pula o cabecalho de fato
        
        adicionados = 0
        erros = 0
        
        with closing(get_db_connection()) as conn:
            for row in csv_input:
                if len(row) >= 5:
                    nome = sanitize_field(row[0])
                    matricula = sanitize_field(row[1])
                    cpf = sanitize_field(row[2])
                    data_nascimento = sanitize_field(row[3])
                    
                    # Trata a data de nascimento caso venha em DD/MM/AAAA
                    if '/' in data_nascimento:
                        try:
                            parts = data_nascimento.split('/')
                            if len(parts) == 3 and len(parts[2]) == 4:
                                data_nascimento = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                        except:
                            pass

                    turma_id = sanitize_field(row[4])
                    email = sanitize_field(row[5]) if len(row) > 5 else ''
                    restricoes = sanitize_field(row[6]) if len(row) > 6 else ''
                    permitido_str = sanitize_field(row[7]) if len(row) > 7 else 'S'
                    
                    permitido_almoco = 0 if permitido_str.strip().upper() == 'N' else 1
                    
                    if not nome or not cpf:
                        continue
                        
                    try:
                        # Tentar buscar se o aluno já existe pelo CPF
                        existente = conn.execute("SELECT id FROM alunos WHERE cpf = ?", (cpf,)).fetchone()
                        
                        if existente:
                            # Atualiza (Upsert manual)
                            conn.execute(
                                """UPDATE alunos SET 
                                   nome = ?, matricula = ?, data_nascimento = ?, 
                                   turma_id = ?, email = ?, restricoes = ?, permitido_almoco = ?
                                   WHERE id = ?""",
                                (nome, matricula, data_nascimento, turma_id, email, restricoes, permitido_almoco, existente['id'])
                            )
                            adicionados += 1 # Contamos como sucesso de processamento
                        else:
                            # Insere novo
                            conn.execute(
                                "INSERT INTO alunos (nome, matricula, cpf, data_nascimento, email, restricoes, turma_id, permitido_almoco) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (nome, matricula, cpf, data_nascimento, email, restricoes, turma_id, permitido_almoco)
                            )
                            adicionados += 1
                    except Exception as e:
                        print(f"Erro na linha CSV: {e}")
                        erros += 1
            conn.commit()
            registrar_auditoria("Importar Alunos CSV", f"Importou/atualizou {adicionados} alunos via arquivo CSV")
            
        flash(f'Processamento concluído! Registros novos ou atualizados: {adicionados}. Falhas: {erros}.', 'success')
        
    except Exception as e:
        flash(f'Erro inexperado lendo arquivo CSV: {str(e)}', 'error')
        
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
    Rota Placeholder para a futura integração direta via API do SUAP.
    O desenvolvedor deverá substituir o MOCK pela biblioteca 'requests'.
    """
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('alunos'): return redirect(url_for('admin.admin_dashboard'))
    
    api_url = request.form.get('api_url')
    token = request.form.get('token')
    turma_id = request.form.get('turma_id')
    
    # Mocking (Dados Simulados)
    mock_json = '''
    [
        {"nome": "Maria Emília (Teste SUAP)", "matricula": "202611SUAP", "cpf": "234.345.567-89", "data_nascimento": "2005-08-20"},
        {"nome": "Felipe Souza (Teste SUAP)", "matricula": "202612SUAP", "cpf": "098.876.654-32", "data_nascimento": "2006-12-15"}
    ]
    '''
    try:
        alunos_suap = json.loads(mock_json)
        adicionados = 0
        with closing(get_db_connection()) as conn:
            for asuap in alunos_suap:
                existe = conn.execute("SELECT id FROM alunos WHERE matricula = ? OR cpf = ?", (asuap['matricula'], asuap['cpf'])).fetchone()
                if not existe:
                    conn.execute(
                        "INSERT INTO alunos (nome, matricula, cpf, data_nascimento, restricoes, turma_id) VALUES (?, ?, ?, ?, ?, ?)",
                        (asuap['nome'], asuap['matricula'], asuap['cpf'], asuap['data_nascimento'], '', turma_id)
                    )
                    adicionados += 1
            conn.commit()
            registrar_auditoria("Sincronizar SUAP", f"Sincronizou/adicionou {adicionados} alunos com SUAP")
            
        flash(f'Simulação SUAP Executada! O código-base funcionou e {adicionados} aluno(s) injetado(s) com sucesso.', 'success')
    except Exception as e:
        flash(f'Erro na Simulação SUAP: {str(e)}', 'error')
        
    return redirect(url_for('admin.admin_alunos'))

@admin_bp.route('/admin/api/alunos/buscar')
def admin_api_buscar_alunos():
    if not is_logged_in_admin(): return {"error": "Unauthorized"}, 401
    q = request.args.get('q', '').strip()
    if len(q) < 2: return {"alunos": []}
    
    from database.connection import remove_accents
    
    # Limpar CPF para busca se for o caso
    q_clean = re.sub(r'\D', '', q)
    
    # Normalizar o termo de busca para comparar com remove_accents
    like_norm = f"%{remove_accents(q)}%"
    
    with closing(get_db_connection()) as conn:
        # Busca por nome, matricula ou CPF normalizados
        query = "SELECT id, nome, matricula, cpf FROM alunos WHERE (remove_accents(nome) LIKE ? OR remove_accents(matricula) LIKE ? OR remove_accents(cpf) LIKE ?)"
        params = [like_norm, like_norm, like_norm]
        
        # Se tiver números, busca também pelo CPF limpo normalizado
        if q_clean:
            query += " OR remove_accents(cpf) LIKE ?"
            params.append(f'%{remove_accents(q_clean)}%')
            
        query += " LIMIT 10"
        alunos = conn.execute(query, params).fetchall()
        
    return {"alunos": [dict(a) for a in alunos]}

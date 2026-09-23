# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, session, flash, Response
import csv
import io
import re
import qrcode
import base64
from io import BytesIO
from database import closing, get_db_connection
from utils.auth import is_logged_in_admin, tem_permissao
from utils.helpers import datetime_now_str, date_hoje_str, sanitize_field, registrar_auditoria
from . import admin_bp

@admin_bp.route('/admin/eventos', methods=['GET', 'POST'])
def admin_eventos():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('eventos'): return redirect(url_for('admin.admin_dashboard'))
    
    if request.method == 'POST':
        nome_evento = request.form.get('nome')
        data_inicio = request.form.get('data_inicio')
        data_fim = request.form.get('data_fim')
        if nome_evento and data_inicio and data_fim:
            with closing(get_db_connection()) as conn:
                conn.execute("INSERT INTO turmas (nome, is_evento, data_inicio, data_fim) VALUES (?, 1, ?, ?)", (nome_evento, data_inicio, data_fim))
                conn.commit()
                registrar_auditoria("Criar Evento", f"Criou o evento: {nome_evento}")
                flash('Evento criado com sucesso!', 'success')
        return redirect(url_for('admin.admin_eventos'))
        
    with closing(get_db_connection()) as conn:
        eventos = conn.execute("SELECT * FROM turmas WHERE is_evento = 1 ORDER BY nome").fetchall()
        
    return render_template('admin/eventos.html', eventos=eventos)

@admin_bp.route('/admin/eventos/<int:id>/imprimir')
def admin_evento_imprimir(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('eventos'): return redirect(url_for('admin.admin_dashboard'))
    
    aluno_id_filtro = request.args.get('aluno_id', type=int)
    
    with closing(get_db_connection()) as conn:
        evento = conn.execute("SELECT * FROM turmas WHERE id = ? AND is_evento = 1", (id,)).fetchone()
        if not evento:
            flash('Evento não encontrado.', 'error')
            return redirect(url_for('admin.admin_eventos'))
            
        sql = """
            SELECT a.nome, a.cpf, ep.codigo_cracha
            FROM eventos_participantes ep
            JOIN alunos a ON ep.aluno_id = a.id
            WHERE ep.turma_id = ?
        """
        params = [id]
        
        if aluno_id_filtro:
            sql += " AND a.id = ?"
            params.append(aluno_id_filtro)
            
        sql += " ORDER BY a.nome ASC"
        participantes = conn.execute(sql, params).fetchall()
        
        # Gerar QR Codes em base64 para cada um
        crachas = []
        for p in participantes:
            qr_b64 = ""
            if p['codigo_cracha']:
                qr = qrcode.QRCode(version=1, box_size=5, border=2)
                qr.add_data(p['codigo_cracha'])
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                qr_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                
            crachas.append({
                'nome': p['nome'],
                'cpf': p['cpf'],
                'codigo': p['codigo_cracha'],
                'qr_code': qr_b64
            })
            
    registrar_auditoria("Imprimir Crachás Evento", f"Gerou visualização de impressão de crachás do evento ID {id}")
    return render_template('admin/evento_imprimir.html', evento=evento, crachas=crachas)

@admin_bp.route('/admin/eventos/<int:id>')
def admin_evento_detalhe(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('eventos'): return redirect(url_for('admin.admin_dashboard'))
    
    with closing(get_db_connection()) as conn:
        evento = conn.execute("SELECT * FROM turmas WHERE id = ? AND is_evento = 1", (id,)).fetchone()
        if not evento:
            flash('Evento não encontrado.', 'error')
            return redirect(url_for('admin.admin_eventos'))
            
        convidados = conn.execute("""
            SELECT a.* 
            FROM alunos a 
            JOIN eventos_participantes ep ON a.id = ep.aluno_id 
            WHERE ep.turma_id = ? 
            ORDER BY a.nome
        """, (id,)).fetchall()
        
    return render_template('admin/evento_detalhe.html', evento=evento, convidados=convidados)

@admin_bp.route('/admin/eventos/<int:id>/adicionar', methods=['POST'])
def admin_evento_adicionar_participante(id):
    """Adiciona manualmente um participante ao evento (existente ou novo)."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('eventos'): return redirect(url_for('admin.admin_dashboard'))
    
    nome = sanitize_field(request.form.get('nome'))
    cpf = sanitize_field(request.form.get('cpf'))
    data_nascimento = sanitize_field(request.form.get('data_nascimento'))
    email = sanitize_field(request.form.get('email', ''))
    instituicao = sanitize_field(request.form.get('instituicao', ''))
    
    if not nome or not cpf or not data_nascimento:
        flash('Nome, CPF e Data de Nascimento são obrigatórios.', 'error')
        return redirect(url_for('admin.admin_evento_detalhe', id=id))
        
    cpf_clean = re.sub(r'\D', '', cpf)
    cpf_formatted = f"{cpf_clean[:3]}.{cpf_clean[3:6]}.{cpf_clean[6:9]}-{cpf_clean[9:]}" if len(cpf_clean) == 11 else cpf_clean
    matricula = "EVT-" + cpf_clean
    
    with closing(get_db_connection()) as conn:
        try:
            # 1. Tenta achar o aluno
            aluno = conn.execute("SELECT id FROM alunos WHERE cpf = ? OR cpf = ? OR cpf = ? OR matricula = ?", 
                               (cpf, cpf_clean, cpf_formatted, matricula)).fetchone()
            
            if not aluno:
                # Cria novo aluno
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO alunos (nome, matricula, cpf, data_nascimento, email, instituicao, turma_id, permitido_almoco) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                    (nome, matricula, cpf_formatted, data_nascimento, email, instituicao, id)
                )
                aluno_id = cur.lastrowid
            else:
                aluno_id = aluno['id']
                
            # 2. Vincula ao evento
            try:
                codigo_cracha = generate_badge_code(id, aluno_id)
                conn.execute("INSERT INTO eventos_participantes (aluno_id, turma_id, codigo_cracha) VALUES (?, ?, ?)", (aluno_id, id, codigo_cracha))
                registrar_auditoria("Adicionar Participante Evento", f"Adicionou participante ID {aluno_id} ao evento ID {id}")
                flash(f'{nome} adicionado ao evento!', 'success')
            except sqlite3.IntegrityError:
                # Garante código se estiver sem
                conn.execute("UPDATE eventos_participantes SET codigo_cracha = ? WHERE aluno_id = ? AND turma_id = ? AND codigo_cracha IS NULL", (generate_badge_code(id, aluno_id), aluno_id, id))
                flash(f'{nome} já participa deste evento.', 'info')
                
            conn.commit()
        except Exception as e:
            flash(f'Erro ao adicionar participante: {str(e)}', 'error')
            
    return redirect(url_for('admin.admin_evento_detalhe', id=id))

@admin_bp.route('/admin/eventos/<int:id>/remover/<int:aluno_id>', methods=['POST'])
def admin_evento_remover_participante(id, aluno_id):
    """Remove um participante do evento (remove o vínculo e limpa visitantes temporários órfãos)."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('eventos'): return redirect(url_for('admin.admin_dashboard'))
    
    with closing(get_db_connection()) as conn:
        conn.execute("DELETE FROM eventos_participantes WHERE aluno_id = ? AND turma_id = ?", (aluno_id, id))
        
        # Se for participante temporário (visitante), e não estiver em nenhum outro evento, deleta o aluno
        aluno = conn.execute("SELECT matricula FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
        if aluno and aluno['matricula'].startswith('EVT-'):
            outros_vinculos = conn.execute("SELECT COUNT(*) FROM eventos_participantes WHERE aluno_id = ?", (aluno_id,)).fetchone()[0]
            if outros_vinculos == 0:
                conn.execute("DELETE FROM reservas WHERE aluno_id = ?", (aluno_id,))
                conn.execute("DELETE FROM alunos WHERE id = ?", (aluno_id,))
                
        conn.commit()
        registrar_auditoria("Remover Participante Evento", f"Removeu o aluno ID {aluno_id} do evento ID {id}")
        flash('Participante removido do evento com sucesso.', 'success')
        
    return redirect(url_for('admin.admin_evento_detalhe', id=id))

@admin_bp.route('/admin/eventos/<int:id>/editar_participante/<int:aluno_id>', methods=['POST'])
def admin_evento_editar_participante(id, aluno_id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('eventos'): return redirect(url_for('admin.admin_dashboard'))
    
    nome = sanitize_field(request.form.get('nome'))
    cpf = sanitize_field(request.form.get('cpf'))
    data_nascimento = sanitize_field(request.form.get('data_nascimento'))
    email = sanitize_field(request.form.get('email', ''))
    instituicao = sanitize_field(request.form.get('instituicao', ''))
    
    if not nome or not cpf or not data_nascimento:
        flash('Nome, CPF e Data de Nascimento são obrigatórios.', 'error')
        return redirect(url_for('admin.admin_evento_detalhe', id=id))
        
    cpf_clean = re.sub(r'\D', '', cpf)
    cpf_formatted = f"{cpf_clean[:3]}.{cpf_clean[3:6]}.{cpf_clean[6:9]}-{cpf_clean[9:]}" if len(cpf_clean) == 11 else cpf_clean
    
    with closing(get_db_connection()) as conn:
        try:
            # Checar se o CPF alterado já pertence a outro aluno
            duplicado = conn.execute("SELECT id FROM alunos WHERE (cpf = ? OR cpf = ? OR cpf = ?) AND id != ?", 
                                     (cpf, cpf_clean, cpf_formatted, aluno_id)).fetchone()
            if duplicado:
                flash('Erro ao editar: CPF já cadastrado para outro participante/aluno.', 'error')
                return redirect(url_for('admin.admin_evento_detalhe', id=id))
            
            # Checar se o aluno a ser editado é visitante ou regular
            aluno = conn.execute("SELECT matricula FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
            if aluno:
                if aluno['matricula'].startswith('EVT-'):
                    # Atualiza com matricula EVT- (por segurança)
                    nova_matricula = "EVT-" + cpf_clean
                    conn.execute("""
                        UPDATE alunos 
                        SET nome=?, matricula=?, cpf=?, data_nascimento=?, email=?, instituicao=?
                        WHERE id=?
                    """, (nome, nova_matricula, cpf_formatted, data_nascimento, email, instituicao, aluno_id))
                else:
                    # Aluno regular - não altera a matrícula
                    conn.execute("""
                        UPDATE alunos 
                        SET nome=?, cpf=?, data_nascimento=?, email=?, instituicao=?
                        WHERE id=?
                    """, (nome, cpf_formatted, data_nascimento, email, instituicao, aluno_id))
                
                # Atualizar o código do crachá do participante no evento se necessário
                codigo_cracha = generate_badge_code(id, aluno_id)
                conn.execute("UPDATE eventos_participantes SET codigo_cracha = ? WHERE aluno_id = ? AND turma_id = ?", 
                             (codigo_cracha, aluno_id, id))
                
                conn.commit()
                registrar_auditoria("Editar Participante Evento", f"Editou crachá/dados do aluno ID {aluno_id} no evento ID {id}")
                flash('Participante atualizado com sucesso!', 'success')
        except Exception as e:
            flash(f'Erro ao atualizar participante: {str(e)}', 'error')
            
    return redirect(url_for('admin.admin_evento_detalhe', id=id))

@admin_bp.route('/admin/eventos/<int:id>/editar', methods=['POST'])
def admin_evento_editar(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('eventos'): return redirect(url_for('admin.admin_dashboard'))
    
    nome = request.form.get('nome')
    data_inicio = request.form.get('data_inicio')
    data_fim = request.form.get('data_fim')
    
    with closing(get_db_connection()) as conn:
        conn.execute(
            "UPDATE turmas SET nome = ?, data_inicio = ?, data_fim = ? WHERE id = ? AND is_evento = 1",
            (nome, data_inicio, data_fim, id)
        )
        conn.commit()
        registrar_auditoria("Editar Evento", f"Atualizou dados do evento ID {id} (Nome: {nome})")
        flash('Evento atualizado com sucesso!', 'success')
        
    return redirect(url_for('admin.admin_evento_detalhe', id=id))

@admin_bp.route('/admin/eventos/<int:id>/deletar', methods=['POST'])
def admin_evento_deletar(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('eventos'): return redirect(url_for('admin.admin_dashboard'))
    
    with closing(get_db_connection()) as conn:
        # Apagar reservas dos alunos temporários deste evento
        conn.execute("""
            DELETE FROM reservas 
            WHERE aluno_id IN (SELECT id FROM alunos WHERE turma_id = ? AND matricula LIKE 'EVT-%')
        """, (id,))
        
        # Apagar os alunos temporários (criados exclusivamente para este evento)
        conn.execute("DELETE FROM alunos WHERE turma_id = ? AND matricula LIKE 'EVT-%'", (id,))
        
        # Delete ligações deste evento na tabela eventos_participantes (desvincula alunos regulares)
        conn.execute("DELETE FROM eventos_participantes WHERE turma_id = ?", (id,))
        
        # Apaga o evento em si
        conn.execute("DELETE FROM turmas WHERE id = ? AND is_evento = 1", (id,))
        conn.commit()
        registrar_auditoria("Deletar Evento", f"Deletou o evento ID {id}")
        
    flash('Evento e todo o seu histórico foram deletados permanentemente.', 'success')
    return redirect(url_for('admin.admin_eventos'))

@admin_bp.route('/admin/eventos/csv_template')
def admin_evento_csv_template():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('eventos'): return redirect(url_for('admin.admin_dashboard'))
    
    # Modelo amigável para o usuário brasileiro (com DD/MM/AAAA e CPF limpo)
    csv_content = "Nome;CPF (somente números);Data de Nascimento (DD/MM/AAAA);E-mail;Instituição\nConvidado Exemplo;11122233344;15/05/1990;exemplo@email.com;Empresa X\nOutro Convidado;55566677788;20/10/1995;;"
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=modelo_convidados_evento.csv"}
    )

@admin_bp.route('/admin/eventos/<int:id>/importar', methods=['POST'])
def admin_evento_importar(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('eventos'): return redirect(url_for('admin.admin_dashboard'))
    
    if 'arquivo_csv' not in request.files:
        flash('Nenhum arquivo enviado.', 'error')
        return redirect(url_for('admin.admin_evento_detalhe', id=id))
        
    file = request.files['arquivo_csv']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('admin.admin_evento_detalhe', id=id))
        
    try:
        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        csv_input = csv.reader(stream, delimiter=';')
        
        first_row = next(csv_input, None)
        delimiter_used = ';'
        if first_row and len(first_row) == 1 and ',' in first_row[0]:
            delimiter_used = ','
            
        stream.seek(0)
        csv_input = csv.reader(stream, delimiter=delimiter_used)
        next(csv_input, None) # pula o cabecalho
        
        adicionados = 0
        
        with closing(get_db_connection()) as conn:
            for row in csv_input:
                if len(row) >= 3:
                    nome = sanitize_field(row[0])
                    cpf = sanitize_field(row[1])
                    data_nascimento = sanitize_field(row[2])
                    email = sanitize_field(row[3]) if len(row) > 3 else ''
                    instituicao = sanitize_field(row[4]) if len(row) > 4 else ''
                    
                    if not nome or not cpf or not data_nascimento:
                        continue
                        
                    # Converter DD/MM/AAAA para YYYY-MM-DD
                    if '/' in data_nascimento:
                        try:
                            dia, mes, ano = data_nascimento.split('/')
                            data_nascimento = f"{ano.strip()}-{mes.strip().zfill(2)}-{dia.strip().zfill(2)}"
                        except:
                            pass
                        
                    cpf_clean = re.sub(r'\D', '', cpf)
                    if len(cpf_clean) == 11:
                        cpf_formatted = f"{cpf_clean[:3]}.{cpf_clean[3:6]}.{cpf_clean[6:9]}-{cpf_clean[9:]}"
                    else:
                        cpf_formatted = cpf_clean
                        
                    matricula = "EVT-" + cpf_clean
                        
                    try:
                        aluno_existente = conn.execute("SELECT id FROM alunos WHERE cpf = ? OR cpf = ? OR cpf = ? OR matricula = ?", (cpf, cpf_clean, cpf_formatted, matricula)).fetchone()
                        if not aluno_existente:
                            cur = conn.cursor()
                            cur.execute(
                                "INSERT INTO alunos (nome, matricula, cpf, data_nascimento, email, instituicao, turma_id, permitido_almoco) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                                (nome, matricula, cpf_formatted, data_nascimento, email, instituicao, id)
                            )
                            aluno_id = cur.lastrowid
                        else:
                            aluno_id = aluno_existente['id']
                            
                        # Insere o participante no evento (se não existir a ligação)
                        try:
                            # Gerar código do crachá fixo
                            codigo_cracha = generate_badge_code(id, aluno_id)
                            conn.execute("INSERT INTO eventos_participantes (aluno_id, turma_id, codigo_cracha) VALUES (?, ?, ?)", (aluno_id, id, codigo_cracha))
                            adicionados += 1
                        except sqlite3.IntegrityError:
                            # Se já existir sem código, garante que tenha um
                            conn.execute("UPDATE eventos_participantes SET codigo_cracha = ? WHERE aluno_id = ? AND turma_id = ? AND codigo_cracha IS NULL", (generate_badge_code(id, aluno_id), aluno_id, id))
                            
                    except Exception as e:
                        print(f"Erro na linha CSV (Evento): {e}")
            conn.commit()
            registrar_auditoria("Importar Participantes Evento CSV", f"Importou {adicionados} participantes via CSV no evento ID {id}")
            
        flash(f'Importação concluída! {adicionados} convidado(s) adicionado(s).', 'success')
    except Exception as e:
        flash(f'Erro lendo arquivo CSV: {str(e)}', 'error')
        
    return redirect(url_for('admin.admin_evento_detalhe', id=id))

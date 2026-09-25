# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, session, flash, current_app, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import json
import time
import os
import re
import secrets
from datetime import datetime, timedelta

from database import closing, get_db_connection, get_config
from utils.auth import is_logged_in_admin, tem_permissao
from utils.helpers import datetime_now_str, date_hoje_str, sanitize_field, registrar_auditoria, normalizar_cpf
from utils.mailer import enviar_email_recuperacao, diagnosticar_smtp
from . import admin_bp

@admin_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        ip = request.remote_addr
        from utils.auth import login_limiter
        if login_limiter.is_blocked(ip):
            flash('Muitas tentativas de login de seu IP. Aguarde 60 segundos.', 'error')
            return render_template('admin/login.html')
        login_limiter.record_attempt(ip)

        user = request.form.get('usuario')
        senha = request.form.get('senha')
        lembrar_me = request.form.get('lembrar_me') == 'on'
        with closing(get_db_connection()) as conn:
            admin = conn.execute("SELECT * FROM administradores WHERE usuario = ?", (user,)).fetchone()
            if admin:
                # Verificar se é um hash do Werkzeug (contém ':') ou senha antiga
                senha_valida = False
                if admin['senha'] and ':' in admin['senha']:
                    try:
                        senha_valida = check_password_hash(admin['senha'], senha)
                    except:
                        senha_valida = False
                
                if not senha_valida:
                    # Tentar formatos legados para migração
                    import hashlib
                    hash_antigo = hashlib.sha256(senha.encode()).hexdigest()
                    if admin['senha'] == hash_antigo or admin['senha'] == senha:
                        senha_valida = True
                        # Migrar para o novo hash seguro imediatamente
                        novo_hash = generate_password_hash(senha)
                        conn.execute("UPDATE administradores SET senha = ? WHERE id = ?", (novo_hash, admin['id']))
                        conn.commit()
                
                if senha_valida:
                    session.permanent = lembrar_me
                    session['is_admin'] = True
                    session['admin_id'] = admin['id']
                    session['admin_usuario'] = admin['usuario']
                    session['admin_nome'] = admin['nome'] if 'nome' in admin.keys() and admin['nome'] else admin['usuario']
                    session['admin_email'] = admin['email'] if 'email' in admin.keys() and admin['email'] else ''
                    session['admin_setor'] = admin['setor'] if 'setor' in admin.keys() and admin['setor'] else ''
                    session['admin_perfil'] = admin['perfil'] if 'perfil' in admin.keys() else 'operador'
                    session['admin_modo_escuro'] = admin['modo_escuro'] if 'modo_escuro' in admin.keys() and admin['modo_escuro'] else 0
                    session['admin_tema'] = admin['tema_preferido'] if 'tema_preferido' in admin.keys() and admin['tema_preferido'] else ''
                    
                    # Carregar Permissões
                    try:
                        session['admin_permissoes'] = json.loads(admin['permissoes'] or '[]')
                    except:
                        session['admin_permissoes'] = []
                        
                    registrar_auditoria("Login", f"Usuário {admin['usuario']} logou no sistema")
                    
                    if tem_permissao('fila') and not tem_permissao('all') and len(session['admin_permissoes']) == 1:
                        return redirect(url_for('admin.admin_entrega'))
                        
                    return redirect(url_for('admin.admin_dashboard'))
            
        time.sleep(1) # Prevenir força bruta
        flash('Credenciais inválidas.', 'error')
    return render_template('admin/login.html')

@admin_bp.route('/admin/logout')
def admin_logout():
    registrar_auditoria("Logout", f"Usuário {session.get('admin_usuario')} saiu do sistema")
    session.pop('is_admin', None)
    session.pop('admin_id', None)
    session.pop('admin_usuario', None)
    session.pop('admin_nome', None)
    session.pop('admin_email', None)
    session.pop('admin_setor', None)
    session.pop('admin_perfil', None)
    session.pop('admin_permissoes', None)
    session.pop('admin_modo_escuro', None)
    session.pop('admin_tema', None)
    return redirect(url_for('admin.admin_login'))

@admin_bp.route('/admin')
def admin_dashboard():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    
    with closing(get_db_connection()) as conn:
        total_alunos = conn.execute("SELECT COUNT(*) FROM alunos WHERE matricula NOT LIKE 'EVT-%'").fetchone()[0]
        total_turmas = conn.execute("SELECT COUNT(*) FROM turmas WHERE is_evento = 0").fetchone()[0]
        total_eventos = conn.execute("""
            SELECT COUNT(*) 
            FROM turmas 
            WHERE is_evento = 1 
              AND (data_inicio IS NULL OR data_inicio <= date('now', 'localtime'))
              AND (data_fim IS NULL OR data_fim >= date('now', 'localtime'))
        """).fetchone()[0]
        total_visitantes = conn.execute("SELECT COUNT(*) FROM alunos WHERE matricula LIKE 'EVT-%'").fetchone()[0]
        config = conn.execute("SELECT * FROM configuracoes WHERE id = 1").fetchone()

        # Métricas operacionais do dia
        hoje = date_hoje_str()
        cardapio_hoje = conn.execute("SELECT * FROM cardapios WHERE data = ?", (hoje,)).fetchone()
        
        refeicoes_servidas_hoje = 0
        reservas_hoje = 0
        reservas_normais_hoje = 0
        extras_hoje = 0
        eventos_hoje = 0
        ultimas_retiradas = []
        
        if cardapio_hoje:
            refeicoes_servidas_hoje = conn.execute(
                "SELECT COUNT(*) FROM reservas WHERE cardapio_id = ? AND status = 'CONSUMIDA'", 
                (cardapio_hoje['id'],)
            ).fetchone()[0]
            
            # Reservas agendadas (estudantes regulares)
            reservas_normais_hoje = conn.execute(
                "SELECT COUNT(*) FROM reservas WHERE cardapio_id = ? AND status IN ('ATIVA', 'CONSUMIDA') AND (tipo_consumo = 'NORMAL' OR tipo_consumo IS NULL)", 
                (cardapio_hoje['id'],)
            ).fetchone()[0]

            # Participantes de eventos agendados
            eventos_hoje = conn.execute(
                "SELECT COUNT(*) FROM reservas WHERE cardapio_id = ? AND status IN ('ATIVA', 'CONSUMIDA') AND tipo_consumo = 'EVENTO'", 
                (cardapio_hoje['id'],)
            ).fetchone()[0]

            # Extras entregues (sem reserva prévia)
            extras_hoje = conn.execute(
                "SELECT COUNT(*) FROM reservas WHERE cardapio_id = ? AND status = 'CONSUMIDA' AND tipo_consumo = 'EXTRA'", 
                (cardapio_hoje['id'],)
            ).fetchone()[0]

            # Número principal do card: estritamente reservas regulares do portal
            reservas_hoje = reservas_normais_hoje
            
            ultimas_retiradas = conn.execute("""
                SELECT r.codigo_unico, r.data_registro, a.nome as aluno_nome, a.matricula, t.nome as turma_nome
                FROM reservas r
                JOIN alunos a ON r.aluno_id = a.id
                LEFT JOIN turmas t ON a.turma_id = t.id
                WHERE r.cardapio_id = ? AND r.status = 'CONSUMIDA'
                ORDER BY r.id DESC
                LIMIT 5
            """, (cardapio_hoje['id'],)).fetchall()
        
    return render_template('admin/dashboard.html', 
                           total_alunos=total_alunos, 
                           total_turmas=total_turmas, 
                           total_eventos=total_eventos,
                           total_visitantes=total_visitantes,
                           config=config,
                           refeicoes_servidas_hoje=refeicoes_servidas_hoje,
                           reservas_hoje=reservas_hoje,
                           reservas_normais_hoje=reservas_normais_hoje,
                           extras_hoje=extras_hoje,
                           eventos_hoje=eventos_hoje,
                           cardapio_hoje=cardapio_hoje,
                           ultimas_retiradas=ultimas_retiradas)

# --- CRUD de Administradores ---

@admin_bp.route('/admin/administradores', methods=['GET', 'POST'])
def admin_administradores():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('admins'): return redirect(url_for('admin.admin_dashboard'))
    
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        cpf_raw = request.form.get('cpf', '').strip()
        cpf_clean, cpf_formatted = normalizar_cpf(cpf_raw)
        cpf = cpf_formatted if cpf_clean else cpf_raw
        setor = request.form.get('setor', '').strip()
        email = request.form.get('email', '').strip().lower()
        usuario = request.form.get('usuario', '').strip().lower()
        senha = request.form.get('senha', '')
        
        if not usuario or not senha:
            flash('Usuário e Senha são campos obrigatórios.', 'error')
            return redirect(url_for('admin.admin_administradores'))

        if cpf_raw and not cpf_clean:
            flash('CPF inválido. O CPF deve conter 11 dígitos numéricos.', 'error')
            return redirect(url_for('admin.admin_administradores'))
        
        plist = request.form.getlist('permissoes[]')
        
        todas_perms = {'turmas', 'alunos', 'cardapios', 'relatorios', 'avisos', 'fila', 'admins', 'config', 'smtp', 'qualidade', 'eventos', 'base_conhecimento', 'pesquisas'}
        if 'all' in plist:
            perfil = 'admin_mestre'
            plist = ['all']
        else:
            plist = [p for p in plist if p in todas_perms]
            if todas_perms.issubset(set(plist)):
                perfil = 'admin_mestre'
                plist = ['all']
            elif plist:
                perfil = 'operador'
            else:
                perfil = 'operador'
                plist = []
        
        permissoes_json = json.dumps(plist)
        hash_senha = generate_password_hash(senha)
        
        try:
            with closing(get_db_connection()) as conn:
                # Checar se usuário já existe
                if conn.execute("SELECT id FROM administradores WHERE LOWER(usuario) = LOWER(?)", (usuario,)).fetchone():
                    flash(f'O usuário "{usuario}" já está em uso.', 'error')
                    return redirect(url_for('admin.admin_administradores'))
                
                # Checar se CPF já existe
                if cpf and conn.execute("SELECT id FROM administradores WHERE cpf = ?", (cpf,)).fetchone():
                    flash(f'Já existe um administrador cadastrado com o CPF {cpf}.', 'error')
                    return redirect(url_for('admin.admin_administradores'))

                # Checar se e-mail já existe
                if email and conn.execute("SELECT id FROM administradores WHERE LOWER(email) = LOWER(?)", (email,)).fetchone():
                    flash(f'Já existe um administrador cadastrado com o e-mail {email}.', 'error')
                    return redirect(url_for('admin.admin_administradores'))

                conn.execute("""
                    INSERT INTO administradores (usuario, senha, nome, cpf, setor, email, perfil, permissoes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (usuario, hash_senha, nome, cpf, setor, email, perfil, permissoes_json))
                conn.commit()

                detalhes_log = f"Criou admin: {nome or usuario} (@{usuario})"
                if setor: detalhes_log += f" | Setor: {setor}"
                if cpf: detalhes_log += f" | CPF: {cpf}"
                registrar_auditoria("Criar Administrador", detalhes_log)
                flash('Credencial de administrador adicionada com sucesso!', 'success')
        except Exception as e:
            flash(f'Erro ao cadastrar administrador: {e}', 'error')
        return redirect(url_for('admin.admin_administradores'))
        
    with closing(get_db_connection()) as conn:
        admins = conn.execute("SELECT * FROM administradores ORDER BY id ASC").fetchall()
    return render_template('admin/administradores.html', admins=admins)

@admin_bp.route('/admin/administradores/excluir/<int:id>', methods=['POST'])
def admin_administradores_excluir(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('admins'): return redirect(url_for('admin.admin_dashboard'))
    with closing(get_db_connection()) as conn:
        admin = conn.execute("SELECT usuario FROM administradores WHERE id = ?", (id,)).fetchone()
        usuario_txt = admin['usuario'] if admin else f"ID {id}"
        conn.execute("DELETE FROM administradores WHERE id = ? AND usuario != 'admin'", (id,))
        conn.commit()
        registrar_auditoria("Revogar Acesso Administrador", f"Revogou o acesso do admin: {usuario_txt}")
        flash('Acesso revogado.', 'success')
    return redirect(url_for('admin.admin_administradores'))

@admin_bp.route('/admin/administradores/alterar_senha/<int:id>', methods=['POST'])
def admin_administradores_alterar_senha(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    
    # Pode alterar se for mestre, se tiver permissão de admins ou se for a própria conta
    pode_alterar = session.get('admin_id') == id or tem_permissao('admins')
    if not pode_alterar: return redirect(url_for('admin.admin_dashboard'))
    
    nova_senha = request.form.get('nova_senha')
    if not nova_senha or len(nova_senha) < 6:
        flash('Senha muito curta. Use ao menos 6 caracteres.', 'error')
        return redirect(url_for('admin.admin_administradores'))
        
    hash_senha = generate_password_hash(nova_senha)
    with closing(get_db_connection()) as conn:
        admin = conn.execute("SELECT usuario FROM administradores WHERE id = ?", (id,)).fetchone()
        usuario_txt = admin['usuario'] if admin else f"ID {id}"
        conn.execute("UPDATE administradores SET senha = ? WHERE id = ?", (hash_senha, id))
        conn.commit()
        registrar_auditoria("Alterar Senha Administrador", f"Alterou a senha do administrador: {usuario_txt}")
        flash('Senha do administrador alterada com sucesso!', 'success')
        
    return redirect(url_for('admin.admin_administradores'))

@admin_bp.route('/admin/administradores/editar/<int:id>', methods=['POST'])
def admin_administradores_editar(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('admins'): return redirect(url_for('admin.admin_dashboard'))
    
    nome = request.form.get('nome', '').strip()
    cpf_raw = request.form.get('cpf', '').strip()
    cpf_clean, cpf_formatted = normalizar_cpf(cpf_raw)
    cpf = cpf_formatted if cpf_clean else cpf_raw
    setor = request.form.get('setor', '').strip()
    email = request.form.get('email', '').strip().lower()

    if cpf_raw and not cpf_clean:
        flash('CPF inválido. O CPF deve conter 11 dígitos numéricos.', 'error')
        return redirect(url_for('admin.admin_administradores'))

    plist = request.form.getlist('permissoes[]')
    
    todas_perms = {'turmas', 'alunos', 'cardapios', 'relatorios', 'avisos', 'fila', 'admins', 'config', 'smtp', 'qualidade', 'eventos', 'base_conhecimento', 'pesquisas'}
    if 'all' in plist:
        perfil = 'admin_mestre'
        plist = ['all']
    else:
        plist = [p for p in plist if p in todas_perms]
        if todas_perms.issubset(set(plist)):
            perfil = 'admin_mestre'
            plist = ['all']
        elif plist:
            perfil = 'operador'
        else:
            perfil = 'operador'
            plist = []
    
    permissoes_json = json.dumps(plist)
    
    with closing(get_db_connection()) as conn:
        admin = conn.execute("SELECT * FROM administradores WHERE id = ?", (id,)).fetchone()
        if not admin:
            flash('Administrador não encontrado.', 'error')
            return redirect(url_for('admin.admin_administradores'))

        # Checar unicidade de CPF
        if cpf:
            conf_cpf = conn.execute("SELECT id FROM administradores WHERE cpf = ? AND id != ?", (cpf, id)).fetchone()
            if conf_cpf:
                flash(f'Já existe outro administrador cadastrado com o CPF {cpf}.', 'error')
                return redirect(url_for('admin.admin_administradores'))

        # Checar unicidade de e-mail
        if email:
            conf_email = conn.execute("SELECT id FROM administradores WHERE LOWER(email) = LOWER(?) AND id != ?", (email, id)).fetchone()
            if conf_email:
                flash(f'Já existe outro administrador cadastrado com o e-mail {email}.', 'error')
                return redirect(url_for('admin.admin_administradores'))

        usuario_txt = admin['usuario']
        conn.execute("""
            UPDATE administradores 
            SET nome = ?, cpf = ?, setor = ?, email = ?, perfil = ?, permissoes = ? 
            WHERE id = ?
        """, (nome, cpf, setor, email, perfil, permissoes_json, id))
        conn.commit()

        registrar_auditoria("Editar Administrador", f"Atualizou admin {usuario_txt} ({nome or 'sem nome'}): Setor={setor}, CPF={cpf}, E-mail={email}, Perfil={perfil}")
        
        # Se o admin editado for o próprio logado, atualizar sessão IMEDIATAMENTE
        if session.get('admin_id') == id:
            session['admin_nome'] = nome or usuario_txt
            session['admin_email'] = email
            session['admin_setor'] = setor
            session['admin_perfil'] = perfil
            session['admin_permissoes'] = json.loads(permissoes_json)
            
    flash('Dados e permissões do administrador atualizados com sucesso!', 'success')
    return redirect(url_for('admin.admin_administradores'))

# --- Recuperação de Senha de Administradores ---

@admin_bp.route('/admin/esqueci_senha', methods=['GET', 'POST'])
def admin_esqueci_senha():
    """Solicitação de redefinição de senha para administradores por CPF, E-mail ou Usuário."""
    if request.method == 'POST':
        identificador = request.form.get('identificador', '').strip()
        if not identificador:
            flash('Informe seu CPF, E-mail ou Usuário de administrador.', 'error')
            return render_template('admin/esqueci_senha.html')

        ident_clean, ident_cpf = normalizar_cpf(identificador)
        if not ident_clean:
            ident_clean = re.sub(r'\D', '', identificador)
            ident_cpf = identificador

        with closing(get_db_connection()) as conn:
            admin = conn.execute("""
                SELECT * FROM administradores 
                WHERE LOWER(usuario) = LOWER(?) 
                   OR LOWER(email) = LOWER(?) 
                   OR cpf = ? 
                   OR cpf = ?
                LIMIT 1
            """, (identificador, identificador, identificador, ident_cpf)).fetchone()

            if not admin:
                flash('Nenhum administrador localizado com a credencial informada.', 'error')
                return render_template('admin/esqueci_senha.html')

            if not admin['email']:
                flash(f"O administrador '{admin['usuario']}' não possui e-mail cadastrado. Solicite a redefinição a um Administrador Mestre.", 'error')
                return render_template('admin/esqueci_senha.html')

            config = conn.execute('SELECT * FROM configuracoes WHERE id = 1').fetchone()
            if not config or not config['smtp_ativo'] or not config['smtp_host']:
                flash('O envio de e-mails automáticos (SMTP) não está ativo no sistema. Contate a direção para redefinir a senha.', 'error')
                return render_template('admin/esqueci_senha.html')

            token = secrets.token_hex(16)
            expiracao = datetime.now() + timedelta(hours=1)

            conn.execute("""
                UPDATE administradores 
                SET reset_token = ?, reset_expiracao = ? 
                WHERE id = ?
            """, (token, expiracao.strftime('%Y-%m-%d %H:%M:%S'), admin['id']))
            conn.commit()

            url_recuperacao = url_for('admin.admin_recuperar_senha', token=token, _external=True)
            sucesso = enviar_email_recuperacao(
                {'nome': admin['nome'] or admin['usuario'], 'email': admin['email']},
                url_recuperacao,
                config,
                is_admin=True
            )

            if sucesso:
                registrar_auditoria("Solicitar Recuperação Admin", f"Token de recuperação gerado para {admin['usuario']} ({admin['email']})")
                flash(f"Sucesso! Enviamos as instruções de recuperação para o e-mail ({admin['email']}). O link é válido por 1 hora.", 'success')
                return redirect(url_for('admin.admin_login'))
            else:
                flash('Falha no envio do e-mail de recuperação. Verifique as configurações de SMTP.', 'error')

    return render_template('admin/esqueci_senha.html')

@admin_bp.route('/admin/recuperar_senha/<token>', methods=['GET', 'POST'])
def admin_recuperar_senha(token):
    """Redefinição de senha de administrador através de token seguro enviado por e-mail."""
    with closing(get_db_connection()) as conn:
        admin = conn.execute("SELECT * FROM administradores WHERE reset_token = ?", (token,)).fetchone()
        if not admin:
            flash('Código de recuperação inválido ou já utilizado.', 'error')
            return redirect(url_for('admin.admin_login'))

        try:
            expiracao = datetime.strptime(admin['reset_expiracao'], '%Y-%m-%d %H:%M:%S')
        except Exception:
            expiracao = datetime.min

        if datetime.now() > expiracao:
            flash('O link de recuperação expirou (prazo de 1 hora excedido). Solicite uma nova recuperação.', 'error')
            return redirect(url_for('admin.admin_esqueci_senha'))

        if request.method == 'POST':
            nova_senha = request.form.get('nova_senha', '')
            confirma_senha = request.form.get('confirma_senha', '')

            if len(nova_senha) < 6:
                flash('Senha muito curta. Digite ao menos 6 caracteres.', 'error')
                return render_template('admin/recuperar_senha.html', token=token, admin=admin)

            if nova_senha != confirma_senha:
                flash('A confirmação da senha não coincide com a nova senha digitada.', 'error')
                return render_template('admin/recuperar_senha.html', token=token, admin=admin)

            hash_novo = generate_password_hash(nova_senha)
            conn.execute("""
                UPDATE administradores 
                SET senha = ?, reset_token = NULL, reset_expiracao = NULL 
                WHERE id = ?
            """, (hash_novo, admin['id']))
            conn.commit()

            registrar_auditoria("Recuperar Senha Admin", f"Senha do administrador '{admin['usuario']}' redefinida com sucesso via token de e-mail.")
            flash('Sua senha de administrador foi redefinida com sucesso! Faça login com a nova credencial.', 'success')
            return redirect(url_for('admin.admin_login'))

    return render_template('admin/recuperar_senha.html', token=token, admin=admin)

# --- CRUD de Avisos ---

@admin_bp.route('/admin/avisos', methods=['GET', 'POST'])
def admin_avisos():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('avisos'): return redirect(url_for('admin.admin_dashboard'))
    
    if request.method == 'POST':
        titulo = request.form.get('titulo')
        mensagem = request.form.get('mensagem')
        tipo = request.form.get('tipo', 'info')
        data_criacao = datetime_now_str()
        
        with closing(get_db_connection()) as conn:
            conn.execute("INSERT INTO avisos (titulo, mensagem, tipo, data_criacao) VALUES (?, ?, ?, ?)", (titulo, mensagem, tipo, data_criacao))
            conn.commit()
            registrar_auditoria("Criar Aviso", f"Publicou aviso: {titulo}")
            flash('Aviso publicado para os alunos.', 'success')
        return redirect(url_for('admin.admin_avisos'))
        
    with closing(get_db_connection()) as conn:
        avisos = conn.execute("SELECT * FROM avisos ORDER BY id DESC").fetchall()
    return render_template('admin/avisos.html', avisos=avisos)

@admin_bp.route('/admin/avisos/excluir/<int:id>', methods=['POST'])
def admin_avisos_excluir(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    with closing(get_db_connection()) as conn:
        conn.execute("DELETE FROM avisos WHERE id = ?", (id,))
        conn.commit()
        registrar_auditoria("Excluir Aviso", f"Removeu o aviso ID {id}")
        flash('Aviso removido do mural!', 'success')
    return redirect(url_for('admin.admin_avisos'))

@admin_bp.route('/admin/avisos/editar/<int:id>', methods=['POST'])
def admin_avisos_editar(id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('avisos'): return redirect(url_for('admin.admin_dashboard'))
    
    titulo = request.form.get('titulo', '').strip()
    mensagem = request.form.get('mensagem', '').strip()
    tipo = request.form.get('tipo', 'info')
    
    if not titulo or not mensagem:
        flash('Título e mensagem são obrigatórios para atualizar o aviso.', 'error')
        return redirect(url_for('admin.admin_avisos'))
        
    with closing(get_db_connection()) as conn:
        conn.execute("UPDATE avisos SET titulo = ?, mensagem = ?, tipo = ? WHERE id = ?", (titulo, mensagem, tipo, id))
        conn.commit()
        registrar_auditoria("Editar Aviso", f"Editou o aviso ID {id}: {titulo}")
        flash('Aviso atualizado com sucesso no mural!', 'success')
    return redirect(url_for('admin.admin_avisos'))

@admin_bp.route('/admin/configuracoes', methods=['GET', 'POST'])
def admin_configuracoes():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not (tem_permissao('config') or tem_permissao('smtp')):
        return redirect(url_for('admin.admin_dashboard'))
    
    if request.method == 'POST':
        return save_configuracoes()
        
    smtp_diagnostic = session.pop('smtp_diagnostic', None)
    with closing(get_db_connection()) as conn:
        config = conn.execute("SELECT * FROM configuracoes WHERE id = 1").fetchone()
        janelas = conn.execute("SELECT * FROM config_janelas_reserva ORDER BY dia_refeicao ASC").fetchall()
    return render_template('admin/configuracoes.html', config=config, janelas=janelas, smtp_diagnostic=smtp_diagnostic)

def save_configuracoes():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('config'):
        flash('Acesso negado: você não possui permissão para alterar as configurações globais.', 'error')
        return redirect(url_for('admin.admin_configuracoes'))
    horario_limite = request.form.get('horario_limite') or '18:00'
    nome_sistema = request.form.get('nome_sistema', 'Cantina Estudantil')
    sigla_instituicao = request.form.get('sigla_instituicao', 'SIGLA')
    modo_login_aluno = request.form.get('modo_login_aluno', 'DATA_NASC')
    max_reservas_ativas = request.form.get('max_reservas_ativas', 1, type=int)
    if max_reservas_ativas < 1: max_reservas_ativas = 1
    email_qr_reserva = 1 if request.form.get('email_qr_reserva') == '1' else 0
    tempo_autologout = request.form.get('tempo_autologout', 60, type=int)
    if tempo_autologout < 0:
        tempo_autologout = 60
    elif tempo_autologout > 0 and tempo_autologout < 10:
        tempo_autologout = 10
    tema_admin = request.form.get('tema_admin', 'padrao')
    permitir_reserva_recorrente = 1 if request.form.get('permitir_reserva_recorrente') == '1' else 0
    
    with closing(get_db_connection()) as conn:
        conn.execute(
            "UPDATE configuracoes SET horario_limite = ?, nome_sistema = ?, sigla_instituicao = ?, "
            "modo_login_aluno = ?, max_reservas_ativas = ?, email_qr_reserva = ?, tempo_autologout = ?, tema_admin = ?, "
            "permitir_reserva_recorrente = ? WHERE id = 1",
            (horario_limite, nome_sistema, sigla_instituicao, modo_login_aluno, max_reservas_ativas, email_qr_reserva, tempo_autologout, tema_admin, permitir_reserva_recorrente)
        )

        # Atualiza a configuração manual de cada dia da semana (0 a 6)
        for dia_idx in range(7):
            prefix = f"janela_{dia_idx}_"
            if f"{prefix}fe_hora" in request.form or f"{prefix}ativo" in request.form or f"{prefix}fe_combo" in request.form:
                ativo = 1 if request.form.get(f"{prefix}ativo") == '1' else 0
                
                ab_combo = request.form.get(f"{prefix}ab_combo")
                if ab_combo and '_' in ab_combo:
                    ab_offset, ab_dia = map(int, ab_combo.split('_'))
                else:
                    ab_dia = request.form.get(f"{prefix}ab_dia", 0, type=int)
                    ab_offset = request.form.get(f"{prefix}ab_offset", 1, type=int)
                    
                fe_combo = request.form.get(f"{prefix}fe_combo")
                if fe_combo and '_' in fe_combo:
                    fe_offset, fe_dia = map(int, fe_combo.split('_'))
                else:
                    fe_dia = request.form.get(f"{prefix}fe_dia", 4 if dia_idx == 0 else max(0, dia_idx - 1), type=int)
                    fe_offset = request.form.get(f"{prefix}fe_offset", 1 if dia_idx == 0 else 0, type=int)
                    
                ab_hora = request.form.get(f"{prefix}ab_hora", "08:00").strip() or "08:00"
                fe_hora = request.form.get(f"{prefix}fe_hora", "14:00" if dia_idx == 0 else "10:00").strip() or "10:00"
                
                conn.execute("""
                    UPDATE config_janelas_reserva
                    SET ativo = ?, abertura_dia_semana = ?, abertura_semana_offset = ?, abertura_horario = ?,
                        fechamento_dia_semana = ?, fechamento_semana_offset = ?, fechamento_horario = ?
                    WHERE dia_refeicao = ?
                """, (ativo, ab_dia, ab_offset, ab_hora, fe_dia, fe_offset, fe_hora, dia_idx))

        conn.commit()
        registrar_auditoria("Alterar Configurações", f"Alterou configurações do sistema e regras das janelas semanais de reserva")
        flash('Configurações gerais e regras das janelas de reserva salvas com sucesso.', 'success')
    return redirect(url_for('admin.admin_configuracoes'))

@admin_bp.route('/admin/configuracoes/logo', methods=['POST'])
def save_logo():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('config'): 
        flash('Acesso negado: você não possui permissão para alterar a logomarca institucional.', 'error')
        return redirect(url_for('admin.admin_configuracoes'))
    
    file = request.files.get('logo_file')
    if file and file.filename != '':
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
            flash('Tipo de arquivo não permitido. Por segurança, envie apenas imagens (.png, .jpg, .jpeg, .webp, .gif).', 'error')
            return redirect(url_for('admin.admin_configuracoes'))
            
        filename = "logo_instituicao" + ext
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        logo_url = '/static/uploads/' + filename
        with closing(get_db_connection()) as conn:
            conn.execute("UPDATE configuracoes SET logo_path = ? WHERE id = 1", (logo_url,))
            conn.commit()
            registrar_auditoria("Alterar Logomarca", "Atualizou a logomarca da instituição")
            flash('Logomarca da Instituição atualizada com sucesso.', 'success')
    else:
         flash('Nenhum arquivo enviado.', 'error')
         
    return redirect(url_for('admin.admin_configuracoes'))

# SMTP Configurações
@admin_bp.route('/admin/configuracoes/smtp', methods=['POST'])
def save_configuracoes_smtp():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('smtp'): 
        flash('Acesso negado: você não possui permissão para alterar as configurações de e-mail SMTP.', 'error')
        return redirect(url_for('admin.admin_configuracoes'))
    
    smtp_ativo = 1 if request.form.get('smtp_ativo') == '1' else 0
    smtp_host = request.form.get('smtp_host')
    smtp_porta = request.form.get('smtp_porta')
    smtp_user = request.form.get('smtp_user')
    smtp_senha = request.form.get('smtp_senha')
    
    with closing(get_db_connection()) as conn:
        if smtp_senha:
            conn.execute("UPDATE configuracoes SET smtp_ativo=?, smtp_host=?, smtp_porta=?, smtp_user=?, smtp_senha=? WHERE id=1", 
                         (smtp_ativo, smtp_host, smtp_porta, smtp_user, smtp_senha))
        else:
            conn.execute("UPDATE configuracoes SET smtp_ativo=?, smtp_host=?, smtp_porta=?, smtp_user=? WHERE id=1", 
                         (smtp_ativo, smtp_host, smtp_porta, smtp_user))
        conn.commit()
        registrar_auditoria("Alterar SMTP", f"Atualizou configurações do SMTP (Host: {smtp_host}, Ativo: {smtp_ativo})")
        flash('Configuração do Servidor SMTP salva com sucesso.', 'success')
        
    return redirect(url_for('admin.admin_configuracoes'))

@admin_bp.route('/admin/configuracoes/smtp/testar', methods=['POST'])
def testar_smtp():
    """Envia um e-mail de teste com diagnóstico detalhado passo a passo."""
    is_ajax = request.is_json or request.headers.get('Accept', '').startswith('application/json') or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if not is_logged_in_admin():
        if is_ajax:
            return jsonify({"success": False, "mensagem": "Sessão expirada. Faça login novamente."}), 401
        return redirect(url_for('admin.admin_login'))
        
    if not tem_permissao('smtp'): 
        msg = 'Acesso negado: você não possui permissão para testar a conexão de e-mail.'
        if is_ajax:
            return jsonify({"success": False, "mensagem": msg}), 403
        flash(msg, 'error')
        return redirect(url_for('admin.admin_configuracoes'))

    email_teste = request.form.get('email_teste', '').strip()
    if not email_teste and request.is_json:
        data = request.get_json(silent=True) or {}
        email_teste = data.get('email_teste', '').strip()

    if not email_teste:
        msg = 'Informe um endereço de e-mail para o teste.'
        if is_ajax:
            return jsonify({"success": False, "mensagem": msg}), 400
        flash(msg, 'error')
        return redirect(url_for('admin.admin_configuracoes'))

    db_config = dict(get_config() or {})
    
    # Permite testar com os dados enviados diretamente do formulário ou com o salvo no banco
    cfg = {
        'smtp_host': request.form.get('smtp_host', '').strip() or db_config.get('smtp_host'),
        'smtp_porta': request.form.get('smtp_porta', '').strip() or db_config.get('smtp_porta'),
        'smtp_user': request.form.get('smtp_user', '').strip() or db_config.get('smtp_user'),
        'smtp_senha': request.form.get('smtp_senha') or db_config.get('smtp_senha'),
        'nome_sistema': db_config.get('nome_sistema'),
        'sigla_instituicao': db_config.get('sigla_instituicao')
    }

    diagnostico = diagnosticar_smtp(cfg, email_teste)

    if diagnostico['success']:
        registrar_auditoria("Testar SMTP", f"Enviou e-mail de teste de SMTP para {email_teste}")
        flash(f'E-mail de teste enviado com sucesso para {email_teste}!', 'success')
    else:
        registrar_auditoria("Testar SMTP", f"Falha no teste para {email_teste}: {diagnostico['mensagem']}")
        flash(f"Falha no teste SMTP: {diagnostico['mensagem']}", 'error')

    if is_ajax:
        return jsonify(diagnostico)

    session['smtp_diagnostic'] = diagnostico
    return redirect(url_for('admin.admin_configuracoes'))

@admin_bp.route('/admin/tema', methods=['POST'])
def admin_salvar_tema():
    if not is_logged_in_admin():
        return {"success": False, "error": "Não autenticado"}, 401
    
    data = request.get_json(silent=True) or request.form
    tema = data.get('tema')
    modo_escuro = data.get('modo_escuro')
    
    temas_validos = {'padrao', 'azul', 'indigo', 'esmeralda', 'grafite', 'vinho', 'ambar'}
    admin_id = session.get('admin_id')
    updates = []
    params = []
    
    if tema:
        if tema not in temas_validos:
            tema = 'padrao'
        updates.append("tema_preferido = ?")
        params.append(tema)
        session['admin_tema'] = tema
        
        # Se tiver permissão de config ou for superadmin, atualiza o tema padrão global
        if tem_permissao('config') or session.get('admin_usuario') == 'admin':
            with closing(get_db_connection()) as conn:
                conn.execute("UPDATE configuracoes SET tema_admin = ? WHERE id = 1", (tema,))
                conn.commit()
                registrar_auditoria("Alterar Paleta", f"Paleta de cores padrão alterada para: {tema}")
                
    if modo_escuro is not None:
        try:
            modo_escuro_val = 1 if int(modo_escuro) in (1, '1', True) else 0
        except (ValueError, TypeError):
            modo_escuro_val = 0
        updates.append("modo_escuro = ?")
        params.append(modo_escuro_val)
        session['admin_modo_escuro'] = modo_escuro_val
        registrar_auditoria("Alterar Tema", f"Modo escuro {'ativado' if modo_escuro_val else 'desativado'}")

    if updates and admin_id:
        params.append(admin_id)
        with closing(get_db_connection()) as conn:
            conn.execute(f"UPDATE administradores SET {', '.join(updates)} WHERE id = ?", tuple(params))
            conn.commit()
            
    return {
        "success": True, 
        "tema": session.get('admin_tema', 'padrao'),
        "modo_escuro": session.get('admin_modo_escuro', 0)
    }


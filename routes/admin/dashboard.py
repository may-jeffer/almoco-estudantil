# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, session, flash, Response, current_app
from werkzeug.security import generate_password_hash, check_password_hash
import json
import time
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from email.header import Header

from database import closing, get_db_connection, get_config
from utils.auth import is_logged_in_admin, tem_permissao
from utils.helpers import datetime_now_str, date_hoje_str, pode_reservar, sanitize_field, registrar_auditoria
from utils.qrcode_gen import generate_badge_code, generate_std_badge_code
from utils.mailer import _build_smtp_server
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
                    session['admin_perfil'] = admin['perfil'] if 'perfil' in admin.keys() else 'admin_mestre'
                    
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
    session.pop('admin_perfil', None)
    session.pop('admin_permissoes', None)
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
        
    return render_template('admin/dashboard.html', 
                           total_alunos=total_alunos, 
                           total_turmas=total_turmas, 
                           total_eventos=total_eventos,
                           total_visitantes=total_visitantes,
                           config=config)

@admin_bp.route('/admin/manual')
def admin_manual():
    """Manual interativo e documentação completa de uso do sistema."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    return render_template('admin/manual.html')

# --- CRUD de Administradores ---

@admin_bp.route('/admin/administradores', methods=['GET', 'POST'])
def admin_administradores():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('admins'): return redirect(url_for('admin.admin_dashboard'))
    
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        senha = request.form.get('senha')
        
        plist = request.form.getlist('permissoes[]')
        
        # Se marcou 'all' ou marcou todas as permissões disponíveis => admin_mestre
        todas_perms = {'turmas', 'alunos', 'cardapios', 'relatorios', 'avisos', 'fila', 'admins', 'config', 'smtp'}
        if 'all' in plist or todas_perms.issubset(set(plist)):
            perfil = 'admin_mestre'
            plist = ['all']
        elif plist:
            perfil = 'operador_fila'
        else:
            # Nenhuma permissão marcada => mestre com all
            perfil = 'admin_mestre'
            plist = ['all']
        
        permissoes_json = json.dumps(plist)
        
        # Gerar hash seguro para o administrador
        hash_senha = generate_password_hash(senha)
        
        try:
            with closing(get_db_connection()) as conn:
                conn.execute("INSERT INTO administradores (usuario, senha, perfil, permissoes) VALUES (?, ?, ?, ?)", (usuario, hash_senha, perfil, permissoes_json))
                conn.commit()
                registrar_auditoria("Criar Administrador", f"Criou o administrador: {usuario} ({perfil})")
                flash('Credencial adicionada com sucesso!', 'success')
        except Exception as e:
            flash(f'Erro. Usuário já existente ou erro no banco: {e}', 'error')
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
    if not nova_senha or len(nova_senha) < 4:
        flash('Senha muito curta. Use ao menos 4 caracteres.', 'error')
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
    
    plist = request.form.getlist('permissoes[]')
    
    # Derivar perfil automaticamente das permissões marcadas
    todas_perms = {'turmas', 'alunos', 'cardapios', 'relatorios', 'avisos', 'fila', 'admins', 'config', 'smtp'}
    if 'all' in plist or todas_perms.issubset(set(plist)):
        perfil = 'admin_mestre'
        plist = ['all']
    elif plist:
        perfil = 'operador_fila'
    else:
        perfil = 'admin_mestre'
        plist = ['all']
    
    permissoes_json = json.dumps(plist)
    
    with closing(get_db_connection()) as conn:
        admin = conn.execute("SELECT usuario FROM administradores WHERE id = ?", (id,)).fetchone()
        usuario_txt = admin['usuario'] if admin else f"ID {id}"
        conn.execute("UPDATE administradores SET perfil = ?, permissoes = ? WHERE id = ?", (perfil, permissoes_json, id))
        conn.commit()
        registrar_auditoria("Editar Administrador", f"Editou o perfil/permissões do admin: {usuario_txt} ({perfil})")
        
        # Se o admin editado for o próprio logado, atualizar sessão IMEDIATAMENTE
        if session.get('admin_id') == id:
            session['admin_perfil'] = perfil
            session['admin_permissoes'] = json.loads(permissoes_json)
            
    flash('Perfil e permissões do administrador atualizados!', 'success')
    return redirect(url_for('admin.admin_administradores'))

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

@admin_bp.route('/admin/configuracoes', methods=['POST'])
def save_configuracoes():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('config'): return redirect(url_for('admin.admin_dashboard'))
    horario_limite = request.form.get('horario_limite')
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
    
    with closing(get_db_connection()) as conn:
        conn.execute(
            "UPDATE configuracoes SET horario_limite = ?, nome_sistema = ?, sigla_instituicao = ?, "
            "modo_login_aluno = ?, max_reservas_ativas = ?, email_qr_reserva = ?, tempo_autologout = ? WHERE id = 1",
            (horario_limite, nome_sistema, sigla_instituicao, modo_login_aluno, max_reservas_ativas, email_qr_reserva, tempo_autologout)
        )
        conn.commit()
        registrar_auditoria("Alterar Configurações", f"Alterou configurações do sistema (Nome: {nome_sistema}, Limite: {horario_limite})")
        flash('Configurações gerais salvas com sucesso.', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/configuracoes/logo', methods=['POST'])
def save_logo():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('config'): return redirect(url_for('admin.admin_dashboard'))
    
    file = request.files.get('logo_file')
    if file and file.filename != '':
        # Validação de extensão de arquivo para evitar execução remota de arquivos ou XSS armazenado
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
            flash('Tipo de arquivo não permitido. Por segurança, envie apenas imagens (.png, .jpg, .jpeg, .webp, .gif).', 'error')
            return redirect(url_for('admin.admin_dashboard'))
            
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
         
    return redirect(url_for('admin.admin_dashboard'))

# SMTP Configurações
@admin_bp.route('/admin/configuracoes/smtp', methods=['POST'])
def save_configuracoes_smtp():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('smtp'): return redirect(url_for('admin.admin_dashboard'))
    
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
        
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/configuracoes/smtp/testar', methods=['POST'])
def testar_smtp():
    """Envia um e-mail de teste usando as configurações SMTP atuais do banco."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('smtp'): return redirect(url_for('admin.admin_dashboard'))

    email_teste = request.form.get('email_teste', '').strip()
    if not email_teste:
        flash('Informe um endereço de e-mail para o teste.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    config = get_config()
    if not config or not config['smtp_host'] or not config['smtp_user']:
        flash('Configure o servidor SMTP antes de testar.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    if not config['smtp_senha']:
        flash('Senha SMTP não configurada. Salve a configuração SMTP com a senha antes de testar.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    nome_sistema = config['nome_sistema'] or 'Cantina Estudantil'
    sigla = config['sigla_instituicao'] or ''

    conteudo_html = f"""
    <div id="liveAlertPlaceholder" style="position: fixed; top: 20px; left: 50%; transform: translateX(-50%); width: 90%; max-width: 350px; z-index: 9999; text-align: center;"></div>
    <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto;
                border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden;">
        <div style="background: #CD191E; padding: 24px; text-align: center;">
            <h2 style="color: white; margin: 0; font-size: 1.4rem;">🍽️ {nome_sistema}</h2>
            <p style="color: #fca5a5; margin: 4px 0 0 0; font-size: 0.9rem;">{sigla}</p>
        </div>
        <div style="padding: 28px;">
            <p style="font-size: 1rem;">Olá, <strong>Testador</strong>! 👋</p>
            <p>Este é um <strong>e-mail de teste</strong> enviado pelo painel administrativo.</p>
            <p>Se você recebeu esta mensagem, a configuração SMTP está funcionando corretamente! ✅</p>
            <hr style="border: 0; border-top: 1px solid #e5e7eb; margin: 20px 0;">
            <ul style="color: #6b7280; font-size: 0.85rem;">
                <li>Host: <strong>{config['smtp_host']}:{config['smtp_porta']}</strong></li>
                <li>Remetente: <strong>{config['smtp_user']}</strong></li>
            </ul>
        </div>
    </div>
    """

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'✅ Teste de SMTP — {nome_sistema}'
        msg['From'] = formataddr((str(Header(nome_sistema, 'utf-8')), config['smtp_user']))
        msg['To'] = email_teste
        msg.attach(MIMEText(conteudo_html, 'html'))

        # Passamos debug=True para que todo o fluxo SMTP seja impresso no terminal/console do servidor Flask
        server = _build_smtp_server(config, debug=True)
        server.send_message(msg)
        server.quit()
        
        registrar_auditoria("Testar SMTP", f"Enviou e-mail de teste de SMTP para {email_teste}")
        flash(f'E-mail de teste enviado com sucesso para {email_teste}! Verifique sua caixa de entrada.', 'success')
    except TimeoutError:
        flash('Falha no envio (Timeout): O servidor SMTP demorou muito para responder. Verifique se o Host e a Porta estão corretos e se não há bloqueios de rede no servidor.', 'error')
    except ConnectionRefusedError:
        flash('Falha no envio (Conexão Recusada): A conexão com o servidor SMTP foi recusada. Verifique se o Host e a Porta estão corretos e se o serviço SMTP está rodando.', 'error')
    except smtplib.SMTPAuthenticationError as e:
        flash(f'Falha no envio (Erro de Autenticação): Usuário ou senha SMTP incorretos. Detalhes: {e}', 'error')
    except smtplib.SMTPConnectError as e:
        flash(f'Falha no envio (Erro de Conexão): Não foi possível conectar ao Host SMTP. Detalhes: {e}', 'error')
    except Exception as e:
        flash(f'Falha no envio: {e} (Veja o log detalhado no console do servidor Flask)', 'error')

    return redirect(url_for('admin.admin_dashboard'))

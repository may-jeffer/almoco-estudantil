from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime, timedelta
import re
from werkzeug.security import generate_password_hash, check_password_hash
import time

from database import closing, get_db_connection, get_config
from utils.auth import is_logged_in_aluno
from utils.mailer import enviar_email_recuperacao
from utils.helpers import date_hoje_str, datetime_now_str, parse_data_nascimento
import json

main_bp = Blueprint('main', __name__)

def handle_login_success(aluno):
    session['aluno_id'] = aluno['id']
    session['aluno_nome'] = aluno['nome']
    session['aluno_modo_escuro'] = int(aluno['modo_escuro']) if ('modo_escuro' in aluno.keys() and aluno['modo_escuro']) else 0
    
    contextos = []
    contextos_ids = set()
    
    with closing(get_db_connection()) as conn:
        turma_principal = conn.execute("SELECT id, nome, is_evento FROM turmas WHERE id = ?", (aluno['turma_id'],)).fetchone()
        if turma_principal:
            prefixo = "Evento: " if turma_principal['is_evento'] == 1 else "Turma: "
            contextos.append({'id': turma_principal['id'], 'nome': f"{prefixo}{turma_principal['nome']}"})
            contextos_ids.add(turma_principal['id'])
            
        hoje = datetime.now().strftime('%Y-%m-%d')
        query_eventos = """
            SELECT t.id, t.nome 
            FROM turmas t
            JOIN eventos_participantes ep ON t.id = ep.turma_id
            WHERE ep.aluno_id = ? 
            AND t.is_evento = 1
            AND (t.data_inicio IS NULL OR t.data_inicio <= ?)
            AND (t.data_fim IS NULL OR t.data_fim >= ?)
        """
        eventos_ativos = conn.execute(query_eventos, (aluno['id'], hoje, hoje)).fetchall()
        for ev in eventos_ativos:
            if ev['id'] not in contextos_ids:
                contextos.append({'id': ev['id'], 'nome': f"Evento: {ev['nome']}"})
                contextos_ids.add(ev['id'])
            
    if len(contextos) > 1:
        session['contextos_disponiveis'] = [dict(c) for c in contextos]
        return redirect(url_for('aluno.aluno_selecionar_contexto'))
    else:
        if contextos:
            session['contexto_turma_id'] = contextos[0]['id']
            session['contexto_nome'] = contextos[0]['nome']
        else:
            session['contexto_turma_id'] = aluno['turma_id']
            session['contexto_nome'] = 'Turma Padrão'
        return redirect(url_for('aluno.aluno_dashboard'))

@main_bp.route('/')
def index():
    if is_logged_in_aluno():
        return redirect(url_for('aluno.aluno_dashboard'))
    return redirect(url_for('main.login'))

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = request.remote_addr
        from utils.auth import login_limiter
        if login_limiter.is_blocked(ip):
            flash('Muitas tentativas de login de seu IP. Aguarde 60 segundos.', 'error')
            return render_template('login.html')
        login_limiter.record_attempt(ip)

        raw_cpf = request.form.get('cpf', '')
        cpf_clean = re.sub(r'\D', '', raw_cpf)
        if len(cpf_clean) == 11:
            cpf_formatted = f"{cpf_clean[:3]}.{cpf_clean[3:6]}.{cpf_clean[6:9]}-{cpf_clean[9:]}"
        else:
            cpf_formatted = cpf_clean
            
        data_nascimento = request.form.get('data_nascimento', '').strip()
        senha = request.form.get('senha')
        
        lembrar_me = request.form.get('lembrar_me') == 'on'
        
        normalized_data_nascimento = parse_data_nascimento(data_nascimento) or data_nascimento
                
        config = get_config()
        modo_login = config['modo_login_aluno'] if 'modo_login_aluno' in dict(config) else 'DATA_NASC'
        
        with closing(get_db_connection()) as conn:
            if modo_login == 'DATA_NASC':
                aluno = conn.execute(
                    'SELECT * FROM alunos WHERE (cpf = ? OR cpf = ? OR cpf = ?) AND (data_nascimento = ? OR data_nascimento = ?)', 
                    (cpf_clean, cpf_formatted, raw_cpf, normalized_data_nascimento, data_nascimento)
                ).fetchone()
                if aluno:
                    session.permanent = lembrar_me
                    return handle_login_success(aluno)
                else:
                    flash('CPF ou Data de Nascimento inválidos.', 'error')
            else:
                aluno = conn.execute('SELECT * FROM alunos WHERE (cpf = ? OR cpf = ? OR cpf = ?)', (cpf_clean, cpf_formatted, raw_cpf)).fetchone()
                if aluno:
                    senha_valida = False
                    if aluno['senha_hash']:
                        if aluno['senha_hash'].startswith('pbkdf2:sha256:'):
                            senha_valida = check_password_hash(aluno['senha_hash'], senha)
                        else:
                            import hashlib
                            if hashlib.sha256(senha.encode()).hexdigest() == aluno['senha_hash']:
                                senha_valida = True
                                novo_hash = generate_password_hash(senha)
                                conn.execute("UPDATE alunos SET senha_hash = ? WHERE id = ?", (novo_hash, aluno['id']))
                                conn.commit()
                    
                    if senha_valida:
                        session.permanent = lembrar_me
                        return handle_login_success(aluno)
                    else:
                        senhas_provisorias = [
                            aluno['data_nascimento'],
                            aluno['data_nascimento'].replace('-', ''),
                            datetime.strptime(aluno['data_nascimento'], '%Y-%m-%d').strftime('%d%m%Y')
                        ]
                        if senha in senhas_provisorias:
                            session['setup_aluno_id'] = aluno['id']
                            return redirect(url_for('main.aluno_setup_senha'))
                        
                        time.sleep(1)
                        flash('Senha incorreta ou CPF não cadastrado.', 'error')
                else:
                    time.sleep(1)
                    flash('Estudante não encontrado.', 'error')
                
    return render_template('login.html')

@main_bp.route('/aluno/setup_senha', methods=['GET', 'POST'])
def aluno_setup_senha():
    if 'setup_aluno_id' not in session:
        return redirect(url_for('main.login'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        nova_senha = request.form.get('nova_senha')
        
        if len(nova_senha) < 6:
            flash('A senha precisa ter no mínimo 6 caracteres.', 'error')
            return redirect(url_for('main.aluno_setup_senha'))
            
        hash_senha = generate_password_hash(nova_senha)
        
        with closing(get_db_connection()) as conn:
            conn.execute("UPDATE alunos SET email = ?, senha_hash = ? WHERE id = ?", (email, hash_senha, session['setup_aluno_id']))
            conn.commit()
            
        session.pop('setup_aluno_id', None)
        flash('Cadastro de segurança concluído! Faça login com a sua nova senha.', 'success')
        return redirect(url_for('main.login'))
        
    return render_template('aluno_setup_senha.html')

@main_bp.route('/esqueci_senha', methods=['GET', 'POST'])
def esqueci_senha():
    if request.method == 'POST':
        cpf = request.form.get('cpf')
        
        with closing(get_db_connection()) as conn:
            aluno = conn.execute('SELECT * FROM alunos WHERE cpf = ?', (cpf,)).fetchone()
            config = conn.execute('SELECT * FROM configuracoes WHERE id = 1').fetchone()
            
            if not aluno:
                flash('CPF não encontrado no sistema.', 'error')
                return redirect(url_for('main.esqueci_senha'))
                
            if not aluno['email']:
                flash('Você não cadastrou um e-mail. Solicite o resgate manual na Secretaria do Campus.', 'error')
                return redirect(url_for('main.esqueci_senha'))
                
            if not config['smtp_ativo'] or not config['smtp_host']:
                flash('Recuperação desativada. A Instituição não habilitou o servidor de E-mail automático.', 'error')
                return redirect(url_for('main.login'))
                
            import secrets
            token = secrets.token_hex(16)
            expiracao = datetime.now() + timedelta(minutes=30)
            
            conn.execute("UPDATE alunos SET reset_token = ?, reset_expiracao = ? WHERE id = ?", (token, expiracao.strftime('%Y-%m-%d %H:%M:%S'), aluno['id']))
            conn.commit()
            
            url_recuperacao = url_for('main.recuperar_senha', token=token, _external=True)
            
            sucesso = enviar_email_recuperacao(aluno, url_recuperacao, config)
            if sucesso:
                flash(f'Sucesso! Enviamos um link de recuperação para o e-mail cadastrado ({aluno["email"]}).', 'success')
            else:
                flash(f'Falha no envio do e-mail. Avise a direção', 'error')
                
        return redirect(url_for('main.login'))
        
    return render_template('esqueci_senha.html')

@main_bp.route('/recuperar_senha/<token>', methods=['GET', 'POST'])
def recuperar_senha(token):
    with closing(get_db_connection()) as conn:
        aluno = conn.execute("SELECT * FROM alunos WHERE reset_token = ?", (token,)).fetchone()
        
        if not aluno:
            flash('Código de segurança expirado ou já queimado.', 'error')
            return redirect(url_for('main.login'))
            
        expiracao = datetime.strptime(aluno['reset_expiracao'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() > expiracao:
            flash('Seu Link apodreceu (passaram os 30 minutos vitais). Peça permissão novamente.', 'error')
            return redirect(url_for('main.esqueci_senha'))
            
        if request.method == 'POST':
            nova_senha = request.form.get('nova_senha')
            if len(nova_senha) < 6:
                flash('Senha muito frágil. Tenha resiliência, ao menos 6 blocos.', 'error')
                return redirect(url_for('main.recuperar_senha', token=token))
                
            hash_digitado = generate_password_hash(nova_senha)
            conn.execute("UPDATE alunos SET senha_hash = ?, reset_token = NULL, reset_expiracao = NULL WHERE id = ?", (hash_digitado, aluno['id']))
            conn.commit()
            
            flash('Seu escudo foi refeito. Senha alterada com sucesso!', 'success')
            return redirect(url_for('main.login'))
            
    return render_template('recuperar_senha.html', token=token, aluno=aluno)

@main_bp.route('/logout')
def logout():
    session.pop('aluno_id', None)
    session.pop('aluno_nome', None)
    session.pop('aluno_modo_escuro', None)
    session.pop('pesquisa_aluno_id', None)
    session.pop('pesquisa_aluno_nome', None)
    return redirect(url_for('main.login'))

@main_bp.route('/aluno/modo-escuro', methods=['POST'])
def aluno_modo_escuro():
    data = request.get_json(silent=True) or {}
    modo_escuro = 1 if data.get('modo_escuro') in [1, '1', True] else 0
    session['aluno_modo_escuro'] = modo_escuro
    aluno_id = session.get('aluno_id')
    if aluno_id:
        with closing(get_db_connection()) as conn:
            try:
                conn.execute("UPDATE alunos SET modo_escuro = ? WHERE id = ?", (modo_escuro, aluno_id))
                conn.commit()
            except Exception:
                pass
    return {'status': 'ok', 'modo_escuro': modo_escuro}


# --- ROTAS PÚBLICAS / ESTUDANTE: PREENCHIMENTO DE PESQUISAS ---

@main_bp.route('/pesquisa/<slug>', methods=['GET'])
def pesquisa_responder(slug):
    """Página de preenchimento da pesquisa (anônima ou identificada)."""
    slug = slug.strip().upper()
    config = get_config()
    hoje = date_hoje_str()

    with closing(get_db_connection()) as conn:
        formulario = conn.execute("SELECT * FROM formularios_pesquisa WHERE UPPER(slug) = ?", (slug,)).fetchone()
        if not formulario:
            return render_template('pesquisa_responder.html', erro_status='nao_encontrado')

        # Checagem de status ativo
        if formulario['ativo'] == 0:
            return render_template('pesquisa_responder.html', formulario=formulario, erro_status='desativado')

        # Checagem de validade
        if formulario['data_fim'] and hoje > formulario['data_fim']:
            return render_template('pesquisa_responder.html', formulario=formulario, erro_status='expirado')

        if formulario['data_inicio'] and hoje < formulario['data_inicio']:
            return render_template('pesquisa_responder.html', formulario=formulario, erro_status='nao_iniciado')

        # Checagem de identificação para formulários NÃO ANÔNIMOS
        aluno_id = session.get('aluno_id') or session.get('pesquisa_aluno_id')
        aluno_atual = None
        ja_respondeu = False

        if formulario['is_anonimo'] == 0:
            if aluno_id:
                aluno_atual = conn.execute("""
                    SELECT a.*, t.nome as turma_nome 
                    FROM alunos a 
                    LEFT JOIN turmas t ON a.turma_id = t.id 
                    WHERE a.id = ?
                """, (aluno_id,)).fetchone()

                if aluno_atual:
                    # Verificar se já respondeu
                    resp_existente = conn.execute(
                        "SELECT id, data_envio FROM formulario_respostas_envios WHERE formulario_id = ? AND aluno_id = ?",
                        (formulario['id'], aluno_id)
                    ).fetchone()
                    if resp_existente:
                        ja_respondeu = True
            else:
                # Aluno não identificado: renderizar tela de login / identificação
                modo_login = dict(config).get('modo_login_aluno', 'DATA_NASC') if config else 'DATA_NASC'
                return render_template(
                    'pesquisa_responder.html',
                    formulario=formulario,
                    precisa_identificacao=True,
                    modo_login=modo_login
                )

        if ja_respondeu:
            return render_template('pesquisa_responder.html', formulario=formulario, erro_status='ja_respondeu', aluno_atual=aluno_atual)

        # Buscar perguntas do formulário
        perguntas_db = conn.execute(
            "SELECT * FROM formulario_perguntas WHERE formulario_id = ? ORDER BY ordem ASC, id ASC",
            (formulario['id'],)
        ).fetchall()

        perguntas = []
        for p in perguntas_db:
            opcoes = json.loads(p['opcoes_json']) if p['opcoes_json'] else []
            perguntas.append({
                'id': p['id'],
                'titulo': p['titulo_pergunta'],
                'tipo': p['tipo_pergunta'],
                'opcoes': opcoes,
                'obrigatoria': bool(p['obrigatoria'])
            })

    return render_template(
        'pesquisa_responder.html',
        formulario=formulario,
        perguntas=perguntas,
        aluno_atual=aluno_atual,
        sucesso=False
    )

@main_bp.route('/pesquisa/<slug>/identificar', methods=['POST'])
def pesquisa_identificar(slug):
    """Autenticação/Identificação rápida do estudante para responder pesquisa identificada."""
    slug = slug.strip().upper()
    config = get_config()
    modo_login = dict(config).get('modo_login_aluno', 'DATA_NASC') if config else 'DATA_NASC'

    cpf_raw = request.form.get('cpf', '').strip()
    cpf_clean = re.sub(r'\D', '', cpf_raw)
    
    # Formatação padrão do CPF
    cpf_formatted = f"{cpf_clean[:3]}.{cpf_clean[3:6]}.{cpf_clean[6:9]}-{cpf_clean[9:]}" if len(cpf_clean) == 11 else cpf_clean

    data_nascimento = request.form.get('data_nascimento', '').strip()
    senha = request.form.get('senha', '')

    with closing(get_db_connection()) as conn:
        formulario = conn.execute("SELECT * FROM formularios_pesquisa WHERE UPPER(slug) = ?", (slug,)).fetchone()
        if not formulario:
            flash('Formulário não encontrado.', 'error')
            return redirect(url_for('main.index'))

        aluno = None
        if modo_login == 'DATA_NASC':
            normalized_data = parse_data_nascimento(data_nascimento) or data_nascimento
            
            aluno = conn.execute(
                "SELECT * FROM alunos WHERE (cpf = ? OR cpf = ? OR cpf = ?) AND (data_nascimento = ? OR data_nascimento = ?)",
                (cpf_clean, cpf_formatted, cpf_raw, normalized_data, data_nascimento)
            ).fetchone()
            if not aluno:
                flash('CPF ou Data de Nascimento inválidos. Verifique os dados.', 'error')
                return redirect(url_for('main.pesquisa_responder', slug=slug))
        else:
            aluno = conn.execute(
                "SELECT * FROM alunos WHERE (cpf = ? OR cpf = ? OR cpf = ?)",
                (cpf_clean, cpf_formatted, cpf_raw)
            ).fetchone()
            if not aluno:
                flash('CPF não encontrado.', 'error')
                return redirect(url_for('main.pesquisa_responder', slug=slug))

            senha_valida = False
            if aluno['senha_hash']:
                if aluno['senha_hash'].startswith('pbkdf2:sha256:'):
                    senha_valida = check_password_hash(aluno['senha_hash'], senha)
                else:
                    import hashlib
                    senha_valida = (hashlib.sha256(senha.encode()).hexdigest() == aluno['senha_hash'])

            if not senha_valida:
                # Checar se senha é data de nascimento provisória
                senhas_provisorias = [
                    aluno['data_nascimento'],
                    aluno['data_nascimento'].replace('-', '') if aluno['data_nascimento'] else '',
                ]
                if senha in senhas_provisorias:
                    senha_valida = True

            if not senha_valida:
                flash('Senha incorreta.', 'error')
                return redirect(url_for('main.pesquisa_responder', slug=slug))

        # Guarda identificação na sessão
        session['pesquisa_aluno_id'] = aluno['id']
        session['pesquisa_aluno_nome'] = aluno['nome']

    return redirect(url_for('main.pesquisa_responder', slug=slug))

@main_bp.route('/pesquisa/<slug>/enviar', methods=['POST'])
def pesquisa_enviar(slug):
    """Processa e salva o envio das respostas do formulário de pesquisa."""
    slug = slug.strip().upper()
    hoje = date_hoje_str()
    ip_origem = request.remote_addr

    with closing(get_db_connection()) as conn:
        formulario = conn.execute("SELECT * FROM formularios_pesquisa WHERE UPPER(slug) = ?", (slug,)).fetchone()
        if not formulario:
            flash('Formulário não encontrado.', 'error')
            return redirect(url_for('main.index'))

        if formulario['ativo'] == 0:
            flash('Este formulário está inativo.', 'error')
            return redirect(url_for('main.pesquisa_responder', slug=slug))

        if formulario['data_fim'] and hoje > formulario['data_fim']:
            flash('Este formulário expirou.', 'error')
            return redirect(url_for('main.pesquisa_responder', slug=slug))

        aluno_id = None
        aluno_identificacao = None

        if formulario['is_anonimo'] == 0:
            aluno_id = session.get('aluno_id') or session.get('pesquisa_aluno_id')
            if not aluno_id:
                flash('Identificação obrigatória para esta pesquisa.', 'error')
                return redirect(url_for('main.pesquisa_responder', slug=slug))

            aluno = conn.execute("SELECT a.nome, a.matricula, t.nome as turma_nome FROM alunos a LEFT JOIN turmas t ON a.turma_id = t.id WHERE a.id = ?", (aluno_id,)).fetchone()
            if aluno:
                aluno_identificacao = f"{aluno['nome']} (Mat: {aluno['matricula']} - Turma: {aluno['turma_nome'] or 'Sem Turma'})"

            # Bloqueio de duplicidade
            ja_respondeu = conn.execute(
                "SELECT id FROM formulario_respostas_envios WHERE formulario_id = ? AND aluno_id = ?",
                (formulario['id'], aluno_id)
            ).fetchone()
            if ja_respondeu:
                flash('Você já enviou suas respostas para este formulário.', 'warning')
                return redirect(url_for('main.pesquisa_responder', slug=slug))

        # Buscar perguntas para validar campos obrigatórios
        perguntas = conn.execute(
            "SELECT * FROM formulario_perguntas WHERE formulario_id = ? ORDER BY ordem ASC, id ASC",
            (formulario['id'],)
        ).fetchall()

        respostas_para_salvar = []
        for p in perguntas:
            p_id = p['id']
            tipo = p['tipo_pergunta']
            obrigatoria = bool(p['obrigatoria'])

            if tipo == 'checkbox':
                valores = request.form.getlist(f'pergunta_{p_id}')
                if obrigatoria and not valores:
                    flash(f"A pergunta '{p['titulo_pergunta']}' é obrigatória.", 'error')
                    return redirect(url_for('main.pesquisa_responder', slug=slug))
                resposta_texto = json.dumps(valores, ensure_ascii=False) if valores else ''
            else:
                valor = request.form.get(f'pergunta_{p_id}', '').strip()
                if obrigatoria and not valor:
                    flash(f"A pergunta '{p['titulo_pergunta']}' é obrigatória.", 'error')
                    return redirect(url_for('main.pesquisa_responder', slug=slug))
                resposta_texto = valor

            respostas_para_salvar.append((p_id, resposta_texto))

        # Salvar envio
        agora = datetime_now_str()
        cur = conn.execute("""
            INSERT INTO formulario_respostas_envios
            (formulario_id, aluno_id, aluno_identificacao, ip_origem, data_envio)
            VALUES (?, ?, ?, ?, ?)
        """, (formulario['id'], aluno_id, aluno_identificacao, ip_origem, agora))
        envio_id = cur.lastrowid

        # Salvar itens das respostas
        for p_id, resp_txt in respostas_para_salvar:
            conn.execute("""
                INSERT INTO formulario_respostas_itens
                (envio_id, pergunta_id, resposta_texto)
                VALUES (?, ?, ?)
            """, (envio_id, p_id, resp_txt))

        conn.commit()

    return render_template('pesquisa_responder.html', formulario=formulario, sucesso=True)



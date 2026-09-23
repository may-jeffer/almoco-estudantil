import smtplib
import socket
import time
import io
import sys
import traceback
from contextlib import redirect_stderr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.utils import formataddr
from email.header import Header
import qrcode
from io import BytesIO
from datetime import datetime

def _build_smtp_server(config, debug=False):
    """Cria e autentica uma conexão SMTP a partir das configs do banco."""
    cfg = dict(config) if config else {}
    porta_raw = cfg.get('smtp_porta') or 587
    try:
        porta = int(porta_raw)
    except (ValueError, TypeError):
        porta = 587
    if porta == 465:
        server = smtplib.SMTP_SSL(cfg['smtp_host'], porta, timeout=10)
        if debug:
            server.set_debuglevel(1)
    else:
        server = smtplib.SMTP(cfg['smtp_host'], porta, timeout=10)
        if debug:
            server.set_debuglevel(1)
        server.ehlo()
        server.starttls()
        server.ehlo()
    server.login(cfg['smtp_user'], cfg['smtp_senha'])
    return server

def enviar_qr_por_email(aluno, reserva, cardapio, config):
    """
    Envia o QR Code da reserva para o e-mail do aluno.
    Silencia exceções — falha no envio nunca bloqueia a reserva.
    """
    try:
        aluno_dict = dict(aluno) if aluno else {}
        cfg = dict(config) if config else {}
        reserva_dict = dict(reserva) if reserva else {}
        cardapio_dict = dict(cardapio) if cardapio else {}

        email_destino = aluno_dict.get('email')
        if not email_destino:
            return  # Aluno sem e-mail cadastrado — ignora silenciosamente

        if not cfg or not cfg.get('smtp_ativo') or not cfg.get('smtp_host'):
            return  # SMTP não configurado — ignora

        if not cfg.get('email_qr_reserva'):
            return  # Envio de QR desativado — ignora

        # Gerar QR Code em memória
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(reserva_dict['codigo_unico'])
        qr.make(fit=True)
        img = qr.make_image(fill_color="#CD191E", back_color="white")
        img_bytes = BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        data_fmt = datetime.strptime(cardapio_dict['data'], '%Y-%m-%d').strftime('%d/%m/%Y')
        nome_sistema = cfg.get('nome_sistema') or 'Cantina Estudantil'
        sigla = cfg.get('sigla_instituicao') or ''

        conteudo_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto;
                    border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden;">
            <div style="background: #CD191E; padding: 24px; text-align: center;">
                <h2 style="color: white; margin: 0; font-size: 1.4rem;">🍽️ {nome_sistema}</h2>
                <p style="color: #fca5a5; margin: 4px 0 0 0; font-size: 0.9rem;">{sigla}</p>
            </div>
            <div style="padding: 28px;">
                <p style="font-size: 1rem;">Olá, <strong>{aluno['nome']}</strong>! 👋</p>
                <p>Sua reserva para <strong>{cardapio['tipo_refeicao']}</strong> do dia
                   <strong>{data_fmt}</strong> foi confirmada.</p>
                <p style="color:#555;">Apresente o QR Code abaixo no momento da retirada:</p>
                <div style="text-align: center; margin: 24px 0;">
                    <img src="cid:qrcode_reserva" alt="QR Code" width="200" height="200"
                         style="border: 2px solid #e5e7eb; border-radius: 8px; padding: 8px;">
                </div>
                <div style="background: #f9fafb; border-radius: 8px; padding: 12px; text-align: center;
                            border: 1px solid #e5e7eb; font-size: 1.1rem; letter-spacing: 4px;
                            font-weight: bold; color: #111;">
                    {reserva['codigo_unico']}
                </div>
                <p style="color: #6b7280; font-size: 0.82rem; margin-top: 20px;">
                    Este e-mail é automático. Não responda.
                </p>
            </div>
        </div>
        """

        msg = MIMEMultipart('related')
        msg['Subject'] = f'✅ Reserva Confirmada — {nome_sistema} ({data_fmt})'
        msg['From'] = formataddr((str(Header(nome_sistema, 'utf-8')), config['smtp_user']))
        msg['To'] = email_destino

        msg_alt = MIMEMultipart('alternative')
        msg.attach(msg_alt)
        msg_alt.attach(MIMEText(conteudo_html, 'html'))

        img_mime = MIMEImage(img_bytes.read(), _subtype='png')
        img_mime.add_header('Content-ID', '<qrcode_reserva>')
        img_mime.add_header('Content-Disposition', 'inline', filename='qrcode.png')
        msg.attach(img_mime)

        with _build_smtp_server(config) as server:
            server.send_message(msg)
    except Exception as e:
        print("Erro ao enviar e-mail com QR code:", e)

def enviar_email_recuperacao(aluno, reset_link, config, is_admin=False):
    try:
        aluno_dict = dict(aluno) if aluno else {}
        cfg = dict(config) if config else {}
        email_destino = aluno_dict.get('email')
        if not email_destino:
            return False

        if not cfg or not cfg.get('smtp_ativo') or not cfg.get('smtp_host'):
            return False

        nome_sistema = cfg.get('nome_sistema') or 'Cantina Estudantil'
        header_title = "🔒 Redefinição de Senha Administrativa" if is_admin else "🔒 Redefinição de Senha"
        cor_header = "#4f46e5" if is_admin else "#2563eb"
        msg_contexto = "Recebemos uma solicitação de redefinição para a sua credencial de <strong>Administrador</strong> do sistema." if is_admin else "Recebemos um pedido para restaurar o escudo (senha) da sua conta."

        conteudo_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto;
                    border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="background: {cor_header}; padding: 24px; text-align: center;">
                <h2 style="color: white; margin: 0; font-size: 1.3rem;">{header_title}</h2>
            </div>
            <div style="padding: 28px; background: white; color: #1f2937;">
                <p style="font-size: 1rem; margin-top: 0;">Olá, <strong>{aluno_dict.get('nome', '')}</strong>!</p>
                <p style="font-size: 0.95rem; line-height: 1.5;">{msg_contexto}</p>
                <p style="font-size: 0.95rem; line-height: 1.5;">Clique no botão abaixo para definir sua nova senha com segurança. Este link é válido por <strong>1 hora</strong>.</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_link}" style="background-color: {cor_header}; color: white; padding: 14px 28px;
                       text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; font-size: 1rem;">
                       Redefinir Minha Senha
                    </a>
                </div>
                
                <p style="color: #6b7280; font-size: 0.85rem; line-height: 1.4; border-top: 1px solid #f3f4f6; padding-top: 16px;">
                    Se você não solicitou esta redefinição, desconsidere esta mensagem. Sua senha atual permanecerá inalterada e segura.
                </p>
            </div>
        </div>
        """

        msg = MIMEMultipart('alternative')
        prefixo_assunto = "Acesso Administrativo" if is_admin else "Recuperação de Senha"
        msg['Subject'] = f'{prefixo_assunto} — {nome_sistema}'
        msg['From'] = formataddr((str(Header(nome_sistema, 'utf-8')), cfg.get('smtp_user', '')))
        msg['To'] = email_destino

        msg.attach(MIMEText(conteudo_html, 'html'))

        with _build_smtp_server(cfg) as server:
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail de recuperação ({type(e).__name__}): {e}", file=sys.stderr)
        traceback.print_exc()
        return False

def diagnosticar_smtp(config, email_teste):
    """
    Executa diagnóstico detalhado passo a passo da conexão SMTP,
    capturando tempos de resposta, transcrição do protocolo e rastreamento de erros.
    """
    cfg = dict(config) if config else {}
    host = (cfg.get('smtp_host') or '').strip()
    porta_raw = cfg.get('smtp_porta') or 587
    user = (cfg.get('smtp_user') or '').strip()
    senha = cfg.get('smtp_senha') or ''
    email_dest = (email_teste or '').strip()

    res = {
        "success": False,
        "mensagem": "",
        "etapas": [],
        "log_protocolo": "",
        "traceback": "",
        "dica": "",
        "host": host,
        "porta": str(porta_raw),
        "user": user,
        "destinatario": email_dest,
        "data_hora": datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    }

    # 1. Validação básica de parâmetros
    if not host or not user:
        res["mensagem"] = "Host SMTP ou Usuário não informados."
        res["etapas"].append({
            "nome": "1. Parâmetros de Configuração",
            "status": "erro",
            "detalhe": "Host SMTP ou Usuário estão vazios no cadastro."
        })
        res["dica"] = "Preencha o Host (ex: smtp.gmail.com) e o Usuário (ex: seu.email@gmail.com)."
        return res

    if not senha:
        res["mensagem"] = "Senha SMTP não informada."
        res["etapas"].append({
            "nome": "1. Parâmetros de Configuração",
            "status": "erro",
            "detalhe": "Nenhuma senha ou token de aplicativo informado."
        })
        res["dica"] = "Informe a Senha ou Token de Aplicativo da sua conta de e-mail."
        return res

    try:
        porta = int(porta_raw)
    except (ValueError, TypeError):
        res["mensagem"] = f"Porta SMTP inválida: {porta_raw}"
        res["etapas"].append({
            "nome": "1. Parâmetros de Configuração",
            "status": "erro",
            "detalhe": f"A porta '{porta_raw}' não é um número válido."
        })
        res["dica"] = "Utilize uma porta padrão como 587 (TLS/STARTTLS) ou 465 (SSL direto)."
        return res

    res["etapas"].append({
        "nome": "1. Parâmetros de Configuração",
        "status": "sucesso",
        "detalhe": f"Host: {host} | Porta: {porta} | Usuário: {user}"
    })

    # 2. Resolução DNS
    t0 = time.time()
    try:
        addr_info = socket.getaddrinfo(host, porta, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys([ai[4][0] for ai in addr_info]))
        t_dns = round((time.time() - t0) * 1000, 1)
        res["etapas"].append({
            "nome": "2. Resolução de DNS (Host -> IP)",
            "status": "sucesso",
            "detalhe": f"Resolvido para {', '.join(ips[:3])} ({t_dns} ms)",
            "tempo_ms": t_dns
        })
    except socket.gaierror as e:
        t_dns = round((time.time() - t0) * 1000, 1)
        res["etapas"].append({
            "nome": "2. Resolução de DNS (Host -> IP)",
            "status": "erro",
            "detalhe": f"Falha ao resolver domínio '{host}': {e}",
            "tempo_ms": t_dns
        })
        res["mensagem"] = f"Falha de DNS: Não foi possível resolver o nome '{host}'."
        res["dica"] = "Verifique se o Host SMTP foi digitado corretamente (ex: smtp.gmail.com, smtp.office365.com) e se o servidor possui conexão com a internet."
        _imprimir_debug_terminal(res)
        return res

    # 3. Conectividade TCP (Porta aberta e alcançável)
    t0 = time.time()
    try:
        test_sock = socket.create_connection((host, porta), timeout=8)
        test_sock.close()
        t_tcp = round((time.time() - t0) * 1000, 1)
        res["etapas"].append({
            "nome": "3. Conexão de Rede TCP (Socket)",
            "status": "sucesso",
            "detalhe": f"Porta {porta} aberta e respondendo ({t_tcp} ms)",
            "tempo_ms": t_tcp
        })
    except socket.timeout:
        t_tcp = round((time.time() - t0) * 1000, 1)
        res["etapas"].append({
            "nome": "3. Conexão de Rede TCP (Socket)",
            "status": "erro",
            "detalhe": f"Timeout após {t_tcp} ms aguardando resposta do socket na porta {porta}",
            "tempo_ms": t_tcp
        })
        res["mensagem"] = f"Tempo esgotado (Timeout) ao conectar em {host}:{porta}."
        res["dica"] = f"O servidor não respondeu na porta {porta}. É comum provedores de internet, firewalls corporativos ou antivírus bloquearem portas SMTP. Tente alternar entre a porta 587 e a 465."
        _imprimir_debug_terminal(res)
        return res
    except ConnectionRefusedError as e:
        t_tcp = round((time.time() - t0) * 1000, 1)
        res["etapas"].append({
            "nome": "3. Conexão de Rede TCP (Socket)",
            "status": "erro",
            "detalhe": f"Conexão ativamente recusada na porta {porta}: {e}",
            "tempo_ms": t_tcp
        })
        res["mensagem"] = f"Conexão recusada pelo servidor {host}:{porta}."
        res["dica"] = f"O servidor no endereço informado recusou a conexão na porta {porta}. Verifique se o serviço SMTP está em execução e se a porta está correta."
        _imprimir_debug_terminal(res)
        return res
    except Exception as e:
        t_tcp = round((time.time() - t0) * 1000, 1)
        res["etapas"].append({
            "nome": "3. Conexão de Rede TCP (Socket)",
            "status": "erro",
            "detalhe": f"Falha de conexão TCP: {e}",
            "tempo_ms": t_tcp
        })
        res["mensagem"] = f"Erro ao conectar via TCP na porta {porta}: {e}"
        _imprimir_debug_terminal(res)
        return res

    # 4. Handshake SMTP, Negociação TLS/SSL e Autenticação
    stderr_buf = io.StringIO()
    server = None
    try:
        with redirect_stderr(stderr_buf):
            # Conexão SMTP / SMTP_SSL
            t0 = time.time()
            if porta == 465:
                server = smtplib.SMTP_SSL(host, porta, timeout=12)
                server.set_debuglevel(1)
                t_ssl = round((time.time() - t0) * 1000, 1)
                res["etapas"].append({
                    "nome": "4. Handshake de Criptografia SSL/TLS",
                    "status": "sucesso",
                    "detalhe": f"Conexão SSL/TLS direta estabelecida na porta 465 ({t_ssl} ms)",
                    "tempo_ms": t_ssl
                })
            else:
                server = smtplib.SMTP(host, porta, timeout=12)
                server.set_debuglevel(1)
                server.ehlo()
                
                if server.has_extn('STARTTLS'):
                    server.starttls()
                    server.ehlo()
                    t_tls = round((time.time() - t0) * 1000, 1)
                    res["etapas"].append({
                        "nome": "4. Handshake de Criptografia STARTTLS",
                        "status": "sucesso",
                        "detalhe": f"STARTTLS negociado com sucesso ({t_tls} ms)",
                        "tempo_ms": t_tls
                    })
                else:
                    t_plain = round((time.time() - t0) * 1000, 1)
                    res["etapas"].append({
                        "nome": "4. Handshake SMTP (Texto Puro)",
                        "status": "alerta",
                        "detalhe": f"Servidor não anunciou suporte a STARTTLS ({t_plain} ms)",
                        "tempo_ms": t_plain
                    })

            # Autenticação
            t0 = time.time()
            code_auth, msg_auth = server.login(user, senha)
            msg_auth_str = msg_auth.decode('utf-8', errors='ignore') if isinstance(msg_auth, bytes) else str(msg_auth)
            t_auth = round((time.time() - t0) * 1000, 1)
            res["etapas"].append({
                "nome": "5. Autenticação de Usuário",
                "status": "sucesso",
                "detalhe": f"Credenciais aceitas (Resposta {code_auth}: {msg_auth_str}) em {t_auth} ms",
                "tempo_ms": t_auth
            })

            # Envio de mensagem
            t0 = time.time()
            nome_sistema = config.get('nome_sistema') or 'Cantina Estudantil'
            sigla = config.get('sigla_instituicao') or ''
            conteudo_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto;
                        border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
                <div style="background: #2563eb; padding: 24px; text-align: center;">
                    <h2 style="color: white; margin: 0; font-size: 1.3rem;">✅ Teste de SMTP Concluído!</h2>
                    <p style="color: #bfdbfe; margin: 4px 0 0 0; font-size: 0.9rem;">{nome_sistema} ({sigla})</p>
                </div>
                <div style="padding: 26px; background: #ffffff; color: #1e293b;">
                    <p style="font-size: 1rem; margin-top: 0;">Parabéns! Se você recebeu esta mensagem, o servidor de e-mail da cantina está <strong>100% configurado e funcional</strong>.</p>
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; margin: 18px 0; font-size: 0.88rem;">
                        <div><strong>Host SMTP:</strong> {host}:{porta}</div>
                        <div><strong>Remetente Autenticado:</strong> {user}</div>
                        <div><strong>Destinatário de Teste:</strong> {email_dest}</div>
                        <div><strong>Data/Hora do Disparo:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</div>
                    </div>
                    <p style="color: #64748b; font-size: 0.82rem; margin-bottom: 0;">Este é um disparo de diagnóstico emitido pelo painel de administração.</p>
                </div>
            </div>
            """
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f'✅ Teste de SMTP Bem-Sucedido — {nome_sistema}'
            msg['From'] = formataddr((str(Header(nome_sistema, 'utf-8')), user))
            msg['To'] = email_dest
            msg.attach(MIMEText(conteudo_html, 'html'))

            server.send_message(msg)
            server.quit()
            t_send = round((time.time() - t0) * 1000, 1)
            res["etapas"].append({
                "nome": "6. Envio do E-mail de Teste",
                "status": "sucesso",
                "detalhe": f"Mensagem aceita e despachada para {email_dest} ({t_send} ms)",
                "tempo_ms": t_send
            })

            res["success"] = True
            res["mensagem"] = f"E-mail de teste enviado com sucesso para {email_dest}!"

    except smtplib.SMTPAuthenticationError as e:
        err_msg = e.smtp_error.decode('utf-8', errors='ignore') if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        res["etapas"].append({
            "nome": "5. Autenticação de Usuário",
            "status": "erro",
            "detalhe": f"Falha de autenticação ({e.smtp_code}): {err_msg}"
        })
        res["mensagem"] = f"Erro de Autenticação ({e.smtp_code}): Usuário ou senha incorretos."
        
        host_lower = host.lower()
        if 'gmail' in host_lower:
            res["dica"] = "Para o Gmail: o Google NÃO aceita a sua senha comum de login. É obrigatório ter a Verificação em 2 Etapas ativada na sua Conta Google e criar uma 'Senha de Aplicativo' (16 letras) em: https://myaccount.google.com/apppasswords"
        elif any(k in host_lower for k in ['outlook', 'office365', 'hotmail', 'live']):
            res["dica"] = "Para contas Microsoft/Outlook: Verifique se a autenticação básica SMTP AUTH está liberada para este usuário no painel de administração ou crie uma Senha de Aplicativo nas configurações de segurança."
        elif 'yahoo' in host_lower:
            res["dica"] = "Para o Yahoo Mail: É obrigatório gerar uma 'Senha de Aplicativo' (App Password) na central de segurança do Yahoo."
        else:
            res["dica"] = "Verifique se o usuário e a senha estão corretos. Alguns servidores corporativos exigem apenas o nome de usuário (sem @dominio) ou exigem TLS na porta 587."
            
    except smtplib.SMTPConnectError as e:
        res["etapas"].append({
            "nome": "4. Handshake SMTP",
            "status": "erro",
            "detalhe": f"Erro de conexão com o servidor SMTP: {e}"
        })
        res["mensagem"] = f"Não foi possível conectar ao servidor SMTP: {e}"
    except (smtplib.SMTPServerDisconnected, ConnectionResetError) as e:
        res["etapas"].append({
            "nome": "4. Handshake SMTP",
            "status": "erro",
            "detalhe": f"O servidor encerrou a conexão inesperadamente: {e}"
        })
        res["mensagem"] = f"Servidor SMTP encerrou a conexão inesperadamente: {e}"
        if porta == 587:
            res["dica"] = "Se o servidor fechou a conexão na porta 587, experimente trocar para a porta 465 (com SSL direto) ou confira se seu IP não está em lista de bloqueio."
        elif porta == 465:
            res["dica"] = "Se o servidor fechou a conexão na porta 465, experimente trocar para a porta 587 (com STARTTLS)."
    except smtplib.SMTPSenderRefused as e:
        sender = e.sender
        err_code = e.smtp_code
        err_msg = e.smtp_error.decode('utf-8', errors='ignore') if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        res["etapas"].append({
            "nome": "6. Envio do E-mail de Teste",
            "status": "erro",
            "detalhe": f"Remetente Recusado ({err_code}): {err_msg} (Remetente: {sender})"
        })
        res["mensagem"] = f"Remetente Recusado ({err_code}): O servidor SMTP não aceitou enviar a partir de '{sender}'."
        res["dica"] = f"O servidor SMTP recusou o remetente '{sender}'. Se você estiver usando um serviço de e-mail transacional (como Brevo, SendGrid, Amazon SES ou Mailgun), o e-mail do remetente precisa estar previamente verificado/autorizado no painel do provedor, ou a conta não tem permissão para enviar em nome deste domínio."
    except smtplib.SMTPRecipientsRefused as e:
        res["etapas"].append({
            "nome": "6. Envio do E-mail de Teste",
            "status": "erro",
            "detalhe": f"Destinatário Recusado: {e.recipients}"
        })
        res["mensagem"] = f"Destinatário Recusado: O servidor recusou a entrega para {email_dest}."
        res["dica"] = "Verifique se o endereço de destino foi digitado corretamente ou se o provedor está em modo de teste/sandbox (onde apenas destinatários verificados são permitidos)."
    except Exception as e:
        res["etapas"].append({
            "nome": "Execução do Protocolo SMTP",
            "status": "erro",
            "detalhe": f"Exceção ({type(e).__name__}): {e}"
        })
        res["mensagem"] = f"Erro no processo SMTP ({type(e).__name__}): {e}"
        res["traceback"] = traceback.format_exc()
    finally:
        if server:
            try:
                server.close()
            except Exception:
                pass
        res["log_protocolo"] = stderr_buf.getvalue()

    _imprimir_debug_terminal(res)
    return res

def _imprimir_debug_terminal(res):
    """Exibe o diagnóstico formatado no console do servidor para inspeção imediata."""
    print("\n" + "="*75, file=sys.stderr)
    print(f" [DIAGNÓSTICO SMTP] Teste para: {res.get('destinatario')} | Sucesso: {res.get('success')}", file=sys.stderr)
    print(f" Host: {res.get('host')}:{res.get('porta')} | Usuário: {res.get('user')}", file=sys.stderr)
    if not res.get("success"):
        print(f" Status: FALHA -> {res.get('mensagem')}", file=sys.stderr)
        if res.get("dica"):
            print(f" Dica Recomendada: {res.get('dica')}", file=sys.stderr)
    else:
        print(" Status: SUCESSO -> Conexão e envio efetuados com êxito!", file=sys.stderr)
        
    print("\n --- ETAPAS DO DIAGNÓSTICO ---", file=sys.stderr)
    for etapa in res.get("etapas", []):
        st = "✓" if etapa['status'] == 'sucesso' else ("!" if etapa['status'] == 'alerta' else "✗")
        print(f" [{st}] {etapa['nome']}: {etapa['detalhe']}", file=sys.stderr)

    if res.get("log_protocolo"):
        print("\n --- TRANSCRIÇÃO COMPLETA DO PROTOCOLO SMTP ---", file=sys.stderr)
        print(res["log_protocolo"].strip(), file=sys.stderr)

    if res.get("traceback"):
        print("\n --- RASTREAMENTO COMPLETO (TRACEBACK) ---", file=sys.stderr)
        print(res["traceback"].strip(), file=sys.stderr)

    print("="*75 + "\n", file=sys.stderr)
    sys.stderr.flush()


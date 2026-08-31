import smtplib
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
    if config['smtp_porta'] == 465:
        server = smtplib.SMTP_SSL(config['smtp_host'], config['smtp_porta'], timeout=10)
        if debug:
            server.set_debuglevel(1)
    else:
        server = smtplib.SMTP(config['smtp_host'], config['smtp_porta'], timeout=10)
        if debug:
            server.set_debuglevel(1)
        server.ehlo()
        server.starttls()
        server.ehlo()
    server.login(config['smtp_user'], config['smtp_senha'])
    return server

def enviar_qr_por_email(aluno, reserva, cardapio, config):
    """
    Envia o QR Code da reserva para o e-mail do aluno.
    Silencia exceções — falha no envio nunca bloqueia a reserva.
    """
    try:
        email_destino = aluno['email'] if aluno and aluno['email'] else None
        if not email_destino:
            return  # Aluno sem e-mail cadastrado — ignora silenciosamente

        if not config or not config['smtp_ativo'] or not config['smtp_host']:
            return  # SMTP não configurado — ignora

        if not config.get('email_qr_reserva'):
            return  # Envio de QR desativado — ignora

        # Gerar QR Code em memória
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(reserva['codigo_unico'])
        qr.make(fit=True)
        img = qr.make_image(fill_color="#CD191E", back_color="white")
        img_bytes = BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        data_fmt = datetime.strptime(cardapio['data'], '%Y-%m-%d').strftime('%d/%m/%Y')
        nome_sistema = config['nome_sistema'] or 'Cantina Estudantil'
        sigla = config['sigla_instituicao'] or ''

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

def enviar_email_recuperacao(aluno, reset_link, config):
    try:
        email_destino = aluno['email'] if aluno and aluno['email'] else None
        if not email_destino:
            return False

        if not config or not config['smtp_ativo'] or not config['smtp_host']:
            return False

        nome_sistema = config['nome_sistema'] or 'Cantina Estudantil'

        conteudo_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto;
                    border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden;">
            <div style="background: #2563eb; padding: 24px; text-align: center;">
                <h2 style="color: white; margin: 0;">🔒 Redefinição de Senha</h2>
            </div>
            <div style="padding: 28px;">
                <p>Olá, <strong>{aluno['nome']}</strong>!</p>
                <p>Recebemos um pedido para restaurar o escudo (senha) da sua conta.</p>
                <p>Se foi você, clique no botão abaixo para criar uma nova senha. O link é válido por 1 hora.</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_link}" style="background-color: #2563eb; color: white; padding: 12px 24px;
                       text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                       Redefinir Minha Senha
                    </a>
                </div>
                
                <p style="color: #6b7280; font-size: 0.85rem;">Se não foi você, ignore este e-mail. Seu escudo continuará intacto.</p>
            </div>
        </div>
        """

        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'Recuperação de Senha — {nome_sistema}'
        msg['From'] = formataddr((str(Header(nome_sistema, 'utf-8')), config['smtp_user']))
        msg['To'] = email_destino

        msg.attach(MIMEText(conteudo_html, 'html'))

        with _build_smtp_server(config) as server:
            server.send_message(msg)
        return True
    except Exception as e:
        print("Erro ao enviar e-mail de recuperação:", e)
        return False

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import qrcode
import base64
from io import BytesIO
import threading
import sqlite3

from database import closing, get_db_connection, get_config, get_proximos_cardapios, generate_unique_code
from utils.auth import is_logged_in_aluno
from utils.helpers import date_hoje_str, datetime_now_str, pode_reservar
from utils.qrcode_gen import generate_badge_code, generate_std_badge_code
from utils.mailer import enviar_qr_por_email

aluno_bp = Blueprint('aluno', __name__)

def handle_login_success(aluno):
    # Movemos para utils/auth ou importamos de main?
    # Melhor isolar ou apenas redirecionar para aluno_dashboard.
    pass

@aluno_bp.route('/aluno/selecionar_contexto', methods=['GET', 'POST'])
def aluno_selecionar_contexto():
    if not is_logged_in_aluno() or 'contextos_disponiveis' not in session:
        return redirect(url_for('main.login'))
        
    contextos = session['contextos_disponiveis']
    
    if request.method == 'POST':
        escolha_id = request.form.get('contexto_id')
        if escolha_id:
            try:
                escolha_id = int(escolha_id)
                escolhido = next((c for c in contextos if c['id'] == escolha_id), None)
                if escolhido:
                    session['contexto_turma_id'] = escolhido['id']
                    session['contexto_nome'] = escolhido['nome']
                    session.pop('contextos_disponiveis', None)
                    return redirect(url_for('aluno.aluno_dashboard'))
            except ValueError:
                pass
        flash('Selecione uma opção válida.', 'error')
        
    return render_template('selecionar_contexto.html', contextos=contextos)

@aluno_bp.route('/aluno/trocar_contexto')
def aluno_trocar_contexto():
    if not is_logged_in_aluno():
        return redirect(url_for('main.login'))
        
    aluno_id = session['aluno_id']
    from routes.main import handle_login_success
    with closing(get_db_connection()) as conn:
        aluno = conn.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
        if aluno:
            return handle_login_success(aluno)
            
    return redirect(url_for('aluno.aluno_dashboard'))

@aluno_bp.route('/aluno')
def aluno_dashboard():
    if not is_logged_in_aluno():
        return redirect(url_for('main.login'))
        
    aluno_id = session['aluno_id']
    hoje_str = date_hoje_str()
    
    config = get_config()
    horario_limite = config['horario_limite']
    max_reservas = config['max_reservas_ativas'] if 'max_reservas_ativas' in config.keys() else 1
    
    refeicoes_hoje = []
    reservas_ativas_count = 0
    
    with closing(get_db_connection()) as conn:
        aluno_req = conn.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
        
        todas_ativas = conn.execute(
            "SELECT r.id, c.data FROM reservas r JOIN cardapios c ON r.cardapio_id = c.id WHERE r.aluno_id = ? AND r.status = 'ATIVA'",
            (aluno_id,)
        ).fetchall()
        
        for r in todas_ativas:
            if pode_reservar(r['data'], horario_limite):
                reservas_ativas_count += 1
        
        cardapios_hoje = conn.execute("SELECT * FROM cardapios WHERE data = ? ORDER BY id ASC", (hoje_str,)).fetchall()
        for ch in cardapios_hoje:
            reserva = conn.execute("SELECT * FROM reservas WHERE aluno_id = ? AND cardapio_id = ? AND status != 'CANCELADA'", (aluno_id, ch['id'])).fetchone()
            qr_code = None
            if reserva and reserva['status'] == 'ATIVA':
                qr = qrcode.QRCode(version=1, box_size=10, border=3)
                qr.add_data(reserva['codigo_unico'])
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                qr_code = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            refeicoes_hoje.append({
                'cardapio': ch,
                'reserva': reserva,
                'qr_code': qr_code
            })

    proximos_cardapios = get_proximos_cardapios(hoje_str)
    cardapios_abertos = []
    
    unreserved_needed = max(0, max_reservas - reservas_ativas_count)

    with closing(get_db_connection()) as conn:
        for c in proximos_cardapios:
            if c['data'] != hoje_str:
                reserva = conn.execute(
                    "SELECT * FROM reservas WHERE aluno_id = ? AND cardapio_id = ? AND status = 'ATIVA'",
                    (aluno_id, c['id'])
                ).fetchone()
                
                dentro_prazo = pode_reservar(c['data'], horario_limite)
                
                if dentro_prazo:
                    if reserva or (c['permitir_reserva'] == 1 and unreserved_needed > 0):
                        qr_b64 = None
                        if reserva:
                            qr = qrcode.QRCode()
                            qr.add_data(reserva['codigo_unico'])
                            qr.make(fit=True)
                            img = qr.make_image(fill_color="#4F46E5", back_color="white")
                            buffered = BytesIO()
                            img.save(buffered, format="PNG")
                            qr_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                        
                        cardapios_abertos.append({
                            'cardapio': c,
                            'reserva': reserva,
                            'qr_code': qr_b64,
                            'perdeu_prazo': False
                        })
                        
                        if not reserva:
                            unreserved_needed -= 1
                else:
                    # O prazo encerrou.
                    if reserva:
                        qr_b64 = None
                        qr = qrcode.QRCode()
                        qr.add_data(reserva['codigo_unico'])
                        qr.make(fit=True)
                        img = qr.make_image(fill_color="#4F46E5", back_color="white")
                        buffered = BytesIO()
                        img.save(buffered, format="PNG")
                        qr_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                        
                        cardapios_abertos.append({
                            'cardapio': c,
                            'reserva': reserva,
                            'qr_code': qr_b64,
                            'perdeu_prazo': False
                        })
                    elif c['permitir_reserva'] == 1:
                        # Não reservou e perdeu o prazo (mostra na tela como pendência/aviso)
                        cardapios_abertos.append({
                            'cardapio': c,
                            'reserva': None,
                            'qr_code': None,
                            'perdeu_prazo': True
                        })

    cardapio_aberto = cardapios_abertos[0]['cardapio'] if cardapios_abertos else None
    reserva_aberto = cardapios_abertos[0]['reserva'] if cardapios_abertos else None
    qr_code_aberto = cardapios_abertos[0]['qr_code'] if cardapios_abertos else None
    dentro_do_prazo_aberto = bool(cardapios_abertos)

    contexto_turma_id = session.get('contexto_turma_id')
    contexto_is_evento = False
    qr_code_cracha = None
    
    with closing(get_db_connection()) as conn:
        turma_ctx = conn.execute("SELECT * FROM turmas WHERE id = ?", (contexto_turma_id,)).fetchone()
        if turma_ctx and turma_ctx['is_evento'] == 1:
            contexto_is_evento = True
            ep = conn.execute("SELECT codigo_cracha FROM eventos_participantes WHERE aluno_id = ? AND turma_id = ?", (aluno_id, contexto_turma_id)).fetchone()
            
            codigo_final = None
            if not ep:
                codigo_final = generate_badge_code(contexto_turma_id, aluno_id)
                try:
                    conn.execute("INSERT INTO eventos_participantes (aluno_id, turma_id, codigo_cracha) VALUES (?, ?, ?)", (aluno_id, contexto_turma_id, codigo_final))
                    conn.commit()
                except sqlite3.IntegrityError:
                    pass
            elif not ep['codigo_cracha']:
                codigo_final = generate_badge_code(contexto_turma_id, aluno_id)
                conn.execute("UPDATE eventos_participantes SET codigo_cracha = ? WHERE aluno_id = ? AND turma_id = ?", (codigo_final, aluno_id, contexto_turma_id))
                conn.commit()
            else:
                codigo_final = ep['codigo_cracha']
            
            if codigo_final:
                qr = qrcode.QRCode(version=1, box_size=8, border=3)
                qr.add_data(codigo_final)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                qr_code_cracha = base64.b64encode(buffered.getvalue()).decode("utf-8")

    qr_code_cracha_std = None
    if not contexto_is_evento:
        with closing(get_db_connection()) as conn:
            aluno_row = conn.execute("SELECT codigo_cracha FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
            codigo_std = None
            if aluno_row:
                if aluno_row['codigo_cracha']:
                    codigo_std = aluno_row['codigo_cracha']
                else:
                    codigo_std = generate_std_badge_code(aluno_id)
                    conn.execute("UPDATE alunos SET codigo_cracha = ? WHERE id = ?", (codigo_std, aluno_id))
                    conn.commit()
            
            if codigo_std:
                qr_std = qrcode.QRCode(version=1, box_size=8, border=3)
                qr_std.add_data(codigo_std)
                qr_std.make(fit=True)
                img_std = qr_std.make_image(fill_color="#065f46", back_color="white") 
                buffered_std = BytesIO()
                img_std.save(buffered_std, format="PNG")
                qr_code_cracha_std = base64.b64encode(buffered_std.getvalue()).decode("utf-8")

    with closing(get_db_connection()) as conn:
        avisos = conn.execute("SELECT * FROM avisos ORDER BY id DESC").fetchall()
        
        hoje = datetime.now().strftime('%Y-%m-%d')
        total_contextos = 0
        if aluno_req['turma_id']: total_contextos += 1
        
        eventos_extras = conn.execute("""
            SELECT COUNT(*) FROM eventos_participantes ep
            JOIN turmas t ON t.id = ep.turma_id
            WHERE ep.aluno_id = ? AND t.is_evento = 1
            AND (t.data_inicio IS NULL OR t.data_inicio <= ?)
            AND (t.data_fim IS NULL OR t.data_fim >= ?)
        """, (aluno_id, hoje, hoje)).fetchone()[0]
        
        total_contextos += eventos_extras
        tem_multiplos = total_contextos > 1
        
        # Buscar últimas refeições consumidas sem avaliação nos últimos 7 dias (Ponto 11)
        refeicoes_para_avaliar = conn.execute("""
            SELECT r.id as reserva_id, c.data, c.tipo_refeicao, c.descricao
            FROM reservas r
            JOIN cardapios c ON r.cardapio_id = c.id
            WHERE r.aluno_id = ? AND r.status = 'CONSUMIDA' AND r.avaliacao_nota IS NULL
            AND c.data >= date('now', '-7 days')
            ORDER BY c.data DESC LIMIT 3
        """, (aluno_id,)).fetchall()
            
    return render_template(
        'aluno_dashboard.html', 
        aluno_ativo=aluno_req,
        refeicoes_hoje=refeicoes_hoje,
        cardapio_aberto=cardapio_aberto,
        reserva_aberto=reserva_aberto,
        qr_code_aberto=qr_code_aberto,
        dentro_do_prazo_aberto=dentro_do_prazo_aberto,
        cardapios_abertos=cardapios_abertos,
        proximos_cardapios=proximos_cardapios,
        avisos=avisos,
        reservas_ativas_count=reservas_ativas_count,
        max_reservas=max_reservas,
        tem_multiplos=tem_multiplos,
        contexto_is_evento=contexto_is_evento,
        contexto_evento=turma_ctx,
        qr_code_cracha=qr_code_cracha,
        qr_code_cracha_std=qr_code_cracha_std,
        refeicoes_para_avaliar=refeicoes_para_avaliar
    )

@aluno_bp.route('/aluno/reservar/<int:cardapio_id>', methods=['POST'])
def reservar(cardapio_id):
    if not is_logged_in_aluno(): return redirect(url_for('main.login'))
    
    aluno_id = session['aluno_id']
    config = get_config()
    horario_limite = config['horario_limite']
    
    max_reservas = config['max_reservas_ativas'] if 'max_reservas_ativas' in config.keys() else 1
    
    with closing(get_db_connection()) as conn:
        aluno = conn.execute('SELECT * FROM alunos WHERE id = ?', (aluno_id,)).fetchone()
        cardapio = conn.execute('SELECT * FROM cardapios WHERE id = ?', (cardapio_id,)).fetchone()
        
        if not aluno or aluno['permitido_almoco'] == 0:
            flash('Você não possui permissão para reservar antecipadamente. Compareça à fila de sobras no horário de entrega.', 'error')
            return redirect(url_for('aluno.aluno_dashboard'))
            
        if not cardapio:
            flash('Cardápio não encontrado.', 'error')
            return redirect(url_for('aluno.aluno_dashboard'))

        if cardapio['permitir_reserva'] == 0:
            flash('Este cardápio não está disponível para reserva antecipada (Acesso apenas via crachá de evento ou sobras).', 'warning')
            return redirect(url_for('aluno.aluno_dashboard'))
            
        if not pode_reservar(cardapio['data'], horario_limite):
            flash('O prazo para reservar esta refeição já encerrou.', 'error')
            return redirect(url_for('aluno.aluno_dashboard'))
            
        existente = conn.execute('SELECT id, status FROM reservas WHERE aluno_id = ? AND cardapio_id = ?', (aluno_id, cardapio_id)).fetchone()
        
        if existente:
            if existente['status'] == 'CANCELADA':
                todas_ativas = conn.execute(
                    "SELECT r.id, c.data FROM reservas r JOIN cardapios c ON r.cardapio_id = c.id WHERE r.aluno_id = ? AND r.status = 'ATIVA'",
                    (aluno_id,)
                ).fetchall()
                ativas_count = sum(1 for r in todas_ativas if pode_reservar(r['data'], horario_limite))
                
                if ativas_count >= max_reservas:
                    flash(f'Você atingiu o limite de {max_reservas} reserva(s) ativa(s) futuras. Cancele uma reserva existente antes de fazer outra.', 'error')
                    return redirect(url_for('aluno.aluno_dashboard'))
                
                contexto_turma = session.get('contexto_turma_id')
                novo_codigo = generate_unique_code()
                conn.execute("UPDATE reservas SET status='ATIVA', codigo_unico=?, turma_id=? WHERE id = ?", (novo_codigo, contexto_turma, existente['id']))
                conn.commit()
                flash('Reserva reativada com sucesso!', 'success')
                reserva_atualizada = conn.execute("SELECT * FROM reservas WHERE id = ?", (existente['id'],)).fetchone()
                threading.Thread(target=enviar_qr_por_email, args=(aluno, reserva_atualizada, cardapio, config)).start()
            else:
                flash('Você já possui uma reserva.', 'warning')
        else:
            todas_ativas = conn.execute(
                "SELECT r.id, c.data FROM reservas r JOIN cardapios c ON r.cardapio_id = c.id WHERE r.aluno_id = ? AND r.status = 'ATIVA'",
                (aluno_id,)
            ).fetchall()
            ativas_count = sum(1 for r in todas_ativas if pode_reservar(r['data'], horario_limite))
            
            if ativas_count >= max_reservas:
                flash(f'Você atingiu o limite de {max_reservas} reserva(s) ativa(s) futuras. Cancele uma reserva existente antes de fazer outra.', 'error')
                return redirect(url_for('aluno.aluno_dashboard'))
            
            contexto_turma = session.get('contexto_turma_id')
            novo_codigo = generate_unique_code()
            conn.execute(
                "INSERT INTO reservas (aluno_id, cardapio_id, codigo_unico, data_registro, turma_id) VALUES (?, ?, ?, ?, ?)",
                (aluno_id, cardapio_id, novo_codigo, datetime_now_str(), contexto_turma)
            )
            conn.commit()
            flash('Reserva confirmada com sucesso!', 'success')
            reserva_nova = conn.execute(
                "SELECT * FROM reservas WHERE aluno_id = ? AND cardapio_id = ? AND status = 'ATIVA'",
                (aluno_id, cardapio_id)
            ).fetchone()
            threading.Thread(target=enviar_qr_por_email, args=(aluno, reserva_nova, cardapio, config)).start()
            
    return redirect(url_for('aluno.aluno_dashboard'))

@aluno_bp.route('/aluno/cancelar/<int:cardapio_id>', methods=['POST'])
def cancelar_reserva(cardapio_id):
    if not is_logged_in_aluno(): return redirect(url_for('main.login'))
    
    aluno_id = session['aluno_id']
    config = get_config()
    horario_limite = config['horario_limite']
    
    with closing(get_db_connection()) as conn:
        reserva = conn.execute(
            "SELECT r.*, c.data FROM reservas r JOIN cardapios c ON r.cardapio_id = c.id WHERE r.aluno_id = ? AND r.cardapio_id = ?", 
            (aluno_id, cardapio_id)
        ).fetchone()
        
        if reserva and reserva['status'] == 'ATIVA':
            if not pode_reservar(reserva['data'], horario_limite):
                 flash('O prazo para cancelar a reserva já encerrou.', 'error')
            else:
                conn.execute("UPDATE reservas SET status='CANCELADA' WHERE id = ?", (reserva['id'],))
                conn.commit()
                flash('Sua reserva foi cancelada com sucesso.', 'success')
                
    return redirect(url_for('aluno.aluno_dashboard'))

@aluno_bp.route('/aluno/avaliar/<int:reserva_id>', methods=['POST'])
def avaliar_refeicao(reserva_id):
    if not is_logged_in_aluno(): return redirect(url_for('main.login'))
    aluno_id = session['aluno_id']
    nota = request.form.get('nota', type=int)
    comentario = request.form.get('comentario', '').strip()
    
    if not nota or nota < 1 or nota > 5:
        flash('Nota de avaliação inválida.', 'error')
        return redirect(url_for('aluno.aluno_dashboard'))
        
    with closing(get_db_connection()) as conn:
        # Verifica se a reserva pertence ao aluno e foi consumida
        reserva = conn.execute("SELECT id FROM reservas WHERE id = ? AND aluno_id = ? AND status = 'CONSUMIDA'", (reserva_id, aluno_id)).fetchone()
        if reserva:
            conn.execute("UPDATE reservas SET avaliacao_nota = ?, avaliacao_comentario = ? WHERE id = ?", (nota, comentario, reserva_id))
            conn.commit()
            flash('Agradecemos pelo seu feedback! Sua avaliação ajuda a melhorar nossa cantina.', 'success')
        else:
            flash('Refeição não encontrada ou não disponível para avaliação.', 'error')
            
    return redirect(url_for('aluno.aluno_dashboard'))

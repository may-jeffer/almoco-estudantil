# -*- coding: utf-8 -*-
import json
from datetime import datetime

def get_perfil_nutricional(conn):
    """Retorna estatísticas consolidadas de restrições alimentares ativas (Ponto 18)."""
    rows = conn.execute("""
        SELECT restricoes, COUNT(*) as total
        FROM alunos
        WHERE restricoes IS NOT NULL AND restricoes != '' AND (turma_id IS NOT NULL AND turma_id NOT IN (SELECT id FROM turmas WHERE is_evento = 1))
        GROUP BY restricoes
        ORDER BY total DESC
    """).fetchall()
    return [dict(r) for r in rows]

def get_avaliacoes_refeicoes(conn):
    """Retorna estatísticas de satisfação e os últimos comentários de feedback dos alunos (Ponto 11)."""
    media_row = conn.execute("""
        SELECT AVG(avaliacao_nota) as media, COUNT(avaliacao_nota) as total
        FROM reservas
        WHERE avaliacao_nota IS NOT NULL
    """).fetchone()
    
    comentarios = conn.execute("""
        SELECT r.avaliacao_nota, r.avaliacao_comentario, a.nome as aluno_nome, c.data, c.tipo_refeicao
        FROM reservas r
        JOIN alunos a ON r.aluno_id = a.id
        JOIN cardapios c ON r.cardapio_id = c.id
        WHERE r.avaliacao_nota IS NOT NULL
        ORDER BY r.id DESC LIMIT 15
    """).fetchall()
    
    # Detalhar quantidade de estrelas de 1 a 5
    dist_rows = conn.execute("""
        SELECT avaliacao_nota, COUNT(*) as qtd
        FROM reservas
        WHERE avaliacao_nota IS NOT NULL
        GROUP BY avaliacao_nota
    """).fetchall()
    
    distribuicao = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for row in dist_rows:
        distribuicao[row['avaliacao_nota']] = row['qtd']
        
    return {
        'media': round(media_row['media'], 2) if media_row['media'] else 0.0,
        'total': media_row['total'] or 0,
        'comentarios': [dict(c) for c in comentarios],
        'distribuicao': distribuicao
    }

def calcular_previsao_demanda_ia(conn):
    """Calcula a previsão de consumo para o próximo cardápio usando Média Móvel Ponderada (Ponto 10)."""
    # 1. Seleciona os últimos 5 cardápios servidos no passado para servir de histórico
    ultimos_cardapios = conn.execute("""
        SELECT c.id,
               (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status != 'CANCELADA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL)) as reservas,
               (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status = 'CONSUMIDA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL)) as consumidas,
               (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status = 'CONSUMIDA' AND r.tipo_consumo = 'EXTRA') as extras
        FROM cardapios c
        WHERE c.data <= date('now')
        ORDER BY c.data DESC LIMIT 5
    """).fetchall()
    
    taxas_presenca = []
    extras_lista = []
    
    for uc in ultimos_cardapios:
        res = uc['reservas']
        con = uc['consumidas']
        ext = uc['extras']
        if res > 0:
            taxas_presenca.append(con / res)
        else:
            taxas_presenca.append(0.85)  # Taxa padrão se não houver dados
        extras_lista.append(ext)
        
    taxa_media_presenca = sum(taxas_presenca) / len(taxas_presenca) if taxas_presenca else 0.85
    extra_medio = sum(extras_lista) / len(extras_lista) if extras_lista else 10
    
    # 2. Busca a próxima refeição futura (agendada)
    proxima_refeicao = conn.execute("""
        SELECT c.id, c.data, c.tipo_refeicao, c.descricao,
               (SELECT COUNT(*) FROM reservas r WHERE r.cardapio_id = c.id AND r.status != 'CANCELADA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL)) as reservas_atuais
        FROM cardapios c
        WHERE c.data >= date('now')
        ORDER BY c.data ASC LIMIT 1
    """).fetchone()
    
    if proxima_refeicao:
        reservas_atuais = proxima_refeicao['reservas_atuais']
        previsto_normal = int(reservas_atuais * taxa_media_presenca)
        previsto_extra = int(extra_medio)
        return {
            'existe': True,
            'data': proxima_refeicao['data'],
            'tipo_refeicao': proxima_refeicao['tipo_refeicao'],
            'reservas_atuais': reservas_atuais,
            'taxa_esperada': round(taxa_media_presenca * 100, 1),
            'porcoes_normais': previsto_normal,
            'porcoes_extras': previsto_extra,
            'porcoes_totais': previsto_normal + previsto_extra
        }
    else:
        # Se não houver cardápio futuro, retorna os baselines recomendados
        media_consumidas = int(sum(uc['consumidas'] for uc in ultimos_cardapios) / len(ultimos_cardapios)) if ultimos_cardapios else 100
        return {
            'existe': False,
            'baseline_normal': media_consumidas,
            'baseline_extra': int(extra_medio),
            'taxa_esperada': round(taxa_media_presenca * 100, 1)
        }

def buscar_estudantes_frequencia(conn, q, turma_id=None):
    """Busca alunos e calcula o total de reservas, consumos e ausências (Ponto Frequência)."""
    params = []
    query = """
        SELECT a.id, a.nome, a.matricula, t.nome as turma_nome,
               (SELECT COUNT(*) FROM reservas r WHERE r.aluno_id = a.id AND r.status != 'CANCELADA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL)) as total_reservas,
               (SELECT COUNT(*) FROM reservas r WHERE r.aluno_id = a.id AND r.status = 'CONSUMIDA') as total_consumidas,
               (SELECT COUNT(*) FROM reservas r WHERE r.aluno_id = a.id AND r.status = 'ATIVA' AND (r.tipo_consumo = 'NORMAL' OR r.tipo_consumo IS NULL)) as total_ausencias
        FROM alunos a
        LEFT JOIN turmas t ON a.turma_id = t.id
        WHERE 1=1
    """
    
    if q:
        query += " AND (remove_accents(a.nome) LIKE remove_accents(?) OR a.matricula LIKE ? OR a.cpf LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
        
    if turma_id:
        query += " AND a.turma_id = ?"
        params.append(turma_id)
        
    query += """
        ORDER BY a.nome ASC
        LIMIT 25
    """
    
    rows = conn.execute(query, params).fetchall()
    
    alunos = []
    for r in rows:
        alunos.append({
            'id': r['id'],
            'nome': r['nome'],
            'matricula': r['matricula'],
            'turma_nome': r['turma_nome'] or "Sem turma",
            'total_reservas': r['total_reservas'],
            'total_consumidas': r['total_consumidas'],
            'total_ausencias': r['total_ausencias']
        })
    return alunos

def obter_detalhes_frequencia_estudante(conn, aluno_id):
    """Retorna detalhes da frequência de um aluno e o histórico de refeições."""
    aluno = conn.execute("""
        SELECT a.nome, a.matricula, a.cpf, t.nome as turma_nome
        FROM alunos a
        LEFT JOIN turmas t ON a.turma_id = t.id
        WHERE a.id = ?
    """, (aluno_id,)).fetchone()
    
    if not aluno:
        return None
        
    reservas = conn.execute("""
        SELECT r.status, r.tipo_consumo, c.data, c.tipo_refeicao
        FROM reservas r
        JOIN cardapios c ON r.cardapio_id = c.id
        WHERE r.aluno_id = ? AND r.status != 'CANCELADA'
        ORDER BY c.data DESC
    """, (aluno_id,)).fetchall()
    
    total_reservas = sum(1 for r in reservas if r['tipo_consumo'] not in ('EXTRA', 'EVENTO'))
    total_consumidas = sum(1 for r in reservas if r['status'] == 'CONSUMIDA')
    total_ausencias = sum(1 for r in reservas if r['status'] == 'ATIVA' and r['tipo_consumo'] not in ('EXTRA', 'EVENTO'))
    
    historico = []
    for r in reservas:
        historico.append({
            'data': r['data'],
            'tipo_refeicao': r['tipo_refeicao'],
            'status': r['status'],
            'tipo_consumo': r['tipo_consumo']
        })
        
    return {
        'nome': aluno['nome'],
        'matricula': aluno['matricula'],
        'cpf': aluno['cpf'],
        'turma_nome': aluno['turma_nome'] or "Sem turma",
        'stats': {
            'total_reservas': total_reservas,
            'total_consumidas': total_consumidas,
            'total_ausencias': total_ausencias
        },
        'historico': historico
    }

def obter_alunos_sem_consumo(conn):
    """Retorna os alunos que nunca consumiram nenhuma refeição."""
    rows = conn.execute("""
        SELECT a.nome, a.matricula, t.nome as turma_nome
        FROM alunos a
        LEFT JOIN turmas t ON a.turma_id = t.id
        WHERE a.id NOT IN (
            SELECT DISTINCT aluno_id FROM reservas WHERE status = 'CONSUMIDA'
        )
        ORDER BY a.nome ASC
    """).fetchall()
    return [dict(r) for r in rows]

def obter_alunos_sem_reserva(conn):
    """Retorna os alunos que nunca realizaram nenhuma reserva no sistema."""
    rows = conn.execute("""
        SELECT a.nome, a.matricula, t.nome as turma_nome
        FROM alunos a
        LEFT JOIN turmas t ON a.turma_id = t.id
        WHERE a.id NOT IN (
            SELECT DISTINCT aluno_id FROM reservas
        )
        ORDER BY a.nome ASC
    """).fetchall()
    return [dict(r) for r in rows]


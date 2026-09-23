# -*- coding: utf-8 -*-
"""
Suíte de Testes Automatizados para Bloqueio de Reserva por Turma em Dias da Semana:
1. Esquema e Coluna 'dias_bloqueados' em 'turmas'
2. Funções auxiliares (parse_dias_bloqueados, formatar_dias_bloqueados)
3. Cadastro e Edição de Turma com Dias Bloqueados no Painel Admin
4. Bloqueio de Reserva Manual no Portal do Aluno em Dias Bloqueados
5. Cancelamento Automático de Reservas Futuras ao Bloquear um Dia da Turma
6. Proteção na Recorrência Semanal (salvamento e sincronização automática)
"""
import sqlite3
from datetime import datetime, timedelta
from app import app
from database.connection import get_db_connection, init_db
from utils.helpers import (
    parse_dias_bloqueados, formatar_dias_bloqueados, DIAS_SEMANA_NOMES,
    sincronizar_reservas_recorrentes
)

def testar_bloqueio_turma_dias():
    print("\n========================================================")
    print("TESTE: BLOQUEIO DE RESERVA POR TURMA EM DIAS DA SEMANA")
    print("========================================================")

    init_db()

    # --- 1. TESTE DE ESQUEMA ---
    print("\n--- 1. Validação de Esquema no Banco de Dados ---")
    with get_db_connection() as conn:
        cols = [c[1] for c in conn.execute("PRAGMA table_info(turmas)").fetchall()]
        assert 'dias_bloqueados' in cols, "Coluna 'dias_bloqueados' não encontrada na tabela 'turmas'!"
        print("  [OK] Coluna 'dias_bloqueados' confirmada na tabela 'turmas'.")

    # --- 2. TESTE DOS HELPERS ---
    print("\n--- 2. Validação das Funções Auxiliares ---")
    assert parse_dias_bloqueados("2,4") == {2, 4}
    assert parse_dias_bloqueados("") == set()
    assert parse_dias_bloqueados(["0", "3"]) == {0, 3}
    assert formatar_dias_bloqueados("2,4") == "Quarta-feira, Sexta-feira"
    assert formatar_dias_bloqueados("2,4", abrev=True) == "Qua, Sex"
    print("  [OK] Funções de parsing e formatação validadas com sucesso.")

    admin_client = app.test_client()
    with admin_client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['admin_id'] = 1
        sess['admin_usuario'] = 'admin_teste'
        sess['admin_perfil'] = 'admin_mestre'
        sess['admin_permissoes'] = ['all']

    with get_db_connection() as conn:
        # Limpar registros anteriores de teste
        conn.execute("DELETE FROM turmas WHERE nome LIKE '%Turma Bloq Teste%'")
        conn.execute("DELETE FROM alunos WHERE matricula = 'TEST_BLOQ_ALUNO'")
        conn.commit()

    # --- 3. TESTE DE CADASTRO E EDIÇÃO DE TURMA NO ADMIN ---
    print("\n--- 3. Cadastro e Edição de Turma com Dias Bloqueados ---")
    # Cadastrar turma bloqueando Quarta-feira (2) e Sexta-feira (4)
    resp_cad = admin_client.post('/admin/turmas', data={
        'nome': 'Turma Bloq Teste',
        'curso': 'Curso Técnico em Agropecuária - PTG',
        'serie_ano': '3',
        'ano_letivo': '2026',
        'dias_bloqueados': ['2', '4']
    }, follow_redirects=True)
    assert resp_cad.status_code == 200

    with get_db_connection() as conn:
        turma = conn.execute("SELECT * FROM turmas WHERE nome LIKE '%Turma Bloq Teste%' OR nome LIKE '3º - Curso Técnico em Agropecuária - PTG' ORDER BY id DESC LIMIT 1").fetchone()
        assert turma is not None, "Turma não foi inserida no banco!"
        turma_id = turma['id']
        assert turma['dias_bloqueados'] == '2,4', f"Dias bloqueados incorretos: {turma['dias_bloqueados']}"
        print(f"  [OK] Turma criada com sucesso. ID {turma_id}, dias_bloqueados = '{turma['dias_bloqueados']}'.")

    # --- 4. TESTE DE BLOQUEIO DE RESERVA MANUAL PELO ALUNO ---
    print("\n--- 4. Bloqueio de Reserva Manual no Portal do Aluno ---")
    with get_db_connection() as conn:
        # Cadastrar aluno nesta turma
        cur = conn.execute("""
            INSERT INTO alunos (nome, matricula, cpf, data_nascimento, senha_hash, turma_id, permitido_almoco, situacao_matricula)
            VALUES ('Aluno Teste Bloqueio', 'TEST_BLOQ_ALUNO', '99988877766', '2005-01-01', 'hash123', ?, 1, 'Matriculado')
        """, (turma_id,))
        aluno_id = cur.lastrowid

        # Criar cardápio para uma Quarta-feira futura (bloqueada)
        hoje = datetime.now()
        # Encontrar próxima quarta-feira
        dias_ate_quarta = (2 - hoje.weekday()) % 7
        if dias_ate_quarta == 0: dias_ate_quarta = 7
        data_quarta = (hoje + timedelta(days=dias_ate_quarta)).strftime('%Y-%m-%d')

        conn.execute("DELETE FROM cardapios WHERE data = ?", (data_quarta,))
        cur = conn.execute("INSERT INTO cardapios (data, tipo_refeicao, descricao, permitir_reserva) VALUES (?, 'Almoço', 'Quarta Bloqueada', 1)", (data_quarta,))
        cardapio_quarta_id = cur.lastrowid

        # Criar cardápio para uma Terça-feira futura (liberada)
        dias_ate_terca = (1 - hoje.weekday()) % 7
        if dias_ate_terca == 0: dias_ate_terca = 7
        data_terca = (hoje + timedelta(days=dias_ate_terca)).strftime('%Y-%m-%d')

        conn.execute("DELETE FROM cardapios WHERE data = ?", (data_terca,))
        cur = conn.execute("INSERT INTO cardapios (data, tipo_refeicao, descricao, permitir_reserva) VALUES (?, 'Almoço', 'Terça Liberada', 1)", (data_terca,))
        cardapio_terca_id = cur.lastrowid

        # Garante regra de janela aberta para os testes
        for d_num in [1, 2]:
            conn.execute("""
                UPDATE config_janelas_reserva 
                SET ativo = 1, abertura_semana_offset = 2, abertura_dia_semana = 0, abertura_horario = '00:00',
                    fechamento_semana_offset = 0, fechamento_dia_semana = 6, fechamento_horario = '23:59'
                WHERE dia_refeicao = ?
            """, (d_num,))
        conn.commit()

    aluno_client = app.test_client()
    with aluno_client.session_transaction() as sess:
        sess['aluno_id'] = aluno_id
        sess['aluno_nome'] = 'Aluno Teste Bloqueio'
        sess['aluno_matricula'] = 'TEST_BLOQ_ALUNO'

    # 4.1 Tentar reservar na Quarta-feira (bloqueada para a turma)
    resp_quarta = aluno_client.post(f'/aluno/reservar/{cardapio_quarta_id}', follow_redirects=True)
    conteudo_quarta = resp_quarta.get_data(as_text=True)
    assert "reserva de almoço bloqueada" in conteudo_quarta.lower() or "bloqueada" in conteudo_quarta.lower(), "Deveria ter bloqueado a reserva na quarta!"

    with get_db_connection() as conn:
        res_quarta = conn.execute("SELECT id FROM reservas WHERE aluno_id = ? AND cardapio_id = ?", (aluno_id, cardapio_quarta_id)).fetchone()
        assert res_quarta is None, "Reserva foi inserida indevidamente em dia bloqueado!"
        print("  [OK] Tentativa de reserva em dia bloqueado (Quarta-feira) foi rejeitada com sucesso.")

    # 4.2 Reservar na Terça-feira (dia liberado)
    resp_terca = aluno_client.post(f'/aluno/reservar/{cardapio_terca_id}', follow_redirects=True)
    with get_db_connection() as conn:
        res_terca = conn.execute("SELECT id, status FROM reservas WHERE aluno_id = ? AND cardapio_id = ?", (aluno_id, cardapio_terca_id)).fetchone()
        assert res_terca is not None and res_terca['status'] == 'ATIVA', "Reserva em dia liberado falhou!"
        reserva_terca_id = res_terca['id']
        print("  [OK] Reserva em dia liberado (Terça-feira) confirmada com sucesso.")

    # --- 5. TESTE DE CANCELAMENTO AUTOMÁTICO DE RESERVAS EXISTENTES ---
    print("\n--- 5. Cancelamento Automático de Reservas ao Bloquear Dia da Turma ---")
    # Agora a administração edita a turma e BLOQUEIA também a Terça-feira (1)
    resp_edit = admin_client.post(f'/admin/turmas/editar/{turma_id}', data={
        'nome': 'Turma Bloq Teste',
        'curso': 'Curso Técnico em Agropecuária - PTG',
        'serie_ano': '3',
        'ano_letivo': '2026',
        'ativa': '1',
        'dias_bloqueados': ['1', '2', '4'] # Terça, Quarta e Sexta bloqueadas
    }, follow_redirects=True)
    assert resp_edit.status_code == 200

    with get_db_connection() as conn:
        turma_atualizada = conn.execute("SELECT dias_bloqueados FROM turmas WHERE id = ?", (turma_id,)).fetchone()
        assert turma_atualizada['dias_bloqueados'] == '1,2,4'

        res_terca_pos = conn.execute("SELECT status, motivo_cancelamento FROM reservas WHERE id = ?", (reserva_terca_id,)).fetchone()
        assert res_terca_pos['status'] == 'CANCELADA', f"Status deveria ser CANCELADA, mas está {res_terca_pos['status']}"
        assert 'bloqueada neste dia da semana' in res_terca_pos['motivo_cancelamento']
        print(f"  [OK] Reserva da Terça-feira foi cancelada automaticamente. Motivo: '{res_terca_pos['motivo_cancelamento']}'.")

    # --- 6. TESTE DE RECORRÊNCIA SEMANAL ---
    print("\n--- 6. Proteção de Recorrência Semanal para Dias Bloqueados ---")
    with get_db_connection() as conn:
        conn.execute("UPDATE configuracoes SET permitir_reserva_recorrente = 1")
        conn.commit()

    # Aluno tenta salvar recorrência incluindo Terça (1), Quarta (2) e Segunda (0)
    # Como 1 e 2 estão bloqueados para a turma, apenas 0 (Segunda) deve ser gravada como ativa
    resp_rec = aluno_client.post('/aluno/recorrencia/salvar', data={
        'dias_recorrencia': ['0', '1', '2']
    }, follow_redirects=True)
    assert resp_rec.status_code == 200

    with get_db_connection() as conn:
        recorrencias_aluno = conn.execute(
            "SELECT dia_semana FROM aluno_recorrencia_dias WHERE aluno_id = ? AND ativo = 1",
            (aluno_id,)
        ).fetchall()
        dias_ativos = [r['dia_semana'] for r in recorrencias_aluno]
        assert dias_ativos == [0], f"Deveria ter ativado apenas Segunda (0), mas ativou: {dias_ativos}"
        print("  [OK] Recorrência filtrou e rejeitou os dias bloqueados pela turma.")

        # Testar que sincronizar_reservas_recorrentes não gera nada para os dias bloqueados
        total_sync = sincronizar_reservas_recorrentes(aluno_id=aluno_id)
        # Nenhuma reserva deve ter sido gerada para cardapio_quarta_id ou cardapio_terca_id
        res_sync_bloq = conn.execute(
            "SELECT id FROM reservas WHERE aluno_id = ? AND cardapio_id IN (?, ?) AND status = 'ATIVA'",
            (aluno_id, cardapio_quarta_id, cardapio_terca_id)
        ).fetchall()
        assert len(res_sync_bloq) == 0
        print("  [OK] sincronizar_reservas_recorrentes respeitou a turma e não gerou reservas para dias bloqueados.")

    # --- 7. LIMPEZA ---
    print("\n--- 7. Limpeza dos Dados de Teste ---")
    with get_db_connection() as conn:
        conn.execute("DELETE FROM reservas WHERE aluno_id = ?", (aluno_id,))
        conn.execute("DELETE FROM aluno_recorrencia_dias WHERE aluno_id = ?", (aluno_id,))
        conn.execute("DELETE FROM alunos WHERE id = ?", (aluno_id,))
        conn.execute("DELETE FROM turmas WHERE id = ?", (turma_id,))
        conn.execute("DELETE FROM cardapios WHERE id IN (?, ?)", (cardapio_quarta_id, cardapio_terca_id))
        conn.commit()
        print("  [OK] Registros de teste limpos com sucesso.")

    print("\n========================================================")
    print("TODOS OS TESTES DE BLOQUEIO POR TURMA PASSARAM COM 100% DE SUCESSO!")
    print("========================================================")

if __name__ == '__main__':
    testar_bloqueio_turma_dias()

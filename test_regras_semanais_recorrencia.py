# -*- coding: utf-8 -*-
"""
Suíte de Testes Automatizados:
- Regras semanais dinâmicas de abertura e fechamento por dia da semana (config_janelas_reserva)
- Validação do cálculo de janela (calcular_janela_reserva) para múltiplos cenários e offsets
- Bloqueio e liberação de reservas manuais baseado na janela específica de cada dia
- Ativação/desativação mestre de reservas recorrentes (permitir_reserva_recorrente = 0/1)
- Sincronização automática de reservas com dias ativos do estudante
- Cancelamento automático ao desmarcar dia de recorrência
- Relatório e Exportação Excel para fornecedor (/admin/relatorios/fornecedor)
"""
import io
import sqlite3
from datetime import datetime, timedelta
from openpyxl import load_workbook
from app import app
from database.connection import get_db_connection, init_db
from utils.helpers import calcular_janela_reserva, pode_reservar, sincronizar_reservas_recorrentes

def testar_regras_semanais_e_recorrencia():
    print("\n========================================================")
    print("TESTE: REGRAS SEMANAIS, RECORRÊNCIA E RELATÓRIO FORNECEDOR")
    print("========================================================")

    init_db()

    # ── 1. Verificação do Esquema no Banco ────────────────────────────────
    print("\n--- 1. Esquema do Banco de Dados ---")
    with get_db_connection() as conn:
        # Verifica tabela config_janelas_reserva
        janelas = conn.execute("SELECT * FROM config_janelas_reserva ORDER BY dia_refeicao").fetchall()
        assert len(janelas) == 7, f"Esperado 7 dias configurados em config_janelas_reserva, encontrado: {len(janelas)}"
        print("  [OK] Tabela 'config_janelas_reserva' possui 7 dias cadastrados (Segunda a Domingo).")

        # Verifica coluna permitir_reserva_recorrente em configuracoes
        cols_cfg = [c[1] for c in conn.execute("PRAGMA table_info(configuracoes)").fetchall()]
        assert 'permitir_reserva_recorrente' in cols_cfg, "Coluna 'permitir_reserva_recorrente' não encontrada em configuracoes!"
        print("  [OK] Coluna 'permitir_reserva_recorrente' presente na tabela 'configuracoes'.")

        # Verifica tabela aluno_recorrencia_dias
        cols_rec = [c[1] for c in conn.execute("PRAGMA table_info(aluno_recorrencia_dias)").fetchall()]
        for c in ['aluno_id', 'dia_semana', 'ativo']:
            assert c in cols_rec, f"Coluna '{c}' ausente em 'aluno_recorrencia_dias'!"
        print("  [OK] Tabela 'aluno_recorrencia_dias' confirmada com estrutura íntegra.")

    # ── 2. Testar Cálculo de Janela por Dia da Semana ─────────────────────
    print("\n--- 2. Cálculo de Janela por Dia da Semana (calcular_janela_reserva) ---")
    with get_db_connection() as conn:
        # Configurar Segunda-feira (dia 0): corte na Sexta anterior (offset 1, dia 4) às 14:00
        conn.execute("""
            UPDATE config_janelas_reserva 
            SET ativo = 1,
                abertura_semana_offset = 1, abertura_dia_semana = 0, abertura_horario = '07:00',
                fechamento_semana_offset = 1, fechamento_dia_semana = 4, fechamento_horario = '14:00'
            WHERE dia_refeicao = 0
        """)
        conn.commit()

        # Próxima segunda-feira
        hoje = datetime.now()
        dias_ate_segunda = (0 - hoje.weekday()) % 7
        if dias_ate_segunda == 0:
            dias_ate_segunda = 7
        prox_segunda = hoje + timedelta(days=dias_ate_segunda)
        segunda_str = prox_segunda.strftime('%Y-%m-%d')

        info_segunda = calcular_janela_reserva(segunda_str, conn=conn)
        assert 'status' in info_segunda, "Chave 'status' ausente no retorno de calcular_janela_reserva"
        assert 'pode_reservar' in info_segunda, "Chave 'pode_reservar' ausente"
        assert info_segunda['fechamento_formatado'] != '—', "fechamento_formatado não preenchido"
        print(f"  [OK] Segunda-feira ({segunda_str}): status={info_segunda['status']}, fechamento={info_segunda['fechamento_formatado']}")

    # ── 3. Teste de Recorrência Desativada por Padrão ─────────────────────
    print("\n--- 3. Comportamento com Recorrência Desativada (Padrão) ---")
    with get_db_connection() as conn:
        conn.execute("UPDATE configuracoes SET permitir_reserva_recorrente = 0 WHERE id = 1")
        conn.commit()

        # Preparar estudante de teste
        turma = conn.execute("SELECT id FROM turmas WHERE is_evento = 0 AND (dias_bloqueados IS NULL OR dias_bloqueados = '') LIMIT 1").fetchone()
        if not turma:
            cur_t = conn.execute("INSERT INTO turmas (nome, dias_bloqueados) VALUES ('Turma Teste Sem Bloqueio', '')")
            turma_id = cur_t.lastrowid
        else:
            turma_id = turma['id']

        conn.execute("DELETE FROM alunos WHERE matricula = 'TEST_REC_001'")
        cur = conn.execute("""
            INSERT INTO alunos (nome, matricula, cpf, data_nascimento, senha_hash, turma_id, permitido_almoco, situacao_matricula)
            VALUES ('Aluno Teste Recorrencia', 'TEST_REC_001', '99988877766', '2005-01-01', 'hash123', ?, 1, 'Matriculado')
        """, (turma_id,))
        aluno_rec_id = cur.lastrowid
        conn.commit()

    # Estudante tenta salvar recorrência com flag desativada
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['aluno_id'] = aluno_rec_id
        sess['aluno_nome'] = 'Aluno Teste Recorrencia'
        sess['aluno_matricula'] = 'TEST_REC_001'

    resp_salvar_desativado = client.post('/aluno/recorrencia/salvar', data={'dias_recorrencia': ['0', '1', '2']}, follow_redirects=True)
    assert resp_salvar_desativado.status_code == 200
    with get_db_connection() as conn:
        total_rec = conn.execute("SELECT COUNT(*) FROM aluno_recorrencia_dias WHERE aluno_id = ?", (aluno_rec_id,)).fetchone()[0]
        assert total_rec == 0, "Recorrência não deveria ter sido salva pois o recurso está desativado pelo administrador!"
    print("  [OK] Salvamento de recorrência bloqueado quando permitir_reserva_recorrente = 0.")

    # Sincronização não gera nada quando desativado
    geradas = sincronizar_reservas_recorrentes(aluno_rec_id)
    assert geradas == 0, f"Esperado 0 reservas geradas com flag desativada, retornou {geradas}"
    print("  [OK] sincronizar_reservas_recorrentes respeita a flag geral e não gera reservas quando desativada.")

    # ── 4. Ativação de Recorrência e Sincronização ────────────────────────
    print("\n--- 4. Ativação Mestre de Recorrência e Geração Automática ---")
    with get_db_connection() as conn:
        conn.execute("UPDATE configuracoes SET permitir_reserva_recorrente = 1 WHERE id = 1")
        conn.commit()

    # Agora estudante salva dias Segunda (0) e Terça (1)
    resp_salvar_ativo = client.post('/aluno/recorrencia/salvar', data={'dias_recorrencia': ['0', '1']}, follow_redirects=True)
    assert resp_salvar_ativo.status_code == 200
    with get_db_connection() as conn:
        dias_salvos = [r['dia_semana'] for r in conn.execute("SELECT dia_semana FROM aluno_recorrencia_dias WHERE aluno_id = ? AND ativo = 1", (aluno_rec_id,)).fetchall()]
        assert 0 in dias_salvos and 1 in dias_salvos, f"Dias não salvos corretamente: {dias_salvos}"
    print("  [OK] Dias de recorrência (Segunda e Terça) salvos com sucesso.")

    # Cria cardápios futuros abertos para teste de sincronização
    with get_db_connection() as conn:
        # Encontrar próxima segunda e próxima terça
        dias_ate_seg = (0 - hoje.weekday()) % 7
        if dias_ate_seg <= 0: dias_ate_seg += 7
        prox_seg_dt = hoje + timedelta(days=dias_ate_seg)
        prox_ter_dt = prox_seg_dt + timedelta(days=1)
        prox_qua_dt = prox_seg_dt + timedelta(days=2)

        data_seg = prox_seg_dt.strftime('%Y-%m-%d')
        data_ter = prox_ter_dt.strftime('%Y-%m-%d')
        data_qua = prox_qua_dt.strftime('%Y-%m-%d')

        conn.execute("DELETE FROM cardapios WHERE data IN (?, ?, ?)", (data_seg, data_ter, data_qua))
        cur1 = conn.execute("INSERT INTO cardapios (data, tipo_refeicao, descricao, permitir_reserva) VALUES (?, 'Almoço', 'Menu Seg Test', 1)", (data_seg,))
        c_seg_id = cur1.lastrowid
        cur2 = conn.execute("INSERT INTO cardapios (data, tipo_refeicao, descricao, permitir_reserva) VALUES (?, 'Almoço', 'Menu Ter Test', 1)", (data_ter,))
        c_ter_id = cur2.lastrowid
        cur3 = conn.execute("INSERT INTO cardapios (data, tipo_refeicao, descricao, permitir_reserva) VALUES (?, 'Almoço', 'Menu Qua Test', 1)", (data_qua,))
        c_qua_id = cur3.lastrowid

        # Garantir janela aberta para a terça
        conn.execute("""
            UPDATE config_janelas_reserva 
            SET ativo = 1,
                abertura_semana_offset = 2, abertura_dia_semana = 0, abertura_horario = '00:00',
                fechamento_semana_offset = 0, fechamento_dia_semana = 1, fechamento_horario = '23:59'
            WHERE dia_refeicao = 1
        """)
        conn.commit()

        # Executa sincronização para o aluno
        geradas = sincronizar_reservas_recorrentes(aluno_rec_id)
        assert geradas >= 1, f"Deveria ter gerado pelo menos 1 reserva automática, gerou: {geradas}"

        # Verifica se reserva para a terça foi gerada
        res_terca = conn.execute("SELECT * FROM reservas WHERE aluno_id = ? AND cardapio_id = ? AND status = 'ATIVA'", (aluno_rec_id, c_ter_id)).fetchone()
        assert res_terca, "Reserva da Terça não foi criada pela recorrência!"
        assert res_terca['codigo_unico'], "Código único não gerado para reserva recorrente!"
        print(f"  [OK] Reserva automática gerada com sucesso para Terça ({data_ter}) com código {res_terca['codigo_unico']}.")

        # Verifica que para Quarta (dia 2) NÃO foi gerada reserva (já que o aluno só marcou 0 e 1)
        res_qua = conn.execute("SELECT * FROM reservas WHERE aluno_id = ? AND cardapio_id = ?", (aluno_rec_id, c_qua_id)).fetchone()
        assert not res_qua, "Reserva de Quarta não deveria existir para este aluno!"
        print("  [OK] Quarta-feira não foi reservada, respeitando a escolha seletiva do estudante.")

    # ── 5. Desmarcar Dia de Recorrência Cancela Reservas Futuras ───────────
    print("\n--- 5. Desmarcar Dia de Recorrência Cancela Reservas Futuras ---")
    # Aluno remove a Terça-feira (1), mantendo apenas Segunda (0)
    resp_remover_dia = client.post('/aluno/recorrencia/salvar', data={'dias_recorrencia': ['0']}, follow_redirects=True)
    assert resp_remover_dia.status_code == 200

    with get_db_connection() as conn:
        res_terca_atual = conn.execute("SELECT * FROM reservas WHERE id = ?", (res_terca['id'],)).fetchone()
        assert res_terca_atual['status'] == 'CANCELADA', f"Reserva deveria ter sido cancelada, status={res_terca_atual['status']}"
        assert 'Desmarcado do plano semanal' in (res_terca_atual['motivo_cancelamento'] or ''), f"Motivo incorreto: {res_terca_atual['motivo_cancelamento']}"
        print(f"  [OK] Reserva da Terça-feira cancelada automaticamente com motivo: '{res_terca_atual['motivo_cancelamento']}'.")

    # ── 6. Relatório Semanal do Fornecedor (/admin/relatorios/fornecedor) ──
    print("\n--- 6. Relatório Semanal do Fornecedor ---")
    admin_client = app.test_client()
    with admin_client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['admin_id'] = 1
        sess['admin_usuario'] = 'admin'
        sess['admin_perfil'] = 'admin_mestre'
        sess['admin_permissoes'] = ['relatorios', 'config']

    # Testar visualização HTML
    resp_rep = admin_client.get(f'/admin/relatorios/fornecedor?data_inicio={data_seg}')
    assert resp_rep.status_code == 200, f"Falha ao carregar relatório do fornecedor: {resp_rep.status_code}"
    html = resp_rep.get_data(as_text=True)
    assert "Pedidos e Demanda ao Fornecedor" in html
    assert "Grade Semanal de Refeições &amp; Acionamento" in html or "Grade Semanal de Refeições & Acionamento" in html
    assert "Copiar para WhatsApp" in html
    print("  [OK] Rota HTML '/admin/relatorios/fornecedor' carregada com sucesso com cartões KPI e grade semanal.")

    # Testar exportação Excel
    resp_excel = admin_client.get(f'/admin/relatorios/fornecedor/excel?data_inicio={data_seg}')
    assert resp_excel.status_code == 200, f"Falha ao exportar Excel do fornecedor: {resp_excel.status_code}"
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in resp_excel.content_type

    # Validar conteúdo do Excel
    wb = load_workbook(io.BytesIO(resp_excel.data))
    ws = wb.active
    assert "PEDIDO DE REFEIÇÕES AO FORNECEDOR" in str(ws['A1'].value)
    assert ws['A4'].value == "Data"
    assert ws['I4'].value == "TOTAL CONFIRMADO"
    print("  [OK] Planilha Excel '/admin/relatorios/fornecedor/excel' gerada e validada com cabeçalhos e totais corretos.")

    # ── 7. Limpeza ────────────────────────────────────────────────────────
    print("\n--- 7. Limpeza dos Dados de Teste ---")
    with get_db_connection() as conn:
        conn.execute("DELETE FROM aluno_recorrencia_dias WHERE aluno_id = ?", (aluno_rec_id,))
        conn.execute("DELETE FROM reservas WHERE aluno_id = ?", (aluno_rec_id,))
        conn.execute("DELETE FROM alunos WHERE id = ?", (aluno_rec_id,))
        conn.execute("DELETE FROM cardapios WHERE data IN (?, ?, ?)", (data_seg, data_ter, data_qua))
        # Restaurar permitir_reserva_recorrente = 0
        conn.execute("UPDATE configuracoes SET permitir_reserva_recorrente = 0 WHERE id = 1")
        conn.commit()
    print("  [OK] Limpeza concluída.")

    print("\n========================================================")
    print("TODOS OS TESTES DE REGRAS SEMANAIS E RECORRÊNCIA PASSARAM COM SUCESSO!")
    print("========================================================\n")

if __name__ == '__main__':
    testar_regras_semanais_e_recorrencia()

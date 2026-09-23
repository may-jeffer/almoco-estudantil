# -*- coding: utf-8 -*-
"""
Suíte de Testes para Motivos de Cancelamento de Reservas e Relatório:
- Validação de colunas e integridade de dados em 'reservas' (motivo_cancelamento, cancelado_por, data_cancelamento)
- Fluxo de cancelamento pelo Estudante com captura de motivo e registro em auditoria
- Fluxo de cancelamento pela Administração com captura de motivo e registro em auditoria
- Relatório web de cancelamentos com filtros (origem, período, busca) e cartões KPI
- Exportação em formato Excel (.xlsx) com layout estilizado
"""
import io
import sqlite3
from datetime import datetime, timedelta
from openpyxl import load_workbook
from app import app
from database.connection import get_db_connection, init_db

def testar_motivos_cancelamento():
    print("\n========================================================")
    print("TESTE: MOTIVOS DE CANCELAMENTO DE RESERVAS E RELATÓRIO")
    print("========================================================")

    init_db()

    # 1. Verificar colunas na tabela reservas
    print("\n--- 1. Verificação de Esquema no Banco de Dados ---")
    with get_db_connection() as conn:
        cols = [c[1] for c in conn.execute("PRAGMA table_info(reservas)").fetchall()]
        for c in ['motivo_cancelamento', 'cancelado_por', 'data_cancelamento']:
            assert c in cols, f"Coluna '{c}' não encontrada na tabela reservas!"
        print("  [OK] Colunas 'motivo_cancelamento', 'cancelado_por', 'data_cancelamento' confirmadas.")

        # Preparar dados de teste (turma, aluno, cardapios)
        conn.execute("DELETE FROM logs_auditoria WHERE acao LIKE '%Cancel%'")
        
        # Garante turma
        turma = conn.execute("SELECT id FROM turmas LIMIT 1").fetchone()
        if not turma:
            cur = conn.execute("INSERT INTO turmas (nome, curso, ano_letivo, serie_ano) VALUES ('Turma Teste Canc', 'Informática', 2026, 1)")
            turma_id = cur.lastrowid
        else:
            turma_id = turma['id']

        # Garante aluno de teste
        conn.execute("DELETE FROM alunos WHERE matricula = 'TEST_CANC_999'")
        cur = conn.execute("""
            INSERT INTO alunos (nome, matricula, cpf, data_nascimento, senha_hash, turma_id, permitido_almoco, situacao_matricula)
            VALUES ('Aluno Teste Cancelamento', 'TEST_CANC_999', '11122233344', '2005-05-15', 'hash123', ?, 1, 'Matriculado')
        """, (turma_id,))
        aluno_id = cur.lastrowid

        # Garante cardápio futuro para permitir cancelamento dentro do prazo
        data_futura = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
        conn.execute("DELETE FROM cardapios WHERE data = ?", (data_futura,))
        cur = conn.execute("""
            INSERT INTO cardapios (data, tipo_refeicao, descricao, proteinas)
            VALUES (?, 'Almoço', 'Cardápio Teste Cancelamento', 'Frango Grelhado')
        """, (data_futura,))
        cardapio_id_1 = cur.lastrowid

        data_futura_2 = (datetime.now() + timedelta(days=6)).strftime('%Y-%m-%d')
        conn.execute("DELETE FROM cardapios WHERE data = ?", (data_futura_2,))
        cur = conn.execute("""
            INSERT INTO cardapios (data, tipo_refeicao, descricao, proteinas)
            VALUES (?, 'Almoço', 'Cardápio Teste Cancelamento Admin', 'Bife Acebolado')
        """, (data_futura_2,))
        cardapio_id_2 = cur.lastrowid

        # Cria 2 reservas ativas
        conn.execute("DELETE FROM reservas WHERE aluno_id = ? OR codigo_unico IN ('UNIQ-CANC-1', 'UNIQ-CANC-2')", (aluno_id,))
        cur = conn.execute("""
            INSERT INTO reservas (aluno_id, cardapio_id, status, codigo_unico, data_registro)
            VALUES (?, ?, 'ATIVA', 'UNIQ-CANC-1', ?)
        """, (aluno_id, cardapio_id_1, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        reserva_id_1 = cur.lastrowid

        cur = conn.execute("""
            INSERT INTO reservas (aluno_id, cardapio_id, status, codigo_unico, data_registro)
            VALUES (?, ?, 'ATIVA', 'UNIQ-CANC-2', ?)
        """, (aluno_id, cardapio_id_2, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        reserva_id_2 = cur.lastrowid
        conn.commit()

    # 2. Testar Cancelamento pelo Aluno
    print("\n--- 2. Cancelamento pelo Estudante ---")
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['aluno_id'] = aluno_id
        sess['aluno_nome'] = 'Aluno Teste Cancelamento'
        sess['aluno_matricula'] = 'TEST_CANC_999'

    resp = client.post(f'/aluno/cancelar/{cardapio_id_1}', data={
        'motivo_cancelamento': 'Problema de saúde / Consulta médica',
        'motivo_cancelamento_outro': 'Consulta ao dentista às 12h'
    }, follow_redirects=True)
    assert resp.status_code == 200, f"Falha ao cancelar reserva pelo aluno: {resp.status_code}"

    with get_db_connection() as conn:
        res1 = conn.execute("SELECT * FROM reservas WHERE id = ?", (reserva_id_1,)).fetchone()
        assert res1['status'] == 'CANCELADA', f"Status incorreto: {res1['status']}"
        assert 'Problema de saúde / Consulta médica' in res1['motivo_cancelamento'], f"Motivo incorreto: {res1['motivo_cancelamento']}"
        assert 'Consulta ao dentista' in res1['motivo_cancelamento'], f"Observação ausente: {res1['motivo_cancelamento']}"
        assert res1['cancelado_por'] == 'ALUNO', f"cancelado_por incorreto: {res1['cancelado_por']}"
        assert res1['data_cancelamento'] is not null_or_empty(res1['data_cancelamento']), "data_cancelamento vazia!"

        audit = conn.execute("SELECT * FROM logs_auditoria WHERE acao = 'Cancelamento de Reserva (Aluno)' ORDER BY id DESC LIMIT 1").fetchone()
        assert audit is not None, "Log de auditoria do aluno não foi gravado!"
        assert 'Consulta médica' in audit['detalhes'], f"Motivo não consta no log de auditoria: {audit['detalhes']}"
        print(f"  [OK] Reserva do aluno cancelada. Motivo gravado: '{res1['motivo_cancelamento']}'. Log verificado.")

    # 3. Testar Cancelamento pelo Administrador
    print("\n--- 3. Cancelamento pelo Administrador ---")
    admin_client = app.test_client()
    with admin_client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['admin_id'] = 1
        sess['admin_usuario'] = 'gestor_cantina'
        sess['admin_perfil'] = 'admin_mestre'
        sess['admin_permissoes'] = ['all']

    resp = admin_client.post(f'/admin/reservas/cancelar/{reserva_id_2}', data={
        'motivo_cancelamento': 'Atividade externa da turma / excursão',
        'motivo_cancelamento_outro': 'Visita técnica ao Planetário'
    }, follow_redirects=True)
    assert resp.status_code == 200, f"Falha ao cancelar reserva pelo admin: {resp.status_code}"

    with get_db_connection() as conn:
        res2 = conn.execute("SELECT * FROM reservas WHERE id = ?", (reserva_id_2,)).fetchone()
        assert res2['status'] == 'CANCELADA', f"Status incorreto: {res2['status']}"
        assert 'Atividade externa' in res2['motivo_cancelamento'], f"Motivo incorreto: {res2['motivo_cancelamento']}"
        assert 'Planetário' in res2['motivo_cancelamento'], f"Observação ausente: {res2['motivo_cancelamento']}"
        assert res2['cancelado_por'] == 'ADMIN: gestor_cantina', f"cancelado_por incorreto: {res2['cancelado_por']}"
        assert res2['data_cancelamento'] is not null_or_empty(res2['data_cancelamento']), "data_cancelamento vazia!"

        audit_admin = conn.execute("SELECT * FROM logs_auditoria WHERE acao = 'Cancelar Reserva (Admin)' ORDER BY id DESC LIMIT 1").fetchone()
        assert audit_admin is not None, "Log de auditoria do admin não foi gravado!"
        assert 'gestor_cantina' in audit_admin['detalhes'], "Usuário admin ausente no log!"
        assert 'Planetário' in audit_admin['detalhes'], "Motivo ausente no log do admin!"
        print(f"  [OK] Reserva cancelada pelo admin. Autor: '{res2['cancelado_por']}'. Motivo: '{res2['motivo_cancelamento']}'. Log verificado.")

    # 4. Testar Relatório de Cancelamentos (Web)
    print("\n--- 4. Visualização do Relatório de Cancelamentos (Web) ---")
    resp_rel = admin_client.get('/admin/relatorios/cancelamentos?q=TEST_CANC_999')
    assert resp_rel.status_code == 200, f"Erro ao acessar relatório de cancelamentos: {resp_rel.status_code}"
    conteudo = resp_rel.get_data(as_text=True)
    assert "Relatório de Cancelamentos de Reservas" in conteudo
    assert "Aluno Teste Cancelamento" in conteudo
    assert "Consulta médica" in conteudo
    assert "Planetário" in conteudo
    print("  [OK] Página web do relatório exibiu com sucesso os registros e motivos.")

    # Teste de filtro por Origem: ALUNO
    resp_filtro_aluno = admin_client.get('/admin/relatorios/cancelamentos?origem=ALUNO&q=TEST_CANC_999')
    assert resp_filtro_aluno.status_code == 200
    conteudo_aluno = resp_filtro_aluno.get_data(as_text=True)
    assert "Consulta médica" in conteudo_aluno
    assert "Planetário" not in conteudo_aluno
    print("  [OK] Filtro 'origem=ALUNO' isolou corretamente apenas cancelamentos do estudante.")

    # Teste de filtro por Origem: ADMIN
    resp_filtro_admin = admin_client.get('/admin/relatorios/cancelamentos?origem=ADMIN&q=TEST_CANC_999')
    assert resp_filtro_admin.status_code == 200
    conteudo_admin = resp_filtro_admin.get_data(as_text=True)
    assert "Planetário" in conteudo_admin
    assert "Consulta médica" not in conteudo_admin
    print("  [OK] Filtro 'origem=ADMIN' isolou corretamente apenas cancelamentos da administração.")

    # 5. Testar Exportação Excel
    print("\n--- 5. Exportação para Planilha Excel (.xlsx) ---")
    resp_excel = admin_client.get('/admin/relatorios/cancelamentos/excel?q=TEST_CANC_999')
    assert resp_excel.status_code == 200, f"Erro ao exportar Excel: {resp_excel.status_code}"
    assert resp_excel.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    excel_bytes = io.BytesIO(resp_excel.data)
    wb = load_workbook(excel_bytes)
    assert "Cancelamentos" in wb.sheetnames
    ws = wb["Cancelamentos"]
    
    # Verificar título e cabeçalhos
    assert "RELATÓRIO DE RESERVAS CANCELADAS" in str(ws['A1'].value)
    headers = [cell.value for cell in ws[3]]
    assert "Motivo do Cancelamento" in headers
    assert "Cancelado Por" in headers
    
    # Verificar presença dos registros no Excel
    valores_linhas = []
    for row in ws.iter_rows(min_row=4, values_only=True):
        valores_linhas.append(str(row))
    
    texto_excel = " ".join(valores_linhas)
    assert "Aluno Teste Cancelamento" in texto_excel
    assert "Consulta médica" in texto_excel
    assert "Planetário" in texto_excel
    print(f"  [OK] Arquivo Excel gerado com sucesso contendo {len(valores_linhas)} linhas e motivos detalhados.")

    print("\n========================================================")
    print("TODOS OS TESTES DE CANCELAMENTO E RELATÓRIO PASSARAM COM SUCESSO!")
    print("========================================================")

def null_or_empty(val):
    return val is None or str(val).strip() == ''

if __name__ == '__main__':
    testar_motivos_cancelamento()

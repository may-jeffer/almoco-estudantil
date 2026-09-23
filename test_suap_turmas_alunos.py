# -*- coding: utf-8 -*-
"""
Suíte de Testes da Padronização SUAP:
- Metadados de Turmas e Alunos
- Histórico Acadêmico Permanente (aluno_turma_historico) com constraint UNIQUE
- Matriz de Virada de Ano (Conselho de Turma): Promoção baseada na Turma de Destino, Retenção/Repetência, Evasão, Formatura
- Proteção Anti-Sujeira na Importação CSV
- Consulta de Trajetória Acadêmica
"""
import io
import json
import sqlite3
from app import app
from database.connection import get_db_connection, init_db

def rodar_todos_os_testes():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['admin_id'] = 1
        sess['admin_usuario'] = 'admin_teste'
        sess['admin_perfil'] = 'admin_mestre'
        sess['admin_permissoes'] = ['all']

    print("\n========================================================")
    print("INICIANDO TESTES DA PADRONIZAÇÃO SUAP E HISTÓRICO ESCOLAR")
    print("========================================================")

    # 1. Teste de Migrações e Integridade de Esquema
    print("\n--- 1. TESTE: Esquema do Banco e Constraint UNIQUE no Histórico ---")
    init_db()
    with get_db_connection() as conn:
        turmas_cols = [c[1] for c in conn.execute("PRAGMA table_info(turmas)").fetchall()]
        for col in ['curso', 'ano_letivo', 'periodo_letivo', 'serie_ano', 'turno', 'modalidade', 'ativa']:
            assert col in turmas_cols, f"Coluna '{col}' ausente em turmas!"
        print("  [OK] Colunas de Metadados presentes na tabela 'turmas'.")

        alunos_cols = [c[1] for c in conn.execute("PRAGMA table_info(alunos)").fetchall()]
        for col in ['serie_ano_atual', 'ano_ingresso', 'situacao_matricula']:
            assert col in alunos_cols, f"Coluna '{col}' ausente em alunos!"
        print("  [OK] Colunas SUAP presentes na tabela 'alunos'.")

        hist_cols = [c[1] for c in conn.execute("PRAGMA table_info(aluno_turma_historico)").fetchall()]
        for col in ['aluno_id', 'turma_id', 'ano_letivo', 'periodo_letivo', 'serie_ano', 'situacao', 'data_inicio', 'data_fim']:
            assert col in hist_cols, f"Coluna '{col}' ausente em aluno_turma_historico!"
        print("  [OK] Tabela 'aluno_turma_historico' criada e estruturada com sucesso.")

        # Teste da constraint UNIQUE no histórico
        conn.execute("DELETE FROM aluno_turma_historico WHERE aluno_id = 99999")
        conn.execute("""
            INSERT INTO aluno_turma_historico (aluno_id, turma_id, ano_letivo, periodo_letivo, serie_ano, situacao, data_inicio)
            VALUES (99999, 1, 2026, 1, 1, 'Cursando', '2026-02-01')
        """)
        conn.commit()

        # Segunda inserção idêntica deve falhar por duplicidade se usar INSERT puro
        violou_unique = False
        try:
            conn.execute("""
                INSERT INTO aluno_turma_historico (aluno_id, turma_id, ano_letivo, periodo_letivo, serie_ano, situacao, data_inicio)
                VALUES (99999, 1, 2026, 1, 1, 'Cursando', '2026-02-01')
            """)
            conn.commit()
        except sqlite3.IntegrityError:
            violou_unique = True
        assert violou_unique, "Constraint UNIQUE(aluno_id, turma_id, ano_letivo, periodo_letivo) deveria ter impedido duplicidade!"
        conn.execute("DELETE FROM aluno_turma_historico WHERE aluno_id = 99999")
        conn.commit()
        print("  [OK] Blindagem UNIQUE em aluno_turma_historico validada com sucesso.")

    # 2. Teste da Matriz de Virada de Ano (Conselho de Turma)
    print("\n--- 2. TESTE: Virada de Ano com Promoção, Retenção e Evasão ---")
    with get_db_connection() as conn:
        conn.execute("DELETE FROM aluno_turma_historico WHERE aluno_id IN (SELECT id FROM alunos WHERE cpf IN ('111.111.111-99', '222.222.222-99', '333.333.333-99', '777.777.777-77'))")
        conn.execute("DELETE FROM alunos WHERE cpf IN ('111.111.111-99', '222.222.222-99', '333.333.333-99', '777.777.777-77')")
        conn.execute("DELETE FROM turmas WHERE nome IN ('1º Ano Agro 2025 Teste', '2º Ano Agro 2026 Teste', '1º Ano Agro 2026 Teste', 'TURMA-FALSA-X9')")
        conn.commit()

        cur = conn.cursor()
        # Criar Turma Origem 2025
        cur.execute("""
            INSERT INTO turmas (nome, curso, ano_letivo, periodo_letivo, serie_ano, turno, ativa)
            VALUES ('1º Ano Agro 2025 Teste', 'Agropecuária', 2025, 1, 1, 'Matutino', 1)
        """)
        t_origem_id = cur.lastrowid

        # Criar Turma Destino Promoção (2º Ano 2026, série = 2)
        cur.execute("""
            INSERT INTO turmas (nome, curso, ano_letivo, periodo_letivo, serie_ano, turno, ativa)
            VALUES ('2º Ano Agro 2026 Teste', 'Agropecuária', 2026, 1, 2, 'Matutino', 1)
        """)
        t_promo_id = cur.lastrowid

        # Criar Turma Destino Repetência (1º Ano 2026, série = 1)
        cur.execute("""
            INSERT INTO turmas (nome, curso, ano_letivo, periodo_letivo, serie_ano, turno, ativa)
            VALUES ('1º Ano Agro 2026 Teste', 'Agropecuária', 2026, 1, 1, 'Matutino', 1)
        """)
        t_retido_id = cur.lastrowid

        # Aluno 1: Promovido
        cur.execute("""
            INSERT INTO alunos (nome, matricula, cpf, data_nascimento, turma_id, serie_ano_atual, situacao_matricula, permitido_almoco)
            VALUES ('João Promovido Teste', 'MAT-PROM-999', '111.111.111-99', '2008-01-01', ?, 1, 'Matriculado', 1)
        """, (t_origem_id,))
        aluno_prom_id = cur.lastrowid

        # Aluno 2: Retido
        cur.execute("""
            INSERT INTO alunos (nome, matricula, cpf, data_nascimento, turma_id, serie_ano_atual, situacao_matricula, permitido_almoco)
            VALUES ('Maria Retida Teste', 'MAT-RET-999', '222.222.222-99', '2008-02-02', ?, 1, 'Matriculado', 1)
        """, (t_origem_id,))
        aluno_ret_id = cur.lastrowid

        # Aluno 3: Evadido
        cur.execute("""
            INSERT INTO alunos (nome, matricula, cpf, data_nascimento, turma_id, serie_ano_atual, situacao_matricula, permitido_almoco)
            VALUES ('Pedro Evadido Teste', 'MAT-EVAD-999', '333.333.333-99', '2008-03-03', ?, 1, 'Matriculado', 1)
        """, (t_origem_id,))
        aluno_evad_id = cur.lastrowid

        # Históricos iniciais
        for aid in [aluno_prom_id, aluno_ret_id, aluno_evad_id]:
            cur.execute("""
                INSERT INTO aluno_turma_historico (aluno_id, turma_id, ano_letivo, periodo_letivo, serie_ano, situacao, data_inicio)
                VALUES (?, ?, 2025, 1, 1, 'Cursando', '2025-02-01')
            """, (aid, t_origem_id))
        conn.commit()

    # Rota de dados para carregar a tela
    resp_dados = client.get(f'/admin/turmas/virada_ano/dados?turma_origem_id={t_origem_id}')
    assert resp_dados.status_code == 200
    dados_virada = resp_dados.get_json()
    assert len(dados_virada['alunos']) == 3
    print("  [OK] Endpoint de dados da virada (/admin/turmas/virada_ano/dados) retornou estudantes da turma corretamente.")

    # Submissão da Virada de Ano
    payload = {
        "turma_origem_id": t_origem_id,
        "movimentacoes": [
            {"aluno_id": aluno_prom_id, "resultado": "PROMOVIDO", "turma_destino_id": t_promo_id},
            {"aluno_id": aluno_ret_id, "resultado": "RETIDO", "turma_destino_id": t_retido_id},
            {"aluno_id": aluno_evad_id, "resultado": "EVADIDO", "turma_destino_id": None}
        ]
    }
    resp_exec = client.post('/admin/turmas/virada_ano', json=payload)
    assert resp_exec.status_code == 200
    resumo_json = resp_exec.get_json()
    assert resumo_json['success'] is True
    assert resumo_json['resumo']['PROMOVIDO'] == 1
    assert resumo_json['resumo']['RETIDO'] == 1
    assert resumo_json['resumo']['EVADIDO'] == 1
    print("  [OK] Processamento atômico da virada executado com sucesso.")

    # Validação dos estados no banco
    with get_db_connection() as conn:
        a_prom = conn.execute("SELECT * FROM alunos WHERE id = ?", (aluno_prom_id,)).fetchone()
        assert a_prom['turma_id'] == t_promo_id
        assert a_prom['serie_ano_atual'] == 2, f"Esperado 2º ano para promovido, obtido {a_prom['serie_ano_atual']}"
        assert a_prom['situacao_matricula'] == 'Matriculado'
        print("  [OK] Aluno promovido assumiu turma destino e herdou serie_ano_atual = 2.")

        a_ret = conn.execute("SELECT * FROM alunos WHERE id = ?", (aluno_ret_id,)).fetchone()
        assert a_ret['turma_id'] == t_retido_id
        assert a_ret['serie_ano_atual'] == 1, f"Esperado 1º ano para retido, obtido {a_ret['serie_ano_atual']}"
        assert a_ret['situacao_matricula'] == 'Matriculado'
        print("  [OK] Aluno retido permaneceu na série 1 na turma do novo ano letivo (sem incremento cego).")

        a_evad = conn.execute("SELECT * FROM alunos WHERE id = ?", (aluno_evad_id,)).fetchone()
        assert a_evad['situacao_matricula'] == 'Evadido'
        assert a_evad['permitido_almoco'] == 0, "Aluno evadido deve ter acesso ao almoço bloqueado automaticamente!"
        print("  [OK] Aluno evadido teve situação atualizada e almoço bloqueado automaticamente.")

        # Auditoria da virada registrada
        aud = conn.execute("SELECT * FROM logs_auditoria WHERE acao = 'Virada de Ano Letivo' ORDER BY id DESC LIMIT 1").fetchone()
        assert aud is not None
        assert "Promovido(s)" in aud['detalhes']
        print(f"  [OK] Auditoria detalhada registrada: {aud['detalhes']}")

    # 3. Teste de Trajetória Acadêmica
    print("\n--- 3. TESTE: Trajetória Acadêmica Completa ---")
    resp_traj = client.get(f'/admin/alunos/historico/{aluno_prom_id}')
    assert resp_traj.status_code == 200
    traj_data = resp_traj.get_json()
    assert traj_data['aluno']['id'] == aluno_prom_id
    assert len(traj_data['historico']) == 2
    assert traj_data['historico'][0]['serie_ano'] == 2
    assert traj_data['historico'][0]['situacao'] == 'Cursando'
    assert traj_data['historico'][1]['serie_ano'] == 1
    assert traj_data['historico'][1]['situacao'] == 'Promovido'
    print("  [OK] API de Trajetória Acadêmica retornou a cronologia completa do estudante.")

    # 4. Teste de Importação CSV com Proteção Anti-Sujeira e Nomenclatura Automática SerieAno + Curso
    print("\n--- 4. TESTE: Importação CSV (Sem Coluna Turma), Nomenclatura Automática e Migração ---")
    nome_curso_teste = "Curso Técnico em Agroecologia - Integrado/Integral- PTG"
    nome_turma_esperada = "2º - Curso Técnico em Agroecologia - Integrado/Integral- PTG"

    with get_db_connection() as conn:
        conn.execute("DELETE FROM aluno_turma_historico WHERE aluno_id IN (SELECT id FROM alunos WHERE cpf IN ('777.777.777-77', '999.888.777-66'))")
        conn.execute("DELETE FROM alunos WHERE cpf IN ('777.777.777-77', '999.888.777-66')")
        conn.execute("DELETE FROM turmas WHERE nome IN (?, ?, ?, ?)", (
            nome_turma_esperada, "3º - Curso Técnico em Agroecologia - Integrado/Integral- PTG",
            "10º - Curso Superior de Bacharelado em Engenharia Agronômica - PTG",
            "9º - Curso Superior de Bacharelado em Engenharia Agronômica - PTG"
        ))
        conn.commit()

    # CSV Oficial de 12 colunas sem Turma
    csv_teste = (
        "Nome;Matricula;CPF;DataNascimento;Curso;SerieAno;Turno;Situacao;AnoIngresso;Email;Restricoes;LiberadoAlmoco\n"
        f"Estudante AntiSujeira;MAT-CSV-SEC;777.777.777-77;12/12/2007;{nome_curso_teste};2;Matutino;Matriculado;2026;teste@email.com;;S\n"
    )

    # 4.1 Sem marcar flag de criar turmas -> Rejeita se turma não existir
    data_rejeita = {
        'arquivo_csv': (io.BytesIO(csv_teste.encode('utf-8-sig')), 'import.csv')
    }
    client.post('/admin/alunos/importar', data=data_rejeita, content_type='multipart/form-data', follow_redirects=True)
    with get_db_connection() as conn:
        a_falso = conn.execute("SELECT * FROM alunos WHERE cpf = '777.777.777-77'").fetchone()
        assert a_falso is None, "Aluno NÃO deveria ter sido cadastrado pois a turma não existe e a criação automática estava desligada!"
    print("  [OK] Proteção Anti-Sujeira funcionou: linha com turma inexistente foi rejeitada.")

    # 4.2 Marcando flag criar_turmas_novas = 1 -> Cria turma formatada '2º - Curso...' e cadastra aluno
    data_aceita = {
        'arquivo_csv': (io.BytesIO(csv_teste.encode('utf-8-sig')), 'import.csv'),
        'criar_turmas_novas': '1',
        'bloquear_ausentes': '0'
    }
    client.post('/admin/alunos/importar', data=data_aceita, content_type='multipart/form-data', follow_redirects=True)
    with get_db_connection() as conn:
        a_criado = conn.execute("SELECT * FROM alunos WHERE cpf = '777.777.777-77'").fetchone()
        assert a_criado is not None
        assert a_criado['nome'] == 'Estudante AntiSujeira'
        t_criada = conn.execute("SELECT * FROM turmas WHERE id = ?", (a_criado['turma_id'],)).fetchone()
        assert t_criada is not None
        assert t_criada['nome'] == nome_turma_esperada, f"Esperado '{nome_turma_esperada}', obtido '{t_criada['nome']}'"
    print(f"  [OK] Turma '{nome_turma_esperada}' criada com sucesso a partir de SerieAno + Curso.")

    # 4.3 Teste de Migração Automática de Turma por mudança de Série/Curso no CSV
    print("\n--- 4.3 TESTE: Migração Automática por mudança de Série com Histórico ---")
    nome_turma_migrada = "3º - Curso Técnico em Agroecologia - Integrado/Integral- PTG"
    csv_migracao = (
        "Nome;Matricula;CPF;DataNascimento;Curso;SerieAno;Turno;Situacao;AnoIngresso;Email;Restricoes;LiberadoAlmoco\n"
        f"Estudante AntiSujeira;MAT-CSV-SEC;777.777.777-77;12/12/2007;{nome_curso_teste};3;Matutino;Matriculado;2026;teste@email.com;;S\n"
    )
    data_migra = {
        'arquivo_csv': (io.BytesIO(csv_migracao.encode('utf-8-sig')), 'import.csv'),
        'criar_turmas_novas': '1',
        'bloquear_ausentes': '0'
    }
    client.post('/admin/alunos/importar', data=data_migra, content_type='multipart/form-data', follow_redirects=True)
    with get_db_connection() as conn:
        a_migrado = conn.execute("SELECT * FROM alunos WHERE cpf = '777.777.777-77'").fetchone()
        assert a_migrado['serie_ano_atual'] == 3
        t_migrada = conn.execute("SELECT * FROM turmas WHERE id = ?", (a_migrado['turma_id'],)).fetchone()
        assert t_migrada['nome'] == nome_turma_migrada

        # Verifica histórico acadêmico do aluno
        hist_rows = conn.execute("SELECT * FROM aluno_turma_historico WHERE aluno_id = ? ORDER BY id ASC", (a_migrado['id'],)).fetchall()
        assert len(hist_rows) >= 2
        # Primeiro histórico (turma antiga) deve estar fechado com Transferido
        assert hist_rows[0]['turma_id'] == t_criada['id']
        assert hist_rows[0]['situacao'] == 'Transferido'
        assert hist_rows[0]['data_fim'] is not None

        # Segundo histórico (nova turma) deve estar ativo com Cursando
        assert hist_rows[-1]['turma_id'] == t_migrada['id']
        assert hist_rows[-1]['situacao'] == 'Cursando'
        assert hist_rows[-1]['data_fim'] is None
        assert 'Migrado automaticamente' in (hist_rows[-1]['observacao'] or '')
    print("  [OK] Migração automática de estudante e registro na trajetória acadêmica validados com 100% de sucesso!")

    # 4.4 Teste de Bloqueio Automático de Alunos Ausentes e Situação Diferente de Matriculado
    print("\n--- 4.4 TESTE: Bloqueio de Reservas para Alunos Ausentes da Planilha e Não Matriculados ---")
    cpf_ausente = "666.555.444-33"
    with get_db_connection() as conn:
        conn.execute("DELETE FROM aluno_turma_historico WHERE aluno_id IN (SELECT id FROM alunos WHERE cpf = ?)", (cpf_ausente,))
        conn.execute("DELETE FROM alunos WHERE cpf = ?", (cpf_ausente,))
        # Cria um aluno regular previamente matriculado e ativo para almoço
        conn.execute("""
            INSERT INTO alunos (nome, matricula, cpf, data_nascimento, turma_id, permitido_almoco, situacao_matricula)
            VALUES ('Estudante Que Vai Sair', 'MAT-SAIDA-123', ?, '2005-01-01', ?, 1, 'Matriculado')
        """, (cpf_ausente, t_promo_id))
        aluno_ausente_id = conn.execute("SELECT id FROM alunos WHERE cpf = ?", (cpf_ausente,)).fetchone()['id']
        conn.commit()

    # Importa CSV que contém apenas o Estudante AntiSujeira com bloquear_ausentes=1
    data_import_ausente = {
        'arquivo_csv': (io.BytesIO(csv_migracao.encode('utf-8-sig')), 'import.csv'),
        'criar_turmas_novas': '1',
        'bloquear_ausentes': '1'
    }
    client.post('/admin/alunos/importar', data=data_import_ausente, content_type='multipart/form-data', follow_redirects=True)
    with get_db_connection() as conn:
        a_bloqueado = conn.execute("SELECT * FROM alunos WHERE id = ?", (aluno_ausente_id,)).fetchone()
        assert a_bloqueado['permitido_almoco'] == 0, "Aluno ausente da planilha DEVE ter o acesso ao almoço bloqueado!"
        assert a_bloqueado['situacao_matricula'] == 'Não Matriculado'
        print("  [OK] Aluno ausente da listagem do CSV teve reserva bloqueada (permitido_almoco=0) e situação alterada para 'Não Matriculado'.")

        # Limpa o aluno de teste ausente e restaura os alunos de produção
        conn.execute("DELETE FROM alunos WHERE id = ?", (aluno_ausente_id,))
        conn.execute("UPDATE alunos SET permitido_almoco = 1, situacao_matricula = 'Matriculado' WHERE matricula NOT LIKE 'EVT-%' AND cpf NOT IN ('777.777.777-77', '999.888.777-66')")
        conn.commit()
    print("\n--- 5. TESTE: Cadastro e Edição Manual Sem Campo Turma (Auto-resolução SerieAno + Curso) ---")
    curso_eng = "Curso Superior de Bacharelado em Engenharia Agronômica - PTG"
    turma_eng_esperada = "10º - Curso Superior de Bacharelado em Engenharia Agronômica - PTG"
    cpf_teste_eng = "999.888.777-66"

    with get_db_connection() as conn:
        conn.execute("DELETE FROM aluno_turma_historico WHERE aluno_id IN (SELECT id FROM alunos WHERE cpf = ?)", (cpf_teste_eng,))
        conn.execute("DELETE FROM alunos WHERE cpf = ?", (cpf_teste_eng,))
        conn.commit()

    # 5.1 Cadastro Manual: Apenas Curso e Série (10º Período), sem turma_id
    payload_manual = {
        'nome': 'Estudante Engenharia Agronomica',
        'matricula': 'MAT-ENG-TEST-10',
        'cpf': cpf_teste_eng,
        'data_nascimento': '2000-05-15',
        'email': 'engenheiro@escola.edu.br',
        'curso': curso_eng,
        'serie_ano_atual': '10',
        'ano_ingresso': '2021',
        'situacao_matricula': 'Matriculado',
        'permitido_almoco': '1'
    }
    client.post('/admin/alunos', data=payload_manual, follow_redirects=True)
    with get_db_connection() as conn:
        a_eng = conn.execute("SELECT * FROM alunos WHERE cpf = ?", (cpf_teste_eng,)).fetchone()
        assert a_eng is not None
        assert a_eng['serie_ano_atual'] == 10
        t_eng = conn.execute("SELECT * FROM turmas WHERE id = ?", (a_eng['turma_id'],)).fetchone()
        assert t_eng is not None
        assert t_eng['nome'] == turma_eng_esperada
        print(f"  [OK] Cadastro manual vinculou automaticamente à turma: '{turma_eng_esperada}'")

    # 5.2 Edição Manual: Aluno mudou de curso ou série
    turma_eng_9_esperada = "9º - Curso Superior de Bacharelado em Engenharia Agronômica - PTG"
    payload_manual_edit = {
        'nome': 'Estudante Engenharia Agronomica',
        'matricula': 'MAT-ENG-TEST-10',
        'cpf': cpf_teste_eng,
        'data_nascimento': '2000-05-15',
        'email': 'engenheiro@escola.edu.br',
        'curso': curso_eng,
        'serie_ano_atual': '9',
        'ano_ingresso': '2021',
        'situacao_matricula': 'Matriculado',
        'permitido_almoco': '1'
    }
    client.post(f'/admin/alunos/editar/{a_eng["id"]}', data=payload_manual_edit, follow_redirects=True)
    with get_db_connection() as conn:
        a_eng_edit = conn.execute("SELECT * FROM alunos WHERE id = ?", (a_eng['id'],)).fetchone()
        assert a_eng_edit['serie_ano_atual'] == 9
        t_eng_9 = conn.execute("SELECT * FROM turmas WHERE id = ?", (a_eng_edit['turma_id'],)).fetchone()
        assert t_eng_9 is not None
        assert t_eng_9['nome'] == turma_eng_9_esperada

        # Verifica histórico
        hist_eng = conn.execute("SELECT * FROM aluno_turma_historico WHERE aluno_id = ? ORDER BY id ASC", (a_eng['id'],)).fetchall()
        assert len(hist_eng) == 2
        assert hist_eng[0]['turma_id'] == t_eng['id']
        assert hist_eng[0]['situacao'] == 'Transferido'
        assert hist_eng[1]['turma_id'] == t_eng_9['id']
        assert hist_eng[1]['situacao'] == 'Cursando'
        print(f"  [OK] Edição manual migrou automaticamente para '{turma_eng_9_esperada}' com histórico registrado.")

    # Limpeza dos registros de teste
    with get_db_connection() as conn:
        conn.execute("DELETE FROM aluno_turma_historico WHERE aluno_id IN (?, ?, ?)", (aluno_prom_id, aluno_ret_id, aluno_evad_id))
        if a_criado:
            conn.execute("DELETE FROM aluno_turma_historico WHERE aluno_id = ?", (a_criado['id'],))
            conn.execute("DELETE FROM alunos WHERE id = ?", (a_criado['id'],))
        if a_eng:
            conn.execute("DELETE FROM aluno_turma_historico WHERE aluno_id = ?", (a_eng['id'],))
            conn.execute("DELETE FROM alunos WHERE id = ?", (a_eng['id'],))
        conn.execute("DELETE FROM alunos WHERE id IN (?, ?, ?)", (aluno_prom_id, aluno_ret_id, aluno_evad_id))
        conn.execute("DELETE FROM turmas WHERE id IN (?, ?, ?)", (t_origem_id, t_promo_id, t_retido_id))
        if a_criado and t_criada:
            conn.execute("DELETE FROM turmas WHERE id = ?", (t_criada['id'],))
        conn.execute("DELETE FROM turmas WHERE nome IN (?, ?, ?, ?)", (
            nome_turma_esperada, nome_turma_migrada, turma_eng_esperada, turma_eng_9_esperada
        ))
        conn.commit()

    print("\n========================================================")
    print("TODOS OS TESTES DA PADRONIZAÇÃO SUAP PASSARAM COM SUCESSO (100%)!")
    print("========================================================\n")

if __name__ == '__main__':
    rodar_todos_os_testes()

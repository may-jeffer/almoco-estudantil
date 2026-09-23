import json
import sqlite3
from app import app

def test_permissoes_e_modo_escuro():
    client = app.test_client()

    print("--- 1. TESTE: Administrador com permissoes restritas (angela: turmas, alunos) ---")
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['admin_id'] = 5
        sess['admin_usuario'] = 'angela'
        sess['admin_perfil'] = 'operador'
        sess['admin_permissoes'] = ['turmas', 'alunos']

    # Deve ter acesso a turmas e alunos
    resp_turmas = client.get('/admin/turmas')
    assert resp_turmas.status_code == 200, f"Esperado 200 em /admin/turmas, obtido {resp_turmas.status_code}"
    resp_alunos = client.get('/admin/alunos')
    assert resp_alunos.status_code == 200, f"Esperado 200 em /admin/alunos, obtido {resp_alunos.status_code}"
    print("  [OK] Acesso permitido para turmas e alunos.")

    # Deve ser BLOQUEADO e redirecionado para dashboard em cardapios, qualidade, eventos, config, etc.
    for rota in ['/admin/cardapios', '/admin/qualidade', '/admin/eventos', '/admin/configuracoes', '/admin/administradores', '/admin/pesquisas']:
        resp = client.get(rota)
        assert resp.status_code == 302 and resp.headers.get('Location') in ['/admin', '/admin/'], f"Rota {rota} deveria ser bloqueada (redirect), obtido status {resp.status_code} para {resp.headers.get('Location')}"
    print("  [OK] Rotas restritas (cardapios, qualidade, eventos, config, admins, pesquisas) foram todas devidamente bloqueadas!")

    print("\n--- 2. TESTE: Administrador apenas com 'cardapios' nao pode acessar 'qualidade' ---")
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['admin_id'] = 99
        sess['admin_usuario'] = 'nutricionista_apenas_cardapio'
        sess['admin_perfil'] = 'operador'
        sess['admin_permissoes'] = ['cardapios']

    resp_cardapios = client.get('/admin/cardapios')
    assert resp_cardapios.status_code == 200, "Esperado 200 em /admin/cardapios"
    resp_qualidade = client.get('/admin/qualidade')
    assert resp_qualidade.status_code == 302, f"Esperado 302 em /admin/qualidade para quem so tem cardapios, obtido {resp_qualidade.status_code}"
    print("  [OK] Permissao 'cardapios' nao vaza para 'qualidade'.")

    print("\n--- 3. TESTE: Superadmin 'admin' tem acesso total irrestrito ---")
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['admin_id'] = 1
        sess['admin_usuario'] = 'admin'
        sess['admin_perfil'] = 'admin_mestre'
        sess['admin_permissoes'] = ['all']

    for rota in ['/admin/turmas', '/admin/cardapios', '/admin/qualidade', '/admin/configuracoes', '/admin/administradores']:
        resp = client.get(rota)
        assert resp.status_code == 200, f"Superadmin deveria acessar {rota}, obtido {resp.status_code}"
    print("  [OK] Superadmin acessa todos os modulos normalmente.")

    print("\n--- 4. TESTE: Persistencia de Modo Escuro e Tema Preferido ---")
    # Salvar modo escuro ativado e paleta 'azul'
    resp_tema = client.post('/admin/tema', json={'modo_escuro': 1, 'tema': 'azul'})
    assert resp_tema.status_code == 200, f"Esperado 200 em /admin/tema, obtido {resp_tema.status_code}"
    data = resp_tema.get_json()
    assert data['modo_escuro'] == 1 and data['tema'] == 'azul', f"Resposta incorreta: {data}"

    # Conferir se salvou no banco de dados para o admin_id 1
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT modo_escuro, tema_preferido FROM administradores WHERE id = 1").fetchone()
    assert row['modo_escuro'] == 1 and row['tema_preferido'] == 'azul', f"Banco nao atualizado: {dict(row)}"
    print("  [OK] Modo escuro = 1 e tema = azul salvos com sucesso no banco de dados!")

    # Alternar para modo escuro = 0 mantendo a paleta
    resp_tema2 = client.post('/admin/tema', json={'modo_escuro': 0})
    assert resp_tema2.status_code == 200
    data2 = resp_tema2.get_json()
    assert data2['modo_escuro'] == 0 and data2['tema'] == 'azul', f"Resposta incorreta: {data2}"

    row2 = conn.execute("SELECT modo_escuro, tema_preferido FROM administradores WHERE id = 1").fetchone()
    assert row2['modo_escuro'] == 0 and row2['tema_preferido'] == 'azul'
    print("  [OK] Alternancia de modo escuro = 0 gravada corretamente no banco preservando a paleta.")

    # Restaurar padrao
    client.post('/admin/tema', json={'modo_escuro': 0, 'tema': 'padrao'})
    conn.close()

    print("\n--- 5. TESTE: Admin com 'config' mas SEM 'smtp' ---")
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['admin_id'] = 50
        sess['admin_usuario'] = 'admin_somente_config'
        sess['admin_perfil'] = 'operador'
        sess['admin_permissoes'] = ['config']

    resp_cfg = client.get('/admin/configuracoes')
    assert resp_cfg.status_code == 200, f"Esperado 200 em /admin/configuracoes, obtido {resp_cfg.status_code}"
    html_cfg = resp_cfg.get_data(as_text=True)
    assert 'Identidade Visual' in html_cfg, "Deveria exibir Identidade Visual"
    assert 'Parâmetros e Regras do Sistema' in html_cfg, "Deveria exibir Parâmetros do Sistema"
    assert 'Servidor de E-mail (SMTP)' not in html_cfg, "NÃO deveria exibir Servidor de E-mail (SMTP) para quem não tem permissao smtp!"

    # Tentativa de POST no SMTP deve ser rejeitada
    resp_post_smtp = client.post('/admin/configuracoes/smtp', data={'smtp_host': 'hacker.smtp.com'}, follow_redirects=True)
    assert 'Acesso negado' in resp_post_smtp.get_data(as_text=True), "Deveria barrar POST no SMTP para quem só tem config!"
    print("  [OK] Admin com 'config' NÃO vê nem acessa o Servidor SMTP.")

    print("\n--- 6. TESTE: Admin com 'smtp' mas SEM 'config' ---")
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['admin_id'] = 51
        sess['admin_usuario'] = 'admin_somente_smtp'
        sess['admin_perfil'] = 'operador'
        sess['admin_permissoes'] = ['smtp']

    resp_smtp_only = client.get('/admin/configuracoes')
    assert resp_smtp_only.status_code == 200, f"Esperado 200 em /admin/configuracoes para quem tem smtp, obtido {resp_smtp_only.status_code}"
    html_smtp = resp_smtp_only.get_data(as_text=True)
    assert 'Servidor de E-mail (SMTP)' in html_smtp, "Deveria exibir Servidor de E-mail (SMTP)"
    assert 'Identidade Visual' not in html_smtp, "NÃO deveria exibir Identidade Visual para quem só tem smtp!"
    assert 'Parâmetros e Regras do Sistema' not in html_smtp, "NÃO deveria exibir Parâmetros para quem só tem smtp!"

    # Tentativa de POST nas configurações gerais deve ser rejeitada
    resp_post_cfg = client.post('/admin/configuracoes', data={'nome_sistema': 'Invasao'}, follow_redirects=True)
    assert 'Acesso negado' in resp_post_cfg.get_data(as_text=True), "Deveria barrar POST nas configurações gerais!"
    print("  [OK] Admin com 'smtp' NÃO vê nem acessa as Configurações Gerais/Identidade Visual.")

    print("\n--- 7. TESTE: Modo Escuro do Estudante ---")
    with client.session_transaction() as sess:
        sess.clear()
        sess['aluno_id'] = 1
        sess['aluno_nome'] = 'Aluno Teste'

    # Salva modo escuro = 1 para o aluno
    resp_aluno_dark = client.post('/aluno/modo-escuro', json={'modo_escuro': 1})
    assert resp_aluno_dark.status_code == 200, f"Esperado 200 em /aluno/modo-escuro, obtido {resp_aluno_dark.status_code}"
    data_aluno = resp_aluno_dark.get_json()
    assert data_aluno['modo_escuro'] == 1, f"Retorno incorreto: {data_aluno}"

    # Conferir se gravou no banco na tabela alunos
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    aluno_db = conn.execute("SELECT modo_escuro FROM alunos WHERE id = 1").fetchone()
    assert aluno_db['modo_escuro'] == 1, f"Tabela alunos não gravou modo_escuro: {dict(aluno_db)}"

    # Verificar se tela do aluno renderiza com os botoes de alternancia
    resp_aluno_page = client.get('/')
    assert resp_aluno_page.status_code in [200, 302], f"Esperado 200 ou 302 na home do aluno, obtido {resp_aluno_page.status_code}"
    if resp_aluno_page.status_code == 302:
        resp_aluno_page = client.get(resp_aluno_page.headers.get('Location'))
    html_aluno = resp_aluno_page.get_data(as_text=True)
    assert 'btnStudentDarkMode' in html_aluno or 'toggleStudentDarkMode' in html_aluno, "Deveria renderizar o botão ou função de modo escuro do estudante!"

    # Restaurar modo escuro = 0 para o aluno
    client.post('/aluno/modo-escuro', json={'modo_escuro': 0})
    conn.close()
    print("  [OK] Modo escuro do estudante persistido no banco e disponibilizado na interface!")

    print("\n--- 8. TESTE: Paleta da Tela do Aluno sempre segue o Administrador ---")
    # Admin altera tema global para 'vinho'
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['admin_id'] = 1
        sess['admin_usuario'] = 'admin'
        sess['admin_permissoes'] = ['all']
    client.post('/admin/tema', json={'tema': 'vinho'})

    # Aluno acessa /aluno (sessão pura de aluno)
    with client.session_transaction() as sess:
        sess.clear()
        sess['aluno_id'] = 1
        sess['aluno_nome'] = 'Aluno Teste'

    resp_aluno_theme = client.get('/aluno')
    assert resp_aluno_theme.status_code == 200
    html_theme = resp_aluno_theme.get_data(as_text=True)
    assert 'const globalTheme = "vinho";' in html_theme, "Tema global vinho deve estar injetado na pagina do aluno"
    # Aluno NÃO deve ter modal de paleta de cores ou seletor de paleta
    assert 'openPaletteModal' not in html_theme, "Aluno não deve ter controle sobre a troca de paleta!"
    assert 'border-top: 4px solid var(--primary);' in html_theme, "Cards do aluno devem usar var(--primary)"

    # Restaurar para padrao
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['admin_id'] = 1
        sess['admin_usuario'] = 'admin'
        sess['admin_permissoes'] = ['all']
    client.post('/admin/tema', json={'tema': 'padrao'})
    print("  [OK] Página do aluno segue estritamente a paleta institucional do admin e não possui controle de paleta.")

    print("\n--- 9. TESTE: Diagnóstico Detalhado do SMTP ---")
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['admin_id'] = 1
        sess['admin_usuario'] = 'admin'
        sess['admin_permissoes'] = ['all']

    # Teste via AJAX / JSON
    resp_diag = client.post('/admin/configuracoes/smtp/testar', 
                            data={'email_teste': 'teste@escola.edu.br', 'smtp_host': 'smtp.inexistente.local', 'smtp_porta': '587', 'smtp_user': 'teste', 'smtp_senha': '123'},
                            headers={'Accept': 'application/json'})
    assert resp_diag.status_code == 200
    diag_data = resp_diag.get_json()
    assert 'etapas' in diag_data, "Deve retornar lista de etapas do diagnóstico"
    assert 'log_protocolo' in diag_data, "Deve retornar transcrição do protocolo"
    assert 'traceback' in diag_data, "Deve retornar campo de traceback"
    assert diag_data['success'] is False
    assert len(diag_data['etapas']) >= 2
    assert diag_data['etapas'][1]['status'] == 'erro'
    print("  [OK] Endpoint AJAX de teste SMTP retorna etapas, logs e sugestões com sucesso.")

    # Teste via formulário padrão com fallback de sessão
    resp_form = client.post('/admin/configuracoes/smtp/testar', 
                            data={'email_teste': 'teste@escola.edu.br', 'smtp_host': 'smtp.inexistente.local', 'smtp_porta': '587', 'smtp_user': 'teste', 'smtp_senha': '123'},
                            follow_redirects=True)
    assert resp_form.status_code == 200
    html_config = resp_form.get_data(as_text=True)
    assert 'smtp-diagnostic-card' in html_config, "Página de configurações deve exibir o cartão de diagnóstico detalhado"
    assert 'Transcrição do Protocolo SMTP e Rastreamento' in html_config
    print("  [OK] Submissão padrão de formulário renderiza painel detalhado de diagnóstico na interface.")

    print("\n TODOS OS TESTES PASSARAM COM 100% DE SUCESSO!")

if __name__ == '__main__':
    test_permissoes_e_modo_escuro()



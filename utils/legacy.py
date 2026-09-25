import flask

LEGACY_ENDPOINTS = {
    # main
    'index': 'main.index',
    'login': 'main.login',
    'logout': 'main.logout',
    'esqueceu_senha': 'main.esqueceu_senha',
    'resetar_senha_token': 'main.resetar_senha_token',

    # aluno
    'aluno_dashboard': 'aluno.aluno_dashboard',
    'aluno_selecionar_contexto': 'aluno.aluno_selecionar_contexto',
    'aluno_alterar_senha': 'aluno.aluno_alterar_senha',
    'aluno_reservar': 'aluno.aluno_reservar',
    'aluno_reservar_multiplas': 'aluno.aluno_reservar_multiplas',
    'aluno_cancelar': 'aluno.aluno_cancelar',
    'aluno_trocar_contexto': 'aluno.aluno_trocar_contexto',

    # admin
    'admin_login': 'admin.admin_login',
    'admin_logout': 'admin.admin_logout',
    'admin_esqueci_senha': 'admin.admin_esqueci_senha',
    'admin_recuperar_senha': 'admin.admin_recuperar_senha',
    'admin_dashboard': 'admin.admin_dashboard',
    'admin_administradores': 'admin.admin_administradores',
    'admin_administradores_excluir': 'admin.admin_administradores_excluir',
    'admin_administradores_alterar_senha': 'admin.admin_administradores_alterar_senha',
    'admin_administradores_editar': 'admin.admin_administradores_editar',
    'admin_avisos': 'admin.admin_avisos',
    'admin_avisos_excluir': 'admin.admin_avisos_excluir',
    'admin_avisos_editar': 'admin.admin_avisos_editar',
    'admin_reservas': 'admin.admin_reservas',
    'admin_reservas_manual': 'admin.admin_reservas_manual',
    'admin_reservas_cancelar': 'admin.admin_reservas_cancelar',
    'admin_turmas': 'admin.admin_turmas',
    'admin_turmas_editar': 'admin.admin_turmas_editar',
    'admin_turmas_excluir': 'admin.admin_turmas_excluir',
    'admin_alunos': 'admin.admin_alunos',
    'admin_alunos_editar': 'admin.admin_alunos_editar',
    'admin_alunos_excluir': 'admin.admin_alunos_excluir',
    'admin_alunos_imprimir': 'admin.admin_alunos_imprimir',
    'admin_alunos_csv_template': 'admin.admin_alunos_csv_template',
    'admin_alunos_importar': 'admin.admin_alunos_importar',
    'admin_alunos_resetar_senha': 'admin.admin_alunos_resetar_senha',
    'admin_alunos_suap_sync': 'admin.admin_alunos_suap_sync',
    'admin_eventos': 'admin.admin_eventos',
    'admin_evento_imprimir': 'admin.admin_evento_imprimir',
    'admin_evento_detalhe': 'admin.admin_evento_detalhe',
    'admin_evento_adicionar_participante': 'admin.admin_evento_adicionar_participante',
    'admin_evento_remover_participante': 'admin.admin_evento_remover_participante',
    'admin_evento_editar': 'admin.admin_evento_editar',
    'admin_evento_deletar': 'admin.admin_evento_deletar',
    'admin_evento_csv_template': 'admin.admin_evento_csv_template',
    'admin_evento_importar': 'admin.admin_evento_importar',
    'admin_cardapios': 'admin.admin_cardapios',
    'admin_cardapios_excluir': 'admin.admin_cardapios_excluir',
    'admin_cardapios_editar': 'admin.admin_cardapios_editar',
    'save_configuracoes': 'admin.save_configuracoes',
    'save_logo': 'admin.save_logo',
    'save_configuracoes_smtp': 'admin.save_configuracoes_smtp',
    'testar_smtp': 'admin.testar_smtp',
    'admin_entrega': 'admin.admin_entrega',
    'baixar_reserva': 'admin.baixar_reserva',
    'api_baixar_reserva': 'admin.api_baixar_reserva',
    'api_adicionar_extra': 'admin.api_adicionar_extra',
    'admin_relatorios': 'admin.admin_relatorios',
    'admin_relatorio_periodo': 'admin.admin_relatorio_periodo',
    'admin_relatorio_eventos': 'admin.admin_relatorio_eventos',
    'admin_relatorio_eventos_imprimir': 'admin.admin_relatorio_eventos_imprimir',
    'admin_relatorio_periodo_excel': 'admin.admin_relatorio_periodo_excel',
    'admin_relatorio_dia': 'admin.admin_relatorio_dia',
    'admin_relatorio_dia_imprimir': 'admin.admin_relatorio_dia_imprimir',
    'admin_api_buscar_alunos': 'admin.admin_api_buscar_alunos',
    'admin_relatorio_excel': 'admin.admin_relatorio_excel',
    'admin_auditoria': 'admin.admin_auditoria',
    'admin_pesquisas': 'admin.admin_pesquisas',
    'admin_pesquisa_novo': 'admin.admin_pesquisa_novo',
    'admin_pesquisa_editar': 'admin.admin_pesquisa_editar',
    'admin_pesquisa_toggle': 'admin.admin_pesquisa_toggle',
    'admin_pesquisa_excluir': 'admin.admin_pesquisa_excluir',
    'admin_pesquisa_respostas': 'admin.admin_pesquisa_respostas',
    'admin_pesquisa_excel': 'admin.admin_pesquisa_excel',
    'admin_pesquisa_qrcode': 'admin.admin_pesquisa_qrcode',
    'pesquisa_responder': 'main.pesquisa_responder',
    'pesquisa_identificar': 'main.pesquisa_identificar',
    'pesquisa_enviar': 'main.pesquisa_enviar',

    # qualidade / controle de recebimento e temperatura
    'admin_qualidade': 'admin.admin_qualidade',
    'admin_qualidade_novo': 'admin.admin_qualidade_novo',
    'admin_qualidade_editar': 'admin.admin_qualidade_editar',
    'admin_qualidade_excluir': 'admin.admin_qualidade_excluir',
    'admin_qualidade_detalhes': 'admin.admin_qualidade_detalhes',
    'admin_qualidade_imprimir': 'admin.admin_qualidade_imprimir',
    'admin_qualidade_imprimir_em_branco': 'admin.admin_qualidade_imprimir_em_branco',
    'admin_qualidade_salvar_padrao': 'admin.admin_qualidade_salvar_padrao',
}

original_url_for = flask.url_for

def custom_url_for(endpoint, **values):
    if endpoint in LEGACY_ENDPOINTS:
        endpoint = LEGACY_ENDPOINTS[endpoint]
    return original_url_for(endpoint, **values)

def setup_legacy_url_patch(app=None):
    flask.url_for = custom_url_for
    if app:
        app.jinja_env.globals['url_for'] = custom_url_for

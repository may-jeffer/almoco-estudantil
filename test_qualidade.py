# -*- coding: utf-8 -*-
import unittest
from app import create_app
from database import closing, get_db_connection

class TestQualidadeRefeicoes(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

        # Garantir cardápio de teste
        with closing(get_db_connection()) as conn:
            c = conn.execute("SELECT id FROM cardapios LIMIT 1").fetchone()
            if not c:
                conn.execute("""
                    INSERT INTO cardapios (data, tipo_refeicao, descricao, proteinas, acompanhamento)
                    VALUES ('2026-09-17', 'Almoço', 'Frango assado com arroz e feijão', 'Frango assado', 'Arroz e feijão')
                """)
                conn.commit()
                c = conn.execute("SELECT id FROM cardapios LIMIT 1").fetchone()
            self.cardapio_id = c['id']

    def test_fluxo_completo_qualidade(self):
        with self.client.session_transaction() as sess:
            sess['is_admin'] = True
            sess['admin_id'] = 1
            sess['admin_usuario'] = 'nutricionista.teste'
            sess['admin_perfil'] = 'admin_mestre'
            sess['admin_permissoes'] = ['all']

        # 1. Testar acesso à listagem
        res = self.client.get('/admin/qualidade')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Recebimento, Temperatura e Qualidade', res.data)

        # 2. Testar tela de novo registro
        res = self.client.get(f'/admin/qualidade/novo?cardapio_id={self.cardapio_id}')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Card\xc3\xa1pio de Refer\xc3\xaancia', res.data)

        # 3. Testar envio de novo registro com múltiplos itens
        payload = {
            'cardapio_id': str(self.cardapio_id),
            'campus': 'Campus Central',
            'data_recebimento': '2026-09-17',
            'horario_recebimento': '11:45',
            'fornecedor': 'Refeicoes Escolares Ltda',
            'tipo_preparo[]': ['Proteína', 'Feijão', 'Arroz', 'Macarrão', 'Outros'],
            'tipo_preparo_outro[]': ['', '', '', '', 'Salada Cozida de Legumes'],
            'temperatura[]': ['68.5', '65.0', '66.2', '63.0', '8.0'],
            'conformidade[]': ['Sim', 'Sim', 'Sim', 'Sim', 'Sim'],
            'aspecto_sensorial[]': ['Adequado', 'Adequado', 'Adequado', 'Adequado', 'Adequado'],
            'profissional_medicao[]': ['Dra. Ana Nutricionista', 'Dra. Ana Nutricionista', 'Dra. Ana Nutricionista', 'Dra. Ana Nutricionista', 'Dra. Ana Nutricionista'],
            'responsavel_recebimento[]': ['Joao Cantina', 'Joao Cantina', 'Joao Cantina', 'Joao Cantina', 'Joao Cantina'],
            'responsavel_fornecedor[]': ['Carlos Motorista', 'Carlos Motorista', 'Carlos Motorista', 'Carlos Motorista', 'Carlos Motorista'],
            'observacoes[]': ['Temperatura ótima', 'Em conformidade', 'Cozimento perfeito', 'Ponto adequado', 'Caixa térmica refrigerada']
        }

        res = self.client.post('/admin/qualidade/novo', data=payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'salvo com sucesso', res.data)

        # Verificar se salvou no banco
        with closing(get_db_connection()) as conn:
            registro = conn.execute("SELECT * FROM controle_qualidade WHERE campus = 'Campus Central' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNotNone(registro)
            reg_id = registro['id']

            itens = conn.execute("SELECT * FROM controle_qualidade_itens WHERE controle_id = ?", (reg_id,)).fetchall()
            self.assertEqual(len(itens), 5)

            # Verificar auditoria
            audit = conn.execute("SELECT * FROM logs_auditoria WHERE acao = 'Criar Controle de Qualidade' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNotNone(audit)
            self.assertIn(f'ID #{reg_id}', audit['detalhes'])

        # 4. Testar visualização de detalhes e impressão
        res_det = self.client.get(f'/admin/qualidade/detalhes/{reg_id}')
        self.assertEqual(res_det.status_code, 200)
        self.assertIn(b'Ficha de Controle', res_det.data)
        self.assertIn(b'Salada Cozida de Legumes', res_det.data)

        res_imp = self.client.get(f'/admin/qualidade/imprimir/{reg_id}')
        self.assertEqual(res_imp.status_code, 200)
        self.assertIn(b'Padr\xc3\xb5es de Recebimento', res_imp.data)

        # 4.1. Testar impressão em branco (avulsa)
        res_branco_avulso = self.client.get('/admin/qualidade/imprimir-em-branco')
        self.assertEqual(res_branco_avulso.status_code, 200)
        self.assertIn(b'Preenchimento Manual', res_branco_avulso.data)

        # 4.2. Testar impressão em branco (vinculada ao cardápio)
        res_branco_cardapio = self.client.get(f'/admin/qualidade/imprimir-em-branco?cardapio_id={self.cardapio_id}')
        self.assertEqual(res_branco_cardapio.status_code, 200)
        self.assertIn(b'Card\xc3\xa1pio Previsto no Sistema', res_branco_cardapio.data)

        # 4.3. Testar alteração do padrão sanitário (RDC 216 customizada)
        novo_padrao_texto = "Texto personalizado de normas sanitárias da cantina escolar."
        res_padrao = self.client.post('/admin/qualidade/salvar-padrao', data={'padrao_qualidade_texto': novo_padrao_texto}, follow_redirects=True)
        self.assertEqual(res_padrao.status_code, 200)
        self.assertIn(b'atualizados com sucesso', res_padrao.data)

        with closing(get_db_connection()) as conn:
            cfg = conn.execute("SELECT padrao_qualidade_texto FROM configuracoes WHERE id = 1").fetchone()
            self.assertEqual(cfg['padrao_qualidade_texto'], novo_padrao_texto)
            audit_padrao = conn.execute("SELECT * FROM logs_auditoria WHERE acao = 'Alterar Padrões Sanitários' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNotNone(audit_padrao)

            conn.execute("UPDATE configuracoes SET padrao_qualidade_texto = ? WHERE id = 1", (
                "• Preparações Quentes: Devem ser mantidas e recebidas a 60°C ou mais por no máximo 6 horas.\n"
                "• Preparações Frias: Devem ser mantidas e recebidas abaixo de 10°C (ou abaixo de 5°C para carnes e sobremesas lácteas).\n"
                "• Aspecto Sensorial: Avaliação de cor, odor, sabor e textura característicos de alimento próprio para consumo.",
            ))
            conn.commit()

        # 5. Testar edição do registro
        payload_edit = {
            'cardapio_id': str(self.cardapio_id),
            'campus': 'Campus Central (Editado)',
            'data_recebimento': '2026-09-17',
            'horario_recebimento': '12:00',
            'fornecedor': 'Refeicoes Escolares Ltda - Filial Norte',
            'tipo_preparo[]': ['Proteína', 'Arroz'],
            'tipo_preparo_outro[]': ['', ''],
            'temperatura[]': ['70.5', '67.0'],
            'conformidade[]': ['Sim', 'Sim'],
            'aspecto_sensorial[]': ['Adequado', 'Adequado'],
            'profissional_medicao[]': ['Dra. Ana Nutricionista', 'Dra. Ana Nutricionista'],
            'responsavel_recebimento[]': ['Joao Cantina', 'Joao Cantina'],
            'responsavel_fornecedor[]': ['Carlos Motorista', 'Carlos Motorista'],
            'observacoes[]': ['Ajuste de temperatura', 'Ok']
        }
        res_edit = self.client.post(f'/admin/qualidade/editar/{reg_id}', data=payload_edit, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        self.assertIn(b'atualizado com sucesso', res_edit.data)

        with closing(get_db_connection()) as conn:
            reg_atualizado = conn.execute("SELECT * FROM controle_qualidade WHERE id = ?", (reg_id,)).fetchone()
            self.assertEqual(reg_atualizado['campus'], 'Campus Central (Editado)')
            self.assertEqual(reg_atualizado['horario_recebimento'], '12:00')

            itens_atualizados = conn.execute("SELECT * FROM controle_qualidade_itens WHERE controle_id = ?", (reg_id,)).fetchall()
            self.assertEqual(len(itens_atualizados), 2)

            audit_edit = conn.execute("SELECT * FROM logs_auditoria WHERE acao = 'Editar Controle de Qualidade' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNotNone(audit_edit)

        # 6. Testar exclusão do registro
        res_del = self.client.post(f'/admin/qualidade/excluir/{reg_id}', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIn(b'exclu\xc3\xaddo com sucesso', res_del.data)

        with closing(get_db_connection()) as conn:
            reg_deletado = conn.execute("SELECT * FROM controle_qualidade WHERE id = ?", (reg_id,)).fetchone()
            self.assertIsNone(reg_deletado)
            itens_deletados = conn.execute("SELECT * FROM controle_qualidade_itens WHERE controle_id = ?", (reg_id,)).fetchall()
            self.assertEqual(len(itens_deletados), 0)

            audit_del = conn.execute("SELECT * FROM logs_auditoria WHERE acao = 'Excluir Controle de Qualidade' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNotNone(audit_del)

        print("\n>>> TODOS OS TESTES DE CONTROLE DE QUALIDADE PASSARAM COM SUCESSO! <<<")

if __name__ == '__main__':
    unittest.main()

# Manual do Usuário - Sistema de Gestão de Almoço

Bem-vindo ao sistema de gestão de refeições. Este manual guiará você pelas principais funcionalidades da aplicação.

## 1. Visão Geral
O sistema permite que alunos reservem refeições com antecedência e que a cantina controle a entrega via QR Code, evitando desperdícios.

---

## 2. Para o Aluno (Reserva de Almoço)

### 2.1 Acesso Inicial
- Acesse o portal com seu **CPF**.
- No primeiro acesso, sua senha será sua **Data de Nascimento** (DDMMAAAA ou AAAA-MM-DD).
- O sistema solicitará que você cadastre uma **Senha Forte** e seu **E-mail** para recuperação.

### 2.2 Reservando Almoço
- No Dashboard, localize o card **"Agendar Próximo Almoço"**.
- Se houver cardápio aberto, clique em **"Quero Reservar!"**.
- O prazo limite para reserva é definido pela instituição (geralmente até as 18h do dia anterior).

### 2.3 No dia do Almoço
- Abra o sistema no celular.
- No card **"Almoço de Hoje"**, aparecerá o seu **QR Code**.
- Apresente este código para o operador da cantina.

---

## 3. Para o Administrador (Gestão)

### 3.1 Painel de Controle (Dashboard)
- Acesse `/admin/login` com seu usuário e senha.
- **Configurações Globais:** Aqui você define o Nome do Sistema, Sigla da Instituição e o Horário Limite de reserva.
- **Marca Branca:** Você pode subir a Logomarca da sua escola no botão "Atualizar Logo".

### 3.2 Gerenciar Alunos
- **Importação CSV:** Você pode baixar o "Modelo CSV" e preencher com os dados do seu sistema acadêmico (SUAP/SIGAA) para importar centenas de alunos de uma vez.
- **Reset de Senha:** Caso um aluno esqueça a senha e não tenha e-mail, você pode resetar o acesso dele manualmente na lista de alunos.

### 3.3 Cadastro de Cardápio
- Crie o cardápio para datas futuras. O sistema só permite reserva se houver um cardápio cadastrado para o dia.

### 3.4 Ponto de Entrega (Fila)
- Utilize um celular ou tablet com câmera.
- Aponte a câmera para o QR Code do aluno.
- O sistema dará um "Bipe" e confirmará o nome do aluno na tela sem recarregar a página (AJAX).

### 3.5 Relatórios e Auditória
- Acesse a aba **Relatórios**.
- Escolha uma data para ver quem comeu e quem faltou.
- Clique em **"Baixar Planilha (Excel)"** para obter o relatório profissional para prestação de contas.

### 3.6 Gestão de Acessos e Permissões (ACL)
- Na aba **Gestão de Acessos**, você pode cadastrar outros servidores.
- **Níveis de Acesso:**
    - **Mestre:** Possui controle total sobre todas as funções do sistema.
    - **Operador:** Perfil limitado, geralmente usado para quem apenas bipará os QR Codes na fila.
- **Edição de Permissões:** Clique no ícone de **Lápis** em um administrador existente para habilitar ou desabilitar módulos específicos (ex: permitir que um operador veja relatórios, mas não altere cardápios).

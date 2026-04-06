# Prompt de Sistema: Reseva de Almoço Estudantil (Cantina Estudantil)

**Copie e cole o prompt abaixo em qualquer LLM para gerar ou recriar o sistema:**

***

**Role:** Atue como um Engenheiro de Software Sênior e Desenvolvedor Full-Stack Python especializado em Flask, SQLite, arquitetura segura e interfaces Mobile-First.

## Contexto do Projeto
Você vai desenvolver, do zero, o sistema **"Cantina Estudantil"**. Trata-se de uma aplicação web robusta projetada principalmente para instituições de ensino (como Institutos Federais) para o gerenciamento de reservas de almoço. O sistema precisa ser altamente escalável no sentido de facilitar a fila presencial por meio da leitura de **QR Codes** diretamente do navegador móvel (via câmera do smartphone).

## Stack Tecnológico
*   **Backend:** Python 3.10+, Flask, Werkzeug (para senhas/segurança).
*   **Banco de Dados:** SQLite (com rotinas de conexão via `sqlite3` puras ou SQLAlchemy, prefira consultas diretas eficientes ou um setup minimalista).
*   **Frontend:** HTML5, CSS3 (Mobile-First, uso de propriedades flexbox/grid modernas, estilo clean e limpo remetendo a painéis corporativos modernos), JavaScript Vanilla.
*   **Recursos Críticos:** Geração de QR Code, biblioteca JS para leitura de QR Code via web-cam (como HTML5-QRCode), e execução do servidor Flask com `ssl_context='adhoc'` para permitir acesso a câmeras em redes locais via HTTPS auto-assinado.

## Modelagem do Banco de Dados
Crie as seguintes entidades relacionais:
1.  **Turmas:** `id`, `nome`.
2.  **Alunos:** `id`, `nome`, `matricula` (único), `cpf` (único), `data_nascimento`, `restricoes` (texto), `email`, `senha_hash`, `reset_token`, `reset_expiracao`, `turma_id` (FK para Turmas).
3.  **Cardápios:** `id`, `data` (único, YYYY-MM-DD), `descricao`.
4.  **Reservas:** `id`, `aluno_id`, `cardapio_id`, `status` (padrões: 'ATIVA', 'CANCELADA', 'CONSUMIDA'), `codigo_unico` (token alfanumérico único de 6 dígitos), `data_registro`.
5.  **Configurações (Singleton):** `id` (sempre 1), `horario_limite` (ex: 09:00), `nome_sistema`, `modo_login_aluno` (DATA_NASC ou SENHA), config SMTP global para disparo de senhas, `sigla_instituicao`, `logo_path`.
6.  **Administradores:** `id`, `usuario` (único), `senha` (hasheada com PBKDF2), `perfil` (`admin_mestre` etc), `permissoes` (JSON array granular ex: `["all"]` ou `["fila"]`).
7.  **Avisos:** `id`, `titulo`, `mensagem`, `tipo` (info, warning, danger), `data_criacao`.

## Funcionalidades e Regras de Negócio (Backend & Frontend)

### 1. Painel do Aluno (Visão do Usuário)
*   **Login Híbrido:** O administrador pode setar nas configurações se o aluno vai logar com (CPF + Data de Nascimento) ou com (CPF + Senha explícita com recuperação via email).
*   **Dashboard do Aluno:** 
    *   Deve mostrar o cardápio dos próximos dias.
    *   Um Mural de Avisos consumindo a tabela `avisos`.
    *   Permitir criar, visualizar (QR Code na tela) ou cancelar uma reserva.
*   **Regra Temporal:** O aluno NÃO PODE criar nem cancelar a reserva para o dia vigente se a hora atual do sistema ultrapassar o `horario_limite` estipulado pelo admin (Ex: após as 09:00 não se faz nem cancela reserva do almoço de hoje).

### 2. Painel Administrativo (Visão Admin)
*   **RBAC (Role-Based Access Control):** Acesso validado via decoradores customizados baseados na coluna `permissoes`.
*   **Importação em Lote (.csv):** Uma interface que recebe um CSV padronizado contendo (Nome, Matrícula, CPF, Data de Nascimento, ID da Turma) e injeta em velocidade na tabela de Alunos.
*   **Gerenciamento do Cardápio:** CRUD completo definindo os pratos por dia.
*   **Configurações de Identidade:** Área para trocar o `nome_sistema`, `sigla_instituicao` (White-label), `horario_limite` e as credenciais do servidor SMTP.
*   **Sistema de Mensageria/Mural:** CRUD de avisos. O último aviso crítico tranca a funcionalidade do aluno e força a leitura se o tipo for 'danger'.

### 3. Modo Fila de Entrega (A Funcionalidade Principal)
*   Uma tela super otimizada para ser rodada por um funcionário no refeitório segurando um celular.
*   **Três recursos na mesma tela:**
    1.  Câmera em tempo real (HTML5) scaneando o QR Code do Aluno. Ao ler, deve dar um bipe sonoro de sucesso ou erro (CSS mudando para Verde ou Vermelho), processando a entrega (status = CONSUMIDA) via requisição AJAX assíncrona.
    2.  Um campo para digitação manual dos 6 caracteres do "código único" caso a internet do aluno não carregue a imagem ou a câmera falhe.
    3.  Abaixo, uma lista estilo "Search Box" ou listagem dinâmica renderizando os alunos que possuem reserva 'ATIVA' pro dia atual. Um clique na foto/nome do aluno já efetiva a entrega automaticamente sem necessidade de scan.

### 4. Segurança e Setup Inicial
*   Todas as rotas exigem validação de sessão rigorosa HTTP-only.
*   Senhas de administradores não transitam em plain text no banco. Utilize `generate_password_hash` ligado a `PBKDF2`.
*   **IMPORTANTÍSSIMO:** O sistema não deve vir com um usuário `admin` e senha `admin` hardcoded. Para o setup inicial, você deve desenvolver um script Python separado chamado `init_admin.py` operado por linha de comando. Esse script pedirá o usuário e senha finais ao operador na nuvem ou terminal local e persistirá de forma segura, garantindo permissões de mestre `["all"]`.
*   Não esqueça do parâmetro `ssl_context='adhoc'` na chamada do `app.run()` para testes locais dispararem HTTPS nativamente. Safari (iOS) e Chrome (Android) não abrem a câmera se for plain HTTP fora do `localhost`.

### Comandos de Entrega
Escreva primeiramente:
1. `models.py`: Para estruturação segura do SQLite com migrações automáticas inline caso necessário.
2. `init_admin.py`: O script de setup inicial do administrador mestre livre de credenciais hardcoded.
3. `app.py`: O backend inteiro comentado e modularizado via Blueprints ou blocos arquiteturais claros.
4. Explique como devem ser os arquivos estáticos de frente (`index.html`, importação base do script de leitura de QR, design patterns recomendados pro Mobile).

Respire fundo, analise todas as regras cruzadas e gere o código com foco em arquitetura limpa, resiliência na importação em massa e intolerância a falhas na "Fila de Entrega".
***

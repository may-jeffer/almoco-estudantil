# 🍽️ Cantina Estudantil - Sistema de Gestão de Refeições & Fila

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/framework-Flask%203.x-green.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/database-SQLite-lightgrey.svg)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/license-Software%20Livre%20%2F%20Open%20Source-emerald.svg)](#-licen%C3%A7a-e-uso)

> Sistema web completo, moderno e responsivo para gestão da alimentação escolar em institutos federais, escolas técnicas, universidades e polos educacionais. Inclui controle de cardápios, encomendas a fornecedores terceirizados, fila com scanner de crachás/QR Code, detecção de alergias críticas, emissão de crachás térmicos (PVC Fargo DTC1250e / A4), formulários de pesquisa estilo Google Forms, relatórios de desperdício/sobras e manual operacional integrado.

---

## 🌟 Principais Funcionalidades

### 1. 👥 Gestão de Turmas, Estudantes & Impressão de Crachás
- **Cadastro & Importação em Lote:** Cadastro individual ou importação massiva de estudantes via planilha CSV (`Nome,Matricula,CPF,DataNascimento,Restricoes,Turma`).
- **Sincronização com SUAP:** Integração com o sistema acadêmico para importação e atualização automática de estudantes.
- **Impressão de Crachás de Alta Precisão:**
  - **Cartão PVC CR-80 (Impressoras Térmicas Fargo DTC1250e / Evolis / Zebra):** Formato padrão 54mm × 86mm com quebra contínua de página por aluno.
  - **Grade Folha A4:** 8 crachás por página com marcas de corte para plastificação/polaseal.
  - **Memória de Seleção:** O sistema lembra a sua escolha preferida de impressão no navegador.

### 2. 🍽️ Gestão de Cardápios & Controle de Fornecedor
- **Planejamento Nutricional:** Cadastro de refeições (Almoço, Jantar, Lanche), proteínas, acompanhamentos, saladas e sobremesas.
- **Quantidade Solicitada ao Fornecedor:**
  - **Modo Automático:** A meta encomendada à empresa contratada é atualizada automaticamente conforme as reservas dos alunos.
  - **Modo Manual:** Definição de cota fixa contratada (ex: `250` refeições).

### 3. ⚡ Modo Fila & Scanner de Refeições
- **Leitura Ágil de Tickets & Crachás:** Compatível com leitor de código de barras USB, leitor de QR Code de câmeras móveis ou digitação direta.
- **4 Indicadores em Tempo Real:**
  1. *Solicitado à Empresa (Meta fixa ou reservas)*
  2. *Reservas no Sistema (Agendamentos prévios)*
  3. *Extras Entregues (Alunos sem reserva prévia)*
  4. *Total Entregue (Consumo Reserva + Extras)*
- **🛡️ Protocolo Crítico de Alergias & Restrições Alimentares:** Dispara um **alerta sonoro imediato e modal bloqueante em vermelho** destacando o nome do aluno, turma e a restrição exata (ex: *Intolerância a Lactose, Celíaco, Alergia a Frutos do Mar*).

### 4. 🎟️ Gerenciar Reservas Ativas & Reserva Manual
- **Listagem Paginada:** Acompanhamento de todas as reservas ativas para o dia atual e dias futuros.
- **Cancelamento Preventivo:** Cancelamento de reservas de alunos ausentes para liberar pratos.
- **Reserva Manual para Administradores:** Permite emitir reservas para estudantes mesmo após o horário limite ter expirado, com registro detalhado em logs de auditoria.

### 5. 📋 Pesquisas e Formulários Dinâmicos (Google Forms)
- **Construtor Visual de Formulários:** Criação de pesquisas com 4 tipos de campos (Múltipla Escolha, Caixas de Seleção, Resposta Curta e Parágrafo).
- **Controle de Anonimato:**
  - *100% Anônimo:* Sem login, garantindo total sigilo.
  - *Identificado:* Valida sessão ou CPF + Nascimento/Senha com trava de 1 resposta por aluno.
- **Compartilhamento por QR Code:** Geração de QR Code em PNG de alta resolução para impressão ou telões.
- **Exportação para Excel:** Download de todas as respostas em planilha `.xlsx` com um clique.

### 6. ⭐ Módulo de Eventos & Público Externo
- Criação de eventos temporários (congressos, seminários, vestibulares).
- Cadastro de visitantes com matrículas `EVT-...` e emissão de crachás exclusivos.
- Relatórios dedicados para prestação de contas separada da cantina regular.

### 7. 📊 Relatórios de Consumo, Desperdício & Auditoria
- Relatórios por data específica ou consolidados por período com gráficos analíticos.
- Fórmulas auditáveis: *Pratos Previstos*, *Consumo Reserva*, *Extras*, *Sobras (Desperdício)* e *Total Entregue*.
- Exportação oficial de relatórios em planilhas Excel (`.xlsx`).
- **Logs de Auditoria:** Rastreabilidade de todas as ações administrativas com data, hora, usuário e endereço IP.

### 8. ⚙️ Configurações Globais & Identidade Visual
- **Logomarca Institucional Dinâmica:** A logo da instituição é aplicada automaticamente no cabeçalho, nos crachás e como **Favicon** em todas as abas do navegador.
- **Horário Limite Diário de Reserva:** Corte automático para encerramento de agendamentos.
- **Servidor SMTP:** Integração para envio de e-mails de recuperação de senha e comunicados.
- **Auto-Logout:** Encerramento automático de sessão em totens públicos por inatividade.

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem:** Python 3.10+
- **Backend / Framework:** Flask 3.x com Blueprints modulares (`routes/admin/`, `routes/aluno.py`, `routes/main.py`)
- **Banco de Dados:** SQLite3 com conexões gerenciadas (`database/connection.py`)
- **Frontend:** HTML5 Semântico, Vanilla CSS responsivo, Jinja2 Templates e Phosphor Icons
- **Relatórios:** OpenPyXL para planilhas `.xlsx`
- **QR Codes:** Qrcode & Pillow (PIL)
- **Segurança:** Werkzeug Security (`pbkdf2:sha256`), PyOpenSSL / Cryptography para HTTPS

---

## 🚀 Como Executar o Projeto

### 1. Clonar o Repositório
```bash
git clone https://github.com/may-jeffer/almoco-estudantil.git
cd almoco-estudantil
```

### 2. Criar e Ativar o Ambiente Virtual
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux / MacOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar as Dependências
```bash
pip install -r requirements.txt
```

### 4. Criar o Primeiro Administrador Mestre
Execute o script interativo para cadastrar o usuário e senha do primeiro administrador:
```bash
python init_admin.py
```

### 5. Iniciar a Aplicação
Você pode iniciar o servidor de administração via HTTPS:
```bash
python run_admin.py
```
*O sistema iniciará na porta segura `https://127.0.0.1:5443`.*

---

## 📁 Estrutura de Diretórios Completa

```text
almoco-estudantil/
├── config.py                   # Configurações do Flask e caminhos do sistema
├── app.py                      # Ponto de entrada e registro de blueprints
├── init_admin.py               # Script para criar o primeiro administrador
├── run_admin.py                # Inicializador do servidor do portal admin (HTTPS 5443)
├── run_aluno.py                # Inicializador do servidor do portal do estudante
├── requirements.txt            # Dependências Python do projeto
├── README.md                   # Documentação oficial do projeto
│
├── database/                   # Camada de banco de dados SQLite e migrações
│   ├── __init__.py             # Pacote do banco de dados
│   ├── connection.py           # Conexão, factory, funções SQL e migrações automáticas
│   └── queries.py              # Queries auxiliares
│
├── routes/                     # Módulos e Blueprints da aplicação
│   ├── __init__.py             # Inicialização dos blueprints
│   ├── main.py                 # Rotas públicas (login, pesquisas estudantis públicas)
│   ├── aluno.py                # Portal do estudante (reservas, cancelamentos, histórico)
│   └── admin/                  # Módulos da área administrativa
│       ├── __init__.py         # Definição do blueprint admin_bp
│       ├── alunos.py           # Alunos, importação CSV, SUAP e crachás
│       ├── cardapios.py        # Cardápios e controle de fornecedor
│       ├── dashboard.py        # Painel, administradores, SMTP, logo e manual
│       ├── eventos.py          # Gestão de eventos e público externo
│       ├── fila.py             # Modo fila, scanner e reservas ativas/manuais
│       ├── pesquisas.py        # Formulários dinâmicos, QR Code e Excel
│       ├── relatorios.py       # Relatórios consolidados, diários e auditoria
│       └── turmas.py           # Gestão de turmas regulares
│
├── static/                     # Arquivos estáticos
│   ├── style.css               # Estilos globais responsivos do sistema
│   └── uploads/                # Diretório de uploads
│       ├── logo_instituicao.png # Logomarca institucional (favicon e cabeçalho)
│       └── base_conhecimento/  # Arquivos anexados da base de conhecimento
│
├── templates/                  # Templates HTML (Jinja2)
│   ├── base.html               # Layout base com favicon e navbar dinâmicos
│   ├── login.html              # Tela de login do estudante
│   ├── aluno_dashboard.html    # Painel do estudante
│   ├── aluno_setup_senha.html  # Definição inicial de senha
│   ├── esqueci_senha.html      # Solicitação de recuperação de senha
│   ├── recuperar_senha.html    # Redefinição de senha com token
│   ├── pesquisa_responder.html # Tela pública de resposta da pesquisa
│   ├── selecionar_contexto.html# Seleção de contexto (turma regular vs evento)
│   └── admin/                  # Templates da área administrativa
│       ├── dashboard.html      # Painel administrativo com atalhos
│       ├── administradores.html# Controle de acessos e permissões (ACL)
│       ├── alunos.html         # Lista de alunos e importação CSV
│       ├── alunos_imprimir.html# Impressão de crachás (PVC Térmica e A4)
│       ├── auditoria.html      # Histórico de logs de auditoria
│       ├── avisos.html         # Mural de comunicados
│       ├── base_conhecimento.html # Base de conhecimento e tutoriais
│       ├── cardapios.html      # Cadastro e listagem de cardápios
│       ├── entrega.html        # Modo fila com scanner e alerta de alergias
│       ├── eventos.html        # Lista de eventos
│       ├── evento_detalhe.html # Participantes e crachás do evento
│       ├── evento_imprimir.html# Impressão de crachás de evento
│       ├── login.html          # Login restrito de administradores
│       ├── pesquisas.html      # Lista e gestão de formulários de pesquisa
│       ├── pesquisa_form.html  # Construtor visual de formulários (Google Forms)
│       ├── pesquisa_respostas.html # Dashboard analítico de respostas
│       ├── relatorios_filtro.html  # Filtro de relatórios de refeições
│       ├── relatorio_dia.html      # Relatório detalhado por dia
│       ├── relatorio_periodo.html  # Relatório consolidado por período
│       ├── relatorio_eventos.html  # Relatório de consumo por evento
│       ├── reservas.html       # Reservas ativas e emissão manual com auditoria
│       └── turmas.html         # Gestão de turmas
│
└── utils/                      # Módulos utilitários e serviços
    ├── auth.py                 # Autenticação, controle de sessão, rate-limiting e ACL
    ├── filters.py              # Filtros customizados do Jinja2
    ├── helpers.py              # Funções de data, auditoria e sanitização
    ├── legacy.py               # Compatibilidade de rotas e URLs legadas
    ├── mailer.py               # Envio de e-mails via servidor SMTP
    ├── qrcode_gen.py           # Geração de QR Codes e crachás
    └── services.py             # Serviços de regras de negócio
```

---

## 📄 Licença e Uso

Este projeto é um **Software Livre e de Código Aberto (Open Source)**, desenvolvido para fins educacionais, acadêmicos e de gestão pública em institutos federais, escolas e universidades.

Você é livre para utilizar, estudar, modificar e distribuir este sistema na sua instituição de ensino.

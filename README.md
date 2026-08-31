# 🍽️ Cantina Estudantil - Sistema de Gestão de Refeições & Fila

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/framework-Flask%203.x-green.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/database-SQLite-lightgrey.svg)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

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

### 8. 📖 Manual Operacional Integrado (`/admin/manual`)
- Manual completo com 9 capítulos ilustrados acessível diretamente dentro da aplicação.
- Busca rápida por palavras-chave e botão para **Imprimir / Salvar em PDF** formatado para folha A4.

### 9. ⚙️ Configurações Globais & Identidade Visual
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

## 📁 Estrutura de Diretórios

```text
almoco-estudantil/
├── database/                   # Camada de banco de dados SQLite e migrações
│   ├── connection.py           # Conexão, factory e migrações automáticas de schema
│   └── queries.py              # Queries auxiliares
├── routes/                     # Módulos e Blueprints da aplicação
│   ├── admin/                  # Rotas da área administrativa (modular)
│   │   ├── alunos.py           # Alunos, CSV, SUAP e crachás
│   │   ├── cardapios.py        # Cardápios e fornecedor
│   │   ├── dashboard.py        # Painel, administradores, SMTP, logo e manual
│   │   ├── eventos.py          # Eventos e público externo
│   │   ├── fila.py             # Modo fila, scanner e reservas ativas/manuais
│   │   ├── pesquisas.py        # Construtor de formulários, QR Code e Excel
│   │   ├── relatorios.py       # Relatórios, métricas e auditoria
│   │   └── turmas.py           # Turmas escolares
│   ├── aluno.py                # Portal do estudante (reservas, histórico)
│   └── main.py                 # Rotas públicas (login, pesquisas públicas)
├── static/                     # Arquivos estáticos (CSS, imagens, uploads)
│   ├── style.css               # Folha de estilos global
│   └── uploads/                # Logomarca e uploads da base de conhecimento
├── templates/                  # Templates HTML em Jinja2
│   ├── admin/                  # Telas administrativas (pesquisas, manual, etc.)
│   ├── base.html               # Layout base com favicon e navbar dinâmicos
│   └── ...                     # Telas de login, aluno e enquetes
├── utils/                      # Utilitários, segurança e helpers
│   ├── auth.py                 # Controle de sessão, rate-limiting e ACL
│   ├── mailer.py               # Envio de e-mails via SMTP
│   └── qrcode_gen.py           # Gerador de QR Codes e crachás
├── requirements.txt            # Dependências do projeto
├── run_admin.py                # Script de execução do servidor HTTPS
├── init_admin.py               # Inicializador de credenciais de administrador
└── README.md                   # Documentação do projeto
```

---

## 📄 Licença

Distribuído sob a licença **MIT**. Consulte o arquivo `LICENSE` para mais detalhes.

# Cantina Estudantil - Manual e Guia de Instalação 🚀

Um sistema web completo para gerenciamento de reservas de almoço em polos educacionais (foco visual: Instituto Federal), adaptado para mobile, com fila interativa por leitor de QR Code integrado na web e importação ágil.

## 🛠️ Requisitos Rápidos
- Python 3.10 ou superior.
- Celular ou Impressora para o uso dos QR Codes pelos alunos.

---

## ⚡ Como Instalar em Qualquer Servidor ou Computador Local.

### Passo 1: Transferir/Clonar o Repositório
Baixe ou mova a pasta `almoco-estudantil` inteira para o servidor (ex: um PC com Windows ou Linux na mesma rande da sua escola, ou em uma nuvem como Heroku/VPS).

### Passo 2: Criar e Ativar Ambiente Virtual (Recomendado)
Pelo terminal cmd/PowerShell ou bash dentro da pasta do projeto:
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### Passo 3: Instalar Dependências 
Com o ambiente ativado, instale as bibliotecas necessárias usando o arquivo de requisitos:
```bash
pip install -r requirements.txt
```

### Passo 4: Rodar o Servidor
```bash
python app.py
```
**Observação Importante:** Na primeira vez que você rodar, o SQLite criará o arquivo `database.db`. **O sistema não possui senha padrão.**

### Passo 5: Criar Administrador (Obrigatório)
Execute o script de inicialização para definir seu usuário e senha mestres:
```bash
python init_admin.py
```

> [!WARNING]
> **HTTPS Móvel:** Como o `app.py` tem `ssl_context='adhoc'`, o servidor já roda nativamente com um certificado Auto-Assinado criptografado na porta local `https://[seu-ip]:5000`. Isso é **obrigatório** porque o sistema de leitura de código QR baseia-se na restrição fortíssima da Apple (Safari) e Google (Chrome Mobile), que só emprestam a web-cam se virem no rodapé o protocolo HTTPS em trânsito de rede. Ao acessar do navegador local via celular, se apitar "Site Inseguro", clique em "Visualizar Detalhes" > "Acessar Assim Mesmo".

---

## 📖 Como Usar - Manual do Administrador

### Primeiro Acesso
- **URL Admin:** `/admin/login`
- **Credencial:** Use o usuário e senha que você definiu no `Passo 5` via `init_admin.py`.

### 1. Renomeação Dinâmica e Configuração de Horário
- Na Dashboard clique em "Configurações Globais" e troque o nome que se projeta sobre o sistema na nuvem (Ex: IFAP - Cantina).
- Defina o `Horário Limite`. Isso dirá o encerramento em que alunos não mais poderão alterar as regras do dia seguinte (por Exemplo: 09:00).

### 2. Cadastro Inicial (Pré-requisitos da Alimentação)
Antes da cantina voar, monte as rodinhas de engrenagem.
1. **Turmas**: Cadastre `1º Ano Informática` e note o `ID` gerado na tabela, ele será sua âncora nos CSVs.
2. **Cardápio**: Defina "Estrogonofe" para quarta. (Sem cardápios na rua, as paredes dos alunos ficam cinzas e impenetráveis à reserva).

### 3. Subindo a Base (Sistema em Massa)
Vá na área de Alunos. Suas artérias já suportam envios pesados. Se possui os dados de um SUAP ou SIGAA (Em breve via API, hoje via CSV):
- Baixe o "Modelo `.csv`" usando o Botão Branco na Tela.
- Abra no Planilhas do Google (ou Microsoft Excel arrumando codificação UTF-8), inclua os "CPFs" contendo pontos e traços como o usuário quiser (o sistema faz parse puro).
- Referencie estritamente o `TurmaID` correto no aluno.
- Salve via formato delimitado padrão e faça o Upload no botão vermelho de Importação. 1000 estudantes entrarão de uma só vez.

### 4. Mural de Avisos Dinâmico
Use o Painel Mural de Avisos. Precisa decretar paralisação na cantina sem aviso prévio? Dispare um card vermelho e o aplicativo de todos os usuários matriculados bloqueará o sol do QR Code deles com essa nota urgente.

### 5. O Crivo Tático - Modo Fila de Entrega Diária
Abra o último botão laranja "Modo Fila" (ou `/admin/entrega`). Uma tela dividida em pilares perfeitos pro Mobile:
- **Acima:** A câmera vai buscar os tickets QR das telas ou impressos. Um bipe sonoro audita o almoço do estudante.
- **Meio do Fogo Cruzado:** Se a internet tragar o QR Code de um rapaz, basta digitar o token textual embaixo da câmera.
- **Arma Mais Célere:** Barra *Search Box ao Vivo*. Embaixo, há a visualização "Real-time" da fila agendada do dia (em cache leve). Digite fragmentos da placa dele "Marcos" e dê Check/Baixa direta tocando na tela ao lado do garoto, entregando a comida e salvando a cantina sem qualquer código.

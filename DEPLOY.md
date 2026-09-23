# Guia Oficial de Implantação (Deployment) & Publicação na Internet

Este documento descreve como empacotar a aplicação, executar a instalação automatizada (Linux e Windows) com banco de dados limpo, e configurar o acesso seguro via Internet com HTTPS.

---

## 1. Empacotamento para Distribuição (`build_package.py`)

Antes de enviar a aplicação para o servidor de produção, gere o pacote de instalação limpo:

### 1.1 Pacote Padrão (Servidor com Acesso à Internet)
```bash
python build_package.py
```
Gera o arquivo `dist/almoco-estudantil-dist.zip` (ou `.tar.gz`) contendo o código de produção.
- **Garantia de Banco Limpo**: Qualquer arquivo `database.db`, caches (`__pycache__`), arquivos `.env` e arquivos de teste são estritamente excluídos do pacote.

### 1.2 Pacote Offline (Servidor sem Conexão à Internet)
Para instalar em servidores sem acesso à rede externa (redes fechadas ou laboratórios isolados):
```bash
python build_package.py --offline
```
- O script baixa antecipadamente todos os pacotes `.whl` (wheels) para uma pasta interna `wheels/`.
- Os instaladores (`install.sh` e `install.bat`) detectam a pasta e instalam 100% offline.

---

## 2. Instalação Automatizada no Servidor

Envie o arquivo `almoco-estudantil-dist.zip` para o servidor e extraia seu conteúdo.

### Opção A: Servidor Linux (Ubuntu 22.04+ / Debian)
Execute o script instalador como usuário comum (o script solicitará `sudo` quando necessário):
```bash
chmod +x install.sh
./install.sh
```

**O que o instalador do Linux faz automaticamente:**
1. Valida Python 3.10+.
2. Cria o ambiente virtual (`venv/`) e atualiza dependências (offline ou online).
3. Garante a instalação do servidor WSGI **Gunicorn**.
4. Gera um arquivo `.env` com chave secreta criptográfica única (`SECRET_KEY`).
5. Cria o banco de dados limpo e pergunta se deseja criar o Administrador agora ou utilizar o padrão provisório (`admin` / `admin123`).
6. Configura e ativa o serviço no **Systemd** (`/etc/systemd/system/almoco-estudantil.service`) para inicialização automática no boot.
7. Gera o arquivo de configuração para Nginx (`nginx_almoco.conf`).

**Comandos de Gerenciamento do Serviço Linux:**
- Status: `sudo systemctl status almoco-estudantil`
- Reiniciar: `sudo systemctl restart almoco-estudantil`
- Parar: `sudo systemctl stop almoco-estudantil`
- Ver logs em tempo real: `sudo journalctl -u almoco-estudantil -f`

---

### Opção B: Servidor Windows (Windows 10, 11 ou Server)
Basta dar duplo clique em `install.bat` ou executar no Prompt de Comando (CMD) como Administrador:
```cmd
install.bat
```

**O que o instalador do Windows faz automaticamente:**
1. Valida Python 3.10+ no PATH.
2. Cria o ambiente virtual (`venv\`).
3. Instala dependências e o servidor WSGI de alta performance **Waitress**.
4. Gera o arquivo `.env` seguro.
5. Inicializa o banco limpo e cadastra o Administrador.
6. Cria o executável de produção `iniciar_servidor.bat`.

Para rodar o servidor em produção no Windows:
- Execute `iniciar_servidor.bat` (escutando na porta 5000 com multi-threading).

---

## 3. Gestão do Administrador Inicial e Banco Limpo

O sistema utiliza banco de dados SQLite (`database.db`). Na primeira instalação, o banco é criado do zero.

Para gerenciar o Administrador Mestre a qualquer momento:
- **Modo Interativo (Recomendado):**
  ```bash
  python init_admin.py
  ```
- **Modo Padrão Provisório:**
  ```bash
  python init_admin.py --default
  ```
  *(Cria o usuário `admin` com a senha `admin123`. Deve ser alterada imediatamente no primeiro login!)*
- **Modo Automatizado (Scripts / CI):**
  ```bash
  python init_admin.py --user gestor --password 'SenhaForte#2026' --nome 'Gestor Cantina' --email gestor@escola.edu.br
  ```

---

## 4. Guia Completo para Liberação na Internet

Para que estudantes e funcionários acessem o sistema de fora da escola (de suas casas ou redes móveis) e para que a câmera do celular funcione no leitor de QR Code, siga os passos abaixo:

```
[ Usuário / Celular ]
        │  HTTPS (Porta 443)
        ▼
[ Roteador / Firewall da Escola ] (Port Forwarding 80/443 -> IP Interno do Servidor)
        │
        ▼
[ Nginx (Proxy Reverso + SSL Let's Encrypt) ] (Porta 80 e 443)
        │  HTTP Local (127.0.0.1:5000)
        ▼
[ Gunicorn / Waitress (Aplicação Cantina) ]
```

### 4.1 Passo 1: Domínio (DNS) ou IP Fixo
1. **Domínio Próprio:** Crie um apontamento DNS do tipo `A` apontando seu subdomínio (ex: `cantina.escola.edu.br`) para o IP Público da escola.
2. **IP Dinâmico:** Se a escola não possuir IP fixo, configure um serviço DDNS gratuito como [No-IP](https://www.noip.com/) ou [DuckDNS](https://www.duckdns.org/).

### 4.2 Passo 2: Redirecionamento de Portas no Roteador (Port Forwarding / NAT)
No painel do roteador de borda da escola, redirecione o tráfego externo para o IP local do servidor (ex: `192.168.1.100`):
- **Porta Externa 80 (TCP)** ➔ IP Interno `192.168.1.100` : Porta `80`
- **Porta Externa 443 (TCP)** ➔ IP Interno `192.168.1.100` : Porta `443`

> [!IMPORTANT]
> **Por que o HTTPS (Porta 443) é Mandatório?**
> As políticas de segurança dos navegadores modernos (Google Chrome, Safari iOS, Edge) **bloqueiam o uso da câmera do celular** (`navigator.mediaDevices.getUserMedia`) caso o site não seja acessado via HTTPS com certificado válido. Sem HTTPS, o leitor de QR Code para confirmação de refeições não funcionará nos celulares!

### 4.3 Passo 3: Configuração do Nginx (Proxy Reverso)
O script de instalação gera o arquivo `nginx_almoco.conf`.
1. Copie o arquivo para o Nginx:
   ```bash
   sudo cp nginx_almoco.conf /etc/nginx/sites-available/almoco-estudantil.conf
   ```
2. Edite e informe o domínio configurado:
   ```bash
   sudo nano /etc/nginx/sites-available/almoco-estudantil.conf
   # Altere 'cantina.escola.edu.br' pelo seu domínio real
   ```
3. Ative a configuração e valide a sintaxe:
   ```bash
   sudo ln -s /etc/nginx/sites-available/almoco-estudantil.conf /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

### 4.4 Passo 4: Emissão do Certificado SSL Gratuito (Certbot)
Com as portas 80 e 443 abertas e o DNS propagado:
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d cantina.escola.edu.br
```
O Certbot configurará o certificado automaticamente e ativará a renovação automática periódica.

---

## 5. Alternativa sem Abrir Portas no Roteador: Cloudflare Tunnel

Se a rede da instituição estiver sob **CGNAT** (sem IP público acessível) ou possuir bloqueios estritos de firewall:
1. Crie uma conta gratuita na [Cloudflare](https://dash.cloudflare.com/) e aponte seu domínio para lá.
2. Instale o conector `cloudflared` no servidor:
   ```bash
   curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared.deb
   ```
3. Crie o túnel apontando diretamente para `http://localhost:5000`.
- **Vantagens:** Não precisa abrir portas no roteador, não precisa configurar NAT e o certificado SSL é fornecido automaticamente pela Cloudflare.

---

## 6. Rotina de Backup do Banco de Dados

O banco de dados SQLite fica em um único arquivo: `database.db`.
Para realizar o backup seguro sem parar a aplicação, você pode usar o comando online do SQLite:
```bash
sqlite3 database.db ".backup 'backup_cantina_$(date +%Y%m%d_%H%M%S).db'"
```
Recomenda-se agendar uma tarefa diária no `cron` (Linux) ou no `Agendador de Tarefas` (Windows) para enviar a cópia para um drive externo ou nuvem institucional.


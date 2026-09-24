# Guia de Implantação (Deployment) - Servidor de Produção

Este guia descreve como subir a aplicação em um servidor oficial de forma segura e estável.

## 1. Requisitos do Sistema
- Servidor: Linux (**Ubuntu 22.04+**) ou Windows Pro.
- Python: **3.10 ou superior**.
- Porta: **5000** (padrão) ou **80/443**.

---

## 2. Instalação (Linux/Windows)

### 2.1 Preparar Ambiente
1. Clone o repositório no servidor.
2. Crie o ambiente virtual:
   ```bash
   python -m venv venv
   ```
3. Ative o ambiente:
   - Linux: `source venv/bin/activate`
   - Windows: `.\venv\Scripts\activate`

4. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   pip install gunicorn  # Para Linux
   pip install waitress  # Para Windows
   ```

5. **CRIAÇÃO DO ADMINISTRADOR (Obrigatório)**
   O sistema não possui senha padrão por segurança. Para criar sua primeira conta de acesso mestre, execute o script interativo:
   ```bash
   python init_admin.py
   ```
   Siga as instruções na tela para definir seu **Usuário** e **Senha**.

---

## 3. Rodando em Produção (Script de Inicialização)

### Opção A: Servidor Linux (Gunicorn + Systemd) - RECOMENDADO
1. Crie um arquivo de serviço: `/etc/systemd/system/cantina.service`
2. Adicione o conteúdo:
   ```ini
   [Unit]
   Description=Gunicorn instance to serve Cantina App
   After=network.target

   [Service]
   User=www-data
   Group=www-data
   WorkingDirectory=/var/www/almoco-estudantil
   Environment="PATH=/var/www/almoco-estudantil/venv/bin"
   ExecStart=/var/www/almoco-estudantil/venv/bin/gunicorn --workers 3 --bind 0.0.0.0:5000 app:app

   [Install]
   WantedBy=multi-user.target
   ```
3. Inicie o serviço:
   ```bash
   sudo systemctl start cantina
   sudo systemctl enable cantina
   ```

### Opção B: Servidor Windows (Waitress)
Para rodar no Windows de forma estável, crie um arquivo `run_prod.py`:
```python
from waitress import serve
from app import app

if __name__ == "__main__":
    print("Servidor Cantina Iniciado na porta 5000...")
    serve(app, host='0.0.0.0', port=5000)
```
Rode com python: `python run_prod.py`.

---

## 4. Segurança e HTTPS

### 4.1 SSL (HTTPS)
É **obrigatório** usar HTTPS para que a câmera funcione no celular.
- **Opção 1:** Use um Proxy Reverso como **Nginx** com Certbot (Let's Encrypt).
- **Opção 2:** Configure o Nginx para redirecionar o tráfego da porta 80 para a 5000.

### 4.2 Firewall
Abra as portas necessárias:
```bash
sudo ufw allow 5000
sudo ufw allow 80
sudo ufw allow 443
```

---

## 5. Banco de Dados (SQLite)
O banco de dados é um arquivo único `database.db`. 
**DICA:** Faça backup diário deste arquivo enviando-o para uma nuvem ou outro disco.

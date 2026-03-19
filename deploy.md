# Guia Completo: Como Colocar o seu Bot no Ar (Deploy)

Este documento foi escrito para iniciantes. Se você nunca programou, não se preocupe! Aqui vamos descrever o passo a passo para tirar o seu projeto do seu computador e colocá-lo rodando 24 horas por dia, 7 dias por semana, de forma automática e gratuita (ou quase) na nuvem.

Nossa arquitetura de entrega (Deploy) funciona assim:
**Seu Computador** ➡️ envia o código para o **GitHub** ➡️ que avisa o **Fly.io** para rodar o Bot.

---

## 1. Enviando o seu Código para o GitHub

O **GitHub** funciona como um "Google Drive" para programadores. É lá que o código do projeto fica guardado com segurança. E o **Git** é o programa no seu computador que sabe enviar seus arquivos pra lá.

### Passo 1.1: Criar o Repositório no GitHub
1. Crie uma conta no site [github.com](https://github.com/).
2. Na página principal logada, clique no botão verde **"New"** (Novo) no canto superior esquerdo para criar um novo "Repository" (Repositório).
3. Dê um nome ao repositório (ex: `meu-telegram-bot`), deixe como **Public** ou **Private** (Privado é melhor para esconder senhas), desmarque opções de adicionar arquivos `README` e clique em **Create repository**.
4. A tela seguinte mostrará um link do seu repositório. Ele será parecido com: `https://github.com/SeuUsuario/meu-telegram-bot.git`. Guarde esse link!

### Passo 1.2: Subindo o Código do seu PC
Abra o terminal (ou prompt de comando) na pasta onde está o código fonte no seu computador (`C:\Sua\Pasta\Do\Bot`) e digite, linha por linha (apertando ENTER após cada uma):

```bash
# 1. Avisa que essa pasta agora é um projeto gerenciado pelo Git
git init

# 2. Prepara todos os seus arquivos (o ponto significa 'todos') para serem enviados
git add .

# 3. Empacota os arquivos com uma mensagem descrevendo a versão
git commit -m "Versão inicial do meu bot"

# 4. Muda o nome da linha principal de desenvolvimento para 'main'
git branch -M main

# 5. Avisa ao computador qual é a URL lá do GitHub que vai receber tudo
git remote add origin https://github.com/SeuUsuario/meu-telegram-bot.git

# 6. Finalmente, empurra os arquivos para o GitHub!
git push -u origin main
```

Sempre que você mudar/editar o código e quiser mandar a nova versão, repita apenas os passos 2, 3 e 6:
`git add .` ➡️ `git commit -m "Nova melhoria"` ➡️ `git push`.

---

## 2. A "Receita do Bolo" (O arquivo Dockerfile)

O Fly.io (servidor onde rodaremos o Bot) usa máquinas em branco. Ele precisa saber quais arquivos baixar e como instalar o seu projeto. Fazemos isso criando um arquivo chamado exatamente **`Dockerfile`** (sem ponto txt nem nada).

Aqui está o que esse arquivo deve conter (e que você pode copiar no seu projeto base):

```dockerfile
# 1. Pega um "computador" virtual que já tem Python 3.10 instalado
FROM python:3.10-slim

# 2. Entra numa pasta chamada /app dentro desse computador
WORKDIR /app

# 3. Copia apenas o arquivo da lista de dependências
COPY requirements.txt .

# 4. Instala os pacotes necessários (como python-telegram-bot, etc)
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copia todo o resto do seu código pro computador virtual
COPY . .

# 6. Informa ao servidor como iniciar o seu projeto
CMD ["python", "main.py"]
```
*Dica:* Todo o processo do Dockerfile e instalação garante que o seu aplicativo vai funcionar em qualquer computador ou servidor do mundo sem dar falta de programas.

---

## 3. Preparando a Casa (Fly.io e `fly.toml`)

O **Fly.io** é a plataforma de servidor. É ele quem vai ler nosso `Dockerfile`, rodar o programa e abrigar nosso Bot para sempre.

### Obtendo o Fly.io
1. Crie uma conta no site [fly.io](https://fly.io/).
2. No seu terminal de comando no PC, instale a ferramenta do Fly. Dependendo do seu sistema, o comando varia (se for Windows, abra o PowerShell):
   ```powershell
   pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"
   ```
3. Digite `fly auth login` para conectar seu terminal com o site.

### O Arquivo `fly.toml`
Ao invés de clicar num site para escolher processador ou memória, nós descrevemos isso no arquivo **`fly.toml`**. 

**ATENÇÃO MUITO IMPORTANTE:** A maioria dos aplicativos web só "trabalha" e reage se alguém visitar a página da internet. O Fly.io, para poupar dinheiro, *desliga* a máquina virtual (`auto_stop_machines = 'stop'`) caso ele veja que ninguém acessa o servidor via navegador web/HTTP. 
Porém, o nosso **Bot de Telegram** faz o trajeto oposto: ele quem puxa (via long-polling) as mensagens da internet periodicamente, sem ser visitado. Se o Fly tentar ser espertinho e desligá-lo por falta de visitas HTTP, o Bot irá dormir para sempre. 

Por isso o `fly.toml` DEVE garantir que a máquina rode sem parar configurando `min_machines_running = 1` e `auto_stop_machines = 'off'`:

```toml
app = 'nome-do-seu-bot'
primary_region = 'iad' # Escolha regiões que você prefira, GRU é brasil, IAD estados unidos.

[build]

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = 'off'   # Mantenha DESLIGADO o recurso de dormir
  auto_start_machines = true
  min_machines_running = 1     # TEM que ser 1 para que o bot não vá dormir nunca
  processes = ['app']

[[vm]]
  memory = '1gb'
  cpu_kind = 'shared'
  cpus = 1
```

---

## 4. A Mágica Final: Automação Total (Deploy Automático no GitHub Actions)

Não queremos ter que digitar `fly deploy` toda hora. O melhor dos mundos é: atualizar algo no arquivo, dar um `git push` pro GitHub, e deixar o próprio GitHub cuidar de instalar as últimas melhorias no servidor Fly.io pra gente automaticamente!

### 4.1 O Segredo do Fly
O GitHub precisará da "chave da casa" do seu Fly.io para entrar lá e atualizar tudo.
No seu terminal do PC local, execute:
```bash
fly tokens create deploy -x 999999h
```
*Ele exibirá na tela uma **senha super longa**. Copie tudo.*

### 4.2 Repassando a Chave para o GitHub
Vá até a tela do seu repositório no Github (Pelo navegador de internet).
1. Clique em **Settings**.
2. No menu da esquerda, abra **Secrets and variables** e depois **Actions**.
3. Clique em **New repository secret**.
4. No nome (Name) insira precisamente: `FLY_API_TOKEN`
5. Em (Secret) cole a senha longa do passo anterior e clique para salvar.

### 4.3 O Arquivo `fly.yml`
No seu projeto local do computador, você precisa criar uma estrutura específica de pastas e um novo arquivo. 
A pasta *TEM QUE SER*: `.github/workflows/` (atenção para o ponto!) e o arquivo dentro dela se chamará `fly.yml`. O caminho final é:
`[SuaPastaDoProjeto] \ .github \ workflows \ fly.yml`

Dentro do `fly.yml` informe que "No momento do PUSH na branch main", ele deve rodar o instalador:
```yaml
name: Deploy to Fly.io

on:
  push:
    branches:
      - main
      
jobs:
  deploy:
    name: Deploy Telegram Assistant
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Flyctl
        uses: superfly/flyctl-actions/setup-flyctl@master

      - name: Deploy to Fly.io
        run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

## Resumo e Conclusão!
Pronto. A partir desse momento você tem um produto em escala real de software profissional.

O seu dia-a-dia de manutenção será resumido a:
1. No seu PC local, edite o código (`main.py`, `requirements.txt`, etc).
2. Vá no terminal e lance as mudanças:
   `git add .`
   `git commit -m "Corrigi o erro X"`
   `git push`
3. Abordagem *Hands-off*: O GitHub vai ver a mudança, vai usar a senha salva secretamente (`FLY_API_TOKEN`), ler as instruções do `Dockerfile` e do `fly.toml` e subir o seu bot atualizado diretamente para a nuvem sem você mover uma palha extra!

Divirta-se programando seu novo Assistente!

# Use a imagem base oficial do Python
FROM python:3.10-slim

# Define o diretório de trabalho dentro do contêiner
WORKDIR /app

# Copia os arquivos de requisitos primeiro para aproveitar o cache do Docker
COPY requirements.txt .

# Instala as dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do projeto para o contêiner
COPY . .

# Expõe uma porta (opcional para Telegram bots em polling, mas útil para o Fly)
EXPOSE 8080

# Comando para rodar a aplicação
CMD ["python", "main.py"]

# BRAIN Assistant - Telegram Bot

Este bot é um assistente pessoal inteligente integrado ao Google Sheets, Google Calendar e Gemini AI.

## Funcionalidades Principais:

### 1. Gestão de Gastos (Financeiro)
- **Salvar Gastos:** "Gastei 50 reais com gasosa" ou "Paguei 150 no mercado hoje".
- **Consulta de Totais:** "Quanto gastei com mercado este mês?" ou "Qual o total de gastos de Março?".
- **Remover Gastos:** "Excluir o gasto de gasolina" ou "Estornar último gasto".
- **Limpar Tudo:** "Limpar planilha de gastos" (mantém apenas o cabeçalho).

### 2. Agenda Google (Calendar)
- **Marcar Compromissos:** "Agendar reunião com o Time amanhã às 14h".
- **Ver Agenda:** "Quais compromissos tenho hoje?" ou "Ver agenda da próxima semana".
- **Remover Compromisso:** "Apagar reunião de amanhã".
- **Verificação de Conflitos:** O bot avisa se já existir algo no horário e pede confirmação antes de agendar.

### 3. Lista de Compras
- **Adicionar Itens:** "Colocar leite, pão e café na lista de compras".
- **Ver Lista:** "O que tem na lista de compras?".
- **Remover Item:** "Tirar maçã da lista".
- **Limpar Lista:** "Limpar lista de compras".

### 4. Pauta de Reunião (Novo!)
- **Adicionar Assuntos:** "Adicionar na pauta de amanhã: Revisão de custos e Alinhamento".
- **Ver Pauta:** "Ver pauta de amanhã" ou "Qual a pauta de hoje?".
- **Remover Assunto:** "Remover assunto 'Revisão' da pauta".
- **Tratamento de Ambiguidade:** Se houver vários temas parecidos, o bot pergunta qual você deseja excluir.

### 5. Lembretes Inteligentes
- **Criar Lembretes:** "Me lembre de tirar o bolo do forno em 30 minutos" ou "Me avise de ligar para o suporte às 15h".
- **Notificações:** O bot envia uma mensagem automática no horário programado.

### 6. Consultas de Energia
- **Mercado Livre de Energia:** "Qual o preço da energia hoje?" (Busca dados de PLD e preços de mercado).

### 7. Interação Avançada
- **Comandos de Voz:** O bot processa áudios e interpreta os pedidos usando a inteligência artificial do Gemini.
- **Interpretação Natural:** Consegue entender gírias, datas relativas (hoje, amanhã, próxima terça) e múltiplos comandos em uma mesma frase.
- **Fallback Local:** Funciona com comandos básicos mesmo se a API do Gemini estiver fora do ar.

## Configuração:
- Requer arquivo `.env` com tokens e IDs das planilhas/calendário.
- Requer `credentials.json` para acesso às APIs do Google.

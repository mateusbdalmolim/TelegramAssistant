import logging
import os
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler

from services.gemini_service import interpret_message
from services.google_service import GoogleService
from services.reminder_service import ReminderService
from services.energy_service import EnergyService

# Configuração de Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

load_dotenv()
from dotenv import dotenv_values
dotenv_config = dotenv_values(".env")

# Inicialização de Serviços Globais
spreadsheet_id = os.getenv("SPREADSHEET_ID") or dotenv_config.get("SPREADSHEET_ID")
calendar_id = os.getenv("CALENDAR_ID") or dotenv_config.get("CALENDAR_ID") or "primary"
google_service = None
reminder_service = None

if spreadsheet_id:
    print(f"   [OK] Iniciando GoogleService com Calendar ID: {calendar_id}")
    google_service = GoogleService(spreadsheet_id, calendar_id)
else:
    print("AVISO: SPREADSHEET_ID nao configurado.")

energy_service = EnergyService()

async def ensure_reminder_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Garante que o serviço de lembretes esteja rodando para o chat atual."""
    global reminder_service
    if reminder_service is None and update.effective_chat:
        reminder_min = os.getenv("REMINDER_MINUTES", "60")
        reminder_service = ReminderService(google_service, context.bot, update.effective_chat.id, reminder_min)
        reminder_service.loop = asyncio.get_running_loop()
        reminder_service.start()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde ao comando /start."""
    await update.message.reply_text(
        "Olá! Eu sou o seu assistente pessoal **BRAIN** versão Telegram.\n\n"
        "Posso te ajudar a salvar gastos, marcar reuniões e criar lembretes.\n"
        "Basta me enviar uma mensagem!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Interpreta texto e executa o comando."""
    text = update.message.text
    if not text: return
    print(f"[MSG] Recebida: '{text}'")
    
    text_lower = text.lower().strip()
    
    # 1. VERIFICAÇÃO DE ESTADO (Sim/Não para conflitos)
    if text_lower in ["sim", "pode marcar", "confirmar", "com certeza", "quero", "pode", "manda ver", "agende"]:
        pending = context.user_data.pop("pending_appointment", None)
        if pending:
            title = pending.get("title")
            time_iso = pending.get("time_iso")
            if google_service and google_service.add_event(title, time_iso):
                await update.message.reply_text(f"✅ *Evento Agendado mesmo com conflito!*\n\nEvento: {title}\nData: {time_iso}")
            else:
                await update.message.reply_text("[!] Não consegui agendar agora.")
            return

    if text_lower in ["não", "nao", "cancelar", "melhor não", "deixa pra lá", "não agendar"]:
        pending = context.user_data.pop("pending_appointment", None)
        context.user_data.pop("pending_agenda_delete", None) # Limpa outros pendentes também
        if pending:
            await update.message.reply_text("❌ *Ok!* O compromisso não foi agendado.")
            return

    # 1.1 VERIFICAÇÃO DE ESCOLHA NUMÉRICA (Agenda Delete)
    if 'pending_agenda_delete' in context.user_data:
        pending = context.user_data['pending_agenda_delete']
        matches = pending.get("matches", [])
        
        # Tenta encontrar um número na mensagem
        import re
        num_match = re.search(r'\b(\d+)\b', text_lower)
        choice_idx = -1
        
        if num_match:
            choice_idx = int(num_match.group(1)) - 1
        else:
            # Tenta encontrar pelo nome (se o usuário repetiu o nome do item)
            for i, m in enumerate(matches):
                if text_lower in m['topic'].lower():
                    choice_idx = i
                    break
        
        if 0 <= choice_idx < len(matches):
            item_to_delete = matches[choice_idx]
            if google_service and google_service.delete_agenda_item_by_row(item_to_delete['row']):
                context.user_data.pop("pending_agenda_delete")
                await update.message.reply_text(f"🗑️ *'{item_to_delete['topic']}'* removido da pauta!")
            else:
                await update.message.reply_text("[!] Não consegui remover o item agora.")
            return
        elif "cancelar" in text_lower or "esquecer" in text_lower:
            context.user_data.pop("pending_agenda_delete")
            await update.message.reply_text("❌ *Operação cancelada.*")
            return
        else:
            await update.message.reply_text("🤔 Não entendi qual você quer excluir. Por favor, diga o *número* da opção ou o *nome do item* (ou diga 'cancelar').")
            return

    # 2. INTERPRETAÇÃO (Gemini)
    analysis = interpret_message(text)
    await handle_execution(update, context, analysis)

async def handle_execution(update: Update, context: ContextTypes.DEFAULT_TYPE, analysis: dict):
    """Agrupa a lógica de execução para ser usada por texto ou voz."""
    response_msg = ""
    # 3. Execução do comando
    if not analysis or not isinstance(analysis, dict):
        logging.error(f"Falha na análise da mensagem: {analysis}")
        await update.message.reply_text("🤖 [!] *Erro de Interpretação:* Não consegui entender seu pedido. Por favor, tente falar de outra forma via texto.")
        return

    if analysis.get("type") == "expense":
        item = analysis.get('item')
        val = analysis.get('value')
        cat = analysis.get('category') or "Geral"
        date = analysis.get('date') or datetime.now().strftime("%d/%m/%Y")
        
        saved = False
        if google_service:
            saved = google_service.add_expense(date, item, val, cat)
        
        if saved:
            response_msg = f"✅ *Gasto Salvo!*\n\n📅 Data: {date}\n🛍️ Item: {item}\n💰 Valor: R$ {val}\n📂 Categoria: {cat}"
        else:
            response_msg = f"💰 *Gasto Detectado*\nItem: {item}\nValor: R$ {val}\n\n[!] _Não consegui salvar na planilha._"

    # 2. EXCLUSÃO (Delete)
    elif analysis.get("type") == "delete":
        target = analysis.get("target", "").lower()
        content_type = analysis.get("content_type", "expense")
        date = analysis.get("date")

        # Limpeza de ruído temporal se o Gemini falhou em extrair a data
        if not date:
            if "amanhã" in target:
                date = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
            elif "hoje" in target:
                date = datetime.now().strftime("%d/%m/%Y")
        
        # Remove palavras de ligação e tempo do alvo para melhorar a busca de forma segura (palavras inteiras)
        import re
        for word in ["amanhã", "hoje", "às", "de", "da", "na", "no", "com", "do"]:
            target = re.sub(rf'\b{word}\b', '', target, flags=re.IGNORECASE).strip()
            target = re.sub(r'\s+', ' ', target).strip() # Limpa espaços duplos

        # Se o alvo parecer compromisso ou lista de compras, muda o tipo
        if any(word in target for word in ["reunião", "compromisso", "evento", "consulta"]) or content_type == "appointment":
            content_type = "appointment"
            if target in ["reunião", "compromisso", "evento", "consulta"]:
                target = ""
        elif any(word in target for word in ["lista", "compras", "carrinho"]) or content_type == "shopping_list":
            content_type = "shopping_list"
            import re
            for word in ["lista", "compras", "carrinho", "da", "do", "de"]:
                target = re.sub(rf'\b{word}\b', '', target, flags=re.IGNORECASE).strip()
        elif any(word in target for word in ["pauta", "assunto"]) or content_type == "agenda":
            content_type = "agenda"
            import re
            for word in ["pauta", "assunto", "da", "do", "de", "reunião"]:
                target = re.sub(rf'\b{word}\b', '', target, flags=re.IGNORECASE).strip()

        if content_type == "appointment":
            target_date = date # Usa a data calculada acima (extraída ou inferida de 'amanhã'/'hoje')
            if google_service and google_service.delete_event_by_title(target, target_date):
                date_info = f" de {target_date}" if target_date else ""
                event_name = f"'{target.capitalize()}'" if target else "o único compromisso da data"
                response_msg = f"🗑️ *Compromisso {event_name}{date_info} removido!*"
            else:
                response_msg = f"[!] Não encontrei nenhum compromisso para apagar."
        elif content_type == "shopping_list":
            if google_service and google_service.delete_shopping_item(target):
                response_msg = f"🛒 *'{target.capitalize()}'* removido da sua lista de compras!"
            else:
                response_msg = f"[!] Não encontrei o item '{target}' na sua lista de compras."
        elif content_type == "agenda":
            # Normalização de data para busca
            if date and "-" in date:
                try: date = datetime.strptime(date, "%Y-%m-%d").strftime("%d/%m/%Y")
                except: pass
            
            matches = google_service.find_agenda_matches(target, date) if google_service else []
            
            if not matches:
                date_info = f" do dia {date}" if date else ""
                response_msg = f"[!] Não encontrei o assunto '{target}' na pauta{date_info}."
            elif len(matches) == 1:
                item = matches[0]
                if google_service.delete_agenda_item_by_row(item['row']):
                    response_msg = f"📝 *'{item['topic']}'* removido da pauta de reunião!"
                else:
                    response_msg = "[!] Erro ao remover assunto da pauta."
            else:
                # Múltiplos matches: Pergunta ao usuário
                context.user_data['pending_agenda_delete'] = {"matches": matches}
                options_str = "\n".join([f"{i+1}️⃣ {m['topic']}" + (f" ({m['date']})" if m['date'] else "") for i, m in enumerate(matches)])
                response_msg = f"🤔 Encontrei mais de um item na pauta que pode ser o que você quer excluir:\n\n{options_str}\n\n*Qual deles você deseja apagar?* (Diga o número ou o nome)"
        elif target:
            target_date = analysis.get("date")
            if google_service and google_service.delete_expense_by_item(target, target_date):
                date_info = f" de {target_date}" if target_date else ""
                response_msg = f"🗑️ *Gasto '{target.capitalize()}'{date_info} removido!*"
            else:
                response_msg = f"[!] Não encontrei esse gasto para apagar."
        else:
            if google_service and google_service.delete_last_expense():
                response_msg = "🗑️ *Último gasto estornado!*"
            else:
                response_msg = "[!] Não encontrei gastos para apagar."

    # 3. AGENDAMENTO (Appointment)
    elif analysis.get("type") == "appointment":
        title = analysis.get("title")
        time_iso = analysis.get("time")
        
        if title and time_iso:
            # Verifica se já há compromisso no horário
            conflict = google_service.check_conflict(time_iso) if google_service else None
            
            if conflict:
                conf_summary = conflict.get('summary', 'Compromisso sem título')
                # SALVA O COMPROMISSO PENDENTE PARA CONFIRMAÇÃO
                context.user_data['pending_appointment'] = {"title": title, "time_iso": time_iso}
                response_msg = f"⚠️ *Conflito de Agenda!*\n\nJá existe este compromisso no mesmo horário:\n📌 *{conf_summary}*\n\nDeseja realizar o agendamento mesmo assim?"
            elif google_service and google_service.add_event(title, time_iso):
                try:
                    dt = datetime.fromisoformat(time_iso.replace('Z', '+00:00'))
                    formatted_time = dt.strftime("%d/%m/%Y às %H:%M")
                    response_msg = f"📅 *Agendado com Sucesso!*\n\nEvento: {title}\n📅 Data: {formatted_time}"
                except:
                    response_msg = f"📅 *Agendado com Sucesso!*\n\nEvento: {title}\n📅 Data: {time_iso}"
            else:
                response_msg = "[!] Não consegui marcar na sua agenda."
        else:
            response_msg = "⚠️ Não consegui entender o horário ou o título da reunião."

    # 4. LISTAR (List)
    elif analysis.get("type") == "list":
        period = analysis.get("period", "week")
        text_lower = update.message.text.lower() if update.message and update.message.text else ""
        
        # Se explicitamente pedir mês no texto, garante o período mensal
        if "mês" in text_lower or "mes" in text_lower:
            period = "month"
            
        if period == "month":
            month = analysis.get("month")
            months_map = {
                "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6, 
                "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12
            }
            
            if isinstance(month, str):
                if month.isdigit():
                    month = int(month)
                else:
                    month = months_map.get(month.lower(), datetime.now().month)
            
            if not month:
                # Fallback manual para o mês atual ou detectado no texto
                now = datetime.now()
                month = now.month
                for name, num in months_map.items():
                    if name in text_lower:
                        month = num
                        break
                        
            year = analysis.get("year", datetime.now().year)
            if isinstance(year, str) and year.isdigit(): year = int(year)
            
            events = google_service.get_month_events(month, year) if google_service else []
            months_names = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
            period_label = f"DE {months_names[month-1].upper()} {year}"
        else:
            is_next_week = analysis.get("next", False)
            period_label = "DA PRÓXIMA SEMANA" if is_next_week else "DA SEMANA"
            events = google_service.get_weekly_events(next_week=is_next_week) if google_service else []
        
        if not events:
            response_msg = f"📅 *Sua agenda está livre {period_label.lower()}!*"
        else:
            header = f"📅 *SUA AGENDA {period_label}*\n"
            body = ""
            current_day = ""
            weekdays = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
            
            for event in events:
                start_str = event['start'].get('dateTime', event['start'].get('date'))
                dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                day_str = dt.strftime("%d/%m")
                weekday = weekdays[dt.weekday()]
                
                if day_str != current_day:
                    body += f"\n📌 *{weekday} ({day_str})*\n"
                    current_day = day_str
                
                time_fmt = dt.strftime("%H:%M") if 'dateTime' in event['start'] else "Dia todo"
                summary = event.get('summary', 'Compromisso')
                body += f"  • {time_fmt} - *{summary}*\n"
            
            response_msg = header + body

    # 5. CONSULTA DE TOTAL (Total Query)
    elif analysis.get("type") == "total_query":
        item = analysis.get("item")
        month = analysis.get("month")
        year = analysis.get("year")
        
        total = google_service.get_total_spent(item, month, year) if google_service else 0.0
        item_label = f"com *{item}*" if item else "no total"
        response_msg = f"💰 No período solicitado, você gastou {item_label} um valor de:\n\n*R$ {total:.2f}*"

    # 6. LEMBRETE (Reminder)
    elif analysis.get("type") == "reminder":
        title = analysis.get("title") or "Lembrete"
        delta_min = analysis.get("delta_minutes")
        delta_sec = analysis.get("delta_seconds")
        time_iso = analysis.get("time")
        
        now = datetime.now()
        target_time = None
        
        if delta_sec is not None:
            target_time = now + timedelta(seconds=int(delta_sec))
        elif delta_min is not None:
            target_time = now + timedelta(minutes=int(delta_min))
        elif time_iso:
            try:
                target_time = datetime.fromisoformat(time_iso.replace('Z', '+00:00')).replace(tzinfo=None)
            except:
                target_time = None
        
        if target_time and reminder_service:
            # Garante que o título não seja 'None' string
            if title == "None": title = "Lembrete"
            
            reminder_service.add_reminder(title, target_time)
            fmt_time = target_time.strftime("%H:%M")
            day_str = "hoje" if target_time.date() == now.date() else f"no dia {target_time.strftime('%d/%m')}"
            response_msg = f"✅ *Lembrete Agendado!*\n\n💡 Vou te avisar sobre *'{title}'* às {fmt_time} {day_str}."
        else:
            response_msg = "[!] Não consegui entender o horário do lembrete. Tente dizer algo como 'me lembre de X em 10 minutos'."

    # 7. CONVERSA FIADA (Chatter)
    elif analysis.get("type") == "chatter":
        kind = analysis.get("kind")
        if kind == "greeting":
            response_msg = "Olá! Em que posso ajudar hoje?"
        elif kind == "thanks":
            response_msg = "Por nada! Estou às ordens."

    # 8. LIMPAR TUDO (Clear All)
    elif analysis.get("type") == "clear_all":
        if google_service and google_service.clear_expenses():
            response_msg = "🗑️ *Planilha de Gastos Limpa!*"
        else:
            response_msg = "[!] Não consegui limpar a planilha."

    # 9. LISTA DE COMPRAS
    elif analysis.get("type") == "shopping_list_add":
        item = analysis.get("item")
        if google_service and google_service.add_shopping_item(item):
            response_msg = f"🛒 *'{item}'* adicionado à sua lista de compras!"
        else:
            response_msg = "[!] Não consegui adicionar à lista."
            
    elif analysis.get("type") == "shopping_list_get":
        items = google_service.get_shopping_list() if google_service else []
        if not items:
            response_msg = "🛒 *Sua lista de compras está vazia!*"
        else:
            lista_str = "\n".join([f"• {i}" for i in items])
            response_msg = f"🛒 *SUA LISTA DE COMPRAS:*\n\n{lista_str}"
            
    elif analysis.get("type") == "shopping_list_clear":
        if google_service and google_service.clear_shopping_list():
            response_msg = "🗑️ *Lista de compras limpa com sucesso!*"
        else:
            response_msg = "[!] Não consegui limpar a lista."

    # 10. PAUTA DE REUNIÃO
    elif analysis.get("type") == "agenda_add":
        topic = analysis.get("topic")
        date = analysis.get("date")
        
        # Normaliza data para DD/MM/YYYY
        if date and "-" in date:
            try:
                date = datetime.strptime(date, "%Y-%m-%d").strftime("%d/%m/%Y")
            except: pass

        if google_service and google_service.add_agenda_item(topic, date):
            response_msg = f"📝 *'{topic}'* adicionado à pauta de reunião!"
        else:
            response_msg = "[!] Não consegui adicionar à pauta."
            
    elif analysis.get("type") == "agenda_get":
        date = analysis.get("date")
        
        # Normaliza data para DD/MM/YYYY
        if date and "-" in date:
            try:
                date = datetime.strptime(date, "%Y-%m-%d").strftime("%d/%m/%Y")
            except: pass

        items = google_service.get_agenda(date) if google_service else []
        if not items:
            date_info = f" do dia {date}" if date else ""
            response_msg = f"📝 *A pauta de reunião{date_info} está vazia!*"
        else:
            lista_str = "\n".join([f"• {i['topic']}" + (f" ({i['date']})" if i['date'] else "") for i in items])
            response_msg = f"📝 *PAUTA DE REUNIÃO:*\n\n{lista_str}"
            
    elif analysis.get("type") == "agenda_clear":
        if google_service and google_service.clear_agenda():
            response_msg = "🗑️ *Pauta de reunião limpa com sucesso!*"
        else:
            response_msg = "[!] Não consegui limpar a pauta."

    elif analysis.get("type") == "energy_prices_query":
        print("   [[ENERGIA]] Buscando preços de energia no Mercado Livre...")
        response_msg = energy_service.get_market_prices()

    # Envia Resposta
    if response_msg:
        await update.message.reply_text(response_msg, parse_mode='Markdown')
    elif analysis.get("type") == "unknown":
        await update.message.reply_text("🤖 [!] *IA Ocupada/Sem Cota:* No momento não consegui processar o áudio. Por favor, tente enviar o comando via **texto** (ex: 'gastos hoje', 'excluir reunião amanhã').")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captura áudio, envia para o Gemini e executa o comando."""
    if not update.message.voice:
        return

    # 1. Avisa que está processando
    status_msg = await update.message.reply_text("[AUDIO] *Ouvindo...*")

    # Garante que o serviço de lembretes esteja ativo
    await ensure_reminder_service(update, context)

    try:
        # 2. Faz o download do arquivo de áudio
        voice_file = await update.message.voice.get_file()
        os.makedirs("temp_audio", exist_ok=True)
        file_path = f"temp_audio/voice_{update.message.message_id}.ogg"
        await voice_file.download_to_drive(file_path)

        # 3. Envia para o Gemini interpretar
        from services.gemini_service import interpret_audio
        analysis = interpret_audio(file_path)

        # 4. Remove o arquivo temporário
        if os.path.exists(file_path):
            os.remove(file_path)

        # 5. Processa a intenção igual ao texto
        await handle_execution(update, context, analysis)
        
        # Opcional: Remover mensagem de status
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status_msg.message_id)

    except Exception as e:
        error_msg = str(e)
        logging.error(f"Erro no processamento de voz: {error_msg}")
        # Reporta o erro real para facilitar o diagnóstico
        await status_msg.edit_text(f"[!] Erro no processamento: {error_msg}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logging.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        text = "🤖 [!] *Erro Interno:* Ocorreu um problema ao processar seu comando. Desculpe por isso!"
        await update.effective_message.reply_text(text, parse_mode='Markdown')

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERRO: TELEGRAM_BOT_TOKEN não encontrado no .env")
        return

    application = ApplicationBuilder().token(token).build()
    
    # Handlers
    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start))
    
    # Handler especial para capturar o chat_id e iniciar lembretes
    async def wrapped_handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await ensure_reminder_service(update, context)
        await handle_message(update, context)

    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), wrapped_handle_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("Bot do Telegram Iniciado!")
    
    # run_polling é bloqueante e gerencia o loop internamente
    application.run_polling()

if __name__ == '__main__':
    main()

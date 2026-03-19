import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

class ReminderService:
    def __init__(self, google_service, bot, chat_id, reminder_minutes=60):
        self.google_service = google_service
        self.bot = bot
        self.chat_id = chat_id
        self.reminder_minutes = int(reminder_minutes)
        self.scheduler = BackgroundScheduler()
        self.sent_reminders = set() 
        self.loop = asyncio.get_event_loop()

    def _send_msg_sync(self, text):
        """Função auxiliar para enviar mensagem de forma assíncrona a partir de código síncrono."""
        asyncio.run_coroutine_threadsafe(self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode='Markdown'), self.loop)

    def check_calendar(self):
        """Busca eventos próximos e envia alerta se estiverem no intervalo de tempo."""
        try:
            if not self.google_service.service_calendar:
                return

            now = datetime.now()
            limit = now + timedelta(minutes=self.reminder_minutes)
            
            time_min = now.strftime("%Y-%m-%dT%H:%M:%S-03:00")
            events_result = self.google_service.service_calendar.events().list(
                calendarId=self.google_service.calendar_id,
                timeMin=time_min,
                maxResults=10,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            for event in events:
                event_id = event['id']
                if event_id in self.sent_reminders:
                    continue
                
                start_str = event['start'].get('dateTime', event['start'].get('date'))
                if not start_str: continue
                
                start_time = datetime.fromisoformat(start_str.replace('Z', '+00:00')).replace(tzinfo=None)
                time_diff = (start_time - now).total_seconds() / 60
                
                if 0 <= time_diff <= self.reminder_minutes:
                    summary = event.get('summary', 'Compromisso sem título')
                    time_fmt = start_time.strftime("%H:%M")
                    
                    msg = f"🔔 *LEMBRETE DE REUNIÃO*\n\n📅 *{summary}*\n⏰ Começa às {time_fmt} (em {int(time_diff)} minutos)"
                    
                    self._send_msg_sync(msg)
                    self.sent_reminders.add(event_id)
                    print(f"   [INFO] Lembrete enviado para: {summary}")
                    
            if len(self.sent_reminders) > 100:
                self.sent_reminders.clear()

        except Exception as e:
            print(f"   [ERRO] Ao checar lembretes: {e}")

    def add_reminder(self, title, run_time):
        """Agenda um lembrete pontual."""
        try:
            if isinstance(run_time, str):
                run_time = datetime.fromisoformat(run_time.replace('Z', '+00:00')).replace(tzinfo=None)
            
            job_id = f"reminder_{title}_{run_time.strftime('%H%M%S')}"
            
            def trigger_reminder():
                print(f"   [INFO] Disparando lembrete agendado: {title}")
                msg = f"🔔 *LEMBRETE AGENDADO*\n\n💡 Não esqueça: *{title}*"
                self._send_msg_sync(msg)

            self.scheduler.add_job(trigger_reminder, 'date', run_date=run_time, id=job_id)
            print(f"   [INFO] Lembrete '{title}' agendado para {run_time.strftime('%H:%M')}")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao agendar lembrete: {e}")
            return False

    def send_daily_briefing(self):
        """Resume todos os compromissos do dia atual (Calendar + Pauta)."""
        try:
            if not self.google_service.service_sheets: return
            
            now = datetime.now()
            date_str = now.strftime("%d/%m/%Y")
            
            # 1. Busca eventos do Google Calendar
            events = []
            if self.google_service.service_calendar:
                time_min = now.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%S-03:00")
                time_max = now.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%dT%H:%M:%S-03:00")
                
                events_result = self.google_service.service_calendar.events().list(
                    calendarId=self.google_service.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                events = events_result.get('items', [])
            
            # 2. Busca itens da Pauta de Reunião
            pauta_items = self.google_service.get_agenda(date_str)
            
            if not events and not pauta_items:
                msg = f"☀️ *BOM DIA - {now.strftime('%d/%m')}*\n\nVocê não tem compromissos agendados para hoje. Aproveite o dia para descansar ou focar em projetos! ✨"
                self._send_msg_sync(msg)
                return

            msg = f"☀️ *BOM DIA - {now.strftime('%d/%m')}*\n\nAqui está seu resumo matinal:\n\n"
            
            if events:
                msg += "🗓️ *AGENDA DODIA:*\n"
                for event in events:
                    summary = event.get('summary', 'Compromisso sem título')
                    start_str = event['start'].get('dateTime', event['start'].get('date'))
                    if 'T' in start_str:
                        time_fmt = datetime.fromisoformat(start_str.replace('Z', '+00:00')).strftime("%H:%M")
                        msg += f"• ⏰ *{time_fmt}* - {summary}\n"
                    else:
                        msg += f"• 📅 *Dia Todo* - {summary}\n"
            
            if pauta_items:
                msg += "\n📝 *PAUTA DE REUNIÃO:*\n"
                for item in pauta_items:
                    msg += f"• {item['topic']}\n"
            
            msg += "\nTenha um excelente dia! 🦾🚀"
            self._send_msg_sync(msg)
            print(f"   [INFO] Resumo matinal enviado ({len(events)} eventos, {len(pauta_items)} pautas).")
            
        except Exception as e:
            print(f"   [ERRO] Ao enviar resumo matinal: {e}")

    def start(self):
        """Inicia o agendador."""
        # 1. Checagem de lembretes próximos (a cada 5 min)
        self.scheduler.add_job(self.check_calendar, 'interval', minutes=5)
        
        # 2. Resumo Matinal (Cron: Todos os dias às 07:00)
        self.scheduler.add_job(self.send_daily_briefing, 'cron', hour=7, minute=0)
        
        self.scheduler.start()
        print(f"Serviço de Lembretes ATIVO (Aviso com {self.reminder_minutes} min e Resumo às 07:00)")

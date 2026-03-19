import os.path
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2 import service_account
from datetime import datetime, timedelta

# Escopos necessários para ler e escrever no Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

class GoogleService:
    def __init__(self, spreadsheet_id, calendar_id='primary'):
        self.spreadsheet_id = spreadsheet_id
        self.calendar_id = calendar_id
        self.creds = None
        self.service_sheets = None
        self.service_calendar = None
        self._authenticate()

    def _authenticate(self):
        """Autentica usando a Service Account (credentials.json)."""
        try:
            creds_path = 'credentials.json.json'
            
            # Se o arquivo não existir fisicamente, tenta ler do segredo GOOGLE_CREDENTIALS_JSON (Nuvem/Fly.io)
            if not os.path.exists(creds_path):
                google_creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
                if google_creds_json:
                    with open(creds_path, 'w') as f:
                        f.write(google_creds_json)
                    print("   [INFO] Arquivo credentials.json.json restaurado a partir de variável de ambiente.")

            if os.path.exists(creds_path):
                self.creds = service_account.Credentials.from_service_account_file(
                    creds_path, scopes=SCOPES + ['https://www.googleapis.com/auth/calendar'])
                self.service_sheets = build('sheets', 'v4', credentials=self.creds)
                self.service_calendar = build('calendar', 'v3', credentials=self.creds)
                print("   [OK] Google APIs (Sheets & Calendar): Autenticado com sucesso!")
            else:
                print("   [ERRO] Arquivo 'credentials.json' não encontrado!")
        except Exception as e:
            print(f"   [ERRO] Na autenticação Google: {e}")

    def add_expense(self, date, item, value, category):
        """Adiciona uma linha de despesa na planilha."""
        if not self.service_sheets:
            print("   [!] Serviço Sheets não inicializado.")
            return False

        try:
            # Prepara os dados (Data, Item, Valor, Categoria)
            values = [[date, item, value, category]]
            body = {'values': values}
            
            # Range 'A:D' faz com que ele procure a próxima linha vazia automaticamente
            result = self.service_sheets.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range='A:D',
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            print(f"   [OK] Linha adicionada na planilha!")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao salvar na planilha: {e}")
            return False

    def clear_expenses(self):
        """Limpa todos os dados da planilha de gastos, mantendo apenas o cabeçalho."""
        if not self.service_sheets:
            return False
        try:
            # Range 'A2:D' apaga tudo a partir da segunda linha até o fim
            self.service_sheets.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range='A2:D'
            ).execute()
            print("   [OK] Planilha de gastos limpa (cabeçalho mantido)!")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao limpar planilha: {e}")
            return False
    def delete_last_expense(self):
        """Remove a última linha preenchida na planilha."""
        if not self.service_sheets:
            return False

        try:
            # 1. Descobre qual é a última linha lendo a coluna A
            sheet = self.service_sheets.spreadsheets()
            result = sheet.values().get(
                spreadsheetId=self.spreadsheet_id,
                range='A:A'
            ).execute()
            
            values = result.get('values', [])
            if not values:
                print("   [!] Planilha já está vazia.")
                return False
            
            last_row_index = len(values)
            
            # Não apaga o cabeçalho (linha 1)
            if last_row_index <= 1:
                print("   [!] Não posso apagar o cabeçalho.")
                return False

            # 2. Limpa a última linha
            # Ex: Se last_row_index for 5, range é 'A5:D5'
            batch_update_values_request_body = {
                'ranges': [f'A{last_row_index}:D{last_row_index}']
            }
            
            sheet.values().batchClear(
                spreadsheetId=self.spreadsheet_id,
                body=batch_update_values_request_body
            ).execute()
            
            print(f"   [OK] Linha {last_row_index} removida com sucesso!")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao excluir linha: {e}")
            return False
    def delete_expense_by_item(self, target_name, target_date=None):
        """Busca o item pelo nome (e data opcional) e remove a linha correspondente."""
        if not self.service_sheets or not target_name:
            return False

        try:
            sheet = self.service_sheets.spreadsheets()
            # Lê as colunas A e B (Data e Item)
            result = sheet.values().get(
                spreadsheetId=self.spreadsheet_id,
                range='A:B'
            ).execute()
            
            values = result.get('values', [])
            target_name = target_name.lower().strip()
            
            # Percorre de trás para frente para apagar o mais recente primeiro
            for i in range(len(values) - 1, 0, -1): # Começa do fim, ignora cabeçalho
                row = values[i]
                if len(row) >= 2:
                    current_date = str(row[0]).strip()
                    current_item = str(row[1]).lower().strip()
                    
                    # Verifica se o nome bate
                    name_match = target_name in current_item or current_item in target_name
                    
                    # Verifica se a data bate (se fornecida)
                    date_match = True
                    if target_date:
                        date_match = (target_date == current_date)
                    
                    if name_match and date_match:
                        row_to_delete = i + 1
                        
                        batch_update_values_request_body = {
                            'ranges': [f'A{row_to_delete}:D{row_to_delete}']
                        }
                        sheet.values().batchClear(
                            spreadsheetId=self.spreadsheet_id,
                            body=batch_update_values_request_body
                        ).execute()
                        
                        print(f"   [[OK]] Linha {row_to_delete} ({current_item}) removida com sucesso!")
                        return True
            
            return False
        except Exception as e:
            print(f"   [❌] Erro ao excluir gasto por item: {e}")
            return False

    def get_total_spent(self, item_name=None, month=None, year=None):
        """Retorna a soma total gasta em um item (ou total geral) em um determinado mês/ano."""
        if not self.service_sheets:
            return 0.0

        try:
            now = datetime.now()
            target_month = int(month) if month else now.month
            target_year = int(year) if year else now.year
            
            print(f"   [[BUSCA]] Consultando gastos para: {item_name or 'Tudo'} ({target_month}/{target_year})")
            
            sheet = self.service_sheets.spreadsheets()
            result = sheet.values().get(
                spreadsheetId=self.spreadsheet_id,
                range='A:C' # Data, Item, Valor
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return 0.0

            total = 0.0
            item_search = item_name.lower().strip() if item_name else None
            
            # Detecta se a primeira linha parece ser dado ou cabeçalho
            start_idx = 1
            first_row = values[0]
            if len(first_row) > 0:
                first_val = str(first_row[0]).lower()
                if "data" not in first_val and "/" not in first_val and "-" not in first_val:
                    # Se não tem "data" e não parece uma data, é cabeçalho.
                    # Mas se parece uma data, talvez não tenha cabeçalho.
                    start_idx = 1
                elif "/" in first_val or "-" in first_val:
                    # Parece uma data, vamos processar desde a linha 0
                    start_idx = 0

            for row in values[start_idx:]:
                if len(row) < 3: continue
                
                try:
                    date_raw = str(row[0]).strip()
                    # Tenta diferentes formatos de data comuns em planilhas
                    row_date = None
                    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%m/%d/%Y"]:
                        try:
                            row_date = datetime.strptime(date_raw, fmt)
                            break
                        except: continue
                    
                    if not row_date:
                        # Se falhou o parse básico, tenta pegar apenas o que parece data por regex
                        import re
                        m = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', date_raw)
                        if m:
                            d, m_num, y = m.groups()
                            y = int(y) + 2000 if len(y) == 2 else int(y)
                            row_date = datetime(y, int(m_num), int(d))

                    if not row_date: continue

                    # Filtra por mês e ano
                    if row_date.month == target_month and row_date.year == target_year:
                        row_item = str(row[1]).lower().strip()
                        
                        # Se pediu item específico, filtra por nome
                        if not item_search or (item_search in row_item or row_item in item_search):
                            val_str = str(row[2]).replace('R$', '').replace(' ', '').replace(',', '.').strip()
                            # Remove caracteres não numéricos extras, exceto ponto e sinal
                            val_str = "".join(c for c in val_str if c.isdigit() or c in ".-")
                            if val_str:
                                total += float(val_str)
                except Exception as e:
                    # print(f"Erro ao processar linha {row}: {e}")
                    continue
            
            print(f"   [OK] Total calculado: R$ {total:.2f}")
            return total
        except Exception as e:
            print(f"   [ERRO] Ao calcular total de gastos: {e}")
            return 0.0

    def add_event(self, title, start_time_iso):
        """Cria um evento no Google Calendar."""
        if not self.service_calendar:
            print("   [!] Serviço Calendar não inicializado.")
            return False

        try:
            # Calcula o fim do evento (default 1 hora depois)
            start = datetime.fromisoformat(start_time_iso.replace('Z', '+00:00'))
            end = (start + timedelta(hours=1)).isoformat()

            event = {
                'summary': title,
                'start': {'dateTime': start_time_iso, 'timeZone': 'America/Sao_Paulo'},
                'end': {'dateTime': end, 'timeZone': 'America/Sao_Paulo'},
            }

            event = self.service_calendar.events().insert(calendarId=self.calendar_id, body=event).execute()
            print(f"   [OK] Evento criado: {event.get('htmlLink')}")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao criar evento na agenda: {e}")
            return False

    def get_weekly_events(self, next_week=False):
        """Retorna todos os eventos dos próximos 7 dias (ou da semana cheia seguinte se next_week=True)."""
        if not self.service_calendar:
            return []

        try:
            now_dt = datetime.now()
            
            if next_week:
                days_until_monday = (7 - now_dt.weekday()) % 7
                if days_until_monday == 0: days_until_monday = 7
                start_dt = (now_dt + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0)
                end_dt = start_dt + timedelta(days=7)
            else:
                # Começa do início do dia atual para o usuário ver o que acabou de marcar
                start_dt = now_dt.replace(hour=0, minute=0, second=0)
                end_dt = start_dt + timedelta(days=7)
            
            time_min = start_dt.strftime("%Y-%m-%dT%H:%M:%S-03:00")
            time_max = end_dt.strftime("%Y-%m-%dT%H:%M:%S-03:00")
            
            events_result = self.service_calendar.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            return events_result.get('items', [])
        except Exception as e:
            print(f"   [ERRO] Ao buscar agenda: {e}")
            return []

    def get_month_events(self, month, year):
        """Retorna todos os eventos de um mês específico."""
        if not self.service_calendar:
            return []

        try:
            import calendar
            # Determina o último dia do mês
            last_day = calendar.monthrange(year, month)[1]
            
            start_dt = datetime(year, month, 1, 0, 0, 0)
            end_dt = datetime(year, month, last_day, 23, 59, 59)
            
            time_min = start_dt.strftime("%Y-%m-%dT%H:%M:%S-03:00")
            time_max = end_dt.strftime("%Y-%m-%dT%H:%M:%S-03:00")
            
            print(f"   [[BUSCA]] Buscando agenda de {month}/{year} ({time_min} a {time_max})")

            events_result = self.service_calendar.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            return events_result.get('items', [])
        except Exception as e:
            print(f"   [ERRO] Ao buscar agenda mensal: {e}")
            return []

    def check_conflict(self, start_time_iso):
        """Verifica se há conflitos no calendário do Google analisando sobreposições."""
        if not self.service_calendar:
            return None

        try:
            # Se não tem fuso, assume o de Brasília (-03:00)
            if 'T' in start_time_iso and '+' not in start_time_iso and '-' not in start_time_iso.split('T')[1]:
                start_time_iso += "-03:00"
            
            # Horário solicitado
            req_start = datetime.fromisoformat(start_time_iso.replace('Z', '+00:00'))
            req_end = req_start + timedelta(minutes=59) # Duração padrão de 1h
            
            # Busca todos os eventos do dia para comparar
            t_min = req_start.replace(hour=0, minute=0, second=0).isoformat()
            t_max = req_start.replace(hour=23, minute=59, second=59).isoformat()
            
            print(f"   [BUSCA] Verificando conflitos no ID: {self.calendar_id}")

            events_result = self.service_calendar.events().list(
                calendarId=self.calendar_id,
                timeMin=t_min,
                timeMax=t_max,
                singleEvents=True
            ).execute()
            
            events = events_result.get('items', [])
            for event in events:
                e_start_raw = event['start'].get('dateTime', event['start'].get('date'))
                e_end_raw = event['end'].get('dateTime', event['end'].get('date'))
                
                # Normaliza eventos de dia inteiro
                if len(e_start_raw) == 10: e_start_raw += "T00:00:00-03:00"
                if len(e_end_raw) == 10: e_end_raw += "T23:59:59-03:00"
                
                e_start = datetime.fromisoformat(e_start_raw.replace('Z', '+00:00'))
                e_end = datetime.fromisoformat(e_end_raw.replace('Z', '+00:00'))
                
                # Lógica de Sobreposição: 
                # (StartA < EndB) AND (EndA > StartB)
                if (req_start < e_end) and (req_end > e_start):
                    print(f"   [!] Conflito REAL detectado com: '{event.get('summary', 'S/T')}'")
                    return event
            
            return None
        except Exception as e:
            print(f"   [ERRO] Ao verificar conflito: {e}")
            return None

    def delete_event_by_title(self, title=None, target_date=None):
        """Busca um evento pelo título (e opcionalmente data) e o remove."""
        if not self.service_calendar:
            return False

        try:
            now = datetime.now()
            time_min, time_max = None, None
            time_min, time_max = None, None

            if target_date:
                dt = None
                # Tenta vários formatos de data
                for fmt in ["%d/%m/%Y", "%Y-%m-%d"]:
                    try:
                        dt = datetime.strptime(target_date, fmt)
                        break
                    except: continue
                
                if dt:
                    time_min = dt.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%S-03:00")
                    time_max = dt.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%dT%H:%M:%S-03:00")
            
            if not time_min:
                # Se não tem data ou falhou o parse, busca de HOJE até os próximos 7 dias
                time_min = now.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%S-03:00")
                time_max = (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S-03:00")

            print(f"   [[BUSCA]] Buscando evento para deletar no intervalo: {time_min} a {time_max}")

            events_result = self.service_calendar.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            if not events:
                print(f"   [!] Nenhum evento encontrado no período de busca.")
                return False

            print(f"   [[BUSCA]] Eventos encontrados ({len(events)}): {[e.get('summary') for e in events]}")

            from difflib import SequenceMatcher

            # Caso 1: Usuário informou um título específico
            if title:
                title_lower = title.strip().lower()
                best_match = None
                highest_ratio = 0.0

                for event in events:
                    summary = event.get('summary', '').lower().strip()
                    
                    # 1.1 Match exato ou substring (rápido)
                    if title_lower in summary or summary in title_lower:
                        self.service_calendar.events().delete(calendarId=self.calendar_id, eventId=event['id']).execute()
                        print(f"   [[OK]] Evento '{event.get('summary')}' deletado (match exato/substring).")
                        return True
                    
                    # 1.2 Match difuso (fuzzy)
                    ratio = SequenceMatcher(None, title_lower, summary).ratio()
                    if ratio > highest_ratio:
                        highest_ratio = ratio
                        best_match = event
                
                # Se encontrou um match com similaridade aceitável (> 0.5)
                if highest_ratio > 0.5 and best_match:
                    self.service_calendar.events().delete(calendarId=self.calendar_id, eventId=best_match['id']).execute()
                    print(f"   [[OK]] Evento '{best_match.get('summary')}' deletado (similaridade: {highest_ratio:.2f}).")
                    return True
            
            # Caso 2: Usuário NÃO informou título, mas há apenas UM evento no dia
            elif not title and len(events) >= 1:
                event = events[0]
                self.service_calendar.events().delete(calendarId=self.calendar_id, eventId=event['id']).execute()
                print(f"   [[OK]] Evento '{event.get('summary')}' deletado automaticamente (único do período).")
                return True
            
            return False
        except Exception as e:
            print(f"   [ERRO] Ao excluir evento: {e}")
            return False

    def _get_or_create_shopping_sheet(self):
        """Garante que a aba 'Lista de Compras' exista na planilha."""
        try:
            spreadsheet = self.service_sheets.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            sheets = spreadsheet.get('sheets', [])
            for s in sheets:
                if s['properties']['title'] == 'Lista de Compras':
                    return True
            
            # Cria a aba se não existir
            body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': 'Lista de Compras'
                        }
                    }
                }]
            }
            self.service_sheets.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            
            # Adiciona cabeçalho
            self.service_sheets.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range='Lista de Compras!A1',
                valueInputOption='USER_ENTERED',
                body={'values': [['Item', 'Data de Adição']]}
            ).execute()
            
            print("   [OK] Aba 'Lista de Compras' criada com sucesso!")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao criar aba de compras: {e}")
            return False

    def add_shopping_item(self, item):
        """Adiciona um item (ou vários separados por vírgula) à lista de compras."""
        if not self.service_sheets or not item: return False
        self._get_or_create_shopping_sheet()
        try:
            date_now = datetime.now().strftime("%d/%m/%Y")
            
            # Divide se o usuário falou vários de uma vez (ex: "leite, pão e café")
            # Substitui " e " por vírgula e divide
            items_raw = item.replace(' e ', ',').split(',')
            items_to_add = [[i.strip(), date_now] for i in items_raw if i.strip()]

            if not items_to_add:
                return False

            body = {'values': items_to_add}
            self.service_sheets.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range='Lista de Compras!A:B',
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            print(f"   [OK] {len(items_to_add)} itens adicionados à lista de compras.")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao adicionar item à lista: {e}")
            return False
        except Exception as e:
            print(f"   [ERRO] Ao adicionar item à lista: {e}")
            return False

    def get_shopping_list(self):
        """Retorna todos os itens da lista de compras, um por um."""
        if not self.service_sheets: return []
        self._get_or_create_shopping_sheet()
        try:
            result = self.service_sheets.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Lista de Compras!A2:A'
            ).execute()
            values = result.get('values', [])
            
            # Coleta todos os itens e garante que se houver vírgula em uma célula, ela seja separada
            unfiltered_items = []
            for row in values:
                if row:
                    # Limpeza de prefixos sujos (ex: "A lista : maçã" -> "maçã")
                    clean_row = re.sub(r'^(?:a\s+lista\s*[:\-]\s*|item\s*[:\-]\s*)', '', row[0], flags=re.IGNORECASE).strip()
                    
                    # Divide por vírgula ou " e "
                    parts = clean_row.replace(' e ', ',').split(',')
                    unfiltered_items.extend([p.strip().capitalize() for p in parts if p.strip()])
            
            return unfiltered_items
        except Exception as e:
            print(f"   [ERRO] Ao buscar lista de compras: {e}")
            return []

    def clear_shopping_list(self):
        """Limpa a lista de compras."""
        if not self.service_sheets: return False
        try:
            self.service_sheets.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range='Lista de Compras!A2:B'
            ).execute()
            print("   [OK] Lista de compras limpa.")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao limpar lista de compras: {e}")
            return False

    def delete_shopping_item(self, item_name):
        """Busca um item na lista de compras e exclui sua linha."""
        if not self.service_sheets or not item_name: return False
        try:
            # 1. Busca todos os itens (Coluna A)
            result = self.service_sheets.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Lista de Compras!A:A'
            ).execute()
            rows = result.get('values', [])
            
            item_to_delete = item_name.lower().strip()
            row_index = -1
            
            # 2. Encontra o índice da linha (1-based para o Google Sheets)
            for i, row in enumerate(rows):
                if row and row[0].lower().strip() == item_to_delete:
                    row_index = i + 1
                    break
            
            if row_index == -1:
                print(f"   [!] Item '{item_name}' não encontrado na lista de compras.")
                return False

            # 3. Descobre o ID da aba 'Lista de Compras' para o batchUpdate
            spreadsheet = self.service_sheets.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            sheet_id = None
            for s in spreadsheet.get('sheets', []):
                if s['properties']['title'] == 'Lista de Compras':
                    sheet_id = s['properties']['sheetId']
                    break
            
            if sheet_id is None: return False

            # 4. Executa a deleção da linha
            body = {
                'requests': [{
                    'deleteDimension': {
                        'range': {
                            'sheetId': sheet_id,
                            'dimension': 'ROWS',
                            'startIndex': row_index - 1,
                            'endIndex': row_index
                        }
                    }
                }]
            }
            self.service_sheets.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            
            print(f"   [[OK]] Item '{item_name}' removido da lista de compras.")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao deletar item da lista de compras: {e}")
            return False

    def _get_or_create_agenda_sheet(self):
        """Garante que a aba 'Pauta de Reunião' exista na planilha."""
        try:
            spreadsheet = self.service_sheets.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            sheets = spreadsheet.get('sheets', [])
            for s in sheets:
                if s['properties']['title'] == 'Pauta de Reunião':
                    return True
            
            # Cria a aba se não existir
            body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': 'Pauta de Reunião'
                        }
                    }
                }]
            }
            self.service_sheets.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            
            # Adiciona cabeçalho
            self.service_sheets.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range='Pauta de Reunião!A1',
                valueInputOption='USER_ENTERED',
                body={'values': [['Assunto', 'Data da Reunião', 'Data de Adição']]}
            ).execute()
            
            print("   [OK] Aba 'Pauta de Reunião' criada com sucesso!")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao criar aba de pauta: {e}")
            return False

    def add_agenda_item(self, topic, date=None):
        """Adiciona um assunto (ou vários) à pauta de reunião."""
        if not self.service_sheets or not topic: return False
        self._get_or_create_agenda_sheet()
        try:
            date_added = datetime.now().strftime("%d/%m/%Y")
            # Se não fornecer data da reunião, deixa em branco (pauta geral) ou usa hoje/amanhã se detectado
            meeting_date = date or ""
            
            # Divide se o usuário falou vários de uma vez
            items_raw = topic.replace(' e ', ',').split(',')
            items_to_add = [[i.strip(), meeting_date, date_added] for i in items_raw if i.strip()]

            if not items_to_add:
                return False

            body = {'values': items_to_add}
            self.service_sheets.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range='Pauta de Reunião!A:C',
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            print(f"   [OK] {len(items_to_add)} assuntos adicionados à pauta.")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao adicionar assunto à pauta: {e}")
            return False

    def get_agenda(self, date=None):
        """Retorna os assuntos da pauta, opcionalmente filtrados por data."""
        if not self.service_sheets: return []
        self._get_or_create_agenda_sheet()
        try:
            result = self.service_sheets.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Pauta de Reunião!A2:B'
            ).execute()
            values = result.get('values', [])
            
            agenda_items = []
            for row in values:
                if len(row) >= 1:
                    topic = row[0]
                    row_date = row[1] if len(row) >= 2 else ""
                    
                    if not date or (date == row_date):
                        agenda_items.append({"topic": topic, "date": row_date})
            
            return agenda_items
        except Exception as e:
            print(f"   [ERRO] Ao buscar pauta: {e}")
            return []

    def find_agenda_matches(self, topic_name=None, date=None):
        """Retorna uma lista de itens que coincidem com o termo de busca na pauta."""
        if not self.service_sheets: return []
        self._get_or_create_agenda_sheet()
        try:
            result = self.service_sheets.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Pauta de Reunião!A2:B'
            ).execute()
            values = result.get('values', [])
            
            matches = []
            topic_to_find = topic_name.lower().strip() if topic_name else None
            
            for i, row in enumerate(values):
                if row and len(row) >= 1:
                    current_topic = row[0]
                    current_date = row[1] if len(row) >= 2 else ""
                    
                    # Filtra por data se fornecida
                    if date and date != current_date:
                        continue
                        
                    # Se informou um nome, filtra por nome (parcial ou total)
                    if topic_to_find:
                        if (topic_to_find in current_topic.lower() or current_topic.lower() in topic_to_find):
                            matches.append({"topic": current_topic, "date": current_date, "row": i + 2})
                    else:
                        # Se não informou nome, pega todos da data (ou todos da pauta se data None)
                        matches.append({"topic": current_topic, "date": current_date, "row": i + 2})
            
            return matches
        except Exception as e:
            print(f"   [ERRO] Ao buscar matches na pauta: {e}")
            return []

    def delete_agenda_item_by_row(self, row_index):
        """Deleta uma linha específica da pauta por índice."""
        if not self.service_sheets: return False
        try:
            spreadsheet = self.service_sheets.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            sheet_id = None
            for s in spreadsheet.get('sheets', []):
                if s['properties']['title'] == 'Pauta de Reunião':
                    sheet_id = s['properties']['sheetId']
                    break
            
            if sheet_id is None: return False

            body = {
                'requests': [{
                    'deleteDimension': {
                        'range': {
                            'sheetId': sheet_id,
                            'dimension': 'ROWS',
                            'startIndex': row_index - 1,
                            'endIndex': row_index
                        }
                    }
                }]
            }
            self.service_sheets.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            return True
        except Exception as e:
            print(f"   [ERRO] Ao deletar linha da pauta: {e}")
            return False

    def clear_agenda(self):
        """Limpa toda a pauta de reunião."""
        if not self.service_sheets: return False
        try:
            self.service_sheets.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range='Pauta de Reunião!A2:C'
            ).execute()
            print("   [OK] Pauta de reunião limpa.")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao limpar pauta: {e}")
            return False

    def delete_agenda_item(self, topic_name, date=None):
        """Busca um assunto na pauta e exclui sua linha."""
        if not self.service_sheets or not topic_name: return False
        try:
            result = self.service_sheets.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Pauta de Reunião!A:B'
            ).execute()
            rows = result.get('values', [])
            
            topic_to_delete = topic_name.lower().strip()
            row_index = -1
            
            for i, row in enumerate(rows):
                if row and len(row) >= 1:
                    current_topic = row[0].lower().strip()
                    current_date = row[1] if len(row) >= 2 else ""
                    
                    # Match parcial ou total
                    if (topic_to_delete in current_topic or current_topic in topic_to_delete):
                        if not date or date == current_date:
                            row_index = i + 1
                            break
            
            if row_index == -1:
                return False

            # ID da aba
            spreadsheet = self.service_sheets.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            sheet_id = None
            for s in spreadsheet.get('sheets', []):
                if s['properties']['title'] == 'Pauta de Reunião':
                    sheet_id = s['properties']['sheetId']
                    break
            
            if sheet_id is None: return False

            body = {
                'requests': [{
                    'deleteDimension': {
                        'range': {
                            'sheetId': sheet_id,
                            'dimension': 'ROWS',
                            'startIndex': row_index - 1,
                            'endIndex': row_index
                        }
                    }
                }]
            }
            self.service_sheets.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            
            print(f"   [[OK]] Assunto '{topic_name}' removido da pauta.")
            return True
        except Exception as e:
            print(f"   [ERRO] Ao deletar assunto da pauta: {e}")
            return False

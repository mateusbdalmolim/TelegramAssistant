import os
import json
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Configuração do Novo SDK do Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# O modelo Gemini 3.1 Flash Lite Preview (conforme identificado na sua listagem de modelos)
MODEL_NAME = 'gemini-3.1-flash-lite-preview'

PROMPT_SYSTEM = """
Você é um assistente pessoal inteligente. Sua tarefa é converter pedidos em JSON.
Intenções suportadas: 'expense', 'appointment', 'delete', 'list', 'shopping_list_add', 'shopping_list_get', 'shopping_list_clear', 'total_query', 'reminder', 'chatter', 'clear_all', 'energy_prices_query', 'agenda_add', 'agenda_get', 'agenda_clear'.

REGRAS DE OURO:
1. 'delete': Se for para apagar compromisso, use {"type": "delete", "target": "NOME", "content_type": "appointment"}.
2. Datas: Use formato YYYY-MM-DD para 'date' e ISO para 'time'.
3. 'target': NUNCA inclua palavras de tempo (amanhã, hoje, 14h) no target. Use os campos de data/hora.

EXEMPLOS:
- Gasto: {"type": "expense", "item": "Gasolina", "value": 150.0}
- Agenda (Marcar/Agendar/Anote): {"type": "appointment", "title": "Médico", "time": "2026-03-22T09:00:00"}
- Lista Add: {"type": "shopping_list_add", "item": "Leite, Pão"}
- Lista Ver: {"type": "shopping_list_get"}
- Lista Excluir Item (Exclua/Apague/Remova): {"type": "delete", "target": "maçã", "content_type": "shopping_list"}
- Agenda Excluir (Apague a reunião de amanhã): {"type": "delete", "target": "reunião", "content_type": "appointment", "date": "2026-03-19"}
- Excluir Gasto: {"type": "delete", "target": "gasolina"}
- Preços Energia/Mercado Livre: {"type": "energy_prices_query"}
- Lembrete: {"type": "reminder", "title": "Comprar pão", "delta_minutes": 10}
- Lembrete em segundos: {"type": "reminder", "title": "Tirar o bolo do forno", "delta_seconds": 30}
- Listar mês: {"type": "list", "period": "month", "month": 3, "year": 2026}
- Adicionar pauta (assunto para reunião): {"type": "agenda_add", "topic": "Discutir orçamento", "date": "2026-03-20"}
- Ver pauta: {"type": "agenda_get"}
- Ver pauta do dia 25/03: {"type": "agenda_get", "date": "2026-03-25"}
- Limpar pauta: {"type": "agenda_clear"}

Responda APENAS o JSON puro.
"""

def local_interpret(text):
    """Fallback local robusto para quando o Gemini estiver fora do ar ou sem cota."""
    text_lower = text.lower().strip()
    now = datetime.now()
    date_str = now.strftime("%d/%m/%Y")

    # 1. CHATTER / PERSONALIDADE
    if re.search(r'\bbrain\b', text_lower):
        return {"type": "chatter", "kind": "greeting"}
    if any(word in text_lower for word in ["obrigado", "valeu", "vlw", "obrigada"]) and len(text_lower) < 15:
        return {"type": "chatter", "kind": "thanks"}

    # 2. LIMPAR TUDO
    if any(p in text_lower for p in ["limpar tudo", "apagar tudo", "limpar planilha"]):
        return {"type": "clear_all"}

    # 3. LISTA DE COMPRAS
    if any(kw in text_lower for kw in ["lista", "comprar", "carrinho"]):
        if any(w in text_lower for w in ["ver", "quais", "trazer", "mostrar", "tem"]):
            return {"type": "shopping_list_get"}
        if any(w in text_lower for w in ["limpar", "apagar", "zerar"]) and "lista" in text_lower:
            return {"type": "shopping_list_clear"}
        add_verbs = ["adicione", "adicionar", "coloca", "coloque", "anotar", "anote", "põe", "poe", "comprar"]
        if any(v in text_lower for v in add_verbs):
            item = text_lower
            for v in add_verbs + ["na lista", "no carrinho", "de compras", "a lista", "o item"]:
                item = item.replace(v, "").strip()
            item = item.strip(": ").strip()
            if item: return {"type": "shopping_list_add", "item": item.capitalize()}

    # 4. EXCLUSÃO (Delete)
    if any(w in text_lower for w in ["excluir", "apagar", "deletar", "remover", "desfazer"]):
        target = text_lower
        for w in ["excluir", "apagar", "deletar", "remover", "desfazer", "o", "a", "os", "as"]:
            target = target.replace(f" {w} ", " ").replace(f" {w}", "").strip()
        
        content_type = "expense"
        if any(w in target for w in ["reunião", "compromisso", "evento", "agenda"]):
            content_type = "appointment"
            target = target.replace("reunião", "").replace("compromisso", "").replace("evento", "").replace("agenda", "").strip()

        date_ret = None
        if "amanhã" in target or "amanha" in target:
            date_ret = (now + timedelta(days=1)).strftime("%d/%m/%Y")
            target = target.replace("amanhã", "").replace("amanha", "").strip()
        elif "hoje" in target:
            date_ret = now.strftime("%d/%m/%Y")
            target = target.replace("hoje", "").strip()
        
        return {"type": "delete", "target": target, "content_type": content_type, "date": date_ret}

    # 5. GASTOS (Regex Valor)
    price_match = re.search(r'(?:r\$?\s*|reais\s*)?(\d+(?:[.,]\d{1,2})?)\s*(?:reais|r\$?)?', text_lower)
    if price_match and any(w in text_lower for w in ["gastei", "paguei", "valor", "reais", "custou"]):
        try:
            val = float(price_match.group(1).replace(',', '.'))
            item_text = text_lower.replace(price_match.group(0), "").replace("gastei", "").replace("paguei", "").strip()
            if not item_text: item_text = "Gasto Diversos"
            return {"type": "expense", "item": item_text.capitalize(), "value": val, "date": date_str}
        except: pass

    # 6. LEMBRETE (RegEx simples)
    if "lembre" in text_lower or "avisar" in text_lower:
        time_match = re.search(r'em\s+(\d+)\s+(minuto|segundo|min|seg)', text_lower)
        if time_match:
            num = int(time_match.group(1))
            unit = time_match.group(2)
            title = text_lower.replace(time_match.group(0), "").replace("me lembre de", "").replace("me lembre", "").replace("me avisar", "").strip()
            if not title: title = "Lembrete"
            
            if "min" in unit:
                return {"type": "reminder", "title": title.capitalize(), "delta_minutes": num}
            else:
                return {"type": "reminder", "title": title.capitalize(), "delta_seconds": num}

    # 7. AGENDA (Data/Hora simples)
    if any(w in text_lower for w in ["reunião", "compromisso", "evento", "agendar", "marcar"]):
        title = text_lower.replace("marcar", "").replace("agendar", "").replace("reunião", "").replace("compromisso", "").strip()
        return {"type": "appointment", "title": title.capitalize()}

    # 8. PAUTA DE REUNIÃO (Local Fallback)
    if any(kw in text_lower for kw in ["pauta", "assunto", "pauta da reunião"]):
        date_ret = None
        if "amanhã" in text_lower or "amanha" in text_lower:
            date_ret = (now + timedelta(days=1)).strftime("%d/%m/%Y")
        elif "hoje" in text_lower:
            date_ret = now.strftime("%d/%m/%Y")
        
        if any(w in text_lower for w in ["ver", "quais", "mostrar", "tem", "trazer"]):
            return {"type": "agenda_get", "date": date_ret}
        if any(w in text_lower for w in ["limpar", "apagar", "zerar"]):
            return {"type": "agenda_clear"}
        
        add_verbs = ["adicione", "adicionar", "coloca", "coloque", "anotar", "anote", "põe", "poe"]
        if any(v in text_lower for v in add_verbs) or "pauta" in text_lower:
            topic = text_lower
            for v in add_verbs + ["na pauta", "da reunião", "assunto", "hoje", "amanhã", "amanha"]:
                topic = topic.replace(v, "").strip()
            topic = topic.strip(": ").strip()
            if topic: return {"type": "agenda_add", "topic": topic.capitalize(), "date": date_ret}

    return {"type": "unknown"}

def interpret_message(text):
    """Tenta Novo Gemini (3.1/2.0) -> Fallback Local."""
    text_lower = text.lower().strip()
    now = datetime.now()
    date_context = f"Data de Hoje: {now.strftime('%Y-%m-%d')} ({now.strftime('%A')})"
    
    # 0. Prioridade Local: Nome do bot ou Agradecimento
    if re.search(r'\bbrain\b', text_lower) or (any(w in text_lower for w in ["obrigado", "valeu"]) and len(text_lower) < 15):
        return local_interpret(text)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=f"{PROMPT_SYSTEM}\n\nCONTEXTO: {date_context}\nMensagem: {text}")
                    ]
                )
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        if response and response.text:
            return json.loads(response.text.strip())
    except Exception as e:
        print(f"[⚠️] Erro na API Gemini (Geral): {e}. Usando fallback local...")
    
    return local_interpret(text)

def interpret_audio(audio_path):
    """Interpreta áudio usando o novo SDK e o Gemini 3.1."""
    now = datetime.now()
    date_context = f"Data de Hoje: {now.strftime('%Y-%m-%d')} ({now.strftime('%A')})"
    try:
        # Lê o arquivo binário
        with open(audio_path, "rb") as f:
            audio_data = f.read()
            
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=f"{PROMPT_SYSTEM}\n\nCONTEXTO: {date_context}"),
                        types.Part.from_bytes(data=audio_data, mime_type="audio/ogg"),
                        types.Part.from_text(text="Analise o áudio acima. Transcreva e classifique conforme as instruções, retornando APENAS JSON.")
                    ]
                )
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        if response and response.text:
            return json.loads(response.text.strip())
    except Exception as e:
        print(f"[⚠️] Erro ao processar áudio no novo SDK: {e}")
    return {"type": "unknown"}

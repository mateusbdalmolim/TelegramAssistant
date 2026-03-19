import httpx
import logging

class EnergyService:
    def __init__(self):
        self.api_url = "https://dashboardapi.denergia.com.br/api/IndicesCurvaForward/home"
        self.headers = {
            "Origin": "https://denergia.com.br",
            "Referer": "https://denergia.com.br/",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def get_market_prices(self):
        """Busca os preços de energia (Mercado Livre e PLD) na API dEnergia."""
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(self.api_url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                
                result = data.get("result", {})
                if not result:
                    return "⚠️ Não consegui extrair os dados do dashboard no momento."

                # 1. Curva Forward (Mercado Livre)
                forward = result.get("curvaForwardGrafico", {})
                
                def get_last_val(key):
                    serie = forward.get(key, {}).get("serie", [])
                    if not serie: return "N/A"
                    last_entry = serie[-1]
                    if isinstance(last_entry, dict):
                        return last_entry.get("valor", "N/A")
                    return last_entry

                conv_tri = get_last_val("convencional_trimestre")
                conv_longo = get_last_val("convencional_longo_prazo")
                inc50_tri = get_last_val("incentivada_50_trimestre")
                inc50_longo = get_last_val("incentivada_50_longo_prazo")

                # 2. PLD por Submercado (Últimos valores diários)
                pld_data = result.get("pldSubmercado", {})
                pld_table = pld_data.get("tabela", [])
                pld_info = ""
                
                # Busca a linha do PLD Diário
                daily_row = next((row for row in pld_table if row.get("patamar") == "Diário"), None)
                
                if daily_row:
                    # Mapeia os submercados (pode usar o dicionário do JSON se quiser ser 100% dinâmico)
                    regions = {
                        "sudeste": "Sudeste/CO",
                        "sul": "Sul",
                        "nordeste": "Nordeste",
                        "norte": "Norte"
                    }
                    for key, label in regions.items():
                        val = daily_row.get(key, "N/A")
                        pld_info += f"• *{label}:* R$ {val}\n"
                else:
                    pld_info = "• _Dados de PLD indisponíveis no momento._\n"

                msg = (
                    "📊 *PREÇOS ENERGIA - MERCADO LIVRE*\n\n"
                    "📈 *Curva Forward (M+1 a M+3):*\n"
                    f"• Convencional: R$ {conv_tri}\n"
                    f"• Incentivada 50%: R$ {inc50_tri}\n\n"
                    "📅 *Longo Prazo (A+1 a A+4):*\n"
                    f"• Convencional: R$ {conv_longo}\n"
                    f"• Incentivada 50%: R$ {inc50_longo}\n\n"
                    "⚡ *PLD Diário por Regional:*\n"
                    f"{pld_info}\n"
                    "🔗 _Fonte: dEnergia Dashboard_"
                )
                return msg

        except Exception as e:
            logging.error(f"Erro ao buscar preços de energia: {e}")
            return "❌ Erro ao conectar com o serviço de preços de energia."

import os
import json
from typing import Dict, Any
from groq import Groq
from dotenv import load_dotenv

# Muat file .env dari root
load_dotenv(dotenv_path=".env")

class GroqChatbot:
    """
    Chatbot AI untuk analisis data sales restoran menggunakan Groq API.
    """

    def __init__(self):
        self.api_key = os.getenv('GROQ_API_KEY')

        # Debugging jika tidak ada API key
        if not self.api_key or self.api_key.strip() == "":
            raise ValueError("❌ GROQ_API_KEY tidak ditemukan dalam file .env")

        print(f"[DEBUG] GROQ_API_KEY loaded: {self.api_key[:6]}...")  # Jangan tampilkan seluruh API key di log

        self.client = Groq(api_key=self.api_key)
        # self.model = "mixtral-8x7b-32768"
        self.model = "llama3-70b-8192"


        self.system_prompt = """
        Anda adalah AI Data Analyst expert yang fokus pada analisis penjualan restoran dan COGS.
        Berikan analisis yang akurat, mendalam, dan menggunakan data yang tersedia.
        Gunakan bahasa Indonesia profesional, mudah dipahami, dan respons yang actionable.
        """

    def get_response(self, user_question: str, data_context: Dict[str, Any]) -> str:
        """
        Mengirim pertanyaan dan data ke model Groq untuk mendapatkan jawaban.
        """
        try:
            context_prompt = self._create_context_prompt(data_context)
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"Data penjualan:\n{context_prompt}\n\nPertanyaan: {user_question}"}
            ]

            response = self.client.chat.completions.create(
                messages=messages,
                model=self.model,
                temperature=0.3,
                max_tokens=2048,
                top_p=0.9
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"❌ Error saat mengambil respons dari AI: {str(e)}"

    def _create_context_prompt(self, data_context: Dict[str, Any]) -> str:
        """
        Menyusun context prompt dari data penjualan.
        """
        try:
            context = f"""
📊 RINGKASAN SALES
Periode: {data_context.get('period', 'N/A')}
Revenue: Rp {data_context.get('total_revenue', 0):,.0f}
COGS: Rp {data_context.get('total_cogs', 0):,.0f}
Margin: Rp {data_context.get('total_margin', 0):,.0f}
Avg COGS %: {data_context.get('avg_cogs_percentage', 0):.1f}%
Gross Margin %: {(data_context.get('total_margin', 0) / max(data_context.get('total_revenue', 1), 1)) * 100:.1f}%
Transaksi: {data_context.get('total_transactions', 0):,}
Avg Revenue Harian: Rp {data_context.get('daily_average_revenue', 0):,.0f}
Avg per Transaksi: Rp {(data_context.get('total_revenue', 0) / max(data_context.get('total_transactions', 1), 1)):,.0f}

🏆 Top 5 Menu Terlaris:
"""
            for i, menu in enumerate(data_context.get("top_selling_menus", [])[:5], 1):
                context += f"\n{i}. {menu.get('Menu', 'N/A')} - {menu.get('Total_Qty', 0)}x (Rp {menu.get('Total_Revenue', 0):,.0f})"

            context += "\n\n💎 Menu Paling Menguntungkan:"
            for i, menu in enumerate(data_context.get("most_profitable_menus", [])[:5], 1):
                context += f"\n{i}. {menu.get('Menu', 'N/A')} - Rp {menu.get('Avg_Margin', 0):,.0f} ({menu.get('Margin_Percentage', 0):.1f}%)"

            context += "\n\n📊 Performa Kategori Menu:"
            for cat in data_context.get("category_performance", []):
                revenue = cat.get("Total", 0)
                margin = cat.get("Margin", 0)
                margin_pct = (margin / revenue * 100) if revenue else 0
                cogs_pct = cat.get("COGS Total (%)", 0)
                context += f"\n- {cat.get('Menu Category', 'N/A')}: Revenue Rp {revenue:,.0f}, Margin {margin_pct:.1f}%, COGS {cogs_pct:.1f}%"

            return context.strip()

        except Exception as e:
            return f"❌ Error dalam membuat context prompt: {str(e)}"

    def validate_api_connection(self) -> bool:
        """
        Validasi apakah koneksi ke Groq API berhasil.
        """
        try:
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": "Halo"}],
                model=self.model,
                max_tokens=10
            )
            return True
        except Exception as e:
            print(f"❌ Gagal konek ke Groq API: {str(e)}")
            return False
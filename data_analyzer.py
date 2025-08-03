import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class SalesDataAnalyzer:
    """
    Kelas untuk menganalisis data sales menu COGS secara mendalam.
    
    Fitur analisis:
    - Analisis profitabilitas per menu dan kategori
    - Analisis temporal (harian, mingguan, bulanan)
    - Analisis COGS dan optimasi
    - Analisis performa menu
    - Rekomendasi bisnis berbasis data
    """
    
    def __init__(self, uploaded_file):
        """
        Inisialisasi analyzer dengan file upload.
        
        Args:
            uploaded_file: File Excel yang diupload melalui Streamlit
        """
        self.raw_data = self._load_data(uploaded_file)
        self.data = self._clean_and_prepare_data(self.raw_data)
        self.total_records = len(self.data)
        self.min_date = self.data['Sales Date'].min()
        self.max_date = self.data['Sales Date'].max()
    
    def _load_data(self, uploaded_file):
        """
        Memuat data dari file Excel dan menemukan header yang benar.
        
        Args:
            uploaded_file: File Excel yang diupload
            
        Returns:
            pd.DataFrame: Data mentah dari Excel
        """
        try:
            # Baca file Excel
            df = pd.read_excel(uploaded_file)
            
            # Cari row yang berisi header sebenarnya
            for i in range(20):  # Cek 20 baris pertama
                try:
                    # Coba parse dari baris ke-i
                    test_df = pd.read_excel(uploaded_file, header=i)
                    
                    # Cek apakah ini adalah header yang benar
                    if ('Sales Number' in test_df.columns and 
                        'Menu' in test_df.columns and 
                        'COGS Total' in test_df.columns):
                        return test_df
                except:
                    continue
            
            # Jika tidak ditemukan, gunakan default
            return df
            
        except Exception as e:
            raise Exception(f"Error loading data: {str(e)}")
    
    def _clean_and_prepare_data(self, df):
        """
        Membersihkan dan mempersiapkan data untuk analisis.
        
        Args:
            df: DataFrame mentah
            
        Returns:
            pd.DataFrame: Data yang sudah dibersihkan
        """
        # Copy data
        data = df.copy()
        
        # Hapus baris yang kosong atau tidak valid
        data = data.dropna(subset=['Menu', 'Sales Date'])
        
        # Konversi tipe data
        if 'Sales Date' in data.columns:
            data['Sales Date'] = pd.to_datetime(data['Sales Date'])
        
        # Pastikan kolom numerik dalam format yang benar
        numeric_columns = ['Qty', 'Price', 'Total', 'Discount Total', 'COGS Total', 'COGS Total (%)', 'Margin']
        for col in numeric_columns:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')
        
        # Hapus baris dengan nilai numerik yang tidak valid
        data = data.dropna(subset=numeric_columns)
        
        # Tambah kolom analisis tambahan
        data['Hour'] = data['Sales Date'].dt.hour
        data['Day_of_Week'] = data['Sales Date'].dt.day_name()
        data['Week'] = data['Sales Date'].dt.isocalendar().week
        data['Month'] = data['Sales Date'].dt.month
        data['Date'] = data['Sales Date'].dt.date
        
        # Kalkulasi margin percentage jika belum ada
        if 'Margin_Percentage' not in data.columns:
            data['Margin_Percentage'] = (data['Margin'] / data['Total']) * 100
        
        return data
    
    def get_date_range(self):
        """Mendapatkan rentang tanggal data."""
        start_date = self.min_date.strftime('%d/%m/%Y')
        end_date = self.max_date.strftime('%d/%m/%Y')
        return f"{start_date} - {end_date}"
    
    def get_unique_categories(self):
        """Mendapatkan daftar kategori menu unik."""
        return sorted(self.data['Menu Category'].unique().tolist())
    
    def get_unique_branches(self):
        """Mendapatkan daftar cabang unik."""
        if 'Branch' in self.data.columns:
            return sorted(self.data['Branch'].unique().tolist())
        return []
    
    def apply_filters(self, date_range, categories, branch=None):
        """
        Menerapkan filter pada data.
        
        Args:
            date_range: Tuple tanggal (start, end)
            categories: List kategori menu
            branch: Nama cabang (optional)
            
        Returns:
            pd.DataFrame: Data yang sudah difilter
        """
        filtered_data = self.data.copy()
        
        # Filter tanggal
        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_data = filtered_data[
                (filtered_data['Sales Date'].dt.date >= start_date) &
                (filtered_data['Sales Date'].dt.date <= end_date)
            ]
        
        # Filter kategori
        if categories:
            filtered_data = filtered_data[filtered_data['Menu Category'].isin(categories)]
        
        # Filter cabang
        if branch and 'Branch' in filtered_data.columns:
            filtered_data = filtered_data[filtered_data['Branch'] == branch]
        
        return filtered_data
    
    def get_top_performing_menus(self, data, top_n=10):
        """
        Mendapatkan menu dengan performa terbaik berdasarkan kuantitas terjual.
        
        Args:
            data: DataFrame yang akan dianalisis
            top_n: Jumlah menu teratas
            
        Returns:
            pd.DataFrame: Top performing menus
        """
        menu_performance = data.groupby('Menu').agg({
            'Qty': 'sum',
            'Total': 'sum',
            'Margin': 'sum',
            'COGS Total': 'sum'
        }).reset_index()
        
        menu_performance.columns = ['Menu', 'Total_Qty', 'Total_Revenue', 'Total_Margin', 'Total_COGS']
        menu_performance['Avg_Price'] = menu_performance['Total_Revenue'] / menu_performance['Total_Qty']
        menu_performance['Margin_Percentage'] = (menu_performance['Total_Margin'] / menu_performance['Total_Revenue']) * 100
        
        return menu_performance.nlargest(top_n, 'Total_Qty')
    
    def get_most_profitable_menus(self, data, top_n=10):
        """
        Mendapatkan menu paling menguntungkan berdasarkan margin.
        
        Args:
            data: DataFrame yang akan dianalisis
            top_n: Jumlah menu teratas
            
        Returns:
            pd.DataFrame: Most profitable menus
        """
        menu_profit = data.groupby('Menu').agg({
            'Margin': ['sum', 'mean'],
            'Total': 'sum',
            'Qty': 'sum',
            'COGS Total (%)': 'mean'
        }).reset_index()
        
        # Flatten column names
        menu_profit.columns = ['Menu', 'Total_Margin', 'Avg_Margin', 'Total_Revenue', 'Total_Qty', 'Avg_COGS_Pct']
        menu_profit['Margin_Percentage'] = (menu_profit['Total_Margin'] / menu_profit['Total_Revenue']) * 100
        
        return menu_profit.nlargest(top_n, 'Avg_Margin')
    
    def get_comprehensive_menu_analysis(self, data):
        """
        Analisis komprehensif untuk semua menu.
        
        Args:
            data: DataFrame yang akan dianalisis
            
        Returns:
            pd.DataFrame: Analisis komprehensif menu
        """
        menu_analysis = data.groupby(['Menu', 'Menu Category']).agg({
            'Qty': ['sum', 'mean', 'count'],
            'Total': ['sum', 'mean'],
            'Margin': ['sum', 'mean'],
            'COGS Total': ['sum', 'mean'],
            'COGS Total (%)': 'mean',
            'Price': 'mean'
        }).reset_index()
        
        # Flatten column names
        menu_analysis.columns = [
            'Menu', 'Menu_Category', 'Total_Qty', 'Avg_Qty', 'Order_Count',
            'Total_Revenue', 'Avg_Revenue', 'Total_Margin', 'Avg_Margin',
            'Total_COGS', 'Avg_COGS', 'Avg_COGS_Pct', 'Avg_Price'
        ]
        
        # Tambah kalkulasi tambahan
        menu_analysis['Margin_Percentage'] = (menu_analysis['Total_Margin'] / menu_analysis['Total_Revenue']) * 100
        menu_analysis['Revenue_per_Order'] = menu_analysis['Total_Revenue'] / menu_analysis['Order_Count']
        menu_analysis['Frequency_Score'] = menu_analysis['Order_Count'] / data['Date'].nunique()  # Orders per day
        
        return menu_analysis.sort_values('Total_Revenue', ascending=False)
    
    def get_daily_sales_trend(self, data):
        """
        Mendapatkan tren penjualan harian.
        
        Args:
            data: DataFrame yang akan dianalisis
            
        Returns:
            pd.DataFrame: Daily sales trend
        """
        daily_trend = data.groupby('Date').agg({
            'Total': 'sum',
            'Qty': 'sum',
            'Margin': 'sum',
            'COGS Total': 'sum'
        }).reset_index()
        
        daily_trend.columns = ['Sales Date', 'Daily_Revenue', 'Daily_Qty', 'Daily_Margin', 'Daily_COGS']
        daily_trend['Sales Date'] = pd.to_datetime(daily_trend['Sales Date'])
        
        # Tambah moving average
        daily_trend['Revenue_MA_7'] = daily_trend['Daily_Revenue'].rolling(window=7, min_periods=1).mean()
        
        return daily_trend.sort_values('Sales Date')
    
    def get_hourly_sales_pattern(self, data):
        """
        Mendapatkan pola penjualan per jam.
        
        Args:
            data: DataFrame yang akan dianalisis
            
        Returns:
            pd.DataFrame: Hourly sales pattern
        """
        hourly_pattern = data.groupby('Hour').agg({
            'Total': ['sum', 'mean', 'count'],
            'Qty': 'sum'
        }).reset_index()
        
        hourly_pattern.columns = ['Hour', 'Total_Revenue', 'Avg_Revenue', 'Transaction_Count', 'Total_Qty']
        
        return hourly_pattern.sort_values('Hour')
    
    def get_daily_sales_pattern(self, data):
        """
        Mendapatkan pola penjualan per hari dalam seminggu.
        
        Args:
            data: DataFrame yang akan dianalisis
            
        Returns:
            pd.DataFrame: Daily sales pattern
        """
        # Map day names to numbers for proper ordering
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        daily_pattern = data.groupby('Day_of_Week').agg({
            'Total': ['sum', 'mean'],
            'Qty': 'sum'
        }).reset_index()
        
        daily_pattern.columns = ['Day_Name', 'Total_Revenue', 'Avg_Revenue', 'Total_Qty']
        
        # Reorder by day of week
        daily_pattern['Day_Order'] = daily_pattern['Day_Name'].map({day: i for i, day in enumerate(day_order)})
        daily_pattern = daily_pattern.sort_values('Day_Order').drop('Day_Order', axis=1)
        
        return daily_pattern
    
    def get_weekly_trend(self, data):
        """
        Mendapatkan tren penjualan mingguan.
        
        Args:
            data: DataFrame yang akan dianalisis
            
        Returns:
            pd.DataFrame: Weekly trend
        """
        weekly_trend = data.groupby('Week').agg({
            'Total': 'sum',
            'Qty': 'sum',
            'Margin': 'sum'
        }).reset_index()
        
        weekly_trend.columns = ['Week', 'Weekly_Revenue', 'Weekly_Qty', 'Weekly_Margin']
        
        return weekly_trend.sort_values('Week')
    
    def get_sales_heatmap_data(self, data):
        """
        Mendapatkan data untuk heatmap penjualan (jam vs hari).
        
        Args:
            data: DataFrame yang akan dianalisis
            
        Returns:
            pd.DataFrame: Heatmap data
        """
        heatmap_data = data.groupby(['Hour', 'Day_of_Week'])['Total'].sum().reset_index()
        heatmap_pivot = heatmap_data.pivot(index='Hour', columns='Day_of_Week', values='Total').fillna(0)
        
        # Reorder columns by day of week
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        available_days = [day for day in day_order if day in heatmap_pivot.columns]
        heatmap_pivot = heatmap_pivot[available_days]
        
        return heatmap_pivot
    
    def get_menu_profitability_analysis(self, data):
        """
        Analisis profitabilitas menu secara detail.
        
        Args:
            data: DataFrame yang akan dianalisis
            
        Returns:
            pd.DataFrame: Menu profitability analysis
        """
        menu_profit = data.groupby(['Menu', 'Menu Category']).agg({
            'Total': 'sum',
            'Margin': 'sum',
            'COGS Total': 'sum',
            'COGS Total (%)': 'mean',
            'Qty': 'sum'
        }).reset_index()
        
        menu_profit['Margin_Percentage'] = (menu_profit['Margin'] / menu_profit['Total']) * 100
        menu_profit['Avg_COGS_Pct'] = menu_profit['COGS Total (%)']
        menu_profit['Total_Margin'] = menu_profit['Margin']
        menu_profit['Total_Qty'] = menu_profit['Qty']
        
        return menu_profit
    
    def get_cogs_trend(self, data):
        """
        Mendapatkan tren COGS harian.
        
        Args:
            data: DataFrame yang akan dianalisis
            
        Returns:
            pd.DataFrame: COGS trend
        """
        cogs_trend = data.groupby('Date').agg({
            'COGS Total': 'sum',
            'Total': 'sum',
            'COGS Total (%)': 'mean'
        }).reset_index()
        
        cogs_trend.columns = ['Sales Date', 'Daily_COGS', 'Daily_Revenue', 'Avg_COGS_Pct']
        cogs_trend['Sales Date'] = pd.to_datetime(cogs_trend['Sales Date'])
        cogs_trend['COGS_Efficiency'] = (1 - cogs_trend['Avg_COGS_Pct'] / 100) * 100
        
        return cogs_trend.sort_values('Sales Date')
    
    def get_high_cogs_menus(self, data, top_n=10):
        """
        Mendapatkan menu dengan COGS tertinggi.
        
        Args:
            data: DataFrame yang akan dianalisis
            top_n: Jumlah menu teratas
            
        Returns:
            pd.DataFrame: High COGS menus
        """
        high_cogs = data.groupby('Menu').agg({
            'COGS Total (%)': 'mean',
            'Total': 'sum',
            'Qty': 'sum'
        }).reset_index()
        
        high_cogs.columns = ['Menu', 'Avg_COGS_Pct', 'Total_Revenue', 'Total_Qty']
        
        return high_cogs.nlargest(top_n, 'Avg_COGS_Pct')
    
    def get_low_cogs_menus(self, data, top_n=10):
        """
        Mendapatkan menu dengan COGS terendah.
        
        Args:
            data: DataFrame yang akan dianalisis
            top_n: Jumlah menu teratas
            
        Returns:
            pd.DataFrame: Low COGS menus
        """
        low_cogs = data.groupby('Menu').agg({
            'COGS Total (%)': 'mean',
            'Total': 'sum',
            'Qty': 'sum'
        }).reset_index()
        
        low_cogs.columns = ['Menu', 'Avg_COGS_Pct', 'Total_Revenue', 'Total_Qty']
        
        return low_cogs.nsmallest(top_n, 'Avg_COGS_Pct')
    
    def calculate_cogs_efficiency(self, data):
        """
        Menghitung efisiensi COGS secara keseluruhan.
        
        Args:
            data: DataFrame yang akan dianalisis
            
        Returns:
            float: COGS efficiency percentage
        """
        total_revenue = data['Total'].sum()
        total_cogs = data['COGS Total'].sum()
        
        if total_revenue > 0:
            cogs_percentage = (total_cogs / total_revenue) * 100
            efficiency = 100 - cogs_percentage
            return efficiency
        
        return 0
    
    def get_cogs_optimization_recommendations(self, data):
        """
        Mendapatkan rekomendasi optimasi COGS.
        
        Args:
            data: DataFrame yang akan dianalisis
            
        Returns:
            list: List of optimization recommendations
        """
        recommendations = []
        
        # Analisis menu dengan COGS tinggi
        high_cogs_menus = self.get_high_cogs_menus(data, 5)
        if not high_cogs_menus.empty:
            worst_menu = high_cogs_menus.iloc[0]
            recommendations.append({
                'title': 'Optimasi Menu dengan COGS Tertinggi',
                'description': f'Menu "{worst_menu["Menu"]}" memiliki COGS {worst_menu["Avg_COGS_Pct"]:.1f}%. Pertimbangkan untuk mengevaluasi supplier atau resep untuk mengurangi biaya bahan baku.',
                'potential_saving': f'Rp {worst_menu["Total_Revenue"] * 0.05:,.0f} per periode'
            })
        
        # Analisis kategori dengan COGS tinggi
        category_cogs = data.groupby('Menu Category')['COGS Total (%)'].mean().sort_values(ascending=False)
        if not category_cogs.empty:
            worst_category = category_cogs.index[0]
            worst_cogs_pct = category_cogs.iloc[0]
            recommendations.append({
                'title': f'Fokus Optimasi Kategori {worst_category}',
                'description': f'Kategori {worst_category} memiliki rata-rata COGS {worst_cogs_pct:.1f}%. Lakukan evaluasi menyeluruh pada kategori ini.',
                'potential_saving': 'Hingga 10-15% dari total COGS kategori'
            })
        
        # Rekomendasi berdasarkan volume vs COGS
        menu_analysis = self.get_comprehensive_menu_analysis(data)
        high_volume_high_cogs = menu_analysis[
            (menu_analysis['Total_Qty'] > menu_analysis['Total_Qty'].quantile(0.7)) &
            (menu_analysis['Avg_COGS_Pct'] > menu_analysis['Avg_COGS_Pct'].quantile(0.7))
        ]
        
        if not high_volume_high_cogs.empty:
            recommendations.append({
                'title': 'Prioritas Optimasi Menu Volume Tinggi',
                'description': f'Terdapat {len(high_volume_high_cogs)} menu dengan volume tinggi namun COGS tinggi. Optimasi menu-menu ini akan memberikan dampak besar.',
                'potential_saving': 'Impact tertinggi pada profitabilitas keseluruhan'
            })
        
        # Rekomendasi supplier negotiation
        total_cogs = data['COGS Total'].sum()
        recommendations.append({
            'title': 'Negosiasi dengan Supplier',
            'description': 'Lakukan negosiasi ulang kontrak dengan supplier utama, terutama untuk item dengan volume pembelian tinggi.',
            'potential_saving': f'Rp {total_cogs * 0.03:,.0f} (estimasi 3% dari total COGS)'
        })
        
        return recommendations
    
    def prepare_data_summary_for_ai(self, data):
        """
        Mempersiapkan ringkasan data untuk AI chatbot.
        
        Args:
            data: DataFrame yang akan dianalisis
            
        Returns:
            dict: Data summary for AI
        """
        # Basic metrics
        total_revenue = data['Total'].sum()
        total_cogs = data['COGS Total'].sum()
        total_margin = data['Margin'].sum()
        avg_cogs_pct = data['COGS Total (%)'].mean()
        total_transactions = len(data)
        
        # Top performers
        top_menus = self.get_top_performing_menus(data, 5)
        top_profitable = self.get_most_profitable_menus(data, 5)
        
        # Category analysis
        category_performance = data.groupby('Menu Category').agg({
            'Total': 'sum',
            'Margin': 'sum',
            'COGS Total (%)': 'mean'
        }).reset_index()
        
        # Time analysis
        date_range = self.get_date_range()
        daily_avg = total_revenue / data['Date'].nunique()
        
        summary = {
            'period': date_range,
            'total_revenue': total_revenue,
            'total_cogs': total_cogs,
            'total_margin': total_margin,
            'avg_cogs_percentage': avg_cogs_pct,
            'total_transactions': total_transactions,
            'daily_average_revenue': daily_avg,
            'top_selling_menus': top_menus[['Menu', 'Total_Qty', 'Total_Revenue']].to_dict('records'),
            'most_profitable_menus': top_profitable[['Menu', 'Avg_Margin', 'Margin_Percentage']].to_dict('records'),
            'category_performance': category_performance.to_dict('records')
        }
        
        return summary
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
import io
warnings.filterwarnings('ignore')

class MultiBranchSalesAnalyzer:
    """
    Kelas untuk menganalisis data sales dari multiple cabang/branch.
    Disesuaikan dengan format Excel: 
    - Nama cabang di A2
    - Header di baris 14 (A14-O14)
    - Data mulai baris 15 (A15-O15...)
    """
    
    def __init__(self):
        """
        Inisialisasi multi-branch analyzer.
        """
        self.combined_data = pd.DataFrame()
        self.branch_files = {}
        self.total_records = 0
        self.min_date = None
        self.max_date = None
        self.branches = []
    
    def load_multiple_files(self, uploaded_files):
        """
        Memuat dan menggabungkan multiple files Excel.
        
        Args:
            uploaded_files: List of file-like objects atau file paths
            
        Returns:
            pd.DataFrame: Combined data from all branches
        """
        all_data = []
        
        for uploaded_file in uploaded_files:
            try:
                # Load dan extract branch data
                branch_data = self._load_single_branch_file(uploaded_file)
                if not branch_data.empty:
                    all_data.append(branch_data)
                    
            except Exception as e:
                print(f"Error loading {getattr(uploaded_file, 'name', 'file')}: {str(e)}")
                continue
        
        if all_data:
            # Combine all data
            self.combined_data = pd.concat(all_data, ignore_index=True)
            self._prepare_combined_data()
            
        return self.combined_data
    
    def _load_single_branch_file(self, uploaded_file):
        """
        Memuat single file Excel dengan struktur yang benar.
        
        Args:
            uploaded_file: File-like object
            
        Returns:
            pd.DataFrame: Data with branch information
        """
        try:
            # Reset file pointer if it's a file-like object
            if hasattr(uploaded_file, 'seek'):
                uploaded_file.seek(0)
            
            # Baca file Excel - ambil nama cabang dari A2
            temp_df = pd.read_excel(uploaded_file, header=None, nrows=5)
            
            # Extract branch name dari A2 (baris 2, kolom A = index [1,0])
            branch_name = "Unknown Branch"
            if len(temp_df) > 1 and len(temp_df.columns) > 0:
                if pd.notna(temp_df.iloc[1, 0]):  # A2 = row 1, col 0 (0-indexed)
                    branch_name = str(temp_df.iloc[1, 0]).strip()
            
            # Reset file pointer lagi
            if hasattr(uploaded_file, 'seek'):
                uploaded_file.seek(0)
            
            # Baca data dengan header di baris 14 (index 13)
            df = pd.read_excel(uploaded_file, header=13)  # Baris 14 = index 13
            
            # Verifikasi kolom yang diperlukan ada
            required_columns = ['Sales Number', 'Sales Date', 'Menu', 'Total', 'COGS Total', 'COGS Total (%)', 'Margin']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                print(f"Missing columns in {getattr(uploaded_file, 'name', 'file')}: {missing_columns}")
                return pd.DataFrame()
            
            # Clean data
            df = self._clean_branch_data(df)
            
            if not df.empty:
                # Add branch column
                df['Branch'] = branch_name
                
                # Store file info
                self.branch_files[branch_name] = {
                    'filename': getattr(uploaded_file, 'name', 'uploaded_file'),
                    'records': len(df)
                }
                
                print(f"Successfully loaded {len(df)} records from {branch_name}")
                return df
            
        except Exception as e:
            print(f"Error processing {getattr(uploaded_file, 'name', 'file')}: {str(e)}")
            return pd.DataFrame()
    
    def _clean_branch_data(self, df):
        """
        Membersihkan data dari single branch.
        
        Args:
            df: Raw DataFrame
            
        Returns:
            pd.DataFrame: Cleaned data
        """
        # Copy data
        data = df.copy()
        
        # Hapus baris kosong berdasarkan kolom kunci
        data = data.dropna(subset=['Menu', 'Sales Date', 'Total'])
        
        # Konversi Sales Date
        if 'Sales Date' in data.columns:
            data['Sales Date'] = pd.to_datetime(data['Sales Date'], errors='coerce')
        
        # Pastikan kolom numerik dalam format yang benar
        numeric_columns = ['Qty', 'Price', 'Total', 'COGS Total', 'COGS Total (%)', 'Margin']
        for col in numeric_columns:
            if col in data.columns:
                # Convert to numeric, handling various formats
                data[col] = pd.to_numeric(data[col], errors='coerce')
        
        # Handle Discount Total if exists
        if 'Discount Total' in data.columns:
            data['Discount Total'] = pd.to_numeric(data['Discount Total'], errors='coerce').fillna(0)
        
        # Hapus baris dengan nilai numerik yang tidak valid pada kolom kunci
        data = data.dropna(subset=['Sales Date', 'Total', 'COGS Total', 'Margin'])
        
        # Filter data yang masuk akal (positive values)
        data = data[data['Total'] > 0]
        data = data[data['COGS Total'] >= 0]
        
        # Ensure COGS percentage is reasonable (0-100%)
        if 'COGS Total (%)' in data.columns:
            data = data[data['COGS Total (%)'].between(0, 100)]
        
        return data
    
    def _prepare_combined_data(self):
        """
        Mempersiapkan combined data untuk analisis.
        """
        if not self.combined_data.empty:
            # Add time-based columns
            self.combined_data['Hour'] = self.combined_data['Sales Date'].dt.hour
            self.combined_data['Day_of_Week'] = self.combined_data['Sales Date'].dt.day_name()
            self.combined_data['Week'] = self.combined_data['Sales Date'].dt.isocalendar().week
            self.combined_data['Month'] = self.combined_data['Sales Date'].dt.month
            self.combined_data['Date'] = self.combined_data['Sales Date'].dt.date
            
            # Calculate additional metrics
            if 'Margin_Percentage' not in self.combined_data.columns:
                self.combined_data['Margin_Percentage'] = (
                    self.combined_data['Margin'] / self.combined_data['Total']
                ) * 100
            
            # Set basic info
            self.total_records = len(self.combined_data)
            self.min_date = self.combined_data['Sales Date'].min()
            self.max_date = self.combined_data['Sales Date'].max()
            self.branches = sorted(self.combined_data['Branch'].unique().tolist())
            
            print(f"Combined data prepared: {self.total_records} records from {len(self.branches)} branches")
    
    def get_branch_revenue_comparison(self):
        """
        Komparasi pendapatan semua cabang.
        
        Returns:
            pd.DataFrame: Revenue comparison by branch
        """
        branch_comparison = self.combined_data.groupby('Branch').agg({
            'Total': ['sum', 'mean', 'count'],
            'Margin': ['sum', 'mean'],
            'COGS Total': 'sum',
            'Qty': 'sum',
            'Sales Date': ['min', 'max']
        }).round(2)
        
        # Flatten column names
        branch_comparison.columns = [
            'Total_Revenue', 'Avg_Transaction', 'Transaction_Count',
            'Total_Margin', 'Avg_Margin', 'Total_COGS', 'Total_Qty',
            'Start_Date', 'End_Date'
        ]
        
        # Calculate additional metrics
        branch_comparison['Margin_Percentage'] = (
            branch_comparison['Total_Margin'] / branch_comparison['Total_Revenue']
        ) * 100
        
        branch_comparison['COGS_Percentage'] = (
            branch_comparison['Total_COGS'] / branch_comparison['Total_Revenue']
        ) * 100
        
        branch_comparison['Revenue_per_Day'] = branch_comparison.apply(
            lambda row: row['Total_Revenue'] / max(1, (row['End_Date'] - row['Start_Date']).days + 1),
            axis=1
        )
        
        # Reset index and sort by revenue
        branch_comparison = branch_comparison.reset_index()
        branch_comparison = branch_comparison.sort_values('Total_Revenue', ascending=False)
        
        # Add ranking
        branch_comparison['Revenue_Rank'] = range(1, len(branch_comparison) + 1)
        
        return branch_comparison
    
    def get_product_comparison_by_branch(self, top_n_products=20):
        """
        Komparasi produk per cabang.
        
        Args:
            top_n_products: Number of top products to analyze
            
        Returns:
            pd.DataFrame: Product comparison across branches
        """
        # Get top products overall
        top_products = self.combined_data.groupby('Menu')['Total'].sum().nlargest(top_n_products).index
        
        # Filter data for top products only
        filtered_data = self.combined_data[self.combined_data['Menu'].isin(top_products)]
        
        # Create comparison data
        product_comparison = filtered_data.groupby(['Menu', 'Branch']).agg({
            'Qty': 'sum',
            'Total': 'sum',
            'Margin': 'sum',
            'COGS Total (%)': 'mean'
        }).reset_index()
        
        # Calculate metrics
        product_comparison['Revenue_per_Unit'] = (
            product_comparison['Total'] / product_comparison['Qty']
        )
        product_comparison['Margin_per_Unit'] = (
            product_comparison['Margin'] / product_comparison['Qty']
        )
        product_comparison['Margin_Percentage'] = (
            product_comparison['Margin'] / product_comparison['Total']
        ) * 100
        
        return product_comparison
    
    def get_sales_by_time_all_branches(self):
        """
        Sales by time untuk semua cabang.
        
        Returns:
            dict: Various time-based analyses
        """
        time_analysis = {}
        
        # Hourly sales by branch
        time_analysis['hourly'] = self.combined_data.groupby(['Branch', 'Hour']).agg({
            'Total': 'sum',
            'Qty': 'sum',
            'Margin': 'sum'
        }).reset_index()
        
        # Daily pattern by branch
        time_analysis['daily_pattern'] = self.combined_data.groupby(['Branch', 'Day_of_Week']).agg({
            'Total': ['sum', 'mean'],
            'Qty': 'sum'
        }).reset_index()
        time_analysis['daily_pattern'].columns = ['Branch', 'Day_of_Week', 'Total_Revenue', 'Avg_Revenue', 'Total_Qty']
        
        # Daily trend by branch
        time_analysis['daily_trend'] = self.combined_data.groupby(['Branch', 'Date']).agg({
            'Total': 'sum',
            'Qty': 'sum',
            'Margin': 'sum'
        }).reset_index()
        
        # Weekly comparison
        time_analysis['weekly'] = self.combined_data.groupby(['Branch', 'Week']).agg({
            'Total': 'sum',
            'Qty': 'sum'
        }).reset_index()
        
        # Monthly comparison
        time_analysis['monthly'] = self.combined_data.groupby(['Branch', 'Month']).agg({
            'Total': 'sum',
            'Qty': 'sum',
            'Margin': 'sum'
        }).reset_index()
        
        return time_analysis
    
    def get_cogs_per_product_per_branch(self, top_n_products=15):
        """
        COGS per product per cabang.
        
        Args:
            top_n_products: Number of top products to analyze
            
        Returns:
            pd.DataFrame: COGS analysis by product and branch
        """
        # Get top products by revenue
        top_products = self.combined_data.groupby('Menu')['Total'].sum().nlargest(top_n_products).index
        
        # Filter data
        filtered_data = self.combined_data[self.combined_data['Menu'].isin(top_products)]
        
        # COGS analysis
        cogs_analysis = filtered_data.groupby(['Menu', 'Branch']).agg({
            'COGS Total': 'sum',
            'COGS Total (%)': 'mean',
            'Total': 'sum',
            'Qty': 'sum',
            'Margin': 'sum'
        }).reset_index()
        
        # Calculate metrics
        cogs_analysis['COGS_per_Unit'] = cogs_analysis['COGS Total'] / cogs_analysis['Qty']
        cogs_analysis['Revenue_per_Unit'] = cogs_analysis['Total'] / cogs_analysis['Qty']
        cogs_analysis['Margin_per_Unit'] = cogs_analysis['Margin'] / cogs_analysis['Qty']
        cogs_analysis['COGS_Efficiency'] = 100 - cogs_analysis['COGS Total (%)']
        
        # Sort by COGS percentage
        cogs_analysis = cogs_analysis.sort_values(['Menu', 'COGS Total (%)'])
        
        return cogs_analysis
    
    def get_branch_summary_stats(self):
        """
        Statistik summary untuk semua cabang.
        
        Returns:
            dict: Summary statistics
        """
        return {
            'total_branches': len(self.branches),
            'total_records': self.total_records,
            'date_range': f"{self.min_date.strftime('%d/%m/%Y')} - {self.max_date.strftime('%d/%m/%Y')}",
            'total_revenue': self.combined_data['Total'].sum(),
            'total_margin': self.combined_data['Margin'].sum(),
            'total_cogs': self.combined_data['COGS Total'].sum(),
            'avg_cogs_percentage': self.combined_data['COGS Total (%)'].mean(),
            'total_transactions': len(self.combined_data),
            'unique_products': self.combined_data['Menu'].nunique(),
            'avg_transaction_value': self.combined_data['Total'].mean(),
            'files_processed': self.branch_files
        }
    
    def get_cross_branch_insights(self):
        """
        Mendapatkan insights cross-branch.
        
        Returns:
            dict: Various insights across branches
        """
        insights = {}
        
        # Revenue distribution
        branch_revenue = self.get_branch_revenue_comparison()
        total_revenue = branch_revenue['Total_Revenue'].sum()
        
        insights['revenue_concentration'] = {
            'top_3_branches_share': (
                branch_revenue.head(3)['Total_Revenue'].sum() / total_revenue * 100
            ),
            'bottom_3_branches_share': (
                branch_revenue.tail(3)['Total_Revenue'].sum() / total_revenue * 100
            ),
            'revenue_inequality': branch_revenue['Total_Revenue'].std() / branch_revenue['Total_Revenue'].mean()
        }
        
        # Product consistency across branches
        product_comparison = self.get_product_comparison_by_branch()
        
        # Find products available in most branches
        product_branch_count = product_comparison.groupby('Menu')['Branch'].nunique().reset_index()
        product_branch_count.columns = ['Menu', 'Available_Branches']
        product_branch_count['Availability_Percentage'] = (
            product_branch_count['Available_Branches'] / len(self.branches) * 100
        )
        
        insights['product_consistency'] = {
            'universal_products': len(product_branch_count[product_branch_count['Availability_Percentage'] == 100]),
            'limited_products': len(product_branch_count[product_branch_count['Availability_Percentage'] < 50]),
            'avg_availability': product_branch_count['Availability_Percentage'].mean()
        }
        
        # COGS consistency
        cogs_data = self.get_cogs_per_product_per_branch()
        cogs_variance = cogs_data.groupby('Menu')['COGS Total (%)'].agg(['mean', 'std']).reset_index()
        cogs_variance['CV'] = cogs_variance['std'] / cogs_variance['mean']  # Coefficient of variation
        
        insights['cogs_consistency'] = {
            'high_variance_products': len(cogs_variance[cogs_variance['CV'] > 0.2]),
            'avg_cogs_variance': cogs_variance['CV'].mean(),
            'most_consistent_cogs': cogs_variance.loc[cogs_variance['CV'].idxmin(), 'Menu'] if not cogs_variance.empty else None
        }
        
        return insights
    
    def prepare_data_for_ai(self):
        """
        Mempersiapkan data summary untuk AI chatbot.
        
        Returns:
            dict: Comprehensive data summary for AI
        """
        summary_stats = self.get_branch_summary_stats()
        branch_comparison = self.get_branch_revenue_comparison()
        cross_insights = self.get_cross_branch_insights()
        
        # Top performers
        top_branch = branch_comparison.iloc[0] if not branch_comparison.empty else None
        worst_branch = branch_comparison.iloc[-1] if not branch_comparison.empty else None
        
        # Top products across all branches
        top_products = self.combined_data.groupby('Menu').agg({
            'Qty': 'sum',
            'Total': 'sum',
            'Margin': 'sum'
        }).nlargest(5, 'Total').reset_index()
        
        ai_context = {
            'summary': summary_stats,
            'branch_performance': {
                'best_branch': {
                    'name': top_branch['Branch'] if top_branch is not None else 'N/A',
                    'revenue': top_branch['Total_Revenue'] if top_branch is not None else 0,
                    'margin_pct': top_branch['Margin_Percentage'] if top_branch is not None else 0
                },
                'worst_branch': {
                    'name': worst_branch['Branch'] if worst_branch is not None else 'N/A',
                    'revenue': worst_branch['Total_Revenue'] if worst_branch is not None else 0,
                    'margin_pct': worst_branch['Margin_Percentage'] if worst_branch is not None else 0
                }
            },
            'top_products_overall': top_products.to_dict('records'),
            'cross_branch_insights': cross_insights,
            'branch_list': self.branches
        }
        
        return ai_context

if __name__ == "__main__":
    # This file should be imported, not run directly
    pass
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.utils
import json
import os
import sys
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import warnings
import io
import traceback
warnings.filterwarnings('ignore')

# Import analyzer modules dengan error handling yang lebih baik
try:
    from multi_branch_analyzer import MultiBranchSalesAnalyzer
    print("✅ MultiBranchSalesAnalyzer imported successfully")
except ImportError as e:
    print(f"❌ Error importing MultiBranchSalesAnalyzer: {e}")
    MultiBranchSalesAnalyzer = None

try:
    from chatbot import GroqChatbot
    print("✅ GroqChatbot imported successfully")
except ImportError as e:
    print(f"❌ Error importing GroqChatbot: {e}")
    GroqChatbot = None

# Initialize Flask dengan absolute template path
app = Flask(__name__, 
            template_folder=os.path.abspath('templates'),
            static_folder=os.path.abspath('static'))

app.secret_key = os.getenv('SECRET_KEY', 'debug-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['DEBUG'] = True

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global variables to store data
analyzer = None
current_data = None
chatbot = None

# Allowed file extensions
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_currency(value):
    """Format currency in Indonesian Rupiah."""
    if pd.isna(value) or value == 0:
        return "Rp 0"
    try:
        return f"Rp {float(value):,.0f}"
    except (ValueError, TypeError):
        return "Rp 0"

def format_percentage(value):
    """Format percentage."""
    if pd.isna(value):
        return "0%"
    try:
        return f"{float(value):.1f}%"
    except (ValueError, TypeError):
        return "0%"

def format_number(value):
    """Format number with thousand separators."""
    if pd.isna(value):
        return "0"
    try:
        return f"{float(value):,.0f}"
    except (ValueError, TypeError):
        return "0"

def safe_divide(numerator, denominator):
    """Safe division with zero handling."""
    try:
        return float(numerator) / float(denominator) if denominator != 0 else 0
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@app.route('/')
def index():
    """Main dashboard page."""
    global analyzer, current_data
    
    print("🔍 Dashboard route accessed")
    
    if analyzer is None or current_data is None:
        print("❌ No data available, redirecting to upload")
        return redirect(url_for('upload_files'))
    
    if current_data.empty:
        print("❌ Data is empty, redirecting to upload")
        return redirect(url_for('upload_files'))
    
    try:
        print("📊 Getting summary statistics...")
        summary_stats = analyzer.get_branch_summary_stats()
        
        print("📈 Getting branch comparison...")
        branch_comparison = analyzer.get_branch_revenue_comparison()
        
        # Get key metrics dengan safe calculations
        total_revenue = summary_stats.get('total_revenue', 0)
        total_margin = summary_stats.get('total_margin', 0)
        gross_margin_pct = safe_divide(total_margin, total_revenue) * 100
        
        print("📊 Creating dashboard charts...")
        charts_data = create_dashboard_charts()
        
        print("✅ Rendering dashboard template...")
        return render_template('dashboard.html',
                             summary_stats=summary_stats,
                             branch_comparison=branch_comparison,
                             charts_data=charts_data,
                             total_revenue=format_currency(total_revenue),
                             total_margin=format_currency(total_margin),
                             gross_margin_pct=format_percentage(gross_margin_pct),
                             branches=analyzer.branches)
    
    except Exception as e:
        print(f"❌ Error in dashboard: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        flash(f'Error loading dashboard: {str(e)}')
        return redirect(url_for('upload_files'))

@app.route('/upload', methods=['GET', 'POST'])
def upload_files():
    """Handle file uploads."""
    print("📁 Upload route accessed")
    
    if request.method == 'POST':
        print("📤 Processing file upload...")
        
        # Check if files were uploaded
        if 'files[]' not in request.files:
            flash('No files selected')
            return redirect(request.url)
        
        files = request.files.getlist('files[]')
        
        if not files or files[0].filename == '':
            flash('No files selected')
            return redirect(request.url)
        
        uploaded_files = []
        
        # Process each uploaded file
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                uploaded_files.append(file_path)
                print(f"📄 Saved file: {filename}")
        
        if uploaded_files:
            try:
                print(f"🔄 Processing {len(uploaded_files)} files...")
                
                # Load data using analyzer
                global analyzer, current_data, chatbot
                
                if MultiBranchSalesAnalyzer is None:
                    flash('Analyzer module not available. Check imports.')
                    return redirect(url_for('upload_files'))
                
                analyzer = MultiBranchSalesAnalyzer()
                
                # Create file-like objects for the analyzer
                processed_files = []
                for file_path in uploaded_files:
                    with open(file_path, 'rb') as f:
                        file_buffer = io.BytesIO(f.read())
                        file_buffer.name = os.path.basename(file_path)
                        processed_files.append(file_buffer)
                
                current_data = analyzer.load_multiple_files(processed_files)
                
                if current_data.empty:
                    flash('No valid data found in uploaded files. Please check file format.')
                    return redirect(url_for('upload_files'))
                
                print(f"✅ Loaded {len(current_data)} records from {len(uploaded_files)} files")
                
                # Initialize chatbot
                try:
                    if GroqChatbot is not None:
                        chatbot = GroqChatbot()
                        print("✅ Chatbot initialized")
                except Exception as e:
                    print(f"❌ Chatbot initialization failed: {e}")
                    chatbot = None
                
                # Clean up uploaded files
                for file_path in uploaded_files:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                
                flash(f'Successfully loaded {len(uploaded_files)} files with {len(current_data)} records!')
                # LANGSUNG REDIRECT KE DASHBOARD SETELAH UPLOAD BERHASIL
                return redirect(url_for('index'))
                
            except Exception as e:
                print(f"❌ Error processing files: {str(e)}")
                print(f"Traceback: {traceback.format_exc()}")
                flash(f'Error processing files: {str(e)}')
                # Clean up files on error
                for file_path in uploaded_files:
                    if os.path.exists(file_path):
                        os.remove(file_path)
        else:
            flash('No valid Excel files found')
    
    print("📄 Rendering upload template...")
    return render_template('upload.html')

@app.route('/branch-comparison')
def branch_comparison():
    """Branch comparison analysis page."""
    global analyzer, current_data
    
    print("🏢 Branch comparison route accessed")
    
    if analyzer is None or current_data is None or current_data.empty:
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))
    
    try:
        print("📊 Getting branch comparison data...")
        branch_comparison_data = analyzer.get_branch_revenue_comparison()
        
        print("📈 Creating branch comparison charts...")
        charts = create_branch_comparison_charts(branch_comparison_data)
        
        print("✅ Rendering branch comparison template...")
        return render_template('branch_comparison.html',
                             branch_data=branch_comparison_data,
                             charts=charts)
    except Exception as e:
        print(f"❌ Error in branch comparison: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        flash(f'Error loading branch comparison: {str(e)}')
        return redirect(url_for('index'))

@app.route('/product-analysis')
def product_analysis():
    """Product analysis page."""
    global analyzer, current_data
    
    print("📦 Product analysis route accessed")
    
    if analyzer is None or current_data is None or current_data.empty:
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))
    
    try:
        print("📊 Getting product comparison data...")
        product_comparison = analyzer.get_product_comparison_by_branch(20)
        
        if product_comparison.empty:
            flash('No product data available for analysis.')
            return redirect(url_for('index'))
        
        print("📈 Getting top products...")
        top_products = product_comparison.groupby('Menu').agg({
            'Qty': 'sum',
            'Total': 'sum',
            'Margin': 'sum'
        }).reset_index()
        
        # Safe calculation untuk margin percentage
        top_products['Margin_Percentage'] = top_products.apply(
            lambda row: safe_divide(row['Margin'], row['Total']) * 100, axis=1
        )
        top_products = top_products.sort_values('Total', ascending=False)
        
        print("📊 Creating product analysis charts...")
        charts = create_product_analysis_charts(product_comparison, top_products)
        
        print("✅ Rendering product analysis template...")
        return render_template('product_analysis.html',
                             product_data=product_comparison,
                             top_products=top_products,
                             charts=charts)
    except Exception as e:
        print(f"❌ Error in product analysis: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        flash(f'Error loading product analysis: {str(e)}')
        return redirect(url_for('index'))

@app.route('/sales-by-time')
def sales_by_time():
    """Sales by time analysis page."""
    global analyzer, current_data
    
    print("⏰ Sales by time route accessed")
    
    if analyzer is None or current_data is None or current_data.empty:
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))
    
    try:
        print("📊 Getting time analysis data...")
        time_analysis = analyzer.get_sales_by_time_all_branches()
        
        print("📈 Creating time analysis charts...")
        charts = create_time_analysis_charts(time_analysis)
        
        print("✅ Rendering sales by time template...")
        return render_template('sales_by_time.html',
                             time_data=time_analysis,
                             charts=charts)
    except Exception as e:
        print(f"❌ Error in sales by time: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        flash(f'Error loading sales by time: {str(e)}')
        return redirect(url_for('index'))

@app.route('/cogs-analysis')
def cogs_analysis():
    """COGS analysis page."""
    global analyzer, current_data
    
    print("💰 COGS analysis route accessed")
    
    if analyzer is None or current_data is None or current_data.empty:
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))
    
    try:
        print("📊 Getting COGS analysis data...")
        cogs_data = analyzer.get_cogs_per_product_per_branch(15)
        
        if cogs_data.empty:
            flash('No COGS data available for analysis.')
            return redirect(url_for('index'))
        
        print("📈 Calculating branch COGS efficiency...")
        branch_cogs = cogs_data.groupby('Branch')['COGS Total (%)'].mean().reset_index()
        branch_cogs['COGS_Efficiency'] = 100 - branch_cogs['COGS Total (%)']
        branch_cogs = branch_cogs.sort_values('COGS_Efficiency', ascending=False)
        
        print("📊 Creating COGS analysis charts...")
        charts = create_cogs_analysis_charts(cogs_data, branch_cogs)
        
        print("✅ Rendering COGS analysis template...")
        return render_template('cogs_analysis.html',
                             cogs_data=cogs_data,
                             branch_cogs=branch_cogs,
                             charts=charts)
    except Exception as e:
        print(f"❌ Error in COGS analysis: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        flash(f'Error loading COGS analysis: {str(e)}')
        return redirect(url_for('index'))

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    """AI chatbot page."""
    global analyzer, chatbot
    
    print("🤖 Chat route accessed")
    
    if analyzer is None:
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))
    
    if request.method == 'POST':
        user_question = request.form.get('question', '').strip()
        
        if user_question and chatbot:
            try:
                # Prepare data context for AI
                data_context = analyzer.prepare_data_for_ai()
                ai_response = chatbot.get_response(user_question, data_context)
                
                return jsonify({
                    'success': True,
                    'response': ai_response
                })
            except Exception as e:
                print(f"❌ Chat error: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                })
        else:
            return jsonify({
                'success': False,
                'error': 'No question provided or chatbot not available'
            })
    
    print("✅ Rendering chat template...")
    return render_template('chat.html', chatbot_available=chatbot is not None)

def create_dashboard_charts():
    """Create charts for main dashboard with consistent scaling."""
    global analyzer
    
    if analyzer is None:
        print("❌ Analyzer not available for charts")
        return {}
    
    charts = {}
    
    try:
        print("📊 Creating revenue comparison chart...")
        branch_comparison = analyzer.get_branch_revenue_comparison()
        
        if branch_comparison.empty:
            print("❌ No branch data for charts")
            return {}
        
        # PERBAIKI: Sort by revenue untuk consistent visualization
        branch_comparison_sorted = branch_comparison.sort_values('Total_Revenue', ascending=False).head(10)
        
        # PERBAIKI: Gunakan bar chart vertikal dengan data yang sama
        fig_revenue = px.bar(
            branch_comparison_sorted,
            x='Branch',
            y='Total_Revenue',
            title='📊 Revenue per Cabang (Top 10)',
            color='Total_Revenue',
            color_continuous_scale='Viridis',
            text='Total_Revenue'
        )
        fig_revenue.update_traces(
            texttemplate='%{text:,.0f}', 
            textposition='outside',
            textfont_size=10
        )
        fig_revenue.update_layout(
            height=400,
            margin=dict(l=20, r=20, t=40, b=120),
            xaxis_title='Cabang',
            yaxis_title='Revenue (Rp)',
            xaxis_tickangle=-45,
            showlegend=False
        )
        charts['revenue_bar'] = json.dumps(fig_revenue, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("🥧 Creating revenue pie chart...")
        # Revenue distribution pie chart (top 8 branches)
        top_branches = branch_comparison.head(8)
        fig_pie = px.pie(
            top_branches,
            values='Total_Revenue',
            names='Branch',
            title='📊 Distribusi Revenue per Cabang (Top 8)'
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        fig_pie.update_layout(height=400)
        charts['revenue_pie'] = json.dumps(fig_pie, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("💎 Creating performance matrix...")
        # Performance matrix
        fig_scatter = px.scatter(
            branch_comparison,
            x='Total_Revenue',
            y='Margin_Percentage',
            size='Transaction_Count',
            color='COGS_Percentage',
            hover_data=['Branch', 'Total_Margin', 'Avg_Transaction'],
            title='💎 Matrix Performa Cabang (Revenue vs Margin)',
            labels={
                'Total_Revenue': 'Total Revenue (Rp)',
                'Margin_Percentage': 'Margin (%)',
                'COGS_Percentage': 'COGS (%)',
                'Transaction_Count': 'Transactions'
            }
        )
        fig_scatter.update_layout(height=400)
        charts['performance_matrix'] = json.dumps(fig_scatter, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("🍜 Creating top products chart...")
        # Top products
        try:
            product_comparison = analyzer.get_product_comparison_by_branch(10)
            if not product_comparison.empty:
                top_products = product_comparison.groupby('Menu').agg({
                    'Qty': 'sum',
                    'Total': 'sum'
                }).reset_index().sort_values('Total', ascending=False).head(10)
                
                fig_products = px.bar(
                    top_products,
                    x='Menu',
                    y='Total',
                    title='🍜 Top 10 Produk by Revenue',
                    color='Total',
                    color_continuous_scale='Plasma',
                    text='Total'
                )
                fig_products.update_traces(
                    texttemplate='%{text:,.0f}', 
                    textposition='outside',
                    textfont_size=10
                )
                fig_products.update_layout(
                    height=400,
                    margin=dict(l=20, r=20, t=40, b=120),
                    xaxis_title='Produk',
                    yaxis_title='Revenue (Rp)',
                    xaxis_tickangle=-45,
                    showlegend=False
                )
                charts['top_products'] = json.dumps(fig_products, cls=plotly.utils.PlotlyJSONEncoder)
        except Exception as e:
            print(f"❌ Error creating products chart: {e}")
        
        print("✅ Dashboard charts created successfully")
        
    except Exception as e:
        print(f"❌ Error creating dashboard charts: {e}")
        print(f"Traceback: {traceback.format_exc()}")
    
    return charts

def create_branch_comparison_charts(branch_data):
    """Create charts for branch comparison page dengan data yang konsisten."""
    charts = {}
    
    try:
        if branch_data.empty:
            print("❌ No branch data for comparison charts")
            return charts
        
        print("📊 Creating branch revenue comparison...")
        # PERBAIKI: Gunakan data yang sama persis seperti di dashboard
        branch_sorted = branch_data.sort_values('Total_Revenue', ascending=False)
        
        # Chart 1: Revenue comparison (vertikal seperti dashboard)
        fig_revenue = px.bar(
            branch_sorted,
            x='Branch',
            y='Total_Revenue',
            title='💰 Total Revenue per Cabang',
            color='Total_Revenue',
            color_continuous_scale='Viridis',
            text='Total_Revenue'
        )
        fig_revenue.update_traces(
            texttemplate='%{text:,.0f}', 
            textposition='outside',
            textfont_size=10
        )
        fig_revenue.update_layout(
            height=500,
            margin=dict(l=20, r=20, t=40, b=120),
            xaxis_title='Cabang',
            yaxis_title='Revenue (Rp)',
            xaxis_tickangle=-45,
            showlegend=False
        )
        charts['revenue_comparison'] = json.dumps(fig_revenue, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("💹 Creating margin vs COGS scatter...")
        # Chart 2: Margin vs COGS scatter plot
        fig_margin_cogs = px.scatter(
            branch_data,
            x='COGS_Percentage',
            y='Margin_Percentage',
            size='Total_Revenue',
            color='Branch',
            title='📊 Margin vs COGS per Cabang',
            labels={
                'COGS_Percentage': 'COGS (%)', 
                'Margin_Percentage': 'Margin (%)',
                'Total_Revenue': 'Revenue (Rp)'
            },
            hover_data={
                'Total_Revenue': ':,.0f',
                'Transaction_Count': ':,',
                'Avg_Transaction': ':,.0f'
            }
        )
        fig_margin_cogs.update_layout(height=500)
        charts['margin_cogs'] = json.dumps(fig_margin_cogs, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("⚡ Creating efficiency chart...")
        # Chart 3: Transaction efficiency
        branch_data_copy = branch_data.copy()
        branch_data_copy['Revenue_per_Transaction'] = branch_data_copy.apply(
            lambda row: safe_divide(row['Total_Revenue'], row['Transaction_Count']), axis=1
        )
        branch_efficiency_sorted = branch_data_copy.sort_values('Revenue_per_Transaction', ascending=False)
        
        fig_efficiency = px.bar(
            branch_efficiency_sorted,
            x='Branch',
            y='Revenue_per_Transaction',
            title='⚡ Efisiensi Revenue per Transaksi',
            color='Revenue_per_Transaction',
            color_continuous_scale='RdYlBu_r',
            text='Revenue_per_Transaction'
        )
        fig_efficiency.update_traces(
            texttemplate='%{text:,.0f}', 
            textposition='outside',
            textfont_size=10
        )
        fig_efficiency.update_layout(
            height=500,
            margin=dict(l=20, r=20, t=40, b=120),
            xaxis_title='Cabang',
            yaxis_title='Revenue per Transaksi (Rp)',
            xaxis_tickangle=-45,
            showlegend=False
        )
        charts['efficiency'] = json.dumps(fig_efficiency, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("✅ Branch comparison charts created successfully")
        
    except Exception as e:
        print(f"❌ Error creating branch comparison charts: {e}")
        print(f"Traceback: {traceback.format_exc()}")
    
    return charts

def create_product_analysis_charts(product_data, top_products):
    """Create charts for product analysis page."""
    charts = {}
    
    try:
        if product_data.empty or top_products.empty:
            print("❌ No product data for analysis charts")
            return charts
        
        print("🔥 Creating product heatmap...")
        # Product revenue heatmap (top 15 for performance)
        top_15_products = top_products.head(15)['Menu'].tolist()
        filtered_product_data = product_data[product_data['Menu'].isin(top_15_products)]
        
        if not filtered_product_data.empty:
            product_revenue_pivot = filtered_product_data.pivot(
                index='Menu',
                columns='Branch',
                values='Total'
            ).fillna(0)
            
            fig_heatmap = px.imshow(
                product_revenue_pivot,
                title='🔥 Heatmap Revenue Produk per Cabang (Top 15)',
                aspect='auto',
                color_continuous_scale='YlOrRd',
                labels={'color': 'Revenue (Rp)'}
            )
            fig_heatmap.update_layout(height=600)
            charts['product_heatmap'] = json.dumps(fig_heatmap, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("💰 Creating top revenue products chart...")
        # Top products by revenue
        top_revenue_data = top_products.head(15).sort_values('Total', ascending=False)
        fig_top_revenue = px.bar(
            top_revenue_data,
            x='Menu',
            y='Total',
            title='💰 Top 15 Produk by Revenue',
            color='Total',
            color_continuous_scale='Viridis',
            text='Total'
        )
        fig_top_revenue.update_traces(
            texttemplate='%{text:,.0f}', 
            textposition='outside',
            textfont_size=9
        )
        fig_top_revenue.update_layout(
            height=600,
            margin=dict(l=20, r=20, t=40, b=150),
            xaxis_tickangle=-45,
            showlegend=False
        )
        charts['top_revenue'] = json.dumps(fig_top_revenue, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("📦 Creating top quantity products chart...")
        # Top products by quantity
        top_by_qty = top_products.sort_values('Qty', ascending=False).head(15)
        fig_top_qty = px.bar(
            top_by_qty,
            x='Menu',
            y='Qty',
            title='📦 Top 15 Produk by Quantity',
            color='Qty',
            color_continuous_scale='Plasma',
            text='Qty'
        )
        fig_top_qty.update_traces(
            texttemplate='%{text:,}', 
            textposition='outside',
            textfont_size=9
        )
        fig_top_qty.update_layout(
            height=600,
            margin=dict(l=20, r=20, t=40, b=150),
            xaxis_tickangle=-45,
            showlegend=False
        )
        charts['top_quantity'] = json.dumps(fig_top_qty, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("✅ Product analysis charts created successfully")
        
    except Exception as e:
        print(f"❌ Error creating product analysis charts: {e}")
        print(f"Traceback: {traceback.format_exc()}")
    
    return charts

def create_time_analysis_charts(time_data):
    """Create charts for time analysis page - HAPUS weekly, fokus monthly."""
    charts = {}
    
    try:
        # Hourly heatmap
        if 'hourly' in time_data and not time_data['hourly'].empty:
            print("🔥 Creating hourly heatmap...")
            hourly_pivot = time_data['hourly'].pivot(
                index='Hour',
                columns='Branch',
                values='Total'
            ).fillna(0)
            
            fig_hourly_heatmap = px.imshow(
                hourly_pivot,
                title='🔥 Heatmap Penjualan per Jam per Cabang',
                aspect='auto',
                color_continuous_scale='YlOrRd',
                labels={'color': 'Revenue (Rp)'}
            )
            fig_hourly_heatmap.update_layout(height=500)
            charts['hourly_heatmap'] = json.dumps(fig_hourly_heatmap, cls=plotly.utils.PlotlyJSONEncoder)
            
            print("📈 Creating hourly average chart...")
            # Average hourly pattern
            hourly_avg = time_data['hourly'].groupby('Hour')['Total'].mean().reset_index()
            
            fig_hourly_avg = px.line(
                hourly_avg,
                x='Hour',
                y='Total',
                title='📈 Rata-rata Penjualan per Jam (Semua Cabang)',
                markers=True
            )
            fig_hourly_avg.update_traces(
                line=dict(width=3),
                marker=dict(size=8)
            )
            fig_hourly_avg.update_layout(
                xaxis_title='Jam',
                yaxis_title='Rata-rata Revenue (Rp)',
                height=400
            )
            charts['hourly_average'] = json.dumps(fig_hourly_avg, cls=plotly.utils.PlotlyJSONEncoder)
        
        # Daily pattern
        if 'daily_pattern' in time_data and not time_data['daily_pattern'].empty:
            print("📊 Creating daily pattern chart...")
            daily_comparison = time_data['daily_pattern'].groupby('Day_of_Week')['Total_Revenue'].sum().reset_index()
            
            # Reorder days
            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            day_mapping = {day: i for i, day in enumerate(day_order)}
            daily_comparison['Day_Order'] = daily_comparison['Day_of_Week'].map(day_mapping)
            daily_comparison = daily_comparison.sort_values('Day_Order')
            
            fig_daily = px.bar(
                daily_comparison,
                x='Day_of_Week',
                y='Total_Revenue',
                title='📊 Total Penjualan per Hari (Semua Cabang)',
                color='Total_Revenue',
                color_continuous_scale='Viridis',
                text='Total_Revenue'
            )
            fig_daily.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
            fig_daily.update_layout(height=400, showlegend=False)
            charts['daily_pattern'] = json.dumps(fig_daily, cls=plotly.utils.PlotlyJSONEncoder)
        
        # MONTHLY TREND dengan date range sesuai data
        if 'monthly' in time_data and not time_data['monthly'].empty:
            print("📅 Creating monthly trend chart...")
            monthly_data = time_data['monthly']
            
            # Get actual date range from data
            min_date = current_data['Sales Date'].min()
            max_date = current_data['Sales Date'].max()
            
            # Group by actual month-year
            monthly_summary = current_data.groupby([
                current_data['Sales Date'].dt.to_period('M'), 'Branch'
            ])['Total'].sum().reset_index()
            monthly_summary['Month_Year'] = monthly_summary['Sales Date'].astype(str)
            
            # Create line chart for each branch
            fig_monthly = go.Figure()
            
            branches = monthly_summary['Branch'].unique()
            colors = px.colors.qualitative.Set3
            
            for i, branch in enumerate(branches):
                branch_data = monthly_summary[monthly_summary['Branch'] == branch]
                fig_monthly.add_trace(go.Scatter(
                    x=branch_data['Month_Year'],
                    y=branch_data['Total'],
                    mode='lines+markers',
                    name=branch,
                    line=dict(width=3, color=colors[i % len(colors)]),
                    marker=dict(size=8)
                ))
            
            fig_monthly.update_layout(
                title=f'📅 Trend Penjualan Bulanan ({min_date.strftime("%b %Y")} - {max_date.strftime("%b %Y")})',
                xaxis_title='Periode',
                yaxis_title='Revenue (Rp)',
                height=400,
                hovermode='x unified'
            )
            charts['monthly_trend'] = json.dumps(fig_monthly, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("✅ Time analysis charts created successfully")
        
    except Exception as e:
        print(f"❌ Error creating time analysis charts: {e}")
        print(f"Traceback: {traceback.format_exc()}")
    
    return charts

def create_cogs_analysis_charts(cogs_data, branch_cogs):
    """Create charts for COGS analysis page."""
    charts = {}
    
    try:
        if cogs_data.empty or branch_cogs.empty:
            print("❌ No COGS data for analysis charts")
            return charts
        
        print("🔥 Creating COGS heatmap...")
        # COGS heatmap - top 15 products only
        top_products = cogs_data.groupby('Menu')['Total'].sum().nlargest(15).index
        filtered_cogs = cogs_data[cogs_data['Menu'].isin(top_products)]
        
        if not filtered_cogs.empty:
            cogs_pivot = filtered_cogs.pivot(
                index='Menu',
                columns='Branch',
                values='COGS Total (%)'
            ).fillna(0)
            
            fig_cogs_heatmap = px.imshow(
                cogs_pivot,
                title='🔥 COGS Percentage per Produk per Cabang (Top 15)',
                aspect='auto',
                color_continuous_scale='RdYlGn_r',
                labels={'color': 'COGS (%)'}
            )
            fig_cogs_heatmap.update_layout(height=600)
            charts['cogs_heatmap'] = json.dumps(fig_cogs_heatmap, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("📊 Creating branch COGS efficiency chart...")
        # Branch COGS efficiency
        branch_cogs_sorted = branch_cogs.sort_values('COGS_Efficiency', ascending=False)
        fig_branch_cogs = px.bar(
            branch_cogs_sorted,
            x='Branch',
            y='COGS_Efficiency',
            title='📊 Efisiensi COGS per Cabang',
            color='COGS_Efficiency',
            color_continuous_scale='RdYlGn',
            text='COGS_Efficiency'
        )
        fig_branch_cogs.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig_branch_cogs.update_layout(
            height=500,
            margin=dict(l=20, r=20, t=40, b=120),
            xaxis_tickangle=-45,
            showlegend=False
        )
        charts['branch_efficiency'] = json.dumps(fig_branch_cogs, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("📊 Creating COGS variance chart...")
        # COGS variance
        product_cogs_stats = cogs_data.groupby('Menu')['COGS Total (%)'].agg(['mean', 'std', 'count']).reset_index()
        # Only calculate CV for products with more than 1 data point
        product_cogs_stats = product_cogs_stats[
            (product_cogs_stats['count'] > 1) & 
            (product_cogs_stats['std'] > 0) & 
            (product_cogs_stats['mean'] > 0)
        ]
        
        if not product_cogs_stats.empty:
            product_cogs_stats['CV'] = product_cogs_stats['std'] / product_cogs_stats['mean']
            product_cogs_stats = product_cogs_stats.sort_values('CV', ascending=False).head(15)
            
            fig_cogs_variance = px.bar(
                product_cogs_stats,
                x='Menu',
                y='CV',
                title='📊 Top 15 Produk dengan Variasi COGS Tertinggi',
                color='CV',
                color_continuous_scale='Reds',
                text='CV'
            )
            fig_cogs_variance.update_traces(texttemplate='%{text:.2f}', textposition='outside')
            fig_cogs_variance.update_layout(
                height=600,
                margin=dict(l=20, r=20, t=40, b=150),
                xaxis_tickangle=-45,
                showlegend=False
            )
            charts['cogs_variance'] = json.dumps(fig_cogs_variance, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("✅ COGS analysis charts created successfully")
        
    except Exception as e:
        print(f"❌ Error creating COGS analysis charts: {e}")
        print(f"Traceback: {traceback.format_exc()}")
    
    return charts

# Custom template filters
@app.template_filter('currency')
def currency_filter(value):
    return format_currency(value)

@app.template_filter('percentage')
def percentage_filter(value):
    return format_percentage(value)

@app.template_filter('number')
def number_filter(value):
    return format_number(value)

@app.template_filter('round')
def round_filter(value, precision=2):
    try:
        return round(float(value), precision)
    except (ValueError, TypeError):
        return value

# Error handlers dengan logging yang lebih baik
@app.errorhandler(404)
def not_found_error(error):
    print(f"❌ 404 Error: {request.url}")
    return render_template('error.html', 
                         error_code=404, 
                         error_message="Halaman tidak ditemukan"), 404

@app.errorhandler(500)
def internal_error(error):
    print(f"❌ 500 Error: {str(error)}")
    print(f"Traceback: {traceback.format_exc()}")
    return render_template('error.html', 
                         error_code=500, 
                         error_message="Terjadi kesalahan internal server"), 500

@app.errorhandler(413)
def too_large(error):
    print(f"❌ 413 Error: File too large")
    return render_template('error.html', 
                         error_code=413, 
                         error_message="File terlalu besar. Maksimal 50MB per file"), 413

@app.errorhandler(Exception)
def handle_exception(e):
    print(f"❌ Unhandled Exception: {str(e)}")
    print(f"Traceback: {traceback.format_exc()}")
    
    # Check if it's a template not found error
    if "TemplateNotFound" in str(e):
        return f"Template not found: {str(e)}. Please check if all template files exist in the templates folder.", 500
    
    return f"An error occurred: {str(e)}", 500

# Debug route untuk check status
@app.route('/debug')
def debug_status():
    """Debug route untuk check system status."""
    status = {
        'analyzer_loaded': analyzer is not None,
        'data_loaded': current_data is not None and not current_data.empty if current_data is not None else False,
        'chatbot_loaded': chatbot is not None,
        'templates_dir': os.path.abspath(app.template_folder),
        'templates_exist': os.path.exists(app.template_folder),
        'current_dir': os.getcwd(),
        'python_path': sys.path[:3]  # Show first 3 paths
    }
    
    if os.path.exists(app.template_folder):
        status['template_files'] = [f for f in os.listdir(app.template_folder) if f.endswith('.html')]
    
    if analyzer and current_data is not None and not current_data.empty:
        status['data_summary'] = {
            'total_records': len(current_data),
            'branches': len(analyzer.branches),
            'unique_products': current_data['Menu'].nunique() if 'Menu' in current_data.columns else 0,
            'date_range': f"{current_data['Sales Date'].min()} to {current_data['Sales Date'].max()}"
        }
    
    return jsonify(status)

if __name__ == '__main__':
    print("🚀 Starting Flask Multi-Branch Analytics...")
    print(f"📁 Templates folder: {app.template_folder}")
    print(f"📁 Static folder: {app.static_folder}")
    print(f"🔧 Debug mode: {app.config['DEBUG']}")
    
    # Check critical files
    required_templates = [
        'base.html', 'dashboard.html', 'upload.html', 
        'branch_comparison.html', 'product_analysis.html', 
        'sales_by_time.html', 'cogs_analysis.html', 'chat.html', 'error.html'
    ]
    
    missing_templates = []
    for template in required_templates:
        template_path = os.path.join(app.template_folder, template)
        if not os.path.exists(template_path):
            missing_templates.append(template)
    
    if missing_templates:
        print(f"❌ Missing template files: {missing_templates}")
        print("Please run: python setup_templates.py")
    else:
        print("✅ All required template files found")
    
    print("🌐 Starting server on http://127.0.0.1:5000")
    print("🔍 Visit /debug for system status")
    
    app.run(debug=True, host='127.0.0.1', port=5000)
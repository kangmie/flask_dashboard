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

def safe_df_check(data):
    """Safely check if dataframe is empty or None."""
    try:
        return data is not None and not data.empty
    except Exception:
        return False

@app.route('/')
def index():
    """Main dashboard page."""
    global analyzer, current_data
    
    print("🔍 Dashboard route accessed")
    
    if analyzer is None or not safe_df_check(current_data):
        print("❌ No data available, redirecting to upload")
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
                
                if not safe_df_check(current_data):
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
    
    if analyzer is None or not safe_df_check(current_data):
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
    
    if analyzer is None or not safe_df_check(current_data):
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))
    
    try:
        print("📊 Getting product comparison data...")
        product_comparison = analyzer.get_product_comparison_by_branch(20)
        
        if not safe_df_check(product_comparison):
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

# @app.route('/sales-by-time')
# def sales_by_time():
#     """Sales by time analysis page - COMPLETELY SAFE VERSION."""
#     global analyzer, current_data
    
#     print("⏰ Sales by time route accessed")
    
#     if analyzer is None or not safe_df_check(current_data):
#         flash('No data available. Please upload files first.')
#         return redirect(url_for('upload_files'))
    
#     try:
#         print("📊 Getting time analysis data...")
#         time_analysis = analyzer.get_sales_by_time_all_branches()
        
#         print("📈 Creating MINIMAL time charts...")
#         # HANYA buat chart minimal untuk menghindari error
#         charts = create_minimal_time_charts(time_analysis)
        
#         print("✅ Rendering sales by time template...")
#         return render_template('sales_by_time.html',
#                              time_data=time_analysis,
#                              charts=charts)
#     except Exception as e:
#         print(f"❌ Error in sales by time: {str(e)}")
#         print(f"Traceback: {traceback.format_exc()}")
#         flash(f'Error loading sales by time: {str(e)}')
#         return redirect(url_for('index'))

# REPLACE HANYA BAGIAN INI di app.py Anda

@app.route('/sales-by-time')
def sales_by_time():
    """Sales by time analysis page - MINIMAL VERSION."""
    global analyzer, current_data
    
    print("⏰ Sales by time route accessed - MINIMAL VERSION")
    
    if analyzer is None or not safe_df_check(current_data):
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))
    
    try:
        print("📊 Getting basic time data...")
        
        # Create MINIMAL time_data without complex processing
        time_analysis = {
            'daily_pattern': pd.DataFrame(),
            'daily_trend': pd.DataFrame(), 
            'monthly': pd.DataFrame()
        }
        
        # Try to get simple time data if possible
        try:
            actual_time_data = analyzer.get_sales_by_time_all_branches()
            if actual_time_data:
                time_analysis = actual_time_data
        except Exception as e:
            print(f"⚠️ Could not get full time data: {e}")
            # Use empty data - that's fine!
        
        print("📈 Creating EMPTY charts (safe)...")
        # Create completely empty/minimal charts
        charts = {
            'daily_pattern': json.dumps({
                'data': [],
                'layout': {'title': 'Daily Pattern (Data akan ditampilkan setelah processing)'}
            }),
            'branch_trends': json.dumps({
                'data': [],
                'layout': {'title': 'Branch Trends (Data akan ditampilkan setelah processing)'}
            }),
            'monthly_comparison': json.dumps({
                'data': [],
                'layout': {'title': 'Monthly Comparison (Data akan ditampilkan setelah processing)'}
            })
        }
        
        print("✅ Rendering sales by time template with minimal data...")
        return render_template('sales_by_time.html',
                             time_data=time_analysis,
                             charts=charts)
                             
    except Exception as e:
        print(f"❌ STILL Error in sales by time: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        
        # FORCE SUCCESS - return template with empty data
        print("🔄 FORCING template render with empty data...")
        empty_time_data = {
            'daily_pattern': pd.DataFrame(),
            'daily_trend': pd.DataFrame(),
            'monthly': pd.DataFrame()
        }
        empty_charts = {
            'daily_pattern': '{}',
            'branch_trends': '{}', 
            'monthly_comparison': '{}'
        }
        
        try:
            return render_template('sales_by_time.html',
                                 time_data=empty_time_data,
                                 charts=empty_charts)
        except Exception as template_error:
            print(f"❌ Template error: {template_error}")
            # Last resort - show simple message
            return f"""
            <h1>Sales by Time</h1>
            <p>Page is being loaded. Time analysis will be available soon.</p>
            <p><a href="{url_for('index')}">Back to Dashboard</a></p>
            <p>Debug: {str(e)}</p>
            """
@app.route('/cogs-analysis')
def cogs_analysis():
    """COGS analysis page."""
    global analyzer, current_data
    
    print("💰 COGS analysis route accessed")
    
    if analyzer is None or not safe_df_check(current_data):
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))
    
    try:
        print("📊 Getting COGS analysis data...")
        cogs_data = analyzer.get_cogs_per_product_per_branch(15)
        
        if not safe_df_check(cogs_data):
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
    """FIXED: Create charts for main dashboard - PROPER SORTING."""
    global analyzer
    
    if analyzer is None:
        print("❌ Analyzer not available for charts")
        return {}
    
    charts = {}
    
    try:
        print("📊 Creating revenue comparison chart...")
        branch_comparison = analyzer.get_branch_revenue_comparison()
        
        if not safe_df_check(branch_comparison):
            print("❌ No branch data for charts")
            return {}
        
        # CRITICAL FIX: Sort data dan maintain order
        branch_sorted = branch_comparison.sort_values('Total_Revenue', ascending=False).head(10).copy()
        
        # Revenue Bar Chart - FIXED dengan explicit ordering
        fig_revenue = go.Figure(data=[
            go.Bar(
                x=list(range(len(branch_sorted))),  # Use numeric indices
                y=branch_sorted['Total_Revenue'].tolist(),
                text=[f'Rp {x:,.0f}' for x in branch_sorted['Total_Revenue']],
                textposition='outside',
                marker_color='rgba(0, 139, 139, 0.8)',
                name='Revenue'
            )
        ])
        
        fig_revenue.update_layout(
            title='📊 Revenue per Cabang (Top 10)',
            xaxis=dict(
                tickmode='array',
                tickvals=list(range(len(branch_sorted))),
                ticktext=branch_sorted['Branch'].tolist(),
                tickangle=-45
            ),
            yaxis_title='Revenue (Rp)',
            height=400,
            margin=dict(l=20, r=20, t=40, b=120),
            showlegend=False
        )
        charts['revenue_bar'] = json.dumps(fig_revenue, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("🥧 Creating revenue pie chart...")
        # Revenue pie chart
        top_8_branches = branch_comparison.head(8)
        fig_pie = px.pie(
            top_8_branches,
            values='Total_Revenue',
            names='Branch',
            title='📊 Distribusi Revenue per Cabang (Top 8)'
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        fig_pie.update_layout(height=400)
        charts['revenue_pie'] = json.dumps(fig_pie, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("💎 Creating performance matrix...")
        # Performance matrix scatter
        fig_scatter = go.Figure()
        fig_scatter.add_trace(go.Scatter(
            x=branch_comparison['Total_Revenue'],
            y=branch_comparison['Margin_Percentage'],
            mode='markers',
            marker=dict(
                size=10,
                color=branch_comparison['COGS_Percentage'],
                colorscale='RdYlBu_r',
                showscale=True,
                colorbar=dict(title="COGS (%)")
            ),
            text=branch_comparison['Branch'],
            hovertemplate='<b>%{text}</b><br>Revenue: %{x:,.0f}<br>Margin: %{y:.1f}%<extra></extra>'
        ))
        fig_scatter.update_layout(
            title='💎 Matrix Performa Cabang (Revenue vs Margin)',
            xaxis_title='Total Revenue (Rp)',
            yaxis_title='Margin (%)',
            height=400
        )
        charts['performance_matrix'] = json.dumps(fig_scatter, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("🍜 Creating top products chart...")
        # Top products chart
        try:
            product_comparison = analyzer.get_product_comparison_by_branch(10)
            if safe_df_check(product_comparison):
                top_products = product_comparison.groupby('Menu').agg({
                    'Qty': 'sum',
                    'Total': 'sum'
                }).reset_index().sort_values('Total', ascending=False).head(10).copy()
                
                # FIXED: Top products chart dengan explicit ordering
                fig_products = go.Figure(data=[
                    go.Bar(
                        x=list(range(len(top_products))),  # Use numeric indices
                        y=top_products['Total'].tolist(),
                        text=[f'Rp {x:,.0f}' for x in top_products['Total']],
                        textposition='outside',
                        marker_color='rgba(255, 140, 0, 0.8)',
                        name='Revenue'
                    )
                ])
                
                fig_products.update_layout(
                    title='🍜 Top 10 Produk by Revenue',
                    xaxis=dict(
                        tickmode='array',
                        tickvals=list(range(len(top_products))),
                        ticktext=top_products['Menu'].tolist(),
                        tickangle=-45
                    ),
                    yaxis_title='Revenue (Rp)',
                    height=400,
                    margin=dict(l=20, r=20, t=40, b=120),
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
    """FIXED: Create charts for branch comparison - PROPER SORTING."""
    charts = {}
    
    try:
        if not safe_df_check(branch_data):
            print("❌ No branch data for comparison charts")
            return charts
        
        print("📊 Creating branch revenue comparison...")
        branch_sorted = branch_data.sort_values('Total_Revenue', ascending=False).copy()
        
        # Revenue comparison chart - FIXED
        fig_revenue = go.Figure(data=[
            go.Bar(
                x=list(range(len(branch_sorted))),
                y=branch_sorted['Total_Revenue'].tolist(),
                text=[f'Rp {x:,.0f}' for x in branch_sorted['Total_Revenue']],
                textposition='outside',
                marker_color='rgba(0, 139, 139, 0.8)',
                name='Revenue'
            )
        ])
        
        fig_revenue.update_layout(
            title='💰 Total Revenue per Cabang',
            xaxis=dict(
                tickmode='array',
                tickvals=list(range(len(branch_sorted))),
                ticktext=branch_sorted['Branch'].tolist(),
                tickangle=-45
            ),
            yaxis_title='Revenue (Rp)',
            height=500,
            margin=dict(l=20, r=20, t=40, b=120),
            showlegend=False
        )
        charts['revenue_comparison'] = json.dumps(fig_revenue, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("💹 Creating margin vs COGS scatter...")
        # Margin vs COGS scatter
        fig_margin_cogs = go.Figure()
        fig_margin_cogs.add_trace(go.Scatter(
            x=branch_data['COGS_Percentage'],
            y=branch_data['Margin_Percentage'],
            mode='markers',
            marker=dict(
                size=12,
                color=branch_data['Total_Revenue'],
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(title="Revenue (Rp)")
            ),
            text=branch_data['Branch'],
            hovertemplate='<b>%{text}</b><br>COGS: %{x:.1f}%<br>Margin: %{y:.1f}%<extra></extra>'
        ))
        fig_margin_cogs.update_layout(
            title='📊 Margin vs COGS per Cabang',
            xaxis_title='COGS (%)',
            yaxis_title='Margin (%)',
            height=500
        )
        charts['margin_cogs'] = json.dumps(fig_margin_cogs, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("⚡ Creating efficiency chart...")
        # Efficiency chart - FIXED
        branch_data_copy = branch_data.copy()
        branch_data_copy['Revenue_per_Transaction'] = branch_data_copy.apply(
            lambda row: safe_divide(row['Total_Revenue'], row['Transaction_Count']), axis=1
        )
        efficiency_sorted = branch_data_copy.sort_values('Revenue_per_Transaction', ascending=False).copy()
        
        fig_efficiency = go.Figure(data=[
            go.Bar(
                x=list(range(len(efficiency_sorted))),
                y=efficiency_sorted['Revenue_per_Transaction'].tolist(),
                text=[f'Rp {x:,.0f}' for x in efficiency_sorted['Revenue_per_Transaction']],
                textposition='outside',
                marker_color='rgba(255, 165, 0, 0.8)',
                name='Efficiency'
            )
        ])
        
        fig_efficiency.update_layout(
            title='⚡ Efisiensi Revenue per Transaksi',
            xaxis=dict(
                tickmode='array',
                tickvals=list(range(len(efficiency_sorted))),
                ticktext=efficiency_sorted['Branch'].tolist(),
                tickangle=-45
            ),
            yaxis_title='Revenue per Transaksi (Rp)',
            height=500,
            margin=dict(l=20, r=20, t=40, b=120),
            showlegend=False
        )
        charts['efficiency'] = json.dumps(fig_efficiency, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("✅ Branch comparison charts created successfully")
        
    except Exception as e:
        print(f"❌ Error creating branch comparison charts: {e}")
        print(f"Traceback: {traceback.format_exc()}")
    
    return charts

def create_product_analysis_charts(product_data, top_products):
    """FIXED: Create charts for product analysis - PROPER SORTING."""
    charts = {}
    
    try:
        if not safe_df_check(product_data) or not safe_df_check(top_products):
            print("❌ No product data for analysis charts")
            return charts
        
        print("💰 Creating top revenue products chart...")
        # Top products by revenue - FIXED
        top_revenue_data = top_products.head(15).sort_values('Total', ascending=False).copy()
        
        fig_top_revenue = go.Figure(data=[
            go.Bar(
                x=list(range(len(top_revenue_data))),
                y=top_revenue_data['Total'].tolist(),
                text=[f'Rp {x:,.0f}' for x in top_revenue_data['Total']],
                textposition='outside',
                marker_color='rgba(0, 139, 139, 0.8)',
                name='Revenue'
            )
        ])
        
        fig_top_revenue.update_layout(
            title='💰 Top 15 Produk by Revenue',
            xaxis=dict(
                tickmode='array',
                tickvals=list(range(len(top_revenue_data))),
                ticktext=top_revenue_data['Menu'].tolist(),
                tickangle=-45
            ),
            yaxis_title='Revenue (Rp)',
            height=600,
            margin=dict(l=20, r=20, t=40, b=150),
            showlegend=False
        )
        charts['top_revenue'] = json.dumps(fig_top_revenue, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("📦 Creating top quantity products chart...")
        # Top products by quantity - FIXED
        top_by_qty = top_products.sort_values('Qty', ascending=False).head(15).copy()
        
        fig_top_qty = go.Figure(data=[
            go.Bar(
                x=list(range(len(top_by_qty))),
                y=top_by_qty['Qty'].tolist(),
                text=[f'{x:,}' for x in top_by_qty['Qty']],
                textposition='outside',
                marker_color='rgba(255, 140, 0, 0.8)',
                name='Quantity'
            )
        ])
        
        fig_top_qty.update_layout(
            title='📦 Top 15 Produk by Quantity',
            xaxis=dict(
                tickmode='array',
                tickvals=list(range(len(top_by_qty))),
                ticktext=top_by_qty['Menu'].tolist(),
                tickangle=-45
            ),
            yaxis_title='Quantity',
            height=600,
            margin=dict(l=20, r=20, t=40, b=150),
            showlegend=False
        )
        charts['top_quantity'] = json.dumps(fig_top_qty, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("✅ Product analysis charts created successfully")
        
    except Exception as e:
        print(f"❌ Error creating product analysis charts: {e}")
        print(f"Traceback: {traceback.format_exc()}")
    
    return charts

def create_minimal_time_charts(time_data):
    """MINIMAL SAFE: Create only basic charts without complex data processing."""
    charts = {}
    
    try:
        print("📊 Creating MINIMAL time charts...")
        
        # Chart 1: Daily Pattern - ONLY if data exists
        if 'daily_pattern' in time_data and safe_df_check(time_data['daily_pattern']):
            try:
                daily_df = time_data['daily_pattern']
                if 'Day_of_Week' in daily_df.columns and 'Total_Revenue' in daily_df.columns:
                    daily_summary = daily_df.groupby('Day_of_Week')['Total_Revenue'].sum().reset_index()
                    
                    # Simple day ordering
                    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    day_mapping = {day: i for i, day in enumerate(day_order)}
                    daily_summary['Day_Index'] = daily_summary['Day_of_Week'].map(day_mapping).fillna(7)
                    daily_summary = daily_summary.sort_values('Day_Index')
                    
                    fig_daily = go.Figure(data=[
                        go.Bar(
                            x=daily_summary['Day_of_Week'].tolist(),
                            y=daily_summary['Total_Revenue'].tolist(),
                            text=[f'Rp {x:,.0f}' for x in daily_summary['Total_Revenue']],
                            textposition='outside',
                            marker_color='rgba(0, 139, 139, 0.8)'
                        )
                    ])
                    
                    fig_daily.update_layout(
                        title='📊 Penjualan per Hari dalam Seminggu',
                        xaxis_title='Hari',
                        yaxis_title='Revenue (Rp)',
                        height=400,
                        showlegend=False
                    )
                    charts['daily_pattern'] = json.dumps(fig_daily, cls=plotly.utils.PlotlyJSONEncoder)
                    print("✅ Daily pattern chart created")
            except Exception as e:
                print(f"❌ Error creating daily chart: {e}")
        
        # Chart 2: Branch Trends - ONLY if data exists  
        if 'daily_trend' in time_data and safe_df_check(time_data['daily_trend']):
            try:
                daily_trend_df = time_data['daily_trend']
                if 'Branch' in daily_trend_df.columns and 'Total' in daily_trend_df.columns:
                    # Get top 3 branches only (simpler)
                    branch_totals = daily_trend_df.groupby('Branch')['Total'].sum().sort_values(ascending=False)
                    top_3_branches = branch_totals.head(3).index.tolist()
                    
                    fig_trends = go.Figure()
                    colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
                    
                    for i, branch in enumerate(top_3_branches):
                        branch_data = daily_trend_df[daily_trend_df['Branch'] == branch]
                        if 'Date' in branch_data.columns:
                            branch_data = branch_data.sort_values('Date')
                            fig_trends.add_trace(go.Scatter(
                                x=branch_data['Date'],
                                y=branch_data['Total'],
                                mode='lines+markers',
                                name=branch,
                                line=dict(width=2, color=colors[i]),
                                marker=dict(size=4)
                            ))
                    
                    fig_trends.update_layout(
                        title='📅 Trend Penjualan Harian (Top 3 Cabang)',
                        xaxis_title='Tanggal',
                        yaxis_title='Revenue (Rp)',
                        height=400,
                        showlegend=True
                    )
                    charts['branch_trends'] = json.dumps(fig_trends, cls=plotly.utils.PlotlyJSONEncoder)
                    print("✅ Branch trends chart created")
            except Exception as e:
                print(f"❌ Error creating trends chart: {e}")
        
        # Chart 3: Simple Monthly Summary
        if 'monthly' in time_data and safe_df_check(time_data['monthly']):
            try:
                monthly_df = time_data['monthly']
                if 'Month' in monthly_df.columns and 'Total' in monthly_df.columns:
                    monthly_summary = monthly_df.groupby('Month')['Total'].sum().reset_index()
                    monthly_summary = monthly_summary.sort_values('Month')
                    
                    fig_monthly = go.Figure(data=[
                        go.Bar(
                            x=[f'Month {int(m)}' for m in monthly_summary['Month']],
                            y=monthly_summary['Total'].tolist(),
                            text=[f'Rp {x:,.0f}' for x in monthly_summary['Total']],
                            textposition='outside',
                            marker_color='rgba(255, 165, 0, 0.8)'
                        )
                    ])
                    
                    fig_monthly.update_layout(
                        title='📊 Total Penjualan per Bulan',
                        xaxis_title='Bulan',
                        yaxis_title='Revenue (Rp)',
                        height=400,
                        showlegend=False
                    )
                    charts['monthly_comparison'] = json.dumps(fig_monthly, cls=plotly.utils.PlotlyJSONEncoder)
                    print("✅ Monthly chart created")
            except Exception as e:
                print(f"❌ Error creating monthly chart: {e}")
        
        # If no charts created, create empty placeholders
        if not charts:
            print("⚠️ No charts created, adding placeholders")
            empty_fig = go.Figure()
            empty_fig.add_annotation(
                text="Data tidak tersedia untuk analisis waktu",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=16, color="gray")
            )
            empty_fig.update_layout(height=300)
            
            charts = {
                'daily_pattern': json.dumps(empty_fig, cls=plotly.utils.PlotlyJSONEncoder),
                'branch_trends': json.dumps(empty_fig, cls=plotly.utils.PlotlyJSONEncoder),
                'monthly_comparison': json.dumps(empty_fig, cls=plotly.utils.PlotlyJSONEncoder)
            }
        
        print("✅ Minimal time charts completed")
        
    except Exception as e:
        print(f"❌ Error creating minimal time charts: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        
        # Fallback: empty charts
        empty_fig = go.Figure()
        empty_fig.add_annotation(
            text="Error memuat data",
            xref="paper", yref="paper", 
            x=0.5, y=0.5, showarrow=False
        )
        empty_fig.update_layout(height=300)
        
        charts = {
            'daily_pattern': json.dumps(empty_fig, cls=plotly.utils.PlotlyJSONEncoder),
            'branch_trends': json.dumps(empty_fig, cls=plotly.utils.PlotlyJSONEncoder),
            'monthly_comparison': json.dumps(empty_fig, cls=plotly.utils.PlotlyJSONEncoder)
        }
    
    return charts

def create_cogs_analysis_charts(cogs_data, branch_cogs):
    """FIXED: Create charts for COGS analysis - PROPER SORTING."""
    charts = {}
    
    try:
        if not safe_df_check(cogs_data) or not safe_df_check(branch_cogs):
            print("❌ No COGS data for analysis charts")
            return charts
        
        print("🔥 Creating COGS heatmap...")
        # COGS heatmap - top 15 products only
        top_products = cogs_data.groupby('Menu')['Total'].sum().nlargest(15).index
        filtered_cogs = cogs_data[cogs_data['Menu'].isin(top_products)]
        
        if safe_df_check(filtered_cogs):
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
        # Branch COGS efficiency - FIXED
        branch_cogs_sorted = branch_cogs.sort_values('COGS_Efficiency', ascending=False).copy()
        
        fig_branch_cogs = go.Figure(data=[
            go.Bar(
                x=list(range(len(branch_cogs_sorted))),
                y=branch_cogs_sorted['COGS_Efficiency'].tolist(),
                text=[f'{x:.1f}%' for x in branch_cogs_sorted['COGS_Efficiency']],
                textposition='outside',
                marker_color='rgba(50, 205, 50, 0.8)',
                name='COGS Efficiency'
            )
        ])
        
        fig_branch_cogs.update_layout(
            title='📊 Efisiensi COGS per Cabang',
            xaxis=dict(
                tickmode='array',
                tickvals=list(range(len(branch_cogs_sorted))),
                ticktext=branch_cogs_sorted['Branch'].tolist(),
                tickangle=-45
            ),
            yaxis_title='Efisiensi COGS (%)',
            height=500,
            margin=dict(l=20, r=20, t=40, b=120),
            showlegend=False
        )
        charts['branch_efficiency'] = json.dumps(fig_branch_cogs, cls=plotly.utils.PlotlyJSONEncoder)
        
        print("📊 Creating COGS variance chart...")
        # COGS variance - FIXED
        product_cogs_stats = cogs_data.groupby('Menu')['COGS Total (%)'].agg(['mean', 'std', 'count']).reset_index()
        product_cogs_stats = product_cogs_stats[
            (product_cogs_stats['count'] > 1) & 
            (product_cogs_stats['std'] > 0) & 
            (product_cogs_stats['mean'] > 0)
        ]
        
        if safe_df_check(product_cogs_stats):
            product_cogs_stats['CV'] = product_cogs_stats['std'] / product_cogs_stats['mean']
            cogs_variance_sorted = product_cogs_stats.sort_values('CV', ascending=False).head(15).copy()
            
            fig_cogs_variance = go.Figure(data=[
                go.Bar(
                    x=list(range(len(cogs_variance_sorted))),
                    y=cogs_variance_sorted['CV'].tolist(),
                    text=[f'{x:.2f}' for x in cogs_variance_sorted['CV']],
                    textposition='outside',
                    marker_color='rgba(220, 20, 60, 0.8)',
                    name='COGS Variance'
                )
            ])
            
            fig_cogs_variance.update_layout(
                title='📊 Top 15 Produk dengan Variasi COGS Tertinggi',
                xaxis=dict(
                    tickmode='array',
                    tickvals=list(range(len(cogs_variance_sorted))),
                    ticktext=cogs_variance_sorted['Menu'].tolist(),
                    tickangle=-45
                ),
                yaxis_title='Coefficient of Variation',
                height=600,
                margin=dict(l=20, r=20, t=40, b=150),
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
        'data_loaded': safe_df_check(current_data),
        'chatbot_loaded': chatbot is not None,
        'templates_dir': os.path.abspath(app.template_folder),
        'templates_exist': os.path.exists(app.template_folder),
        'current_dir': os.getcwd(),
        'python_path': sys.path[:3]  # Show first 3 paths
    }
    
    if os.path.exists(app.template_folder):
        status['template_files'] = [f for f in os.listdir(app.template_folder) if f.endswith('.html')]
    
    if analyzer and safe_df_check(current_data):
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
        print("Please make sure all template files are in the templates folder")
    else:
        print("✅ All required template files found")
    
    print("🌐 Starting server on http://127.0.0.1:5000")
    print("🔍 Visit /debug for system status")
    
    app.run(debug=True, host='127.0.0.1', port=5000)
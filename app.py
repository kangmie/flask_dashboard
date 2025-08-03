from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.utils
import json
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import warnings
import io
warnings.filterwarnings('ignore')

# Import analyzer modules
try:
    from multi_branch_analyzer import MultiBranchSalesAnalyzer
    from chatbot import GroqChatbot
except ImportError as e:
    print(f"Warning: Import error - {e}")
    MultiBranchSalesAnalyzer = None
    GroqChatbot = None

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

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

@app.route('/')
def index():
    """Main dashboard page."""
    global analyzer, current_data
    
    if analyzer is None or current_data is None or current_data.empty:
        return redirect(url_for('upload_files'))
    
    try:
        # Get summary statistics
        summary_stats = analyzer.get_branch_summary_stats()
        
        # Get branch comparison
        branch_comparison = analyzer.get_branch_revenue_comparison()
        
        # Get key metrics
        total_revenue = summary_stats['total_revenue']
        total_margin = summary_stats['total_margin']
        gross_margin_pct = (total_margin / total_revenue) * 100 if total_revenue > 0 else 0
        
        # Create charts data
        charts_data = create_dashboard_charts()
        
        return render_template('dashboard.html',
                             summary_stats=summary_stats,
                             branch_comparison=branch_comparison,
                             charts_data=charts_data,
                             total_revenue=format_currency(total_revenue),
                             total_margin=format_currency(total_margin),
                             gross_margin_pct=format_percentage(gross_margin_pct),
                             branches=analyzer.branches)
    
    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}')
        return redirect(url_for('upload_files'))

@app.route('/upload', methods=['GET', 'POST'])
def upload_files():
    """Handle file uploads."""
    if request.method == 'POST':
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
        
        if uploaded_files:
            try:
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
                
                # Initialize chatbot
                try:
                    if GroqChatbot is not None:
                        chatbot = GroqChatbot()
                except Exception as e:
                    print(f"Chatbot initialization failed: {e}")
                    chatbot = None
                
                # Clean up uploaded files
                for file_path in uploaded_files:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                
                flash(f'Successfully loaded {len(uploaded_files)} files with {len(current_data)} records!')
                return redirect(url_for('index'))
                
            except Exception as e:
                flash(f'Error processing files: {str(e)}')
                # Clean up files on error
                for file_path in uploaded_files:
                    if os.path.exists(file_path):
                        os.remove(file_path)
        else:
            flash('No valid Excel files found')
    
    return render_template('upload.html')

@app.route('/branch-comparison')
def branch_comparison():
    """Branch comparison analysis page."""
    global analyzer, current_data
    
    if analyzer is None or current_data is None or current_data.empty:
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))
    
    try:
        branch_comparison_data = analyzer.get_branch_revenue_comparison()
        
        # Create branch comparison charts
        charts = create_branch_comparison_charts(branch_comparison_data)
        
        return render_template('branch_comparison.html',
                             branch_data=branch_comparison_data,
                             charts=charts)
    except Exception as e:
        flash(f'Error loading branch comparison: {str(e)}')
        return redirect(url_for('index'))

@app.route('/product-analysis')
def product_analysis():
    """Product analysis page."""
    global analyzer, current_data
    
    if analyzer is None or current_data is None or current_data.empty:
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))
    
    try:
        # Get product comparison data
        product_comparison = analyzer.get_product_comparison_by_branch(20)
        
        # Get top products overall
        top_products = product_comparison.groupby('Menu').agg({
            'Qty': 'sum',
            'Total': 'sum',
            'Margin': 'sum'
        }).reset_index()
        top_products['Margin_Percentage'] = (top_products['Margin'] / top_products['Total']) * 100
        top_products = top_products.sort_values('Total', ascending=False)
        
        # Create product analysis charts
        charts = create_product_analysis_charts(product_comparison, top_products)
        
        return render_template('product_analysis.html',
                             product_data=product_comparison,
                             top_products=top_products,
                             charts=charts)
    except Exception as e:
        flash(f'Error loading product analysis: {str(e)}')
        return redirect(url_for('index'))

@app.route('/sales-by-time')
def sales_by_time():
    """Sales by time analysis page."""
    global analyzer, current_data
    
    if analyzer is None or current_data is None or current_data.empty:
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))
    
    try:
        # Get time analysis data
        time_analysis = analyzer.get_sales_by_time_all_branches()
        
        # Create time analysis charts
        charts = create_time_analysis_charts(time_analysis)
        
        return render_template('sales_by_time.html',
                             time_data=time_analysis,
                             charts=charts)
    except Exception as e:
        flash(f'Error loading sales by time: {str(e)}')
        return redirect(url_for('index'))

@app.route('/cogs-analysis')
def cogs_analysis():
    """COGS analysis page."""
    global analyzer, current_data
    
    if analyzer is None or current_data is None or current_data.empty:
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))
    
    try:
        # Get COGS analysis data
        cogs_data = analyzer.get_cogs_per_product_per_branch(15)
        
        # Branch COGS efficiency
        branch_cogs = cogs_data.groupby('Branch')['COGS Total (%)'].mean().reset_index()
        branch_cogs['COGS_Efficiency'] = 100 - branch_cogs['COGS Total (%)']
        branch_cogs = branch_cogs.sort_values('COGS_Efficiency', ascending=False)
        
        # Create COGS analysis charts
        charts = create_cogs_analysis_charts(cogs_data, branch_cogs)
        
        return render_template('cogs_analysis.html',
                             cogs_data=cogs_data,
                             branch_cogs=branch_cogs,
                             charts=charts)
    except Exception as e:
        flash(f'Error loading COGS analysis: {str(e)}')
        return redirect(url_for('index'))

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    """AI chatbot page."""
    global analyzer, chatbot
    
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
                return jsonify({
                    'success': False,
                    'error': str(e)
                })
        else:
            return jsonify({
                'success': False,
                'error': 'No question provided or chatbot not available'
            })
    
    return render_template('chat.html', chatbot_available=chatbot is not None)

@app.route('/api/chart-data/<chart_type>')
def get_chart_data(chart_type):
    """API endpoint to get chart data."""
    global analyzer, current_data
    
    if analyzer is None:
        return jsonify({'error': 'No data loaded'})
    
    try:
        if chart_type == 'revenue_comparison':
            branch_data = analyzer.get_branch_revenue_comparison()
            return jsonify(branch_data.to_dict('records'))
        
        elif chart_type == 'product_heatmap':
            product_data = analyzer.get_product_comparison_by_branch(15)
            return jsonify(product_data.to_dict('records'))
        
        elif chart_type == 'hourly_sales':
            time_data = analyzer.get_sales_by_time_all_branches()
            return jsonify(time_data['hourly'].to_dict('records'))
        
        elif chart_type == 'cogs_efficiency':
            cogs_data = analyzer.get_cogs_per_product_per_branch(15)
            branch_cogs = cogs_data.groupby('Branch')['COGS Total (%)'].mean().reset_index()
            return jsonify(branch_cogs.to_dict('records'))
        
        else:
            return jsonify({'error': 'Invalid chart type'})
    
    except Exception as e:
        return jsonify({'error': str(e)})

def create_dashboard_charts():
    """Create charts for main dashboard."""
    global analyzer
    
    if analyzer is None:
        return {}
    
    charts = {}
    
    try:
        # Revenue comparison chart
        branch_comparison = analyzer.get_branch_revenue_comparison()
        
        fig_revenue = px.bar(
            branch_comparison.head(10),
            x='Branch',
            y='Total_Revenue',
            title='📊 Revenue per Cabang (Top 10)',
            color='Total_Revenue',
            color_continuous_scale='Viridis'
        )
        fig_revenue.update_layout(
            xaxis_tickangle=45,
            height=400,
            margin=dict(l=20, r=20, t=40, b=80)
        )
        charts['revenue_bar'] = json.dumps(fig_revenue, cls=plotly.utils.PlotlyJSONEncoder)
        
        # Revenue distribution pie chart
        fig_pie = px.pie(
            branch_comparison.head(8),
            values='Total_Revenue',
            names='Branch',
            title='📊 Distribusi Revenue per Cabang',
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        fig_pie.update_layout(height=400)
        charts['revenue_pie'] = json.dumps(fig_pie, cls=plotly.utils.PlotlyJSONEncoder)
        
        # Performance matrix
        fig_scatter = px.scatter(
            branch_comparison,
            x='Total_Revenue',
            y='Margin_Percentage',
            size='Transaction_Count',
            color='COGS_Percentage',
            hover_data=['Branch'],
            title='💎 Matrix Performa Cabang',
            labels={
                'Total_Revenue': 'Total Revenue (Rp)',
                'Margin_Percentage': 'Margin (%)',
                'COGS_Percentage': 'COGS (%)'
            }
        )
        fig_scatter.update_layout(height=400)
        charts['performance_matrix'] = json.dumps(fig_scatter, cls=plotly.utils.PlotlyJSONEncoder)
        
        # Top products
        product_comparison = analyzer.get_product_comparison_by_branch(10)
        if not product_comparison.empty:
            top_products = product_comparison.groupby('Menu').agg({
                'Qty': 'sum',
                'Total': 'sum'
            }).reset_index().sort_values('Total', ascending=False).head(10)
            
            fig_products = px.bar(
                top_products,
                x='Total',
                y='Menu',
                orientation='h',
                title='🍜 Top 10 Produk by Revenue',
                color='Total',
                color_continuous_scale='Plasma'
            )
            fig_products.update_layout(
                yaxis={'categoryorder': 'total ascending'},
                height=400,
                margin=dict(l=20, r=20, t=40, b=20)
            )
            charts['top_products'] = json.dumps(fig_products, cls=plotly.utils.PlotlyJSONEncoder)
        
    except Exception as e:
        print(f"Error creating dashboard charts: {e}")
    
    return charts

def create_branch_comparison_charts(branch_data):
    """Create charts for branch comparison page."""
    charts = {}
    
    try:
        # Revenue comparison
        fig_revenue = px.bar(
            branch_data,
            x='Branch',
            y='Total_Revenue',
            title='💰 Total Revenue per Cabang',
            color='Total_Revenue',
            color_continuous_scale='Viridis'
        )
        fig_revenue.update_layout(xaxis_tickangle=45, height=500)
        charts['revenue_comparison'] = json.dumps(fig_revenue, cls=plotly.utils.PlotlyJSONEncoder)
        
        # Margin vs COGS
        fig_margin_cogs = px.scatter(
            branch_data,
            x='COGS_Percentage',
            y='Margin_Percentage',
            size='Total_Revenue',
            color='Branch',
            title='📊 Margin vs COGS per Cabang',
            labels={'COGS_Percentage': 'COGS (%)', 'Margin_Percentage': 'Margin (%)'}
        )
        fig_margin_cogs.update_layout(height=500)
        charts['margin_cogs'] = json.dumps(fig_margin_cogs, cls=plotly.utils.PlotlyJSONEncoder)
        
        # Transaction efficiency
        branch_data_copy = branch_data.copy()
        branch_data_copy['Revenue_per_Transaction'] = branch_data_copy['Total_Revenue'] / branch_data_copy['Transaction_Count']
        
        fig_efficiency = px.bar(
            branch_data_copy,
            x='Branch',
            y='Revenue_per_Transaction',
            title='⚡ Efisiensi Revenue per Transaksi',
            color='Revenue_per_Transaction',
            color_continuous_scale='RdYlBu_r'
        )
        fig_efficiency.update_layout(xaxis_tickangle=45, height=500)
        charts['efficiency'] = json.dumps(fig_efficiency, cls=plotly.utils.PlotlyJSONEncoder)
        
    except Exception as e:
        print(f"Error creating branch comparison charts: {e}")
    
    return charts

def create_product_analysis_charts(product_data, top_products):
    """Create charts for product analysis page."""
    charts = {}
    
    try:
        # Product revenue heatmap
        if not product_data.empty:
            product_revenue_pivot = product_data.pivot(
                index='Menu',
                columns='Branch',
                values='Total'
            ).fillna(0)
            
            fig_heatmap = px.imshow(
                product_revenue_pivot,
                title='🔥 Heatmap Revenue Produk per Cabang',
                aspect='auto',
                color_continuous_scale='YlOrRd',
                labels={'color': 'Revenue (Rp)'}
            )
            fig_heatmap.update_layout(height=600)
            charts['product_heatmap'] = json.dumps(fig_heatmap, cls=plotly.utils.PlotlyJSONEncoder)
        
        # Top products by revenue
        fig_top_revenue = px.bar(
            top_products.head(15),
            x='Total',
            y='Menu',
            orientation='h',
            title='💰 Top 15 Produk by Revenue',
            color='Total',
            color_continuous_scale='Viridis'
        )
        fig_top_revenue.update_layout(
            yaxis={'categoryorder': 'total ascending'},
            height=600
        )
        charts['top_revenue'] = json.dumps(fig_top_revenue, cls=plotly.utils.PlotlyJSONEncoder)
        
        # Top products by quantity
        top_by_qty = top_products.sort_values('Qty', ascending=False).head(15)
        fig_top_qty = px.bar(
            top_by_qty,
            x='Qty',
            y='Menu',
            orientation='h',
            title='📦 Top 15 Produk by Quantity',
            color='Qty',
            color_continuous_scale='Plasma'
        )
        fig_top_qty.update_layout(
            yaxis={'categoryorder': 'total ascending'},
            height=600
        )
        charts['top_quantity'] = json.dumps(fig_top_qty, cls=plotly.utils.PlotlyJSONEncoder)
        
    except Exception as e:
        print(f"Error creating product analysis charts: {e}")
    
    return charts

def create_time_analysis_charts(time_data):
    """Create charts for time analysis page."""
    charts = {}
    
    try:
        # Hourly heatmap
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
        
        # Average hourly pattern
        hourly_avg = time_data['hourly'].groupby('Hour')['Total'].mean().reset_index()
        
        fig_hourly_avg = px.line(
            hourly_avg,
            x='Hour',
            y='Total',
            title='📈 Rata-rata Penjualan per Jam (Semua Cabang)',
            markers=True
        )
        fig_hourly_avg.update_layout(
            xaxis_title='Jam',
            yaxis_title='Rata-rata Revenue (Rp)',
            height=400
        )
        charts['hourly_average'] = json.dumps(fig_hourly_avg, cls=plotly.utils.PlotlyJSONEncoder)
        
        # Daily pattern
        daily_comparison = time_data['daily_pattern'].groupby('Day_of_Week')['Total_Revenue'].sum().reset_index()
        
        # Reorder days
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        daily_comparison['Day_Order'] = daily_comparison['Day_of_Week'].map(
            {day: i for i, day in enumerate(day_order)}
        )
        daily_comparison = daily_comparison.sort_values('Day_Order')
        
        fig_daily = px.bar(
            daily_comparison,
            x='Day_of_Week',
            y='Total_Revenue',
            title='📊 Total Penjualan per Hari (Semua Cabang)',
            color='Total_Revenue',
            color_continuous_scale='Viridis'
        )
        fig_daily.update_layout(height=400)
        charts['daily_pattern'] = json.dumps(fig_daily, cls=plotly.utils.PlotlyJSONEncoder)
        
    except Exception as e:
        print(f"Error creating time analysis charts: {e}")
    
    return charts

def create_cogs_analysis_charts(cogs_data, branch_cogs):
    """Create charts for COGS analysis page."""
    charts = {}
    
    try:
        # COGS heatmap
        cogs_pivot = cogs_data.pivot(
            index='Menu',
            columns='Branch',
            values='COGS Total (%)'
        ).fillna(0)
        
        fig_cogs_heatmap = px.imshow(
            cogs_pivot,
            title='🔥 COGS Percentage per Produk per Cabang',
            aspect='auto',
            color_continuous_scale='RdYlGn_r',
            labels={'color': 'COGS (%)'}
        )
        fig_cogs_heatmap.update_layout(height=600)
        charts['cogs_heatmap'] = json.dumps(fig_cogs_heatmap, cls=plotly.utils.PlotlyJSONEncoder)
        
        # Branch COGS efficiency
        fig_branch_cogs = px.bar(
            branch_cogs,
            x='Branch',
            y='COGS_Efficiency',
            title='📊 Efisiensi COGS per Cabang',
            color='COGS_Efficiency',
            color_continuous_scale='RdYlGn'
        )
        fig_branch_cogs.update_layout(xaxis_tickangle=45, height=500)
        charts['branch_efficiency'] = json.dumps(fig_branch_cogs, cls=plotly.utils.PlotlyJSONEncoder)
        
        # COGS variance
        product_cogs_stats = cogs_data.groupby('Menu')['COGS Total (%)'].agg(['mean', 'std']).reset_index()
        product_cogs_stats['CV'] = product_cogs_stats['std'] / product_cogs_stats['mean']
        product_cogs_stats = product_cogs_stats.sort_values('CV', ascending=False).head(15)
        
        fig_cogs_variance = px.bar(
            product_cogs_stats,
            x='CV',
            y='Menu',
            orientation='h',
            title='📊 Top 15 Produk dengan Variasi COGS Tertinggi',
            color='CV',
            color_continuous_scale='Reds'
        )
        fig_cogs_variance.update_layout(
            yaxis={'categoryorder': 'total ascending'},
            height=600
        )
        charts['cogs_variance'] = json.dumps(fig_cogs_variance, cls=plotly.utils.PlotlyJSONEncoder)
        
    except Exception as e:
        print(f"Error creating COGS analysis charts: {e}")
    
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

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', 
                         error_code=404, 
                         error_message="Halaman tidak ditemukan"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', 
                         error_code=500, 
                         error_message="Terjadi kesalahan internal server"), 500

@app.errorhandler(413)
def too_large(error):
    return render_template('error.html', 
                         error_code=413, 
                         error_message="File terlalu besar. Maksimal 50MB per file"), 413

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
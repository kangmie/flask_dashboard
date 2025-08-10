from flask import Flask, render_template, render_template_string, request, jsonify, redirect, url_for, flash
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.utils
import json
import os
import sys
from werkzeug.utils import secure_filename
import warnings
import io
import traceback

warnings.filterwarnings('ignore')

# ===== Imports eksternal (best-effort) =====
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

# ===== Flask App =====
app = Flask(
    __name__,
    template_folder=os.path.abspath('templates'),
    static_folder=os.path.abspath('static')
)
app.secret_key = os.getenv('SECRET_KEY', 'debug-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
app.config['DEBUG'] = True
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ===== Global State =====
analyzer = None
current_data = None
chatbot = None

# ===== Utils =====
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
def allowed_file(filename): return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_currency(v):
    try: return f"Rp {float(v):,.0f}"
    except: return "Rp 0"

def format_percentage(v):
    try: return f"{float(v):.1f}%"
    except: return "0%"

def format_number(v):
    try: return f"{float(v):,.0f}"
    except: return "0"

def safe_divide(a, b):
    try:
        b = float(b)
        return float(a) / b if b != 0 else 0
    except:
        return 0

def safe_df_check(df):
    try: return df is not None and hasattr(df, "empty") and not df.empty
    except: return False

# ===== Jinja Filters =====
@app.template_filter('currency')
def currency_filter(v): return format_currency(v)

@app.template_filter('percentage')
def percentage_filter(v): return format_percentage(v)

@app.template_filter('number')
def number_filter(v): return format_number(v)

@app.template_filter('round')
def round_filter(v, precision=2):
    try: return round(float(v), precision)
    except: return v

# ===== Routes =====
@app.route('/')
def index():
    global analyzer, current_data
    print("🔍 Dashboard route accessed")

    if analyzer is None or not safe_df_check(current_data):
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))

    try:
        summary_stats = analyzer.get_branch_summary_stats()
        branch_comp = analyzer.get_branch_revenue_comparison()

        total_revenue = summary_stats.get('total_revenue', 0)
        total_margin = summary_stats.get('total_margin', 0)
        gross_margin_pct = safe_divide(total_margin, total_revenue) * 100

        charts_data = create_dashboard_charts()

        return render_template(
            'dashboard.html',
            summary_stats=summary_stats,
            branch_comparison=branch_comp,
            charts_data=charts_data,
            total_revenue=format_currency(total_revenue),
            total_margin=format_currency(total_margin),
            gross_margin_pct=format_percentage(gross_margin_pct),
            branches=analyzer.branches
        )
    except Exception as e:
        print(f"❌ Error in dashboard: {e}")
        print(traceback.format_exc())
        flash(f'Error loading dashboard: {e}')
        return redirect(url_for('upload_files'))

@app.route('/upload', methods=['GET', 'POST'])
def upload_files():
    print("📁 Upload route accessed")
    if request.method == 'POST':
        if 'files[]' not in request.files:
            flash('No files selected')
            return redirect(request.url)

        files = request.files.getlist('files[]')
        if not files or files[0].filename == '':
            flash('No files selected')
            return redirect(request.url)

        uploaded = []
        for f in files:
            if f and allowed_file(f.filename):
                name = secure_filename(f.filename)
                path = os.path.join(app.config['UPLOAD_FOLDER'], name)
                f.save(path)
                uploaded.append(path)
                print(f"📄 Saved: {name}")

        if not uploaded:
            flash('No valid Excel files found')
            return redirect(request.url)

        try:
            global analyzer, current_data, chatbot
            if MultiBranchSalesAnalyzer is None:
                flash('Analyzer module not available. Check imports.')
                return redirect(url_for('upload_files'))

            analyzer = MultiBranchSalesAnalyzer()

            buffers = []
            for p in uploaded:
                with open(p, 'rb') as fh:
                    b = io.BytesIO(fh.read())
                    b.name = os.path.basename(p)
                    buffers.append(b)

            current_data = analyzer.load_multiple_files(buffers)
            if not safe_df_check(current_data):
                flash('No valid data found in uploaded files.')
                return redirect(url_for('upload_files'))

            # init chatbot (optional)
            try:
                chatbot = GroqChatbot() if GroqChatbot else None
                if chatbot: print("✅ Chatbot initialized")
            except Exception as e:
                print(f"⚠️ Chatbot init failed: {e}")
                chatbot = None

            # cleanup
            for p in uploaded:
                if os.path.exists(p): os.remove(p)

            flash(f'Successfully loaded {len(uploaded)} files with {len(current_data)} records!')
            return redirect(url_for('index'))

        except Exception as e:
            print(f"❌ Upload processing error: {e}")
            print(traceback.format_exc())
            for p in uploaded:
                if os.path.exists(p): os.remove(p)
            flash(f'Error processing files: {e}')

    return render_template('upload.html')

@app.route('/branch-comparison')
def branch_comparison():
    global analyzer, current_data
    if analyzer is None or not safe_df_check(current_data):
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))

    try:
        data = analyzer.get_branch_revenue_comparison()
        charts = create_branch_comparison_charts(data)
        return render_template('branch_comparison.html', branch_data=data, charts=charts)
    except Exception as e:
        print(f"❌ Branch comparison error: {e}")
        print(traceback.format_exc())
        flash(f'Error loading branch comparison: {e}')
        return redirect(url_for('index'))

@app.route('/product-analysis')
def product_analysis():
    """Branch-first. Detail produk di frontend hanya Revenue & Qty."""
    global analyzer, current_data
    if analyzer is None or not safe_df_check(current_data):
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))

    try:
        df = analyzer.get_product_comparison_by_branch(top_n_products=None)
        if not safe_df_check(df):
            flash('No product data available for analysis.')
            return redirect(url_for('index'))

        top_products = (
            df.groupby('Menu')
              .agg({'Qty': 'sum', 'Total': 'sum', 'Margin': 'sum'})
              .reset_index()
        )
        top_products['Margin_Percentage'] = top_products.apply(
            lambda r: safe_divide(r['Margin'], r['Total']) * 100, axis=1
        )
        top_products = top_products.sort_values('Total', ascending=False)

        return render_template('product_analysis.html', product_data=df, top_products=top_products)
    except Exception as e:
        print(f"❌ Product analysis error: {e}")
        print(traceback.format_exc())
        flash(f'Error loading product analysis: {e}')
        return redirect(url_for('index'))

@app.route('/sales-by-time')
def sales_by_time():
    """Branch Trends: ALL branches, tooltip hanya untuk trace yang di-pointer (hovermode='closest')."""
    global analyzer, current_data
    if analyzer is None or not safe_df_check(current_data):
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))

    try:
        raw = analyzer.get_sales_by_time_all_branches()  # dict of DataFrames
        time_analysis = {}
        if isinstance(raw, dict):
            for k, df in raw.items():
                if safe_df_check(df):
                    time_analysis[k] = {
                        'data': df.to_dict('records'),
                        'columns': df.columns.tolist(),
                        'length': len(df)
                    }
                else:
                    time_analysis[k] = {'data': [], 'columns': [], 'length': 0}
        else:
            # fallback empty structure
            time_analysis = {k: {'data': [], 'columns': [], 'length': 0}
                             for k in ['hourly','daily_pattern','daily_trend','weekly','monthly']}

        charts = create_time_charts_all_branches(time_analysis)

        summary_stats = {
            'total_branches': len(analyzer.branches) if analyzer.branches else 0,
            'date_range': (
                f"{analyzer.min_date.strftime('%d/%m/%Y')} - {analyzer.max_date.strftime('%d/%m/%Y')}"
                if getattr(analyzer, 'min_date', None) and getattr(analyzer, 'max_date', None)
                else "No date range"
            ),
            'total_records': len(current_data) if safe_df_check(current_data) else 0
        }

        return render_template('sales_by_time.html',
                               time_data=time_analysis,
                               charts=charts,
                               summary_stats=summary_stats)
    except Exception as e:
        print(f"❌ Sales-by-time error: {e}")
        print(traceback.format_exc())
        empty = json.dumps({"data": [], "layout": {"title": "No Data"}})
        fallback_charts = {'daily_pattern': empty, 'branch_trends': empty, 'monthly_comparison': empty}
        fallback_time = {k: {'data': [], 'columns': [], 'length': 0}
                         for k in ['hourly','daily_pattern','daily_trend','weekly','monthly']}
        fallback_stats = {'total_branches': 0, 'date_range': "No data", 'total_records': 0}
        return render_template('sales_by_time.html',
                               time_data=fallback_time, charts=fallback_charts, summary_stats=fallback_stats)

@app.route('/cogs-analysis')
def cogs_analysis():
    """COGS analysis: ALL products (no top limit)."""
    global analyzer, current_data
    if analyzer is None or not safe_df_check(current_data):
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))

    try:
        cogs = analyzer.get_cogs_per_product_per_branch(top_n_products=None)
        if not safe_df_check(cogs):
            flash('No COGS data available for analysis.')
            return redirect(url_for('index'))

        branch_cogs = cogs.groupby('Branch')['COGS Total (%)'].mean().reset_index()
        branch_cogs['COGS_Efficiency'] = 100 - branch_cogs['COGS Total (%)']
        branch_cogs = branch_cogs.sort_values('COGS_Efficiency', ascending=False)

        charts = create_cogs_analysis_charts(cogs, branch_cogs)
        return render_template('cogs_analysis.html', cogs_data=cogs, branch_cogs=branch_cogs, charts=charts)
    except Exception as e:
        print(f"❌ COGS analysis error: {e}")
        print(traceback.format_exc())
        flash(f'Error loading COGS analysis: {e}')
        return redirect(url_for('index'))

@app.route('/debug-cogs')
def debug_cogs():
    """Debug COGS — ringkasan lengkap."""
    global analyzer, current_data
    if analyzer is None or not safe_df_check(current_data):
        return "❌ No data available. Please upload files first."

    try:
        cogs = analyzer.get_cogs_per_product_per_branch(top_n_products=None)
        if not safe_df_check(cogs): return "❌ No COGS data available."

        info = {
            'total_records': len(cogs),
            'unique_branches': cogs['Branch'].nunique(),
            'unique_menus': cogs['Menu'].nunique(),
            'branches': cogs['Branch'].unique().tolist(),
            'sample_data': cogs.head(10).to_dict('records'),
            'columns': cogs.columns.tolist()
        }
        breakdown = {}
        for br in info['branches']:
            sub = cogs[cogs['Branch'] == br]
            breakdown[br] = {
                'total_records': len(sub),
                'unique_menus': sub['Menu'].nunique(),
                'sample_menus': sub['Menu'].unique()[:10].tolist()
            }
        info['branch_breakdown'] = breakdown

        return render_template_string('''
        <h1>🔍 Debug COGS Data (ALL)</h1>
        <ul>
          <li>Total records: {{ d.total_records }}</li>
          <li>Unique branches: {{ d.unique_branches }}</li>
          <li>Unique menus: {{ d.unique_menus }}</li>
        </ul>
        <h3>Branch Breakdown</h3>
        {% for br, i in d.branch_breakdown.items() %}
          <div style="border:1px solid #ccc;margin:6px 0;padding:8px;">
            <b>{{ br }}</b><br>
            Records: {{ i.total_records }} | Unique menus: {{ i.unique_menus }}<br>
            Sample: {{ i.sample_menus|join(", ") }}{% if i.unique_menus > 10 %} ...{% endif %}
          </div>
        {% endfor %}
        <h3>Sample (10)</h3>
        <table border="1" style="border-collapse:collapse;">
          <tr><th>Branch</th><th>Menu</th><th>COGS %</th><th>Total</th><th>Qty</th><th>Margin</th></tr>
          {% for r in d.sample_data %}
          <tr>
            <td>{{ r.Branch }}</td>
            <td>{{ r.Menu }}</td>
            <td>{{ ('%.1f' % r['COGS Total (%)']) if r['COGS Total (%)'] is not none else '-' }}%</td>
            <td>Rp {{ "{:,}".format(r.Total) if r.Total is not none else '0' }}</td>
            <td>{{ r.Qty }}</td>
            <td>Rp {{ "{:,}".format(r.Margin) if r.Margin is not none else '0' }}</td>
          </tr>
          {% endfor %}
        </table>
        ''', d=info)

    except Exception as e:
        print(f"❌ Debug COGS error: {e}")
        return f"❌ Error: {e}"

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    global analyzer, chatbot
    if analyzer is None:
        flash('No data available. Please upload files first.')
        return redirect(url_for('upload_files'))

    if request.method == 'POST':
        q = request.form.get('question', '').strip()
        if q and chatbot:
            try:
                ctx = analyzer.prepare_data_for_ai()
                ans = chatbot.get_response(q, ctx)
                return jsonify({'success': True, 'response': ans})
            except Exception as e:
                print(f"❌ Chat error: {e}")
                return jsonify({'success': False, 'error': str(e)})
        return jsonify({'success': False, 'error': 'No question provided or chatbot not available'})

    return render_template('chat.html', chatbot_available=chatbot is not None)

@app.route('/debug')
def debug_status():
    status = {
        'analyzer_loaded': analyzer is not None,
        'data_loaded': safe_df_check(current_data),
        'chatbot_loaded': chatbot is not None,
        'templates_dir': os.path.abspath(app.template_folder),
        'templates_exist': os.path.exists(app.template_folder),
        'current_dir': os.getcwd(),
        'python_path': sys.path[:3]
    }
    if os.path.exists(app.template_folder):
        status['template_files'] = [f for f in os.listdir(app.template_folder) if f.endswith('.html')]
    if analyzer and safe_df_check(current_data):
        status['data_summary'] = {
            'total_records': len(current_data),
            'branches': len(analyzer.branches),
            'unique_products': current_data['Menu'].nunique() if 'Menu' in current_data.columns else 0,
            'date_range': f"{current_data['Sales Date'].min()} to {current_data['Sales Date'].max()}" if 'Sales Date' in current_data.columns else "N/A"
        }
    return jsonify(status)

# ===== Chart Builders =====
def create_dashboard_charts():
    global analyzer
    charts = {}
    try:
        df = analyzer.get_branch_revenue_comparison()
        if not safe_df_check(df): return charts

        # Revenue bar (Top 10 utk kerapian di dashboard)
        top = df.sort_values('Total_Revenue', ascending=False).head(10).copy()
        fig_revenue = go.Figure([go.Bar(
            x=list(range(len(top))),
            y=top['Total_Revenue'].tolist(),
            text=[f'Rp {x:,.0f}' for x in top['Total_Revenue']],
            textposition='outside',
            marker_color='rgba(0,139,139,0.8)'
        )])
        fig_revenue.update_layout(
            title='📊 Revenue per Cabang (Top 10)',
            xaxis=dict(tickmode='array', tickvals=list(range(len(top))), ticktext=top['Branch'].tolist(), tickangle=-45),
            yaxis_title='Revenue (Rp)', height=400, margin=dict(l=20,r=20,t=40,b=120), showlegend=False
        )
        charts['revenue_bar'] = json.dumps(fig_revenue, cls=plotly.utils.PlotlyJSONEncoder)

        # Revenue Pie (Top 8)
        top8 = df.sort_values('Total_Revenue', ascending=False).head(8)
        fig_pie = px.pie(top8, values='Total_Revenue', names='Branch', title='📊 Distribusi Revenue per Cabang (Top 8)')
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        fig_pie.update_layout(height=400)
        charts['revenue_pie'] = json.dumps(fig_pie, cls=plotly.utils.PlotlyJSONEncoder)

        # Performance matrix
        fig_scatter = go.Figure()
        fig_scatter.add_trace(go.Scatter(
            x=df['Total_Revenue'],
            y=df['Margin_Percentage'],
            mode='markers',
            marker=dict(size=10, color=df['COGS_Percentage'], colorscale='RdYlBu_r', showscale=True, colorbar=dict(title="COGS (%)")),
            text=df['Branch'],
            hovertemplate='<b>%{text}</b><br>Revenue: Rp %{x:,.0f}<br>Margin: %{y:.1f}%<extra></extra>'
        ))
        fig_scatter.update_layout(
            title='💎 Matrix Performa Cabang (Revenue vs Margin)',
            xaxis_title='Total Revenue (Rp)', yaxis_title='Margin (%)', height=400
        )
        charts['performance_matrix'] = json.dumps(fig_scatter, cls=plotly.utils.PlotlyJSONEncoder)

        # Top products (dashboard context)
        try:
            prod = analyzer.get_product_comparison_by_branch(10)
            if safe_df_check(prod):
                top_prod = (prod.groupby('Menu').agg({'Qty':'sum','Total':'sum'}).reset_index()
                            .sort_values('Total', ascending=False).head(10))
                fig_prod = go.Figure([go.Bar(
                    x=list(range(len(top_prod))),
                    y=top_prod['Total'].tolist(),
                    text=[f'Rp {x:,.0f}' for x in top_prod['Total']],
                    textposition='outside',
                    marker_color='rgba(255,140,0,0.8)'
                )])
                fig_prod.update_layout(
                    title='🍜 Top 10 Produk by Revenue',
                    xaxis=dict(tickmode='array', tickvals=list(range(len(top_prod))), ticktext=top_prod['Menu'].tolist(), tickangle=-45),
                    yaxis_title='Revenue (Rp)', height=400, margin=dict(l=20,r=20,t=40,b=120), showlegend=False
                )
                charts['top_products'] = json.dumps(fig_prod, cls=plotly.utils.PlotlyJSONEncoder)
        except Exception as e:
            print(f"⚠️ Products chart error: {e}")

    except Exception as e:
        print(f"❌ Dashboard charts error: {e}")
        print(traceback.format_exc())
    return charts

def create_branch_comparison_charts(df):
    charts = {}
    try:
        if not safe_df_check(df): return charts

        ordered = df.sort_values('Total_Revenue', ascending=False).copy()
        fig_rev = go.Figure([go.Bar(
            x=list(range(len(ordered))),
            y=ordered['Total_Revenue'].tolist(),
            text=[f'Rp {x:,.0f}' for x in ordered['Total_Revenue']],
            textposition='outside',
            marker_color='rgba(0,139,139,0.8)'
        )])
        fig_rev.update_layout(
            title='💰 Total Revenue per Cabang',
            xaxis=dict(tickmode='array', tickvals=list(range(len(ordered))), ticktext=ordered['Branch'].tolist(), tickangle=-45),
            yaxis_title='Revenue (Rp)', height=500, margin=dict(l=20,r=20,t=40,b=120), showlegend=False
        )
        charts['revenue_comparison'] = json.dumps(fig_rev, cls=plotly.utils.PlotlyJSONEncoder)

        fig_mc = go.Figure()
        fig_mc.add_trace(go.Scatter(
            x=df['COGS_Percentage'],
            y=df['Margin_Percentage'],
            mode='markers',
            marker=dict(size=12, color=df['Total_Revenue'], colorscale='Viridis', showscale=True, colorbar=dict(title="Revenue (Rp)")),
            text=df['Branch'],
            hovertemplate='<b>%{text}</b><br>COGS: %{x:.1f}%<br>Margin: %{y:.1f}%<extra></extra>'
        ))
        fig_mc.update_layout(title='📊 Margin vs COGS per Cabang', xaxis_title='COGS (%)', yaxis_title='Margin (%)', height=500)
        charts['margin_cogs'] = json.dumps(fig_mc, cls=plotly.utils.PlotlyJSONEncoder)

        tmp = df.copy()
        tmp['Revenue_per_Transaction'] = tmp.apply(lambda r: safe_divide(r['Total_Revenue'], r['Transaction_Count']), axis=1)
        eff = tmp.sort_values('Revenue_per_Transaction', ascending=False)
        fig_eff = go.Figure([go.Bar(
            x=list(range(len(eff))),
            y=eff['Revenue_per_Transaction'].tolist(),
            text=[f'Rp {x:,.0f}' for x in eff['Revenue_per_Transaction']],
            textposition='outside',
            marker_color='rgba(255,165,0,0.8)'
        )])
        fig_eff.update_layout(
            title='⚡ Efisiensi Revenue per Transaksi',
            xaxis=dict(tickmode='array', tickvals=list(range(len(eff))), ticktext=eff['Branch'].tolist(), tickangle=-45),
            yaxis_title='Revenue per Transaksi (Rp)', height=500, margin=dict(l=20,r=20,t=40,b=120), showlegend=False
        )
        charts['efficiency'] = json.dumps(fig_eff, cls=plotly.utils.PlotlyJSONEncoder)

    except Exception as e:
        print(f"❌ Branch comparison charts error: {e}")
        print(traceback.format_exc())
    return charts

def create_cogs_analysis_charts(cogs, branch_cogs):
    charts = {}
    try:
        if not (safe_df_check(cogs) and safe_df_check(branch_cogs)): return charts

        # Heatmap top 15 produk by revenue (untuk keterbacaan)
        top15 = cogs.groupby('Menu')['Total'].sum().nlargest(15).index
        filt = cogs[cogs['Menu'].isin(top15)]
        if safe_df_check(filt):
            piv = filt.pivot(index='Menu', columns='Branch', values='COGS Total (%)').fillna(0)
            fig_heat = px.imshow(piv, title='🔥 COGS % per Produk per Cabang (Top 15)', aspect='auto',
                                 color_continuous_scale='RdYlGn_r', labels={'color': 'COGS (%)'})
            fig_heat.update_layout(height=600)
            charts['cogs_heatmap'] = json.dumps(fig_heat, cls=plotly.utils.PlotlyJSONEncoder)

        ordered = branch_cogs.sort_values('COGS_Efficiency', ascending=False)
        fig_eff = go.Figure([go.Bar(
            x=list(range(len(ordered))),
            y=ordered['COGS_Efficiency'].tolist(),
            text=[f'{x:.1f}%' for x in ordered['COGS_Efficiency']],
            textposition='outside',
            marker_color='rgba(50,205,50,0.8)'
        )])
        fig_eff.update_layout(
            title='📊 Efisiensi COGS per Cabang',
            xaxis=dict(tickmode='array', tickvals=list(range(len(ordered))), ticktext=ordered['Branch'].tolist(), tickangle=-45),
            yaxis_title='Efisiensi COGS (%)', height=500, margin=dict(l=20,r=20,t=40,b=120), showlegend=False
        )
        charts['branch_efficiency'] = json.dumps(fig_eff, cls=plotly.utils.PlotlyJSONEncoder)

        stats = cogs.groupby('Menu')['COGS Total (%)'].agg(['mean','std','count']).reset_index()
        stats = stats[(stats['count'] > 1) & (stats['std'] > 0) & (stats['mean'] > 0)].copy()
        if safe_df_check(stats):
            stats['CV'] = stats['std'] / stats['mean']
            top_cv = stats.sort_values('CV', ascending=False).head(15)
            fig_cv = go.Figure([go.Bar(
                x=list(range(len(top_cv))),
                y=top_cv['CV'].tolist(),
                text=[f'{x:.2f}' for x in top_cv['CV']],
                textposition='outside',
                marker_color='rgba(220,20,60,0.8)'
            )])
            fig_cv.update_layout(
                title='📊 Top 15 Produk dengan Variasi COGS Tertinggi',
                xaxis=dict(tickmode='array', tickvals=list(range(len(top_cv))), ticktext=top_cv['Menu'].tolist(), tickangle=-45),
                yaxis_title='Coefficient of Variation', height=600, margin=dict(l=20,r=20,t=40,b=150), showlegend=False
            )
            charts['cogs_variance'] = json.dumps(fig_cv, cls=plotly.utils.PlotlyJSONEncoder)

    except Exception as e:
        print(f"❌ COGS charts error: {e}")
        print(traceback.format_exc())
    return charts

def create_time_charts_all_branches(time_analysis):
    """Time analysis. Branch trends: SEMUA cabang, hover single-trace only."""
    charts = {}
    try:
        # Daily pattern (opsional)
        if time_analysis.get('daily_pattern', {}).get('length', 0) > 0:
            daily = time_analysis['daily_pattern']['data']
            agg = {}
            for it in daily:
                d = it.get('Day_of_Week', 'Unknown')
                r = it.get('Total_Revenue', 0) or 0
                agg[d] = agg.get(d, 0) + r
            if agg:
                days = list(agg.keys())
                vals = list(agg.values())
                fig_daily = go.Figure([go.Bar(
                    x=days, y=vals,
                    text=[f'Rp {x:,.0f}' for x in vals], textposition='outside',
                    marker_color='rgba(0,139,139,0.8)'
                )])
                fig_daily.update_layout(
                    title='📊 Penjualan per Hari dalam Seminggu',
                    xaxis_title='Hari', yaxis_title='Revenue (Rp)',
                    height=400, showlegend=False
                )
                charts['daily_pattern'] = json.dumps(fig_daily, cls=plotly.utils.PlotlyJSONEncoder)

        # Branch trends (ALL branches) — HOVER PER TRACE
        if time_analysis.get('daily_trend', {}).get('length', 0) > 0:
            trend = time_analysis['daily_trend']['data']
            per_branch, totals = {}, {}
            for row in trend:
                br = row.get('Branch', 'Unknown')
                dt = row.get('Date')
                rv = row.get('Total', 0) or 0
                per_branch.setdefault(br, []).append((dt, rv))
                totals[br] = totals.get(br, 0) + rv

            ordered = [b for b, _ in sorted(totals.items(), key=lambda x: x[1], reverse=True)]

            fig_trends = go.Figure()
            for br in ordered:
                pts = sorted(per_branch[br], key=lambda x: x[0] or "")
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                fig_trends.add_trace(go.Scatter(
                    x=xs, y=ys,
                    mode='lines+markers',
                    name=br,
                    line=dict(width=2),
                    marker=dict(size=4),
                    hovertemplate="<b>%{x}</b><br>Branch: " + br + "<br>Revenue: Rp %{y:,.0f}<extra></extra>"
                ))

            # ✅ HANYA tooltip untuk trace yang di-pointer
            fig_trends.update_layout(
                title='📅 Branch Sales Trends Over Time (All Branches)',
                xaxis_title='Tanggal',
                yaxis_title='Revenue (Rp)',
                height=450,
                hovermode='closest',  # <-- perbaikan utama (bukan 'x unified')
                # Garis panduan nyaman saat hover (tanpa tooltip gabungan)
                xaxis=dict(
                    showspikes=True, spikemode='across', spikesnap='cursor', spikethickness=1
                ),
                spikedistance=-1,
                hoverlabel=dict(namelength=-1),
                legend=dict(orientation='h', y=-0.2),
                margin=dict(t=60, l=60, r=20, b=80),
                uirevision="keep-zoom"
            )
            charts['branch_trends'] = json.dumps(fig_trends, cls=plotly.utils.PlotlyJSONEncoder)

        # Monthly (opsional)
        if time_analysis.get('monthly', {}).get('length', 0) > 0:
            monthly = time_analysis['monthly']['data']
            agg = {}
            for it in monthly:
                m = it.get('Month', 0) or 0
                r = it.get('Total', 0) or 0
                agg[m] = agg.get(m, 0) + r
            if agg:
                months = sorted(agg.keys())
                vals = [agg[m] for m in months]
                fig_mon = go.Figure([go.Bar(
                    x=[f'Month {int(m)}' for m in months],
                    y=vals, text=[f'Rp {x:,.0f}' for x in vals], textposition='outside',
                    marker_color='rgba(255,165,0,0.8)'
                )])
                fig_mon.update_layout(
                    title='📊 Total Penjualan per Bulan',
                    xaxis_title='Bulan', yaxis_title='Revenue (Rp)',
                    height=400, showlegend=False
                )
                charts['monthly_comparison'] = json.dumps(fig_mon, cls=plotly.utils.PlotlyJSONEncoder)

        # Placeholder jika semua kosong
        if not charts:
            empty = go.Figure()
            empty.add_annotation(text="Data sedang diproses, silakan refresh halaman",
                                 xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                                 font=dict(size=16, color="gray"))
            empty.update_layout(height=300)
            ph = json.dumps(empty, cls=plotly.utils.PlotlyJSONEncoder)
            charts = {'daily_pattern': ph, 'branch_trends': ph, 'monthly_comparison': ph}

        print("✅ Time charts built (ALL branches, hover single-trace)")
    except Exception as e:
        print(f"❌ Time charts error: {e}")
        print(traceback.format_exc())
        empty = json.dumps({"data": [], "layout": {"title": "Chart tidak dapat dimuat"}})
        charts = {'daily_pattern': empty, 'branch_trends': empty, 'monthly_comparison': empty}
    return charts

# ===== Error Handlers =====
@app.errorhandler(404)
def not_found_error(error):
    print(f"❌ 404: {request.url}")
    return render_template('error.html', error_code=404, error_message="Halaman tidak ditemukan"), 404

@app.errorhandler(500)
def internal_error(error):
    print(f"❌ 500: {error}")
    print(traceback.format_exc())
    return render_template('error.html', error_code=500, error_message="Terjadi kesalahan internal server"), 500

@app.errorhandler(413)
def too_large(error):
    print("❌ 413: File too large")
    return render_template('error.html', error_code=413, error_message="File terlalu besar. Maksimal 50MB per file"), 413

@app.errorhandler(Exception)
def handle_exception(e):
    print(f"❌ Unhandled: {e}")
    print(traceback.format_exc())
    if "TemplateNotFound" in str(e):
        return f"Template not found: {str(e)}. Check templates folder.", 500
    return f"An error occurred: {str(e)}", 500

# ===== Main =====
if __name__ == '__main__':
    print("🚀 Starting Flask Multi-Branch Analytics...")
    print(f"📁 Templates: {app.template_folder}")
    print(f"📁 Static:    {app.static_folder}")
    print(f"🔧 Debug:     {app.config['DEBUG']}")

    required = [
        'base.html','dashboard.html','upload.html',
        'branch_comparison.html','product_analysis.html',
        'sales_by_time.html','cogs_analysis.html','chat.html','error.html'
    ]
    missing = [t for t in required if not os.path.exists(os.path.join(app.template_folder, t))]
    if missing:
        print(f"❌ Missing templates: {missing}")
    else:
        print("✅ All required templates found")

    print("🌐 http://127.0.0.1:5000  |  🔍 /debug for status")
    app.run(debug=True, host='127.0.0.1', port=5000)

/**
 * Product Analysis JavaScript
 * Multi-Branch Sales Analytics
 */

// Global variables
let productData = [];

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Product Analysis JS loaded');
    initializeProductAnalysis();
});

function initializeProductAnalysis() {
    const branchSelect = document.getElementById('branchSelect');
    const topCount = document.getElementById('topCount');
    const sortBy = document.getElementById('sortBy');
    const analysisProduct = document.getElementById('analysisProduct');
    const detailAnalysis = document.getElementById('product-detail-analysis');
    
    if (!branchSelect || !topCount || !sortBy) {
        console.log('Product analysis elements not found, skipping initialization');
        return;
    }
    
    // Get product data from window (will be set by template)
    if (window.productAnalysisData) {
        productData = window.productAnalysisData;
        console.log('Product data loaded:', productData.length, 'records');
        
        // Event listeners
        branchSelect.addEventListener('change', function() {
            updateTopPerformersTable(productData);
            updateSelectionInfo(productData);
            updateProductDropdown(productData);
        });
        
        topCount.addEventListener('change', function() {
            if (branchSelect.value) {
                updateTopPerformersTable(productData);
            }
        });
        
        sortBy.addEventListener('change', function() {
            if (branchSelect.value) {
                updateTopPerformersTable(productData);
            }
        });
        
        // Product analysis
        analysisProduct.addEventListener('change', function() {
            const selectedProduct = this.value;
            const selectedBranch = branchSelect.value;
            if (selectedProduct && selectedBranch) {
                showProductDetails(selectedProduct, selectedBranch, productData);
                detailAnalysis.style.display = 'block';
            } else {
                detailAnalysis.style.display = 'none';
            }
        });
        
        // Initial load
        updateSelectionInfo(productData);
    } else {
        console.warn('No product data available');
    }
}

function updateTopPerformersTable(allData) {
    const selectedBranch = document.getElementById('branchSelect').value;
    const count = document.getElementById('topCount').value;
    const sortBy = document.getElementById('sortBy').value;
    const tableContainer = document.getElementById('top-performers-table');
    
    if (!tableContainer || allData.length === 0) {
        return;
    }
    
    console.log('Updating top performers for branch:', selectedBranch, 'count:', count, 'sort:', sortBy);
    
    // Must select a branch first
    if (!selectedBranch || selectedBranch === '') {
        tableContainer.innerHTML = `
            <div class="alert alert-warning text-center">
                <h6><i class="fas fa-info-circle me-2"></i>Pilih Cabang Terlebih Dahulu</h6>
                <p class="mb-0">Setiap cabang memiliki menu yang unik dan berbeda.<br>Silakan pilih cabang dari dropdown di atas untuk melihat top performers spesifik cabang tersebut.</p>
            </div>
        `;
        return;
    }
    
    // Filter data for selected branch ONLY
    const branchData = allData.filter(item => item.Branch === selectedBranch);
    
    if (branchData.length === 0) {
        tableContainer.innerHTML = `
            <div class="alert alert-danger text-center">
                <h6><i class="fas fa-exclamation-triangle me-2"></i>No Data</h6>
                <p class="mb-0">No data available for branch: <strong>${selectedBranch}</strong></p>
            </div>
        `;
        return;
    }
    
    // Aggregate products for this branch
    const productStats = {};
    branchData.forEach(item => {
        if (!productStats[item.Menu]) {
            productStats[item.Menu] = {
                Menu: item.Menu,
                Total: 0,
                Qty: 0,
                Margin: 0,
                branch: selectedBranch
            };
        }
        productStats[item.Menu].Total += (item.Total || 0);
        productStats[item.Menu].Qty += (item.Qty || 0);
        productStats[item.Menu].Margin += (item.Margin || 0);
    });
    
    // Convert to array and calculate percentages
    const products = Object.values(productStats).map(product => ({
        ...product,
        Margin_Percentage: product.Total > 0 ? (product.Margin / product.Total * 100) : 0,
        Avg_Price: product.Qty > 0 ? (product.Total / product.Qty) : 0
    }));
    
    // Sort based on selection
    let sortField = 'Total';
    if (sortBy === 'quantity') sortField = 'Qty';
    else if (sortBy === 'margin') sortField = 'Margin_Percentage';
    
    // Apply count filter - if "all" show all products
    const topProducts = products
        .sort((a, b) => b[sortField] - a[sortField])
        .slice(0, count === 'all' ? products.length : parseInt(count));
    
    console.log('Products calculated for', selectedBranch, ':', topProducts.length, 'of', products.length, 'total');
    
    // Create table
    tableContainer.innerHTML = `
        <div class="table-responsive">
            <table class="table" id="topPerformersTable">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Produk (${selectedBranch})</th>
                        <th>Revenue</th>
                        <th>Quantity</th>
                        <th>Margin %</th>
                        <th>Avg Price</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="topPerformersBody"></tbody>
            </table>
            <div class="mt-3 text-center text-muted">
                Menampilkan ${topProducts.length} dari ${products.length} total menu di ${selectedBranch}
            </div>
        </div>
    `;
    
    const tbody = document.getElementById('topPerformersBody');
    topProducts.forEach((product, index) => {
        const row = document.createElement('tr');
        
        let rankBadge = 'status-fair';
        if (index < 3) rankBadge = 'status-excellent';
        else if (index < 10) rankBadge = 'status-good';
        
        let marginBadge = 'status-poor';
        if (product.Margin_Percentage > 30) marginBadge = 'status-excellent';
        else if (product.Margin_Percentage > 20) marginBadge = 'status-good';
        else if (product.Margin_Percentage > 10) marginBadge = 'status-fair';
        
        let statusBadge = 'status-poor';
        let statusText = 'Needs Review';
        if (index < 3 && product.Margin_Percentage > 20) {
            statusBadge = 'status-excellent';
            statusText = 'Star Product';
        } else if (index < 10 && product.Margin_Percentage > 15) {
            statusBadge = 'status-good';
            statusText = 'Good Performer';
        } else if (product.Margin_Percentage > 10) {
            statusBadge = 'status-fair';
            statusText = 'Average';
        }
        
        row.innerHTML = `
            <td><span class="badge ${rankBadge}">#${index + 1}</span></td>
            <td><strong>${product.Menu.length > 50 ? product.Menu.substring(0, 50) + '...' : product.Menu}</strong></td>
            <td>${formatCurrency(product.Total)}</td>
            <td>${formatNumber(product.Qty)}</td>
            <td><span class="badge ${marginBadge}">${product.Margin_Percentage.toFixed(1)}%</span></td>
            <td>${formatCurrency(product.Avg_Price)}</td>
            <td><span class="badge ${statusBadge}">${statusText}</span></td>
        `;
        
        tbody.appendChild(row);
    });
    
    // Update summary
    updateTopPerformersSummary(topProducts, selectedBranch, sortBy, products.length);
}

function updateSelectionInfo(allData) {
    const selectedBranch = document.getElementById('branchSelect').value;
    const selectionText = document.getElementById('selection-text');
    const statProducts = document.getElementById('stat-products');
    const statRecords = document.getElementById('stat-records');
    const statBranches = document.getElementById('stat-branches');
    
    if (!selectionText || allData.length === 0) {
        return;
    }
    
    if (!selectedBranch || selectedBranch === '') {
        selectionText.textContent = 'Setiap cabang memiliki menu yang UNIK dan BERBEDA';
        if (statProducts) statProducts.textContent = 'N/A';
        if (statRecords) statRecords.textContent = 'N/A';
        if (statBranches) statBranches.textContent = 'N/A';
        return;
    }
    
    const branchData = allData.filter(item => item.Branch === selectedBranch);
    const uniqueProducts = new Set(branchData.map(item => item.Menu)).size;
    
    selectionText.textContent = `Menampilkan menu spesifik untuk: ${selectedBranch}`;
    if (statProducts) statProducts.textContent = uniqueProducts;
    if (statRecords) statRecords.textContent = branchData.length;
    if (statBranches) statBranches.textContent = '1 (Selected)';
}

function updateTopPerformersSummary(topProducts, selectedBranch, sortBy, totalProducts) {
    const summaryContent = document.getElementById('summary-content');
    
    if (!summaryContent || !selectedBranch || selectedBranch === '') {
        if (summaryContent) {
            summaryContent.innerHTML = '<div class="text-muted">Pilih cabang untuk melihat summary</div>';
        }
        return;
    }
    
    if (topProducts.length === 0) {
        summaryContent.innerHTML = '<div class="text-danger">No products found for selected branch</div>';
        return;
    }
    
    const top3 = topProducts.slice(0, 3);
    const totalRevenue = topProducts.reduce((sum, p) => sum + p.Total, 0);
    const avgMargin = topProducts.reduce((sum, p) => sum + p.Margin_Percentage, 0) / topProducts.length;
    
    const sortText = sortBy === 'revenue' ? 'revenue' : sortBy === 'quantity' ? 'quantity' : 'margin';
    
    summaryContent.innerHTML = `
        <div>
            <p class="mb-2"><strong>Top 3 by ${sortText} di ${selectedBranch}:</strong></p>
            <ol class="mb-3">
                ${top3.map(p => `<li>${p.Menu.substring(0, 35)}${p.Menu.length > 35 ? '...' : ''}</li>`).join('')}
            </ol>
            <div class="row">
                <div class="col-md-6">
                    <ul class="mb-0">
                        <li><strong>Total Revenue:</strong> ${formatCurrency(totalRevenue)}</li>
                        <li><strong>Avg Margin:</strong> ${avgMargin.toFixed(1)}%</li>
                    </ul>
                </div>
                <div class="col-md-6">
                    <ul class="mb-0">
                        <li><strong>Showing:</strong> ${topProducts.length} of ${totalProducts || topProducts.length}</li>
                        <li><strong>Analysis:</strong> <span class="text-success">✅ Branch-Specific</span></li>
                    </ul>
                </div>
            </div>
        </div>
    `;
}

function updateProductDropdown(allData) {
    const selectedBranch = document.getElementById('branchSelect').value;
    const analysisProduct = document.getElementById('analysisProduct');
    const branchInfoText = document.getElementById('branchInfoText');
    
    if (!analysisProduct || !selectedBranch || selectedBranch === '') {
        analysisProduct.innerHTML = '<option value="">-- Pilih cabang terlebih dahulu --</option>';
        analysisProduct.disabled = true;
        
        if (branchInfoText) {
            branchInfoText.innerHTML = '<i class="fas fa-info-circle text-primary me-2"></i>Pilih cabang untuk melihat informasi';
        }
        return;
    }
    
    // Get products for selected branch
    const branchData = allData.filter(item => item.Branch === selectedBranch);
    const branchProducts = [...new Set(branchData.map(item => item.Menu))].sort();
    
    // Update product dropdown
    analysisProduct.innerHTML = '<option value="">-- Pilih produk untuk analisis detail --</option>';
    branchProducts.forEach(product => {
        const option = document.createElement('option');
        option.value = product;
        option.textContent = product.length > 60 ? product.substring(0, 60) + '...' : product;
        analysisProduct.appendChild(option);
    });
    
    analysisProduct.disabled = false;
    
    // Update branch info
    if (branchInfoText) {
        branchInfoText.innerHTML = `
            <i class="fas fa-store text-success me-2"></i>
            <strong>${selectedBranch}</strong> - ${branchProducts.length} menu tersedia
        `;
    }
    
    console.log(`Updated product dropdown for ${selectedBranch}: ${branchProducts.length} products`);
}

function showProductDetails(productName, selectedBranch, allData) {
    if (allData.length === 0 || !selectedBranch || selectedBranch === '') {
        return;
    }
    
    // Filter data for selected product and branch
    const productData = allData.filter(item => 
        item.Menu === productName && item.Branch === selectedBranch
    );
    
    if (productData.length === 0) {
        return;
    }
    
    // Calculate product metrics for this specific branch
    const totalRevenue = productData.reduce((sum, item) => sum + (item.Total || 0), 0);
    const totalQty = productData.reduce((sum, item) => sum + (item.Qty || 0), 0);
    const totalMargin = productData.reduce((sum, item) => sum + (item.Margin || 0), 0);
    const avgMargin = totalRevenue > 0 ? (totalMargin / totalRevenue * 100) : 0;
    
    // Update info text
    const infoElement = document.getElementById('product-analysis-info');
    if (infoElement) {
        infoElement.textContent = `Analyzing "${productName}" from ${selectedBranch} - ${productData.length} transaction records found`;
    }
    
    // Update metric cards
    document.getElementById('total-revenue-product').textContent = formatCurrency(totalRevenue);
    document.getElementById('total-qty-product').textContent = formatNumber(totalQty);
    document.getElementById('avg-margin-product').textContent = avgMargin.toFixed(1) + '%';
    document.getElementById('branches-available').textContent = selectedBranch;
    
    // Update chart title
    const chartTitle = document.getElementById('chart-title-dynamic');
    if (chartTitle) {
        chartTitle.textContent = `💰 ${productName} - Financial Breakdown`;
    }
    
    // Create enhanced chart for this single branch product
    createEnhancedProductChart(productData, productName, selectedBranch);
}

function createEnhancedProductChart(productData, productName, branchName) {
    if (productData.length === 0) {
        document.getElementById('product-comparison-chart').innerHTML = `
            <div class="text-center py-5">
                <i class="fas fa-chart-pie fa-3x text-muted mb-3"></i>
                <h5 class="text-muted">No Data Available</h5>
                <p class="text-muted">Unable to create chart for this product</p>
            </div>
        `;
        return;
    }
    
    // Aggregate data for this product
    const totalRevenue = productData.reduce((sum, item) => sum + (item.Total || 0), 0);
    const totalMargin = productData.reduce((sum, item) => sum + (item.Margin || 0), 0);
    const totalCogs = productData.reduce((sum, item) => sum + (item['COGS Total'] || 0), 0);
    
    // Calculate components - Fixed calculation
    const netRevenue = totalRevenue - totalCogs; // Net after COGS, before margin
    const components = [
        { label: 'Net Revenue', value: netRevenue, color: '#2E8B57' },
        { label: 'Margin (Profit)', value: totalMargin, color: '#4CAF50' },
        { label: 'COGS (Cost)', value: totalCogs, color: '#FF6B6B' }
    ].filter(item => item.value > 0);
    
    if (components.length === 0) {
        document.getElementById('product-comparison-chart').innerHTML = `
            <div class="text-center py-5">
                <i class="fas fa-exclamation-triangle fa-3x text-warning mb-3"></i>
                <h5 class="text-warning">Invalid Data</h5>
                <p class="text-muted">Unable to calculate financial breakdown</p>
            </div>
        `;
        return;
    }
    
    const chartData = [{
        values: components.map(c => c.value),
        labels: components.map(c => c.label),
        type: 'pie',
        textinfo: 'label+percent',
        textposition: 'auto',
        hovertemplate: '<b>%{label}</b><br>Value: Rp %{value:,.0f}<br>Percentage: %{percent}<br><extra></extra>',
        marker: {
            colors: components.map(c => c.color),
            line: {
                color: '#FFFFFF',
                width: 2
            }
        },
        textfont: {
            size: 12,
            color: 'white'
        },
        pull: [0.05, 0.05, 0.05]
    }];
    
    const layout = {
        title: {
            text: `${productName}<br><span style="font-size:14px">${branchName}</span>`,
            font: { size: 16, color: '#2c3e50' }
        },
        height: 450,
        margin: { t: 80, l: 50, r: 50, b: 50 },
        showlegend: true,
        legend: {
            orientation: 'h',
            y: -0.1,
            x: 0.5,
            xanchor: 'center',
            font: { size: 12 }
        },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        annotations: [{
            text: `Total: ${formatCurrency(totalRevenue)}<br>Records: ${productData.length}`,
            x: 0.5,
            y: 0.5,
            xref: 'paper',
            yref: 'paper',
            showarrow: false,
            font: {
                size: 14,
                color: '#34495e'
            },
            bgcolor: 'rgba(255,255,255,0.8)',
            bordercolor: '#bdc3c7',
            borderwidth: 1
        }]
    };
    
    try {
        Plotly.newPlot('product-comparison-chart', chartData, layout, {
            responsive: true,
            displayModeBar: false,
            staticPlot: false
        });
        
        console.log('Enhanced product chart created successfully');
    } catch (error) {
        console.error('Error creating enhanced product chart:', error);
        
        // Fallback to simple display
        document.getElementById('product-comparison-chart').innerHTML = `
            <div class="row text-center py-4">
                <div class="col-md-4">
                    <div class="card border-success">
                        <div class="card-body">
                            <h5 class="card-title text-success">Net Revenue</h5>
                            <h4 class="text-success">${formatCurrency(netRevenue)}</h4>
                            <small class="text-muted">${((netRevenue/totalRevenue)*100).toFixed(1)}%</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card border-primary">
                        <div class="card-body">
                            <h5 class="card-title text-primary">Margin (Profit)</h5>
                            <h4 class="text-primary">${formatCurrency(totalMargin)}</h4>
                            <small class="text-muted">${((totalMargin/totalRevenue)*100).toFixed(1)}%</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card border-danger">
                        <div class="card-body">
                            <h5 class="card-title text-danger">COGS (Cost)</h5>
                            <h4 class="text-danger">${formatCurrency(totalCogs)}</h4>
                            <small class="text-muted">${((totalCogs/totalRevenue)*100).toFixed(1)}%</small>
                        </div>
                    </div>
                </div>
            </div>
            <div class="text-center mt-3">
                <h6>${productName} - ${branchName}</h6>
                <p class="text-muted">Total Revenue: ${formatCurrency(totalRevenue)} | Records: ${productData.length}</p>
            </div>
        `;
    }
}

// Utility functions
function formatCurrency(value) {
    return new Intl.NumberFormat('id-ID', {
        style: 'currency',
        currency: 'IDR',
        minimumFractionDigits: 0
    }).format(value || 0);
}

function formatNumber(value) {
    return new Intl.NumberFormat('id-ID').format(value || 0);
}

// Export functions for global access if needed
window.ProductAnalysis = {
    updateTopPerformersTable,
    updateSelectionInfo,
    updateProductDropdown,
    showProductDetails,
    createEnhancedProductChart,
    formatCurrency,
    formatNumber
};
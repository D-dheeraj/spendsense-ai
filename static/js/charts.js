/**
 * SpendSense AI — Chart.js Wrappers
 * ===================================
 * Manages all Chart.js chart instances.
 *
 * Charts:
 *   1. Category Donut Chart   — % spend per category (latest batch)
 *   2. Monthly Trend + Forecast — spending trend with dotted Linear Regression forecast line
 *   3. Health Score Gauge     — 0-100 half-doughnut gauge (Poor / Fair / Good / Excellent)
 */

/* ─── Category Color Map (Warm, Distinct Fintech Palette matching CSS variables) ───*/
const CATEGORY_COLORS = {
  Dining:        { bg: 'rgba(245, 158, 11, 0.85)',  border: '#F59E0B' }, // amber
  Shopping:      { bg: 'rgba(249, 115, 98, 0.85)',  border: '#F97362' }, // coral
  Bills:         { bg: 'rgba(224, 109, 83, 0.85)',  border: '#E06D53' }, // terracotta
  Groceries:     { bg: 'rgba(132, 150, 66, 0.85)',  border: '#849642' }, // olive
  Travel:        { bg: 'rgba(45, 212, 191, 0.85)',  border: '#2DD4BF' }, // teal
  Transfer:      { bg: 'rgba(212, 163, 115, 0.85)', border: '#D4A373' }, // sand
  Entertainment: { bg: 'rgba(168, 85, 247, 0.85)',  border: '#A855F7' }, // plum
  Health:        { bg: 'rgba(148, 163, 184, 0.85)', border: '#94A3B8' }, // slate
};

/* Default fallback colors for unknown categories */
const FALLBACK_COLORS = [
  '#F59E0B', '#F97362', '#E06D53', '#849642',
  '#2DD4BF', '#D4A373', '#A855F7', '#94A3B8'
];

let categoryChartInstance = null;
let trendChartInstance    = null;
let healthGaugeInstance   = null;

/* ─── Global Chart.js Defaults ────────────────────────────────────────────────*/
function isLightTheme() {
  return document.documentElement.getAttribute('data-theme') === 'light';
}

function getChartColors() {
  const light = isLightTheme();
  return {
    text: light ? '#635242' : '#C9BBA8',
    heading: light ? '#2C2219' : '#F5EDE3',
    grid: light ? 'rgba(44, 34, 25, 0.08)' : 'rgba(245, 237, 227, 0.08)',
    tooltipBg: light ? '#FFFFFF' : '#211B15',
    tooltipBorder: light ? '#E5DACB' : '#3A3027',
    tooltipText: light ? '#2C2219' : '#F5EDE3'
  };
}

Chart.defaults.color          = '#C9BBA8';
Chart.defaults.borderColor    = 'rgba(245, 237, 227, 0.08)';
Chart.defaults.font.family    = "'Inter', sans-serif";
Chart.defaults.font.size      = 12;


/* ─── Category Donut Chart ────────────────────────────────────────────────────*/

function renderCategoryChart(categoryTotals) {
  const ctx = document.getElementById('category-chart');
  if (!ctx) return;

  const labels  = Object.keys(categoryTotals);
  const data    = Object.values(categoryTotals).map(v => parseFloat(v).toFixed(2));
  const total   = data.reduce((sum, v) => sum + parseFloat(v), 0);

  const bgColors     = labels.map((l, i) => (CATEGORY_COLORS[l] || {}).bg     || FALLBACK_COLORS[i % FALLBACK_COLORS.length]);
  const borderColors = labels.map((l, i) => (CATEGORY_COLORS[l] || {}).border || FALLBACK_COLORS[i % FALLBACK_COLORS.length]);

  if (categoryChartInstance) {
    categoryChartInstance.destroy();
  }

  categoryChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: bgColors,
        borderColor:     borderColors,
        borderWidth:     2,
        hoverBorderWidth:4,
        hoverOffset:     8,
      }]
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      cutout:              '68%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            padding:    16,
            boxWidth:   12,
            boxHeight:  12,
            borderRadius:6,
            usePointStyle: true,
            pointStyle:   'circle',
            color:        getChartColors().text,
            font:         { size: 12, weight: '500' }
          }
        },
        tooltip: {
          backgroundColor: getChartColors().tooltipBg,
          borderColor:     getChartColors().tooltipBorder,
          borderWidth:     1,
          titleColor:      getChartColors().heading,
          bodyColor:       getChartColors().text,
          padding:         12,
          callbacks: {
            label: function(ctx) {
              const value = parseFloat(ctx.raw);
              const pct   = ((value / total) * 100).toFixed(1);
              return `  ₹${value.toLocaleString('en-IN', {minimumFractionDigits:0})}  (${pct}%)`;
            }
          }
        }
      },
      animation: {
        animateRotate:  true,
        animateScale:   true,
        duration:       800,
        easing:         'easeOutQuart',
      }
    },
    plugins: [{
      id: 'centerText',
      beforeDraw(chart) {
        const { ctx, chartArea: { top, right, bottom, left, width, height } } = chart;
        const cx = left + width  / 2;
        const cy = top  + height / 2;
        const themeColors = getChartColors();
        ctx.save();
        ctx.fillStyle   = themeColors.heading;
        ctx.font        = `800 1.5rem 'Inter', sans-serif`;
        ctx.textAlign   = 'center';
        ctx.textBaseline= 'middle';
        ctx.fillText(`₹${formatCompact(total)}`, cx, cy - 10);
        ctx.fillStyle   = themeColors.text;
        ctx.font        = `500 0.72rem 'Inter', sans-serif`;
        ctx.fillText('Total Spend', cx, cy + 12);
        ctx.restore();
      }
    }]
  });
}


/* ─── Monthly Trend + Forecast Line ───────────────────────────────────────────*/

/**
 * Render monthly spending trend with scikit-learn Linear Regression forecast line.
 * @param {Object} monthlyTotals — {"YYYY-MM": amount}
 * @param {Object} forecast      — {has_enough_data: bool, next_month: str, predicted_amount: float}
 */
function renderTrendChart(monthlyTotals, forecast = null) {
  const ctx = document.getElementById('trend-chart');
  if (!ctx) return;

  const sorted = Object.entries(monthlyTotals)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-8);

  const labels = sorted.map(([ym]) => {
    const [y, m] = ym.split('-');
    return new Date(y, m - 1).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' });
  });

  const actualData = sorted.map(([, v]) => parseFloat(v));
  const forecastData = new Array(actualData.length).fill(null);

  const datasets = [
    {
      type: 'bar',
      label: 'Actual Spend (₹)',
      data: actualData,
      backgroundColor: 'rgba(245, 158, 11, 0.4)',
      borderColor: '#F59E0B',
      borderWidth: 2,
      borderRadius: 8,
      borderSkipped: false,
      hoverBackgroundColor: 'rgba(249, 115, 98, 0.65)',
      order: 2
    }
  ];

  // If forecast is available (>= 3 months data)
  if (forecast && forecast.has_enough_data && forecast.next_month && forecast.predicted_amount) {
    const [ny, nm] = forecast.next_month.split('-');
    const nextLabel = new Date(ny, nm - 1).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' }) + ' (Forecast)';

    labels.push(nextLabel);
    actualData.push(null); // No actual bar for forecast month

    // Dotted line starts at last historical value and connects to predicted value
    const lineData = new Array(labels.length).fill(null);
    const lastHistIdx = sorted.length - 1;
    lineData[lastHistIdx] = actualData[lastHistIdx] || sorted[lastHistIdx][1];
    lineData[labels.length - 1] = forecast.predicted_amount;

    datasets.push({
      type: 'line',
      label: 'Forecast (Next Month)',
      data: lineData,
      borderColor: '#F97362',
      borderWidth: 3,
      borderDash: [6, 6],
      pointBackgroundColor: '#F97362',
      pointBorderColor: '#FFFFFF',
      pointRadius: 6,
      pointHoverRadius: 8,
      fill: false,
      order: 1
    });

    const infoEl = document.getElementById('forecast-info-badge');
    if (infoEl) {
      infoEl.innerHTML = `<strong>Forecast:</strong> ${forecast.message}`;
      infoEl.style.display = 'block';
    }
  } else {
    const infoEl = document.getElementById('forecast-info-badge');
    if (infoEl) {
      infoEl.innerHTML = `<strong>Forecast:</strong> Need at least 3 months data to project future spend.`;
      infoEl.style.display = 'block';
    }
  }

  if (trendChartInstance) {
    trendChartInstance.destroy();
  }

  const themeColors = getChartColors();

  trendChartInstance = new Chart(ctx, {
    data: {
      labels,
      datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            boxWidth: 12,
            boxHeight: 12,
            usePointStyle: true,
            color: themeColors.text,
            font: { size: 11, weight: '600' }
          }
        },
        tooltip: {
          backgroundColor: themeColors.tooltipBg,
          borderColor: themeColors.tooltipBorder,
          borderWidth: 1,
          titleColor: themeColors.heading,
          bodyColor: themeColors.text,
          padding: 12,
          callbacks: {
            label: (ctx) => {
              if (ctx.raw === null || ctx.raw === undefined) return '';
              const prefix = ctx.dataset.label.includes('Forecast') ? 'Predicted' : 'Actual';
              return `  ${prefix}: ₹${parseFloat(ctx.raw).toLocaleString('en-IN', {minimumFractionDigits: 0})}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: themeColors.text, font: { size: 11 } }
        },
        y: {
          grid: { color: themeColors.grid },
          ticks: {
            color: themeColors.text,
            font: { size: 11 },
            callback: (v) => `₹${formatCompact(v)}`
          }
        }
      },
      animation: {
        duration: 800,
        easing: 'easeOutQuart'
      }
    }
  });
}


/* ─── Financial Health Score Gauge (Half-Doughnut) ───────────────────────────*/

/**
 * Render the 0-100 Financial Health Score gauge.
 * Uses half-doughnut with circumference 180 and rotation 270.
 * @param {Object} healthData — from API: {score, label, color, explanation, breakdown}
 */
function renderHealthScoreGauge(healthData) {
  const ctx = document.getElementById('health-gauge-chart');
  if (!ctx || !healthData || !healthData.has_data) return;

  const score = Math.max(0, Math.min(100, healthData.score || 0));
  const remaining = 100 - score;

  if (healthGaugeInstance) {
    healthGaugeInstance.destroy();
  }

  healthGaugeInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Health Score', 'Remaining'],
      datasets: [{
        data: [score, remaining],
        backgroundColor: [
          healthData.color || '#10b981',
          'rgba(255, 255, 255, 0.05)'
        ],
        borderWidth: 0,
        hoverOffset: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      circumference: 180,
      rotation: 270,
      cutout: '78%',
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false }
      },
      animation: {
        animateRotate: true,
        duration: 1000,
        easing: 'easeOutQuart'
      }
    },
    plugins: [{
      id: 'gaugeCenterText',
      beforeDraw(chart) {
        const { ctx, chartArea: { top, right, bottom, left, width, height } } = chart;
        const cx = left + width / 2;
        const cy = top + height - 10;

        ctx.save();
        const themeColors = getChartColors();
        // Big score number
        ctx.fillStyle = healthData.color || '#4ADE80';
        ctx.font = `800 2.2rem 'Inter', sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(score, cx, cy - 20);

        // Grade label
        ctx.fillStyle = themeColors.heading;
        ctx.font = `700 0.85rem 'Inter', sans-serif`;
        ctx.fillText(healthData.label.toUpperCase(), cx, cy - 4);

        // Subtitle
        ctx.fillStyle = themeColors.text;
        ctx.font = `500 0.65rem 'Inter', sans-serif`;
        ctx.fillText('FINANCIAL HEALTH', cx, cy + 12);
        ctx.restore();
      }
    }]
  });

  // Update breakdown UI elements
  const scoreBadge = document.getElementById('health-score-badge');
  if (scoreBadge) {
    scoreBadge.textContent = `${score}/100 · ${healthData.label}`;
    scoreBadge.style.color = healthData.color;
    scoreBadge.style.borderColor = healthData.color;
  }

  const expEl = document.getElementById('health-explanation');
  if (expEl) {
    expEl.textContent = healthData.explanation || '';
  }

  // Pillar indicators
  if (healthData.breakdown) {
    const b = healthData.breakdown;
    const setPillar = (id, val, max, unit='') => {
      const el = document.getElementById(id);
      if (el) el.textContent = `${val}${unit} / ${max}${unit}`;
    };
    setPillar('pillar-disc', b.discretionary_score, b.discretionary_max);
    setPillar('pillar-stability', b.stability_score, b.stability_max);
    setPillar('pillar-anomaly', b.anomaly_score, b.anomaly_max);
    setPillar('pillar-trend', b.trend_score, b.trend_max);
  }
}


/* ─── Dynamic Theme Updates for Charts ────────────────────────────────────────*/

function updateChartsTheme(theme) {
  const colors = getChartColors();
  Chart.defaults.color = colors.text;
  Chart.defaults.borderColor = colors.grid;

  if (categoryChartInstance) {
    categoryChartInstance.options.plugins.legend.labels.color = colors.text;
    categoryChartInstance.options.plugins.tooltip.backgroundColor = colors.tooltipBg;
    categoryChartInstance.options.plugins.tooltip.borderColor = colors.tooltipBorder;
    categoryChartInstance.options.plugins.tooltip.titleColor = colors.heading;
    categoryChartInstance.options.plugins.tooltip.bodyColor = colors.text;
    categoryChartInstance.update();
  }

  if (trendChartInstance) {
    trendChartInstance.options.plugins.legend.labels.color = colors.text;
    trendChartInstance.options.plugins.tooltip.backgroundColor = colors.tooltipBg;
    trendChartInstance.options.plugins.tooltip.borderColor = colors.tooltipBorder;
    trendChartInstance.options.plugins.tooltip.titleColor = colors.heading;
    trendChartInstance.options.plugins.tooltip.bodyColor = colors.text;
    trendChartInstance.options.scales.x.ticks.color = colors.text;
    trendChartInstance.options.scales.y.ticks.color = colors.text;
    trendChartInstance.options.scales.y.grid.color = colors.grid;
    trendChartInstance.update();
  }

  if (healthGaugeInstance) {
    healthGaugeInstance.update();
  }

  // Also check admin category chart if present
  if (window.adminCategoryChartInstance) {
    window.adminCategoryChartInstance.options.plugins.legend.labels.color = colors.text;
    window.adminCategoryChartInstance.update();
  }
}


/* ─── Utility ─────────────────────────────────────────────────────────────────*/

function formatCompact(num) {
  num = parseFloat(num);
  if (num >= 100000) return (num / 100000).toFixed(1) + 'L';
  if (num >= 1000)   return (num / 1000).toFixed(1) + 'K';
  return num.toFixed(0);
}

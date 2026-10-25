/**
 * Smart Ration Tracker - Dashboard Chart.js & Client Controller
 * Manages live Chart.js rendering, month filtering, and reactive UI updates.
 */

document.addEventListener("DOMContentLoaded", () => {
  const data = window.INITIAL_SUMMARY;
  if (!data) return;

  initCharts(data);
});

let chartDistrictDistInstance = null;
let chartMonthlyTrendInstance = null;
let chartStockStatusInstance = null;
let chartReconciliationInstance = null;

function formatKg(num) {
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(num);
}

function formatKgDec(num) {
  return new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(num);
}

function initCharts(summary) {
  // 1. Distribution by District (Bar)
  const ctxDistrict = document.getElementById("chartDistrictDist")?.getContext("2d");
  if (ctxDistrict) {
    const labels = summary.districts_breakdown.map(d => d.district_name);
    const distData = summary.districts_breakdown.map(d => d.monthly_distributed_kg);

    chartDistrictDistInstance = new Chart(ctxDistrict, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{
          label: "Distributed (kg)",
          data: distData,
          backgroundColor: "#3b82f6",
          borderRadius: 6,
          hoverBackgroundColor: "#2563eb",
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${formatKg(ctx.parsed.y)} kg`
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: (val) => `${val / 1000}k`
            },
            grid: { color: "#f1f5f9" }
          },
          x: {
            grid: { display: false }
          }
        }
      }
    });
  }

  // 2. 6-Month Statewide Distribution Trend (Line)
  const ctxTrend = document.getElementById("chartMonthlyTrend")?.getContext("2d");
  if (ctxTrend) {
    chartMonthlyTrendInstance = new Chart(ctxTrend, {
      type: "line",
      data: {
        labels: summary.monthly_trend.labels,
        datasets: [{
          label: "Total State Distribution (kg)",
          data: summary.monthly_trend.values,
          borderColor: "#0284c7",
          backgroundColor: "rgba(2, 132, 199, 0.1)",
          fill: true,
          tension: 0.35,
          pointRadius: 5,
          pointHoverRadius: 7,
          pointBackgroundColor: "#0284c7"
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${formatKg(ctx.parsed.y)} kg (${(ctx.parsed.y / 1000).toFixed(1)} MT)`
            }
          }
        },
        scales: {
          y: {
            ticks: {
              callback: (val) => `${(val / 1000).toFixed(0)}k`
            },
            grid: { color: "#f1f5f9" }
          },
          x: { grid: { display: false } }
        }
      }
    });
  }

  // 3. Shop Stock Status Health (Doughnut)
  const ctxStatus = document.getElementById("chartStockStatus")?.getContext("2d");
  if (ctxStatus) {
    chartStockStatusInstance = new Chart(ctxStatus, {
      type: "doughnut",
      data: {
        labels: ["Normal Stock (>20%)", "Low Stock (10-20%)", "Critical (<10%)"],
        datasets: [{
          data: [
            summary.stock_status.normal,
            summary.stock_status.low,
            summary.stock_status.critical,
          ],
          backgroundColor: ["#10b981", "#f59e0b", "#ef4444"],
          borderWidth: 2,
          hoverOffset: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              boxWidth: 12,
              padding: 16,
              font: { size: 12 }
            }
          },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.parsed} Shops`
            }
          }
        },
        cutout: "65%"
      }
    });
  }

  // 4. Expected vs Measured Stock Physical Audit (Bar)
  const ctxRecon = document.getElementById("chartReconciliation")?.getContext("2d");
  if (ctxRecon) {
    const reconItems = summary.measurements_reconciliation;
    const labels = reconItems.map(r => r.location_id);
    const expectedData = reconItems.map(r => r.expected_stock_kg);
    const measuredData = reconItems.map(r => r.measured_stock_kg);

    chartReconciliationInstance = new Chart(ctxRecon, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Expected (Ledger)",
            data: expectedData,
            backgroundColor: "#94a3b8",
            borderRadius: 4
          },
          {
            label: "Measured (Inspection)",
            data: measuredData,
            backgroundColor: "#0ea5e9",
            borderRadius: 4
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "top",
            labels: { boxWidth: 12 }
          },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.dataset.label}: ${formatKg(ctx.parsed.y)} kg`
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: (val) => `${val / 1000}k`
            },
            grid: { color: "#f1f5f9" }
          },
          x: { grid: { display: false } }
        }
      }
    });
  }
}

/**
 * Triggered when user selects a different month filter
 */
window.updateDashboardMonth = async function(month) {
  try {
    const url = month ? `/api/summary?month=${encodeURIComponent(month)}` : `/api/summary`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to fetch summary data");
    const summary = await res.json();

    // 1. Update Cards
    document.getElementById("valGodownStock").innerHTML = `${formatKg(summary.cards.total_godown_stock_kg)} <span style="font-size:1rem; font-weight:500;">kg</span>`;
    document.getElementById("subGodownStock").innerText = `${summary.cards.total_godown_stock_mt.toLocaleString()} MT across 10 central granaries`;

    document.getElementById("valShopStock").innerHTML = `${formatKg(summary.cards.total_shop_stock_kg)} <span style="font-size:1rem; font-weight:500;">kg</span>`;
    document.getElementById("subShopStock").innerText = `${summary.cards.total_shop_stock_mt.toLocaleString()} MT across 50 retail shops`;

    document.getElementById("valDistributed").innerHTML = `${formatKg(summary.cards.total_distributed_kg)} <span style="font-size:1rem; font-weight:500;">kg</span>`;
    document.getElementById("subDistributed").innerText = `${summary.cards.total_distributed_mt.toLocaleString()} MT distributed via POS`;

    // 2. Update Charts
    if (chartDistrictDistInstance) {
      chartDistrictDistInstance.data.labels = summary.districts_breakdown.map(d => d.district_name);
      chartDistrictDistInstance.data.datasets[0].data = summary.districts_breakdown.map(d => d.monthly_distributed_kg);
      chartDistrictDistInstance.update();
    }

    if (chartStockStatusInstance) {
      chartStockStatusInstance.data.datasets[0].data = [
        summary.stock_status.normal,
        summary.stock_status.low,
        summary.stock_status.critical,
      ];
      chartStockStatusInstance.update();
    }

    // 3. Update District Table Body
    const tbody = document.getElementById("districtTableBody");
    if (tbody) {
      tbody.innerHTML = summary.districts_breakdown.map(d => {
        const badgeClass = d.status_badge === 'Critical' ? 'badge-critical' : (d.status_badge === 'Low' ? 'badge-low' : 'badge-normal');
        return `
          <tr>
            <td><strong>${d.district_code}</strong></td>
            <td><a href="/districts/${d.district_id}" class="table-link">${d.district_name}</a></td>
            <td>${d.godowns_count}</td>
            <td>${d.shops_count}</td>
            <td style="text-align: right; font-family: monospace; font-size: 0.95rem;">${formatKgDec(d.total_godown_stock_kg)}</td>
            <td style="text-align: right; font-family: monospace; font-size: 0.95rem;">${formatKgDec(d.total_shop_stock_kg)}</td>
            <td style="text-align: right; font-family: monospace; font-weight: 700; font-size: 0.95rem;">${formatKgDec(d.total_stock_kg)}</td>
            <td style="text-align: right; font-family: monospace; font-size: 0.95rem;">${formatKgDec(d.monthly_distributed_kg)}</td>
            <td style="text-align: center;"><span class="badge ${badgeClass}">${d.status_badge}</span></td>
          </tr>
        `;
      }).join("");
    }

    // Update Footer Totals
    document.getElementById("footGodownStock").innerText = formatKgDec(summary.cards.total_godown_stock_kg);
    document.getElementById("footShopStock").innerText = formatKgDec(summary.cards.total_shop_stock_kg);
    document.getElementById("footTotalStock").innerText = formatKgDec(summary.cards.total_combined_stock_kg);
    document.getElementById("footDistStock").innerText = formatKgDec(summary.cards.total_distributed_kg);

  } catch (err) {
    console.error("Error refreshing dashboard:", err);
  }
};

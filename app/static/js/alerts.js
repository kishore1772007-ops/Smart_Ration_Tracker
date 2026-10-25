/**
 * Smart Ration Tracker - Alert Centre Client Controller
 */

function applyFilters() {
  const statusFilter = document.getElementById("filterStatus").value;
  const typeFilter = document.getElementById("filterType").value;
  const severityFilter = document.getElementById("filterSeverity").value;

  const rows = document.querySelectorAll("#alertsTableBody tr");
  let visibleCount = 0;

  rows.forEach(row => {
    const s = row.getAttribute("data-status");
    const t = row.getAttribute("data-type");
    const sev = row.getAttribute("data-severity");

    let match = true;
    if (statusFilter && s !== statusFilter) match = false;
    if (typeFilter && t !== typeFilter) match = false;
    if (severityFilter && sev !== severityFilter) match = false;

    if (match) {
      row.style.display = "";
      visibleCount++;
    } else {
      row.style.display = "none";
    }
  });

  const badge = document.getElementById("alertsCountBadge");
  if (badge) badge.innerText = `${visibleCount} Filtered Alerts`;

  // Dynamic empty state
  let emptyRow = document.getElementById("alertsEmptyStateRow");
  if (visibleCount === 0) {
    if (!emptyRow) {
      emptyRow = document.createElement("tr");
      emptyRow.id = "alertsEmptyStateRow";
      emptyRow.innerHTML = `
        <td colspan="8" style="text-align:center; padding: 40px 20px; color: var(--text-secondary);">
          <div style="font-size: 32px; margin-bottom: 8px;">🔔</div>
          <strong style="font-size: 15px; color: var(--text-primary); display:block; margin-bottom: 4px;">No alerts match the selected criteria</strong>
          <span style="font-size: 13px;">Try resetting the status, alert type, or severity filters above to view other active and resolved notices.</span>
        </td>
      `;
      document.getElementById("alertsTableBody").appendChild(emptyRow);
    }
    emptyRow.style.display = "";
  } else if (emptyRow) {
    emptyRow.style.display = "none";
  }
}

function resetFilters() {
  document.getElementById("filterStatus").value = "";
  document.getElementById("filterType").value = "";
  document.getElementById("filterSeverity").value = "";
  applyFilters();
}

function showToast(msg, isError = false) {
  const toast = document.getElementById("alertToast");
  if (!toast) return;
  toast.style.display = "block";
  toast.innerText = msg;
  toast.style.background = isError ? "var(--status-critical-bg)" : "var(--status-normal-bg)";
  toast.style.color = isError ? "var(--status-critical)" : "var(--status-normal)";
  toast.style.border = isError ? "1px solid #fecaca" : "1px solid #a7f3d0";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function triggerScan() {
  try {
    const res = await fetch("/api/alerts/scan", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Scan failed");

    showToast(`✅ ${data.message}`);
    setTimeout(() => window.location.reload(), 1200);
  } catch (err) {
    showToast(`❌ Error: ${err.message}`, true);
  }
}

function openActionModal(alertId, targetStatus) {
  const modal = document.getElementById("actionModal");
  document.getElementById("modalAlertId").value = alertId;
  document.getElementById("modalTargetStatus").value = targetStatus;
  document.getElementById("modalNotes").value = "";

  const title = document.getElementById("modalTitle");
  const desc = document.getElementById("modalDesc");

  if (targetStatus === "UNDER_VERIFICATION") {
    title.innerText = `Mark Alert ${alertId} as 'Under Verification'`;
    desc.innerText = "Assign to field officer or quality inspector for inquiry. Verification notes required.";
  } else if (targetStatus === "RESOLVED") {
    title.innerText = `Resolve Alert ${alertId}`;
    desc.innerText = "Confirm physical reconciliation, delivery completion, or dispatch closure. Verification notes required.";
  }

  modal.style.display = "flex";
  document.getElementById("modalNotes").focus();
}

function closeActionModal() {
  document.getElementById("actionModal").style.display = "none";
}

async function submitAlertAction() {
  const alertId = document.getElementById("modalAlertId").value;
  const targetStatus = document.getElementById("modalTargetStatus").value;
  const notes = document.getElementById("modalNotes").value.trim();

  if (!notes || notes.length < 5) {
    alert("Verification notes are strictly required (minimum 5 characters).");
    return;
  }

  try {
    const res = await fetch(`/api/alerts/${encodeURIComponent(alertId)}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: targetStatus,
        verification_notes: notes,
        operator: "district_incharge",
      }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Status update failed");

    closeActionModal();
    showToast(`✅ ${data.message}`);
    setTimeout(() => window.location.reload(), 1000);
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

// Initial filter apply on DOM load
document.addEventListener("DOMContentLoaded", () => {
  applyFilters();
});

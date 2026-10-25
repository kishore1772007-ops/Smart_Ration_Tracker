/**
 * Smart Ration Tracker - Operations & Transactions Controller
 */

function switchTab(tabId) {
  const forms = [
    "formReceipt",
    "formDispatch",
    "formConfirm",
    "formDistribution",
    "formAdjustment",
    "formMeasurement"
  ];

  const buttons = [
    "btnTabReceipt",
    "btnTabDispatch",
    "btnTabConfirm",
    "btnTabDistribution",
    "btnTabAdjustment",
    "btnTabMeasurement"
  ];

  forms.forEach(f => {
    const el = document.getElementById(f);
    if (el) el.style.display = "none";
  });

  buttons.forEach(b => {
    const btn = document.getElementById(b);
    if (btn) btn.classList.remove("active-tab");
  });

  if (tabId === "tabReceipt") {
    document.getElementById("formReceipt").style.display = "block";
    document.getElementById("btnTabReceipt").classList.add("active-tab");
  } else if (tabId === "tabDispatch") {
    document.getElementById("formDispatch").style.display = "block";
    document.getElementById("btnTabDispatch").classList.add("active-tab");
  } else if (tabId === "tabConfirm") {
    document.getElementById("formConfirm").style.display = "block";
    document.getElementById("btnTabConfirm").classList.add("active-tab");
  } else if (tabId === "tabDistribution") {
    document.getElementById("formDistribution").style.display = "block";
    document.getElementById("btnTabDistribution").classList.add("active-tab");
  } else if (tabId === "tabAdjustment") {
    document.getElementById("formAdjustment").style.display = "block";
    document.getElementById("btnTabAdjustment").classList.add("active-tab");
  } else if (tabId === "tabMeasurement") {
    document.getElementById("formMeasurement").style.display = "block";
    document.getElementById("btnTabMeasurement").classList.add("active-tab");
  }
}

function showToast(message, isError = false) {
  const toast = document.getElementById("toastNotification");
  if (!toast) return;

  toast.style.display = "block";
  toast.innerText = message;
  toast.style.background = isError ? "var(--status-critical-bg)" : "var(--status-normal-bg)";
  toast.style.color = isError ? "var(--status-critical)" : "var(--status-normal)";
  toast.style.border = isError ? "1px solid #fecaca" : "1px solid #a7f3d0";

  window.scrollTo({ top: 0, behavior: "smooth" });
}

function populateDispatchedQty(selectEl) {
  const selectedOpt = selectEl.options[selectEl.selectedIndex];
  if (selectedOpt) {
    const qty = selectedOpt.getAttribute("data-dispatched");
    if (qty) {
      document.getElementById("confirmReceivedQty").value = qty;
    }
  }
}

function toggleAdjustmentLocations(type) {
  const godownOpts = document.querySelectorAll(".opt-godown");
  const shopOpts = document.querySelectorAll(".opt-shop");
  const select = document.getElementById("adjLocId");

  if (type === "godown") {
    godownOpts.forEach(o => o.style.display = "block");
    shopOpts.forEach(o => o.style.display = "none");
    if (godownOpts.length > 0) select.value = godownOpts[0].value;
  } else {
    godownOpts.forEach(o => o.style.display = "none");
    shopOpts.forEach(o => o.style.display = "block");
    if (shopOpts.length > 0) select.value = shopOpts[0].value;
  }
}

function toggleMeasurementLocations(type) {
  const godownOpts = document.querySelectorAll(".opt-meas-godown");
  const shopOpts = document.querySelectorAll(".opt-meas-shop");
  const select = document.getElementById("measLocId");

  if (type === "godown") {
    godownOpts.forEach(o => o.style.display = "block");
    shopOpts.forEach(o => o.style.display = "none");
    if (godownOpts.length > 0) select.value = godownOpts[0].value;
  } else {
    godownOpts.forEach(o => o.style.display = "none");
    shopOpts.forEach(o => o.style.display = "block");
    if (shopOpts.length > 0) select.value = shopOpts[0].value;
  }
}

// -------------------------------------------------------------
// FORM SUBMISSION HANDLERS
// -------------------------------------------------------------

async function handleReceiptSubmit(e) {
  e.preventDefault();
  const payload = {
    godown_id: document.getElementById("receiptGodownId").value,
    quantity_kg: parseFloat(document.getElementById("receiptQty").value),
    reference_id: document.getElementById("receiptRef").value,
    created_by: "fci_operator",
  };

  try {
    const res = await fetch("/api/transactions/receipt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Receipt failed");

    showToast(`✅ ${data.message} (New expected stock: ${data.new_expected_stock_kg.toLocaleString()} kg)`);
    setTimeout(() => window.location.reload(), 1500);
  } catch (err) {
    showToast(`❌ Error: ${err.message}`, true);
  }
}

async function handleDispatchSubmit(e) {
  e.preventDefault();
  const payload = {
    from_godown_id: document.getElementById("dispatchGodownId").value,
    to_shop_id: document.getElementById("dispatchShopId").value,
    quantity_kg: parseFloat(document.getElementById("dispatchQty").value),
    notes: document.getElementById("dispatchNotes").value,
    created_by: "godown_dispatcher",
  };

  try {
    const res = await fetch("/api/transactions/dispatch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Dispatch failed");

    showToast(`✅ ${data.message} Delivery ID: ${data.delivery_id}`);
    setTimeout(() => window.location.reload(), 1500);
  } catch (err) {
    showToast(`❌ Error: ${err.message}`, true);
  }
}

async function handleConfirmSubmit(e) {
  e.preventDefault();
  const payload = {
    delivery_id: document.getElementById("confirmDeliveryId").value,
    received_qty_kg: parseFloat(document.getElementById("confirmReceivedQty").value),
    notes: document.getElementById("confirmNotes").value,
    created_by: "shop_manager",
  };

  try {
    const res = await fetch("/api/transactions/confirm-delivery", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Confirmation failed");

    const diffNote = data.has_difference ? ` (Quantity difference: ${data.difference_kg} kg)` : "";
    showToast(`✅ ${data.message}${diffNote} New shop stock: ${data.shop_new_expected_stock_kg.toLocaleString()} kg`);
    setTimeout(() => window.location.reload(), 1500);
  } catch (err) {
    showToast(`❌ Error: ${err.message}`, true);
  }
}

async function handleDistributionSubmit(e) {
  e.preventDefault();
  const payload = {
    shop_id: document.getElementById("distShopId").value,
    quantity_kg: parseFloat(document.getElementById("distQty").value),
    beneficiary_households: parseInt(document.getElementById("distCards").value, 10),
    reference_id: document.getElementById("distRef").value,
    created_by: "epos_machine",
  };

  try {
    const res = await fetch("/api/transactions/distribution", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Distribution failed");

    showToast(`✅ ${data.message} (Remaining stock: ${data.shop_remaining_stock_kg.toLocaleString()} kg)`);
    setTimeout(() => window.location.reload(), 1500);
  } catch (err) {
    showToast(`❌ Error: ${err.message}`, true);
  }
}

async function handleAdjustmentSubmit(e) {
  e.preventDefault();
  const payload = {
    location_type: document.getElementById("adjLocType").value,
    location_id: document.getElementById("adjLocId").value,
    quantity_kg: parseFloat(document.getElementById("adjQty").value),
    reason: document.getElementById("adjReason").value,
    created_by: "senior_inspector",
  };

  try {
    const res = await fetch("/api/transactions/adjustment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Adjustment failed");

    showToast(`✅ ${data.message} (New balance: ${data.new_expected_stock_kg.toLocaleString()} kg)`);
    setTimeout(() => window.location.reload(), 1500);
  } catch (err) {
    showToast(`❌ Error: ${err.message}`, true);
  }
}

async function handleMeasurementSubmit(e) {
  e.preventDefault();
  const payload = {
    location_type: document.getElementById("measLocType").value,
    location_id: document.getElementById("measLocId").value,
    measured_stock_kg: parseFloat(document.getElementById("measStockQty").value),
    inspector_name: document.getElementById("measInspectorName").value,
    remarks: document.getElementById("measRemarks").value,
  };

  try {
    const res = await fetch("/api/transactions/measurement", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Measurement logging failed");

    const statusNote = data.discrepancy_detected ? " (⚠️ Discrepancy > 2% flagged for verification)" : " (✅ Within normal tolerance)";
    showToast(`✅ ${data.message}${statusNote}`);
    setTimeout(() => window.location.reload(), 1500);
  } catch (err) {
    showToast(`❌ Error: ${err.message}`, true);
  }
}

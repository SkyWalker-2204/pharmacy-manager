# app.py
# Single-file PharmaPro: Frontend (HTML/CSS/JS) served by Flask backend (Python).
# Features: Modal forms, QR/Barcode scanner (browser), OCR (Tesseract client-side),
# Server-side PDF invoice generation (ReportLab), localStorage preserved.
#
# Run:
#   pip install flask flask-cors reportlab pillow
#   python app.py
# Open:
#   http://localhost:5000

from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
import os, json, io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(APP_ROOT, 'uploads')
DB_FILE = os.path.join(APP_ROOT, 'server_db.json')

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# simple server DB to record invoices (persisted)
def load_server_db():
    if not os.path.exists(DB_FILE):
        db = {"invoices": []}
        with open(DB_FILE, 'w') as f:
            json.dump(db, f)
        return db
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_server_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=2, default=str)

app = Flask(__name__, static_folder=None)
CORS(app)

# Serve generated uploads
@app.route('/uploads/<path:fname>')
def uploaded_file(fname):
    return send_from_directory(UPLOAD_DIR, fname, as_attachment=False)

# API: create invoice -> generate server-side PDF and save invoice in server DB
@app.route('/api/invoice/create', methods=['POST'])
def api_create_invoice():
    try:
        payload = request.get_json()
        invoice = payload.get('invoice') or {}
        # ensure id
        inv_id = invoice.get('id') or f"INV-{int(datetime.utcnow().timestamp())}"
        date_str = invoice.get('date') or datetime.utcnow().strftime('%Y-%m-%d')
        items = invoice.get('items') or []
        totals = invoice.get('totals') or {}
        customer = invoice.get('customer') or {}

        # PDF filename
        safe_name = inv_id.replace('/', '-').replace(' ', '_')
        filename = f"invoice_{safe_name}.pdf"
        filepath = os.path.join(UPLOAD_DIR, filename)

        # Generate PDF with ReportLab
        c = canvas.Canvas(filepath, pagesize=A4)
        width, height = A4
        margin = 20 * mm
        y = height - margin

        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin, y, "PharmaPro Manager")
        c.setFont("Helvetica", 10)
        y -= 14
        c.drawString(margin, y, f"Invoice ID: {inv_id}")
        c.drawString(margin + 300, y, f"Date: {date_str}")
        y -= 16
        c.drawString(margin, y, f"Customer: {customer.get('name','Walk-in')} {('|' + customer.get('mobile','')) if customer.get('mobile') else ''}")
        y -= 20

        # Table header
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin, y, "Item")
        c.drawString(margin + 260, y, "Rate")
        c.drawString(margin + 330, y, "Qty")
        c.drawString(margin + 380, y, "GST%")
        c.drawString(margin + 430, y, "Total")
        y -= 10
        c.line(margin, y, width - margin, y)
        y -= 8
        c.setFont("Helvetica", 10)

        grand_total_calc = 0.0
        for it in items:
            name = it.get('name','-')
            rate = float(it.get('rate') or 0)
            qty = float(it.get('qty') or 0)
            gstp = float(it.get('gstPercent') or 0)
            amount = rate * qty
            gst_amt = amount * gstp/100.0
            total_line = amount + gst_amt
            grand_total_calc += total_line

            # wrap name if long
            c.drawString(margin, y, (name[:40] + '...') if len(name) > 40 else name)
            c.drawRightString(margin + 300, y, f"₹{rate:.2f}")
            c.drawRightString(margin + 350, y, f"{int(qty)}")
            c.drawRightString(margin + 410, y, f"{gstp}%")
            c.drawRightString(margin + 480, y, f"₹{total_line:.2f}")
            y -= 14
            if y < margin + 80:
                c.showPage()
                y = height - margin

        # totals
        y -= 6
        c.line(margin, y, width - margin, y)
        y -= 18
        c.drawRightString(margin + 480, y, f"Subtotal: ₹{totals.get('subtotal', '0')}")
        y -= 14
        c.drawRightString(margin + 480, y, f"GST: ₹{totals.get('gst', '0')}")
        y -= 14
        c.setFont("Helvetica-Bold", 12)
        c.drawRightString(margin + 480, y, f"Grand Total: ₹{totals.get('grand', f'{grand_total_calc:.2f}')}")
        c.save()

        # Save invoice record server-side
        db = load_server_db()
        db['invoices'].append({
            "id": inv_id,
            "date": date_str,
            "customer": customer,
            "items": items,
            "totals": totals,
            "file": filename
        })
        save_server_db(db)

        return jsonify({"ok": True, "file": f"/uploads/{filename}", "id": inv_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# API: scan verify - demo: check server invoices for id or just echo
@app.route('/api/scan/verify', methods=['POST'])
def api_scan_verify():
    data = request.get_json() or {}
    code = data.get('code') or ''
    db = load_server_db()
    # if code matches invoice id, return invoice info
    found = next((inv for inv in db.get('invoices', []) if inv.get('id') == code), None)
    if found:
        return jsonify({"ok": True, "type": "invoice", "invoice": found})
    # else try to match medicine code from posted body? For demo, echo
    return jsonify({"ok": True, "type": "unknown", "code": code, "message": "Server received code. (No matching invoice)"})

# Serve main page (embedded single-file HTML)
@app.route('/')
def index():
    # The HTML below contains the entire frontend: HTML/CSS/JS (modals, scanner, OCR, Chart.js, localStorage preservation)
    html = r"""
<!doctype html>
<html lang="hi">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>PharmaPro - Single-file (Flask + Frontend)</title>

<!-- Chart.js -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<!-- Tesseract.js -->
<script src="https://cdn.jsdelivr.net/npm/tesseract.js@4.1.2/dist/tesseract.min.js"></script>
<!-- ZXing (browser) for barcode/QR scanning -->
<script src="https://unpkg.com/@zxing/library@0.18.6/umd/index.min.js"></script>
<!-- jsPDF (client-side optional PDF) -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>

<style>
:root{--primary:#2563eb;--bg:#f1f5f9;--card:#fff;--radius:8px;--text:#334155}
*{box-sizing:border-box}body{font-family:system-ui,Segoe UI,Arial;background:var(--bg);color:var(--text);margin:0}
header{background:linear-gradient(135deg,var(--primary),#1e40af);color:#fff;padding:14px 20px;display:flex;justify-content:space-between;align-items:center}
.container{max-width:1200px;margin:18px auto;padding:0 16px}
.grid{display:grid;grid-template-columns:1fr 360px;gap:20px}
.card{background:var(--card);padding:16px;border-radius:var(--radius);box-shadow:0 6px 18px rgba(0,0,0,0.06)}
.btn{background:var(--primary);color:#fff;padding:8px 12px;border:none;border-radius:6px;cursor:pointer}
.btn-outline{background:transparent;border:1px solid #e2e8f0;padding:7px 10px;border-radius:6px;cursor:pointer}
.row{display:flex;gap:10px;align-items:center}
.table{width:100%;border-collapse:collapse;margin-top:8px}
.table th,.table td{padding:8px;border-bottom:1px solid #eef2f7;text-align:left}
.badge{padding:5px 8px;border-radius:12px;background:#eef2ff;color:#1e40af;font-size:12px}
.footer{padding:18px;text-align:center;color:#64748b}
.modal-back{position:fixed;inset:0;background:rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center}
.modal{width:520px;background:#fff;padding:16px;border-radius:10px}
input,select,textarea{width:100%;padding:8px;border-radius:6px;border:1px solid #e2e8f0;margin-top:6px}
.small{font-size:13px;color:#64748b}
.video-box{background:#000;border-radius:8px;overflow:hidden}
@media(max-width:980px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <div><strong>PharmaPro Manager</strong> • Frontend (HTML/JS) + Backend (Python Flask)</div>
  <div style="display:flex;gap:10px;align-items:center">
    <button class="btn" id="syncServerBtn">Sync DB → Server (invoices)</button>
    <button class="btn" id="downloadAll">Download Server Invoices</button>
  </div>
</header>

<div class="container">
  <div class="grid">
    <div>
      <!-- Inventory Card -->
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div><strong>Inventory</strong><div class="small">Add / edit medicines</div></div>
          <div style="display:flex;gap:8px">
            <button class="btn-outline" id="addMedBtn">Add Medicine</button>
            <button class="btn-outline" id="seedBtn">Seed Sample</button>
          </div>
        </div>

        <div style="margin-top:12px">
          <input id="searchMed" placeholder="Search medicine or batch..." />
          <table class="table" id="medTable">
            <thead><tr><th>Medicine</th><th>Batch</th><th>Stock</th><th>Expiry</th><th>Actions</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
      </div>

      <!-- Billing Card -->
      <div class="card" style="margin-top:14px">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div><strong>Billing & Invoice</strong><div class="small">Add items, generate invoice (server PDF)</div></div>
          <div style="display:flex;gap:8px">
            <button class="btn" id="generateInvoiceBtn">Generate & Download Invoice</button>
          </div>
        </div>

        <div style="margin-top:10px">
          <div class="row">
            <input id="custName" placeholder="Customer name" />
            <input id="custMobile" placeholder="Mobile" style="width:150px" />
          </div>

          <div style="margin-top:8px" class="row">
            <input id="itemSearch" placeholder="Search medicine to add to bill" />
            <input id="itemQty" placeholder="Qty" style="width:80px" type="number" value="1" />
            <button class="btn-outline" id="addToCartBtn">Add</button>
          </div>

          <table class="table" id="cartTable" style="margin-top:10px">
            <thead><tr><th>Item</th><th>Rate</th><th>Qty</th><th>GST%</th><th>Amount</th><th></th></tr></thead>
            <tbody></tbody>
          </table>

          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
            <div class="small">GST % (default): <input id="defaultGST" type="number" value="12" style="width:60px;margin-left:8px" /></div>
            <div style="text-align:right">
              <div>Subtotal: ₹<span id="subtotal">0.00</span></div>
              <div>GST: ₹<span id="gstTotal">0.00</span></div>
              <div style="font-weight:700">Total: ₹<span id="grandTotal">0.00</span></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Customers & Suppliers simplified -->
      <div class="card" style="margin-top:14px">
        <strong>Customers & Suppliers</strong>
        <div style="display:flex;gap:8px;margin-top:8px">
          <input id="newCustName" placeholder="New customer name" />
          <input id="newCustMobile" placeholder="Mobile" style="width:150px" />
          <button class="btn-outline" id="addCustomerBtn">Add</button>
        </div>
      </div>

    </div>

    <!-- Right sidebar: scanner, OCR, reports -->
    <div>
      <div class="card">
        <strong>System Alerts</strong>
        <div id="alertsBox" style="margin-top:8px" class="small">No alerts</div>
      </div>

      <div class="card" style="margin-top:12px">
        <strong>Scanner (QR / Barcode)</strong>
        <div class="small">Open camera and scan barcode/QR</div>
        <div style="margin-top:8px">
          <div class="video-box"><video id="videoPreview" playsinline></video></div>
          <div style="display:flex;gap:8px;margin-top:8px">
            <button class="btn" id="startScanBtn">Start Scan</button>
            <button class="btn-outline" id="stopScanBtn">Stop</button>
          </div>
          <div style="margin-top:8px">Last scan: <span id="lastScan">—</span></div>
        </div>
      </div>

      <div class="card" style="margin-top:12px">
        <strong>Prescription OCR</strong>
        <input type="file" id="presFile" accept="image/*" />
        <div style="display:flex;gap:8px;margin-top:8px">
          <button class="btn-outline" id="doOCRBtn">Extract Text</button>
          <button class="btn" id="savePresBtn">Save</button>
        </div>
        <textarea id="ocrResult" rows="6" style="width:100%;margin-top:8px"></textarea>
      </div>

      <div class="card" style="margin-top:12px">
        <strong>Sales Analytics</strong>
        <canvas id="salesChart" style="height:180px;margin-top:8px"></canvas>
        <div style="display:flex;gap:8px;margin-top:8px">
          <button class="btn-outline" id="genSampleSales">Sample Data</button>
          <button class="btn-outline" id="exportSalesBtn">Export CSV</button>
        </div>
      </div>
    </div>
  </div>

  <div class="footer">PharmaPro • Running with Flask backend • Generated PDFs saved to server /uploads</div>
</div>

<!-- Modal: Add/Edit Medicine -->
<div id="medModal" style="display:none" class="modal-back">
  <div class="modal">
    <h3 id="medModalTitle">Add Medicine</h3>
    <input id="m_name" placeholder="Name" />
    <input id="m_form" placeholder="Form (Tablet/Syrup)" />
    <input id="m_pack" placeholder="Pack info" />
    <input id="m_batch" placeholder="Batch" />
    <input id="m_qty" type="number" placeholder="Qty" />
    <input id="m_expiry" placeholder="Expiry (YYYY-MM-DD)" />
    <input id="m_rate" type="number" placeholder="Rate" />
    <div style="display:flex;gap:8px;margin-top:8px">
      <button class="btn" id="saveMedBtn">Save</button>
      <button class="btn-outline" onclick="closeMedModal()">Cancel</button>
    </div>
  </div>
</div>

<script>
/* ---------- Client-side app.js ---------- */
/* Key: preserve existing localStorage key pharma_pro_db_v2; if absent, create default DB */
const DBKEY = 'pharma_pro_db_v2';

function defaultDB(){
  return {
    stores: [{id: 'store_main', name: 'Main Store'}],
    activeStoreId: 'store_main',
    medicines: [],
    suppliers: [],
    customers: [],
    invoices: [],
    sales: [],
    prescriptions: []
  };
}
function loadDB(){
  try{
    const raw = localStorage.getItem(DBKEY);
    if(!raw){ const d = defaultDB(); localStorage.setItem(DBKEY, JSON.stringify(d)); return d; }
    return JSON.parse(raw);
  }catch(e){ console.error(e); const d = defaultDB(); localStorage.setItem(DBKEY, JSON.stringify(d)); return d; }
}
function saveDB(db){ localStorage.setItem(DBKEY, JSON.stringify(db)); }

let db = loadDB();
let cart = [];
renderAll();

/* ---------- Render functions ---------- */
function renderAll(){
  renderInventory();
  renderCart();
  renderAlerts();
  renderSalesChart();
}

function renderInventory(){
  const tbody = document.querySelector('#medTable tbody');
  tbody.innerHTML = '';
  db.medicines.forEach(m=>{
    m.variants.forEach(v=>{
      const tr = document.createElement('tr');
      tr.innerHTML = '<td><strong>'+m.name+'</strong><div class="small">'+(m.form||'')+' '+(m.pack||'')+'</div></td>' +
        '<td>'+v.batch+'</td>' +
        '<td>'+v.qty+'</td>' +
        '<td>'+ (v.expiry||'N/A') +'</td>' +
        '<td><button class="btn-outline" onclick="openEditMed(\''+m.id+'\',\''+v.batch+'\')">Edit</button> <button class="btn-outline" onclick="quickAdd(\''+m.id+'\',\''+v.batch+'\')">Add to Bill</button></td>';
      tbody.appendChild(tr);
    });
  });
}

/* ---------- Modal Add/Edit Medicine ---------- */
function openMedModal(){
  document.getElementById('medModalTitle').innerText = 'Add Medicine';
  document.getElementById('m_name').value=''; document.getElementById('m_form').value=''; document.getElementById('m_pack').value='';
  document.getElementById('m_batch').value='B'+Math.floor(Math.random()*900+100); document.getElementById('m_qty').value=0;
  document.getElementById('m_expiry').value=''; document.getElementById('m_rate').value=0;
  document.getElementById('medModal').style.display='flex';
}
function closeMedModal(){ document.getElementById('medModal').style.display='none'; }

document.getElementById('addMedBtn').addEventListener('click', openMedModal);
document.getElementById('saveMedBtn').addEventListener('click', ()=>{
  const name = document.getElementById('m_name').value.trim();
  if(!name) return alert('Name required');
  const m = {
    id: 'id'+Math.random().toString(36).slice(2,9),
    name, form: document.getElementById('m_form').value.trim(), pack: document.getElementById('m_pack').value.trim(),
    variants: [{
      batch: document.getElementById('m_batch').value.trim(),
      qty: Number(document.getElementById('m_qty').value||0),
      expiry: document.getElementById('m_expiry').value.trim(),
      location:'',
      suppliers:[], mrp:0, rate: Number(document.getElementById('m_rate').value||0)
    }]
  };
  db.medicines.push(m); saveDB(db); renderInventory(); closeMedModal();
});

/* Quick add to cart */
function quickAdd(medId, batch){
  const med = db.medicines.find(x=>x.id===medId);
  const v = med.variants.find(x=>x.batch===batch);
  const gst = Number(document.getElementById('defaultGST').value||12);
  const found = cart.find(c=>c.medId===medId && c.batch===batch);
  if(found) found.qty += 1;
  else cart.push({medId, batch, name: med.name, rate: v.rate, qty: 1, gstPercent: gst});
  renderCart();
}

/* Add to cart from search */
document.getElementById('addToCartBtn').addEventListener('click', ()=>{
  const q = document.getElementById('itemSearch').value.trim().toLowerCase();
  const qty = Number(document.getElementById('itemQty').value||1);
  if(!q) return alert('Search medicine name or batch');
  let found = null;
  for(const m of db.medicines){
    if(m.name.toLowerCase().includes(q)){ found = {m, v: m.variants[0]}; break; }
    const vmatch = m.variants.find(v=>v.batch.toLowerCase()===q);
    if(vmatch){ found = {m, v: vmatch}; break; }
  }
  if(!found) return alert('Not found');
  const gst = Number(document.getElementById('defaultGST').value||12);
  const exist = cart.find(c=>c.medId===found.m.id && c.batch===found.v.batch);
  if(exist) exist.qty += qty; else cart.push({medId: found.m.id, batch: found.v.batch, name: found.m.name, rate: found.v.rate, qty: qty, gstPercent: gst});
  renderCart();
});

/* Cart render & totals */
function renderCart(){
  const tbody = document.querySelector('#cartTable tbody'); tbody.innerHTML='';
  let subtotal = 0, gstTotal = 0, grand = 0;
  cart.forEach((it, idx)=>{
    const amt = Number(it.rate) * Number(it.qty);
    const gst = amt * (Number(it.gstPercent||0)/100);
    const total = amt + gst;
    subtotal += amt; gstTotal += gst; grand += total;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${it.name}</td><td>₹${Number(it.rate).toFixed(2)}</td><td><input style="width:60px" type="number" value="${it.qty}" onchange="changeQty(${idx},this.value)"></td><td>${it.gstPercent}%</td><td>₹${total.toFixed(2)}</td><td><button class="btn-outline" onclick="removeCart(${idx})">Remove</button></td>`;
    tbody.appendChild(tr);
  });
  document.getElementById('subtotal').innerText = subtotal.toFixed(2);
  document.getElementById('gstTotal').innerText = gstTotal.toFixed(2);
  document.getElementById('grandTotal').innerText = grand.toFixed(2);
}

function changeQty(i, v){ cart[i].qty = Number(v||1); renderCart(); }
function removeCart(i){ cart.splice(i,1); renderCart(); }

/* Generate invoice -> send to server to create PDF */
document.getElementById('generateInvoiceBtn').addEventListener('click', async ()=>{
  if(cart.length===0) return alert('Cart empty');
  const invoice = {
    id: 'INV-'+Date.now(),
    date: new Date().toISOString().slice(0,10),
    customer: { name: document.getElementById('custName').value || 'Walk-in', mobile: document.getElementById('custMobile').value || '' },
    items: cart,
    totals: { subtotal: Number(document.getElementById('subtotal').innerText||0), gst: Number(document.getElementById('gstTotal').innerText||0), grand: Number(document.getElementById('grandTotal').innerText||0) }
  };
  // POST to server
  const res = await fetch('/api/invoice/create', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ invoice }) });
  const j = await res.json();
  if(j.ok){
    alert('Invoice created on server: ' + j.id);
    // Save invoice link in local DB too
    db.invoices.push({ id: j.id, date: invoice.date, items: invoice.items, totals: invoice.totals, file: j.file });
    saveDB(db);
    // open PDF in new tab
    window.open(j.file, '_blank');
    // clear cart
    cart = []; renderCart();
    renderInventory(); renderAlerts();
  } else {
    alert('Invoice create failed: '+(j.error || JSON.stringify(j)));
  }
});

/* ---------- Scanner (ZXing) ---------- */
let codeReader, selectedStream;

document.getElementById('startScanBtn').addEventListener('click', async ()=>{
  const video = document.getElementById('videoPreview');
  codeReader = new ZXing.BrowserMultiFormatContinuousReader();
  try{
    const hints = {};
    // prefer environment camera
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    selectedStream = stream;
    video.srcObject = stream;
    video.play();
    document.getElementById('lastScan').innerText = 'Scanning...';
    codeReader.decodeFromVideoDevice(null, 'videoPreview', (result, err) => {
      if(result){
        const text = result.getText();
        document.getElementById('lastScan').innerText = text;
        // call server verify
        fetch('/api/scan/verify', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ code: text }) })
          .then(r=>r.json()).then(j=>{ console.log('verify', j); if(j.ok){ alert('Scan verified: '+JSON.stringify(j)); }});
        // optional: find item and quick add?
      }
    });
  }catch(e){ alert('Camera error: '+e.message); console.error(e); }
});

document.getElementById('stopScanBtn').addEventListener('click', ()=>{
  if(codeReader) { try{ codeReader.reset(); }catch(e){} codeReader=null; }
  if(selectedStream){ selectedStream.getTracks().forEach(t=>t.stop()); selectedStream=null; }
  document.getElementById('lastScan').innerText = 'Stopped';
});

/* ---------- OCR (Tesseract) ---------- */
document.getElementById('doOCRBtn').addEventListener('click', async ()=>{
  const f = document.getElementById('presFile').files[0];
  if(!f) return alert('Choose an image');
  document.getElementById('ocrResult').value = 'Processing OCR...';
  try{
    const data = await Tesseract.recognize(f, 'eng', { logger: m=>{} });
    document.getElementById('ocrResult').value = data.data.text;
  }catch(e){ document.getElementById('ocrResult').value = 'OCR failed: '+e.message; }
});
document.getElementById('savePresBtn').addEventListener('click', ()=>{
  const text = document.getElementById('ocrResult').value.trim();
  if(!text) return alert('No OCR result');
  db.prescriptions.push({ id:'P-'+Date.now(), date: new Date().toISOString().slice(0,10), text });
  saveDB(db);
  alert('Prescription saved locally');
});

/* ---------- Alerts & Reports ---------- */
function renderAlerts(){
  const box = document.getElementById('alertsBox');
  const lowTh = 5;
  let alerts=[];
  db.medicines.forEach(m=>{
    m.variants.forEach(v=>{
      if(v.qty <= lowTh) alerts.push({type:'low', msg: m.name + ' (Batch ' + v.batch + ') low: ' + v.qty});
      if(v.expiry){
        const d = new Date(v.expiry);
        const diff = Math.ceil((d - new Date())/(1000*60*60*24));
        if(diff < 0) alerts.push({type:'exp', msg: m.name + ' (Batch ' + v.batch + ') expired on ' + v.expiry});
        else if(diff <= 30) alerts.push({type:'near', msg: m.name + ' (Batch ' + v.batch + ') expires on ' + v.expiry});
      }
    });
  });
  if(alerts.length===0) box.innerText = 'No alerts';
  else box.innerHTML = alerts.slice(0,5).map(a=>'<div class="badge">'+a.msg+'</div>').join('<br/>');
}

/* ---------- Sales Chart (simple) ---------- */
function renderSalesChart(){
  const ctx = document.getElementById('salesChart').getContext('2d');
  const last7 = [];
  for(let i=6;i>=0;i--){
    const d = new Date(); d.setDate(d.getDate()-i); last7.push(d.toISOString().slice(0,10));
  }
  const salesMap = {};
  db.sales.forEach(s => { salesMap[s.date] = (salesMap[s.date]||0) + Number(s.amount||0); });
  const data = last7.map(d => salesMap[d]||0);
  if(window.__salesChart) window.__salesChart.destroy();
  window.__salesChart = new Chart(ctx, { type:'bar', data:{ labels: last7, datasets:[{ label:'Sales (₹)', data }] }});
}

/* ---------- Seed sample data ---------- */
document.getElementById('seedBtn').addEventListener('click', ()=>{
  if(db.medicines.length>0) return alert('Already seeded');
  const supp = {id:'sup_'+Date.now(), name:'MedSupply Co', contact:'9876543210'};
  db.suppliers.push(supp);
  const med1 = {
    id:'m1', name:'Paracetamol 500mg', form:'Tablet', pack:'Strip of 10',
    variants:[
      { batch:'P001', qty:120, expiry: new Date(new Date().setMonth(new Date().getMonth()+6)).toISOString().slice(0,10), location:'Shelf A1', suppliers:[supp.id], mrp:50, rate:45 }
    ]
  };
  const med2 = {
    id:'m2', name:'Cough Syrup 100ml', form:'Syrup', pack:'Bottle 100ml',
    variants:[
      { batch:'S001', qty:5, expiry: new Date(new Date().setDate(new Date().getDate()+28)).toISOString().slice(0,10), location:'Shelf B2', suppliers:[supp.id], mrp:120, rate:110 }
    ]
  };
  db.medicines.push(med1, med2);
  saveDB(db); renderAll(); alert('Seeded sample medicines');
});

/* ---------- Quick helpers ---------- */
function openEditMed(mid,batch){
  // find med: prefill modal with first variant values
  const med = db.medicines.find(m=>m.id===mid);
  const v = med.variants.find(x=>x.batch===batch);
  document.getElementById('m_name').value = med.name;
  document.getElementById('m_form').value = med.form||'';
  document.getElementById('m_pack').value = med.pack||'';
  document.getElementById('m_batch').value = v.batch;
  document.getElementById('m_qty').value = v.qty;
  document.getElementById('m_expiry').value = v.expiry||'';
  document.getElementById('m_rate').value = v.rate||0;
  document.getElementById('medModalTitle').innerText = 'Edit Medicine';
  document.getElementById('medModal').style.display='flex';
  // On save replace the med with updated values (simple approach)
  document.getElementById('saveMedBtn').onclick = function(){
    med.name = document.getElementById('m_name').value.trim();
    med.form = document.getElementById('m_form').value.trim();
    med.pack = document.getElementById('m_pack').value.trim();
    v.batch = document.getElementById('m_batch').value.trim();
    v.qty = Number(document.getElementById('m_qty').value||0);
    v.expiry = document.getElementById('m_expiry').value.trim();
    v.rate = Number(document.getElementById('m_rate').value||0);
    saveDB(db); renderInventory(); closeMedModal(); document.getElementById('saveMedBtn').onclick = defaultSaveHandler;
  };
}
const defaultSaveHandler = document.getElementById('saveMedBtn').onclick;

/* ---------- Sync to server: upload server invoices (local invoices to server) ---------- */
document.getElementById('syncServerBtn').addEventListener('click', async ()=>{
  // send all local invoices that do not exist on server (match by id)
  const serverRes = await fetch('/uploads'); // may 404, but we just proceed
  // For demo: send every local invoice as an API call
  for(const inv of db.invoices || []){
    try{
      const res = await fetch('/api/invoice/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ invoice: inv }) });
      const j = await res.json();
      console.log('synced', j);
    }catch(e){ console.error(e); }
  }
  alert('Sync attempted for local invoices (demo).');
});

/* ---------- Export sales CSV ---------- */
document.getElementById('exportSalesBtn').addEventListener('click', ()=>{
  let rows = [['Date','Amount']];
  db.sales.forEach(s => rows.push([s.date, s.amount]));
  const csv = rows.map(r => r.map(c=>`"${String(c).replace(/"/g,'""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], {type:'text/csv'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href=url; a.download='sales.csv'; a.click(); URL.revokeObjectURL(url);
});

/* ---------- Helper: render once on load ---------- */
renderAll();
</script>
</body>
</html>
    """
    return render_template_string(html)

if __name__ == '__main__':
    print("Starting PharmaPro single-file app on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)

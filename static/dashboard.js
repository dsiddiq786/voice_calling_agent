const statuses = ['new', 'accepted', 'preparing', 'ready', 'completed'];
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
async function update(id, status) { await fetch(`/api/orders/${id}/status?status=${status}`, {method:'PATCH'}); load(); }
async function load() {
  const response = await fetch('/api/orders');
  const orders = await response.json();
  const root = document.querySelector('#orders');
  root.innerHTML = '';
  if (!orders.length) { root.innerHTML = '<div class="card empty">No confirmed orders yet.</div>'; return; }
  orders.forEach(order => {
    const card = document.createElement('article');
    card.className = 'card order-card';
    const options = statuses.map(status => `<option ${status===order.status?'selected':''} value="${status}">${status}</option>`).join('');
    const items = order.items.map(item => `<div class="order-item"><span>${item.quantity} × ${escapeHtml(item.name)}${item.notes?` <small>(${escapeHtml(item.notes)})</small>`:''}</span><strong>Rs. ${item.quantity*item.unit_price}</strong></div>`).join('');
    const delivery = order.customer_phone || order.delivery_address ? `<div class="notice"><strong>Delivery</strong><br>${escapeHtml(order.customer_phone||'Phone missing')}<br>${escapeHtml(order.delivery_address||'Address missing')}</div>` : '';
    card.innerHTML = `<h3>${escapeHtml(order.id)}</h3><div class="order-meta"><span>${new Date(order.created_at).toLocaleString()}</span><span class="status">${order.status}</span></div>${delivery}${items}<div class="total"><span>Total</span><span>Rs. ${order.total}</span></div><div class="actions"><select aria-label="Status">${options}</select><button>Update</button></div>`;
    card.querySelector('button').onclick = () => update(order.id, card.querySelector('select').value);
    root.appendChild(card);
  });
}
document.querySelector('#refresh').onclick = load;
load();
setInterval(load, 5000);

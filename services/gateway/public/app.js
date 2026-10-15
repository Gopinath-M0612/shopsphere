// ShopSphere web UI. Talks only to the gateway (/api/*), never to services directly.
const state = { page: 1, pageSize: 8, total: 0, cart: new Map(), stock: new Map() };
const $ = (id) => document.getElementById(id);
const rupees = (n) => `₹${Number(n).toFixed(2)}`;

async function api(path, options = {}) {
  const resp = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  let body = null;
  try { body = await resp.json(); } catch { /* empty body */ }
  if (!resp.ok) {
    const detail = body?.detail;
    const text = typeof detail === 'string' ? detail : detail?.message || `HTTP ${resp.status}`;
    const err = new Error(text);
    err.status = resp.status;
    err.requestId = resp.headers.get('x-request-id');
    throw err;
  }
  return body;
}

function message(text, ok) {
  const el = $('message');
  el.textContent = text;
  el.className = ok ? 'ok' : 'err';
}

async function loadCategories() {
  try {
    const cats = await api('/catalog/categories');
    $('category').innerHTML = '<option value="">All categories</option>'
      + cats.map((c) => `<option value="${c.slug}">${c.name} (${c.product_count})</option>`).join('');
  } catch (e) {
    message(`Could not load categories: ${e.message}`, false);
  }
}

async function loadStock() {
  try {
    const { items } = await api('/inventory/stock');
    state.stock = new Map(items.map((s) => [s.sku, s]));
  } catch {
    state.stock = new Map(); // inventory down: still show products
  }
}

function stockBadge(sku) {
  const s = state.stock.get(sku);
  if (!s) return '<span class="stock">stock unknown</span>';
  if (s.available <= 0) return '<span class="stock out">out of stock</span>';
  if (s.low_stock) return `<span class="stock low">only ${s.available} left</span>`;
  return `<span class="stock">${s.available} in stock</span>`;
}

async function loadProducts() {
  const params = new URLSearchParams({ page: state.page, page_size: state.pageSize });
  if ($('search').value.trim()) params.set('q', $('search').value.trim());
  if ($('category').value) params.set('category', $('category').value);
  try {
    const [data] = await Promise.all([api(`/catalog/products?${params}`), loadStock()]);
    state.total = data.total;
    $('products').innerHTML = data.items.map((p) => `
      <div class="card">
        <div class="name">${p.name}</div>
        <div class="desc">${p.description}</div>
        <div class="price">${rupees(p.price)}</div>
        ${stockBadge(p.sku)}
        <button data-sku="${p.sku}" data-name="${p.name}" data-price="${p.price}">Add to cart</button>
      </div>`).join('') || '<p>No products found.</p>';
    const pages = Math.max(1, Math.ceil(state.total / state.pageSize));
    $('page-info').textContent = `Page ${state.page} of ${pages}`;
    $('prev').disabled = state.page <= 1;
    $('next').disabled = state.page >= pages;
  } catch (e) {
    $('products').innerHTML = `<p class="err">Catalog unavailable: ${e.message}</p>`;
  }
}

function renderCart() {
  let total = 0;
  $('cart').innerHTML = [...state.cart.values()].map((item) => {
    total += item.price * item.qty;
    return `<li>${item.qty} × ${item.name} — ${rupees(item.price * item.qty)}
      <button data-remove="${item.sku}">✕</button></li>`;
  }).join('') || '<li>Cart is empty</li>';
  $('cart-total').textContent = rupees(total);
  $('checkout').disabled = state.cart.size === 0;
}

async function checkout() {
  const email = $('email').value.trim();
  if (!email) return message('Enter your email first', false);
  $('checkout').disabled = true;
  try {
    const order = await api('/orders/orders', {
      method: 'POST',
      body: JSON.stringify({
        customer_email: email,
        items: [...state.cart.values()].map(({ sku, qty }) => ({ sku, qty })),
      }),
    });
    localStorage.setItem('shopsphere-email', email);
    state.cart.clear();
    renderCart();
    message(`Order ${order.id} placed (${rupees(order.total)})`, true);
    await Promise.all([loadOrders(), loadProducts()]);
  } catch (e) {
    message(`Order failed: ${e.message}${e.requestId ? ` (request ${e.requestId.slice(0, 8)})` : ''}`, false);
  } finally {
    renderCart();
  }
}

async function loadOrders() {
  const email = $('email').value.trim();
  if (!email) { $('orders').innerHTML = '<li>Enter your email to see orders</li>'; return; }
  try {
    const orders = await api(`/orders/orders?email=${encodeURIComponent(email)}&limit=10`);
    $('orders').innerHTML = orders.map((o) => `
      <li>${o.id.slice(0, 14)}… ${rupees(o.total)}
        <span class="status ${o.status}">${o.status}</span>
        ${['PENDING', 'CONFIRMED'].includes(o.status) ? `<button data-cancel="${o.id}">Cancel</button>` : ''}
      </li>`).join('') || '<li>No orders yet</li>';
  } catch (e) {
    $('orders').innerHTML = `<li>Orders unavailable: ${e.message}</li>`;
  }
}

async function cancelOrder(id) {
  try {
    await api(`/orders/orders/${id}/cancel`, { method: 'POST', body: JSON.stringify({ reason: 'cancelled in UI' }) });
    message(`Order ${id} cancelled`, true);
  } catch (e) {
    message(`Cancel failed: ${e.message}`, false);
  }
  loadOrders();
  loadProducts();
}

async function checkHealth() {
  try {
    const r = await fetch('/ready').then((x) => x.json());
    $('health').textContent = 'Services: ' + Object.entries(r.upstreams).map(([k, v]) => `${k} ${v}`).join(' · ');
  } catch {
    $('health').textContent = 'Gateway unreachable';
  }
}

document.addEventListener('click', (ev) => {
  const t = ev.target;
  if (t.dataset.sku) {
    const item = state.cart.get(t.dataset.sku) || { sku: t.dataset.sku, name: t.dataset.name, price: Number(t.dataset.price), qty: 0 };
    item.qty += 1;
    state.cart.set(item.sku, item);
    renderCart();
  } else if (t.dataset.remove) {
    state.cart.delete(t.dataset.remove);
    renderCart();
  } else if (t.dataset.cancel) {
    cancelOrder(t.dataset.cancel);
  }
});

let searchTimer;
$('search').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.page = 1; loadProducts(); }, 300);
});
$('category').addEventListener('change', () => { state.page = 1; loadProducts(); });
$('prev').addEventListener('click', () => { state.page -= 1; loadProducts(); });
$('next').addEventListener('click', () => { state.page += 1; loadProducts(); });
$('checkout').addEventListener('click', checkout);
$('email').addEventListener('change', loadOrders);

$('email').value = localStorage.getItem('shopsphere-email') || '';
renderCart();
loadCategories();
loadProducts();
loadOrders();
checkHealth();
setInterval(loadOrders, 4000);
setInterval(checkHealth, 10000);

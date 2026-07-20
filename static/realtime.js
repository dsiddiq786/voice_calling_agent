/* Real-time Fatima call path.
 *
 * Audio uses ElevenLabs' WebRTC client directly in the browser. The browser
 * receives a one-time token from our backend; it never receives an API key.
 * The existing serial voice demo remains available as a fallback in
 * customer.js, but this handler owns the main Call Fatima button.
 */
(function () {
  const callButton = document.querySelector('#call-fatima');
  const screen = document.querySelector('#call-screen');
  const orb = document.querySelector('#voice-orb');
  const state = document.querySelector('#call-state');
  const caption = document.querySelector('#call-caption');
  const timer = document.querySelector('#call-timer');
  const endButton = document.querySelector('#end-call');
  const muteButton = document.querySelector('#call-mic');
  const messages = document.querySelector('#messages');
  let conversation = null;
  let muted = false;
  let startedAt = 0;
  let clock = null;
  let localSessionId = null;

  function setStage(mode, text) {
    orb.className = `voice-orb ${mode}`;
    state.textContent = mode === 'speaking' ? 'Fatima is speaking' : mode === 'listening' ? 'Fatima is listening' : 'Connecting Fatima…';
    if (text) caption.textContent = text;
  }

  function addBubble(text, who) {
    if (!text || !messages) return;
    const last = messages.lastElementChild;
    if (last && last.dataset.realtime === `${who}:${text}`) return;
    const bubble = document.createElement('div');
    bubble.className = `bubble ${who}`;
    bubble.dataset.realtime = `${who}:${text}`;
    bubble.textContent = text;
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
  }

  function startClock() {
    startedAt = Date.now();
    clock = window.setInterval(() => {
      const seconds = Math.floor((Date.now() - startedAt) / 1000);
      timer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    }, 1000);
  }

  function renderRealtimeCart(data) {
    if (!data || !Array.isArray(data.cart)) return;
    const cart = document.querySelector('#cart');
    const total = document.querySelector('#total');
    cart.innerHTML = '';
    if (!data.cart.length) cart.innerHTML = '<div class="empty">No items yet</div>';
    for (const item of data.cart) {
      const row = document.createElement('div');
      row.className = 'cart-row';
      row.innerHTML = `<span>${item.quantity} × ${item.name}</span><strong>Rs. ${item.quantity * item.unit_price}</strong>`;
      cart.appendChild(row);
    }
    total.textContent = `Rs. ${data.total || 0}`;
  }

  async function cartTool(action, parameters = {}) {
    if (!localSessionId) throw new Error('Local order session is not ready');
    const response = await fetch(`/api/realtime/sessions/${localSessionId}/cart`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, ...parameters }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Cart operation failed');
    renderRealtimeCart(result);
    return JSON.stringify(result);
  }

  async function closeRealtime() {
    if (clock) window.clearInterval(clock);
    clock = null;
    const active = conversation;
    conversation = null;
    if (active) {
      try { await active.endSession(); } catch (_) { /* already disconnected */ }
    }
    screen.classList.remove('open');
    screen.setAttribute('aria-hidden', 'true');
    callButton.disabled = false;
    callButton.textContent = '☎ Call Fatima';
  }

  async function startRealtime(event) {
    // Capture-phase listener blocks the old MediaRecorder call handler.
    event.preventDefault();
    event.stopImmediatePropagation();
    if (conversation) return;
    if (!window.ElevenLabsClient?.Conversation) {
      alert('Realtime voice client did not load. Refresh once and try again.');
      return;
    }
    callButton.disabled = true;
    callButton.textContent = 'Connecting…';
    messages.innerHTML = '';
    screen.classList.add('open');
    screen.setAttribute('aria-hidden', 'false');
    setStage('thinking', 'Fatima ko connect kar rahe hain…');
    try {
      const sessionResponse = await fetch('/api/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const localSession = await sessionResponse.json();
      if (!sessionResponse.ok || !localSession.id) throw new Error('Could not create the order session');
      localSessionId = localSession.id;
      renderRealtimeCart({ cart: [], total: 0 });
      const response = await fetch('/api/realtime/conversation-token');
      const data = await response.json();
      if (!response.ok || !data.conversation_token) throw new Error(data.detail || 'No realtime session token');
      conversation = await window.ElevenLabsClient.Conversation.startSession({
        conversationToken: data.conversation_token,
        connectionType: 'webrtc',
        clientTools: {
          addToCart: (parameters) => cartTool('add', parameters),
          removeFromCart: (parameters) => cartTool('remove', parameters),
          getCartSummary: () => cartTool('summary'),
          setDeliveryAddress: (parameters) => cartTool('set_delivery', parameters),
          confirmOrder: () => cartTool('confirm'),
        },
        onConnect: () => {
          callButton.textContent = 'Fatima on call';
          setStage('listening', 'Jee, Fatima sun rahi hai…');
          startClock();
        },
        onDisconnect: () => closeRealtime(),
        onError: (message) => {
          console.error('Fatima realtime error:', message);
          setStage('idle', 'Connection dobara try karein.');
        },
        onModeChange: ({ mode }) => setStage(mode, mode === 'speaking' ? 'Fatima…' : 'Jee, boliye…'),
        onInterruption: () => setStage('listening', 'Haan ji, main sun rahi hoon…'),
        onMessage: ({ message, role }) => {
          addBubble(message, role === 'agent' ? 'agent' : 'customer');
          if (role === 'agent') caption.textContent = message;
        },
      });
    } catch (error) {
      console.error(error);
      await closeRealtime();
      alert('Realtime Fatima start nahi ho saki. Please refresh and try again.');
    }
  }

  callButton.addEventListener('click', startRealtime, true);
  endButton.addEventListener('click', (event) => {
    if (!conversation) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    closeRealtime();
  }, true);
  muteButton.addEventListener('click', (event) => {
    if (!conversation) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    muted = !muted;
    conversation.setMicMuted(muted);
    muteButton.querySelector('small').textContent = muted ? 'Muted' : 'Listening';
  }, true);
}());

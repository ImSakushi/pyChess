const state = {
  ws: null,
  code: null,
  myColor: null, // 'w' | 'b'
  whiteToMove: true,
  board: [],
  selected: null,
};

const $ = (sel) => document.querySelector(sel);
const statusEl = $('#status');
const colorEl = $('#myColor');
const codeEl = $('#roomCode');
const turnEl = $('#turn');
const boardEl = $('#board');

function setStatus(txt) { statusEl.textContent = txt; }

function wsUrl() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/ws`;
}

function pieceImg(code) {
  if (!code || code === '--') return null;
  return `/images/${code}.png`;
}

function renderBoard() {
  boardEl.innerHTML = '';
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 8; c++) {
      const sq = document.createElement('div');
      sq.className = `sq ${(r + c) % 2 === 0 ? 'light' : 'dark'}`;
      sq.dataset.r = r;
      sq.dataset.c = c;
      const img = pieceImg(state.board?.[r]?.[c]);
      if (img) {
        const im = document.createElement('img');
        im.src = img;
        im.alt = state.board[r][c];
        sq.appendChild(im);
      }
      sq.addEventListener('click', onSquareClick);
      boardEl.appendChild(sq);
    }
  }
  turnEl.textContent = state.whiteToMove ? 'Blanc' : 'Noir';
  colorEl.textContent = state.myColor === 'w' ? 'Blanc' : state.myColor === 'b' ? 'Noir' : '—';
  codeEl.textContent = state.code || '—';
}

function myTurn() {
  if (!state.myColor) return false;
  return (state.whiteToMove && state.myColor === 'w') || (!state.whiteToMove && state.myColor === 'b');
}

function onSquareClick(e) {
  const r = parseInt(e.currentTarget.dataset.r, 10);
  const c = parseInt(e.currentTarget.dataset.c, 10);
  if (!myTurn()) return; // not your turn

  // Select own piece
  if (!state.selected) {
    const piece = state.board?.[r]?.[c] || '--';
    if (piece === '--') return;
    if (state.myColor !== piece[0]) return;
    state.selected = { r, c };
    e.currentTarget.classList.add('sel');
    return;
  }

  // Second click: try move
  const from = state.selected;
  const to = { r, c };
  // Clear visual selection
  document.querySelectorAll('.sq.sel').forEach(el => el.classList.remove('sel'));
  state.selected = null;

  // If same square, ignore
  if (from.r === to.r && from.c === to.c) return;

  // Send move; server validates
  state.ws?.send(JSON.stringify({
    type: 'move',
    move: { from: [from.r, from.c], to: [to.r, to.c] }
  }));
}

function connect() {
  state.ws = new WebSocket(wsUrl());
  state.ws.addEventListener('open', () => setStatus('Connecté'));
  state.ws.addEventListener('close', () => setStatus('Déconnecté'));
  state.ws.addEventListener('message', (evt) => {
    let msg;
    try { msg = JSON.parse(evt.data); } catch { return; }
    const t = msg.type;
    if (t === 'created' || t === 'joined') {
      state.code = msg.code;
      // Couleur uniquement connue pour le client courant
      if (msg.color) state.myColor = msg.color;
      renderBoard();
    } else if (t === 'start') {
      // Both connected
    } else if (t === 'state') {
      state.code = msg.code || state.code;
      state.board = msg.board;
      state.whiteToMove = !!msg.white_to_move;
      renderBoard();
    } else if (t === 'error') {
      setStatus(`Erreur: ${msg.message || 'inconnue'}`);
    }
  });
}

function host() {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
  state.ws.send(JSON.stringify({ action: 'create' }));
}

function join() {
  const code = document.getElementById('codeInput').value.trim().toUpperCase();
  if (!code) return;
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
  state.ws.send(JSON.stringify({ action: 'join', code }));
}

document.getElementById('hostBtn').addEventListener('click', host);
document.getElementById('joinBtn').addEventListener('click', join);

connect();
renderBoard();

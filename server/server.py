import asyncio
import json
import secrets
import string
from dataclasses import dataclass, field
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from engine import GameState, Move


def gen_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@dataclass
class Room:
    code: str
    white: Optional[WebSocket] = None
    black: Optional[WebSocket] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    gs: GameState = field(default_factory=GameState)

    def other(self, color: str) -> Optional[WebSocket]:
        return self.black if color == "w" else self.white

    def set_player(self, color: str, ws: WebSocket) -> None:
        if color == "w":
            self.white = ws
        else:
            self.black = ws

    def player_count(self) -> int:
        return int(self.white is not None) + int(self.black is not None)


app = FastAPI(title="PyChess Multiplayer Server")

rooms: Dict[str, Room] = {}


@app.get("/health")
def health():
    return {"ok": True, "message": "PyChess Multiplayer Server running", "rooms": len(rooms)}

# Static web client and images
app.mount("/images", StaticFiles(directory="images"), name="images")
app.mount("/", StaticFiles(directory="web", html=True), name="web")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    color: Optional[str] = None
    room: Optional[Room] = None

    try:
        # First message must be an action: create or join
        raw = await ws.receive_text()
        data = json.loads(raw)
        action = data.get("action")

        if action == "create":
            # Create a new room and assign white by default
            code = gen_code()
            room = Room(code=code)
            rooms[code] = room
            color = "w"
            room.set_player(color, ws)
            await ws.send_json({"type": "created", "code": code, "color": color})
            # Send initial state
            await ws.send_json({
                "type": "state",
                "code": code,
                "board": room.gs.board,
                "white_to_move": room.gs.white_to_move,
            })
        elif action == "join":
            code = str(data.get("code", "")).upper()
            room = rooms.get(code)
            if not room:
                await ws.send_json({"type": "error", "message": "Invalid code"})
                await ws.close()
                return
            # Try to take black if free, else white if free
            if room.black is None:
                color = "b"
            elif room.white is None:
                color = "w"
            else:
                await ws.send_json({"type": "error", "message": "Room full"})
                await ws.close()
                return
            room.set_player(color, ws)
            await ws.send_json({"type": "joined", "code": code, "color": color})
            # Send current state to the joiner
            await ws.send_json({
                "type": "state",
                "code": code,
                "board": room.gs.board,
                "white_to_move": room.gs.white_to_move,
            })
            # Notify opponent if present
            opponent = room.other(color)
            if opponent is not None:
                try:
                    await opponent.send_json({"type": "opponent_joined"})
                except Exception:
                    pass
        else:
            await ws.send_json({"type": "error", "message": "First message must be action=create|join"})
            await ws.close()
            return

        # If both present, signal start to both sides
        if room and room.white and room.black:
            await room.white.send_json({"type": "start", "color": "w", "opponent": "b"})
            await room.black.send_json({"type": "start", "color": "b", "opponent": "w"})

        # Main relay loop
        while True:
            msg = await ws.receive_text()
            try:
                payload = json.loads(msg)
            except json.JSONDecodeError:
                continue
            kind = payload.get("type")
            # Relay moves and control messages
            if kind == "move":
                if room is None or color is None:
                    continue
                # Validate move against room state
                m = payload.get("move", {})
                frm = m.get("from", [0, 0])
                to = m.get("to", [0, 0])
                gs = room.gs
                # Check turn and color
                turn_color = 'w' if gs.white_to_move else 'b'
                if color != turn_color:
                    # Ignore illegal turn
                    continue
                try_move = Move((frm[0], frm[1]), (to[0], to[1]), gs.board)
                legal = None
                for mv in gs.get_valid_moves():
                    if mv == try_move:
                        legal = mv
                        break
                if legal is None:
                    continue
                gs.make_move(legal)
                # Backward compatibility: notify opponent raw move
                other = room.other(color)
                if other is not None:
                    try:
                        await other.send_json({"type": "opponent_move", "move": {"from": frm, "to": to}})
                    except Exception:
                        pass
                # Broadcast full state to both players
                for peer in (room.white, room.black):
                    if peer is not None:
                        try:
                            await peer.send_json({
                                "type": "state",
                                "code": room.code,
                                "board": gs.board,
                                "white_to_move": gs.white_to_move,
                            })
                        except Exception:
                            pass
            elif kind == "reset":
                if room is None:
                    continue
                room.gs = GameState()
                for peer in (room.white, room.black):
                    if peer is not None:
                        try:
                            await peer.send_json({
                                "type": "state",
                                "code": room.code,
                                "board": room.gs.board,
                                "white_to_move": room.gs.white_to_move,
                            })
                        except Exception:
                            pass
            elif kind == "undo":
                if room is None:
                    continue
                # Undo last move regardless of who requested (simple policy)
                room.gs.undo_move()
                for peer in (room.white, room.black):
                    if peer is not None:
                        try:
                            await peer.send_json({
                                "type": "state",
                                "code": room.code,
                                "board": room.gs.board,
                                "white_to_move": room.gs.white_to_move,
                            })
                        except Exception:
                            pass
            elif kind == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        # Cleanup on disconnect
        if room and color:
            async with room.lock:
                try:
                    if color == "w":
                        room.white = None
                    else:
                        room.black = None
                    # Notify remaining player
                    other = room.other(color)
                    if other is not None:
                        try:
                            await other.send_json({"type": "opponent_left"})
                        except Exception:
                            pass
                    # Remove empty room
                    if room.player_count() == 0:
                        rooms.pop(room.code, None)
                except Exception:
                    pass


@app.get("/demo")
def demo_page():
    return HTMLResponse(
        """
        <html>
          <body>
            <h3>PyChess Multiplayer Server</h3>
            <p>Web client is served at <a href='/'>/</a>. WebSocket endpoint: <code>/ws</code></p>
            <pre>
Create: {"action":"create"}
Join:   {"action":"join","code":"ABC123"}
Move:   {"type":"move","move":{"from":[6,4],"to":[4,4]}}
            </pre>
          </body>
        </html>
        """
    )

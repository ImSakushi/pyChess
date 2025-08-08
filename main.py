import os
import pygame
import asyncio
import argparse
import json
from typing import Optional

try:
    import websockets
except Exception:  # pragma: no cover - optional dep for offline mode
    websockets = None

# Initialize Pygame
pygame.init()

DIMENSION = 8
SQ_SIZE = 80  # Par exemple, ajustez selon vos besoins
BORDER_SIZE = SQ_SIZE  # Taille de la bordure égale à une case
WIDTH = HEIGHT = DIMENSION * SQ_SIZE + 2 * BORDER_SIZE
MAX_FPS = 15

BORDER_COLOR = pygame.Color("#553A19")

# Unicode chess pieces
PIECES = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'
}

IMAGES = {}

# Ajoutez ceci près du début de votre fichier, avec vos autres constantes
PIECE_OFFSETS = {
    'P': 30,  # Pion
    'R': 30,   # Tour
    'N': 30,   # Cavalier
    'B': 35,   # Fou
    'Q': 30,   # Reine
    'K': 40    # Roi
}

# Initialize the screen
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Chess")
clock = pygame.time.Clock()

class GameState:
    def __init__(self):
        self.board = [
            ["bR", "bN", "bB", "bQ", "bK", "bB", "bN", "bR"],
            ["bP", "bP", "bP", "bP", "bP", "bP", "bP", "bP"],
            ["--", "--", "--", "--", "--", "--", "--", "--"],
            ["--", "--", "--", "--", "--", "--", "--", "--"],
            ["--", "--", "--", "--", "--", "--", "--", "--"],
            ["--", "--", "--", "--", "--", "--", "--", "--"],
            ["wP", "wP", "wP", "wP", "wP", "wP", "wP", "wP"],
            ["wR", "wN", "wB", "wQ", "wK", "wB", "wN", "wR"]
        ]
        self.white_to_move = True
        self.in_check = False
        self.move_log = []
        self.white_king_location = (7, 4)
        self.black_king_location = (0, 4)
        self.checkmate = False
        self.stalemate = False
        self.pins = []
        self.checks = []
        self.enpassant_possible = ()  # coordinates for the square where en passant capture is possible
        self.current_castling_rights = CastleRights(True, True, True, True)
        self.castle_rights_log = [CastleRights(self.current_castling_rights.wks, self.current_castling_rights.bks,
                                               self.current_castling_rights.wqs, self.current_castling_rights.bqs)]

    def make_move(self, move):
        self.board[move.start_row][move.start_col] = "--"
        self.board[move.end_row][move.end_col] = move.piece_moved
        self.move_log.append(move)
        self.white_to_move = not self.white_to_move
        if move.piece_moved == 'wK':
            self.white_king_location = (move.end_row, move.end_col)
        elif move.piece_moved == 'bK':
            self.black_king_location = (move.end_row, move.end_col)

        # Pawn promotion
        if move.is_pawn_promotion:
            self.board[move.end_row][move.end_col] = move.piece_moved[0] + 'Q'

        # En passant move
        if move.is_enpassant_move:
            self.board[move.start_row][move.end_col] = "--"  # capturing the pawn

        # Update enpassant_possible variable
        if move.piece_moved[1] == 'P' and abs(move.start_row - move.end_row) == 2:  # only on 2 square pawn advance
            self.enpassant_possible = ((move.start_row + move.end_row) // 2, move.start_col)
        else:
            self.enpassant_possible = ()

        # Castle move
        if move.is_castle_move:
            if move.end_col - move.start_col == 2:  # King-side castle
                self.board[move.end_row][move.end_col - 1] = self.board[move.end_row][move.end_col + 1]  # moves rook
                self.board[move.end_row][move.end_col + 1] = '--'  # erase old rook
            else:  # Queen-side castle
                self.board[move.end_row][move.end_col + 1] = self.board[move.end_row][move.end_col - 2]  # moves rook
                self.board[move.end_row][move.end_col - 2] = '--'  # erase old rook

        # Update castling rights
        self.update_castle_rights(move)
        self.in_check = self.check_for_check()
        self.castle_rights_log.append(CastleRights(self.current_castling_rights.wks, self.current_castling_rights.bks,
                                                   self.current_castling_rights.wqs, self.current_castling_rights.bqs))

    def check_for_check(self):
        if self.white_to_move:
            return self.square_under_attack(self.white_king_location[0], self.white_king_location[1])
        else:
            return self.square_under_attack(self.black_king_location[0], self.black_king_location[1])
        
    def undo_move(self):
        if len(self.move_log) != 0:
            move = self.move_log.pop()
            self.board[move.start_row][move.start_col] = move.piece_moved
            self.board[move.end_row][move.end_col] = move.piece_captured
            self.white_to_move = not self.white_to_move
            if move.piece_moved == 'wK':
                self.white_king_location = (move.start_row, move.start_col)
            elif move.piece_moved == 'bK':
                self.black_king_location = (move.start_row, move.start_col)
            # Undo en passant move
            if move.is_enpassant_move:
                self.board[move.end_row][move.end_col] = "--"
                self.board[move.start_row][move.end_col] = move.piece_captured
                self.enpassant_possible = (move.end_row, move.end_col)
            # Undo 2 square pawn advance
            if move.piece_moved[1] == 'P' and abs(move.start_row - move.end_row) == 2:
                self.enpassant_possible = ()
            # Undo castling rights
            self.castle_rights_log.pop()
            new_rights = self.castle_rights_log[-1]
            self.current_castling_rights = CastleRights(new_rights.wks, new_rights.bks, new_rights.wqs, new_rights.bqs)
            # Undo castle move
            if move.is_castle_move:
                if move.end_col - move.start_col == 2:  # King-side castle
                    self.board[move.end_row][move.end_col + 1] = self.board[move.end_row][move.end_col - 1]
                    self.board[move.end_row][move.end_col - 1] = '--'
                else:  # Queen-side castle
                    self.board[move.end_row][move.end_col - 2] = self.board[move.end_row][move.end_col + 1]
                    self.board[move.end_row][move.end_col + 1] = '--'
            self.checkmate = False
            self.stalemate = False

    def update_castle_rights(self, move):
        if move.piece_moved == 'wK':
            self.current_castling_rights.wks = False
            self.current_castling_rights.wqs = False
        elif move.piece_moved == 'bK':
            self.current_castling_rights.bks = False
            self.current_castling_rights.bqs = False
        elif move.piece_moved == 'wR':
            if move.start_row == 7:
                if move.start_col == 0:
                    self.current_castling_rights.wqs = False
                elif move.start_col == 7:
                    self.current_castling_rights.wks = False
        elif move.piece_moved == 'bR':
            if move.start_row == 0:
                if move.start_col == 0:
                    self.current_castling_rights.bqs = False
                elif move.start_col == 7:
                    self.current_castling_rights.bks = False

    def get_valid_moves(self):
        temp_enpassant_possible = self.enpassant_possible
        temp_castle_rights = CastleRights(self.current_castling_rights.wks, self.current_castling_rights.bks,
                                        self.current_castling_rights.wqs, self.current_castling_rights.bqs)
        # 1. Generate all possible moves
        moves = self.get_all_possible_moves()
        # 2. For each move, make the move
        for i in range(len(moves) - 1, -1, -1):
            self.make_move(moves[i])
            # 3. Generate all opponent's moves
            # 4. For each of opponent's moves, see if they attack your king
            self.white_to_move = not self.white_to_move
            if self.check_for_check():
                moves.remove(moves[i])
            self.white_to_move = not self.white_to_move
            self.undo_move()
        if len(moves) == 0:
            if self.in_check:
                self.checkmate = True
            else:
                self.stalemate = True
        else:
            self.checkmate = False
            self.stalemate = False

        if self.white_to_move:
            self.get_castle_moves(self.white_king_location[0], self.white_king_location[1], moves)
        else:
            self.get_castle_moves(self.black_king_location[0], self.black_king_location[1], moves)

        self.enpassant_possible = temp_enpassant_possible
        self.current_castling_rights = temp_castle_rights
        return moves

    def in_check(self):
        if self.white_to_move:
            return self.square_under_attack(self.white_king_location[0], self.white_king_location[1])
        else:
            return self.square_under_attack(self.black_king_location[0], self.black_king_location[1])

    def square_under_attack(self, r, c):
        self.white_to_move = not self.white_to_move
        opp_moves = self.get_all_possible_moves()
        self.white_to_move = not self.white_to_move
        for move in opp_moves:
            if move.end_row == r and move.end_col == c:
                return True
        return False

    def get_all_possible_moves(self):
        moves = []
        for r in range(len(self.board)):
            for c in range(len(self.board[r])):
                turn = self.board[r][c][0]
                if (turn == 'w' and self.white_to_move) or (turn == 'b' and not self.white_to_move):
                    piece = self.board[r][c][1]
                    if piece == 'P':
                        self.get_pawn_moves(r, c, moves)
                    elif piece == 'R':
                        self.get_rook_moves(r, c, moves)
                    elif piece == 'N':
                        self.get_knight_moves(r, c, moves)
                    elif piece == 'B':
                        self.get_bishop_moves(r, c, moves)
                    elif piece == 'Q':
                        self.get_queen_moves(r, c, moves)
                    elif piece == 'K':
                        self.get_king_moves(r, c, moves)
        return moves

    def get_pawn_moves(self, r, c, moves):
        if self.white_to_move:
            if self.board[r - 1][c] == "--":
                moves.append(Move((r, c), (r - 1, c), self.board))
                if r == 6 and self.board[r - 2][c] == "--":
                    moves.append(Move((r, c), (r - 2, c), self.board))
            if c - 1 >= 0:
                if self.board[r - 1][c - 1][0] == 'b':
                    moves.append(Move((r, c), (r - 1, c - 1), self.board))
                elif (r - 1, c - 1) == self.enpassant_possible:
                    moves.append(Move((r, c), (r - 1, c - 1), self.board, is_enpassant_move=True))
            if c + 1 <= 7:
                if self.board[r - 1][c + 1][0] == 'b':
                    moves.append(Move((r, c), (r - 1, c + 1), self.board))
                elif (r - 1, c + 1) == self.enpassant_possible:
                    moves.append(Move((r, c), (r - 1, c + 1), self.board, is_enpassant_move=True))
        else:
            if self.board[r + 1][c] == "--":
                moves.append(Move((r, c), (r + 1, c), self.board))
                if r == 1 and self.board[r + 2][c] == "--":
                    moves.append(Move((r, c), (r + 2, c), self.board))
            if c - 1 >= 0:
                if self.board[r + 1][c - 1][0] == 'w':
                    moves.append(Move((r, c), (r + 1, c - 1), self.board))
                elif (r + 1, c - 1) == self.enpassant_possible:
                    moves.append(Move((r, c), (r + 1, c - 1), self.board, is_enpassant_move=True))
            if c + 1 <= 7:
                if self.board[r + 1][c + 1][0] == 'w':
                    moves.append(Move((r, c), (r + 1, c + 1), self.board))
                elif (r + 1, c + 1) == self.enpassant_possible:
                    moves.append(Move((r, c), (r + 1, c + 1), self.board, is_enpassant_move=True))

    def get_rook_moves(self, r, c, moves):
            directions = ((-1, 0), (0, -1), (1, 0), (0, 1))
            enemy_color = "b" if self.white_to_move else "w"
            for d in directions:
                for i in range(1, 8):
                    end_row = r + d[0] * i
                    end_col = c + d[1] * i
                    if 0 <= end_row < 8 and 0 <= end_col < 8:
                        end_piece = self.board[end_row][end_col]
                        if end_piece == "--":
                            moves.append(Move((r, c), (end_row, end_col), self.board))
                        elif end_piece[0] == enemy_color:
                            moves.append(Move((r, c), (end_row, end_col), self.board))
                            break
                        else:
                            break
                    else:
                        break

    def get_knight_moves(self, r, c, moves):
        knight_moves = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))
        ally_color = "w" if self.white_to_move else "b"
        for m in knight_moves:
            end_row = r + m[0]
            end_col = c + m[1]
            if 0 <= end_row < 8 and 0 <= end_col < 8:
                end_piece = self.board[end_row][end_col]
                if end_piece[0] != ally_color:
                    moves.append(Move((r, c), (end_row, end_col), self.board))

    def get_bishop_moves(self, r, c, moves):
        directions = ((-1, -1), (-1, 1), (1, -1), (1, 1))
        enemy_color = "b" if self.white_to_move else "w"
        for d in directions:
            for i in range(1, 8):
                end_row = r + d[0] * i
                end_col = c + d[1] * i
                if 0 <= end_row < 8 and 0 <= end_col < 8:
                    end_piece = self.board[end_row][end_col]
                    if end_piece == "--":
                        moves.append(Move((r, c), (end_row, end_col), self.board))
                    elif end_piece[0] == enemy_color:
                        moves.append(Move((r, c), (end_row, end_col), self.board))
                        break
                    else:
                        break
                else:
                    break
                    
    def get_queen_moves(self, r, c, moves):
        self.get_rook_moves(r, c, moves)
        self.get_bishop_moves(r, c, moves)

    def get_king_moves(self, r, c, moves):
        king_moves = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
        ally_color = "w" if self.white_to_move else "b"
        for i in range(8):
            end_row = r + king_moves[i][0]
            end_col = c + king_moves[i][1]
            if 0 <= end_row < 8 and 0 <= end_col < 8:
                end_piece = self.board[end_row][end_col]
                if end_piece[0] != ally_color:
                    moves.append(Move((r, c), (end_row, end_col), self.board))

    def get_castle_moves(self, r, c, moves):
        if self.square_under_attack(r, c):
            return
        if (self.white_to_move and self.current_castling_rights.wks) or (not self.white_to_move and self.current_castling_rights.bks):
            self.get_kingside_castle_moves(r, c, moves)
        if (self.white_to_move and self.current_castling_rights.wqs) or (not self.white_to_move and self.current_castling_rights.bqs):
            self.get_queenside_castle_moves(r, c, moves)

    def get_kingside_castle_moves(self, r, c, moves):
        if self.board[r][c+1] == '--' and self.board[r][c+2] == '--':
            if not self.square_under_attack(r, c+1) and not self.square_under_attack(r, c+2):
                moves.append(Move((r, c), (r, c+2), self.board, is_castle_move=True))

    def get_queenside_castle_moves(self, r, c, moves):
        if self.board[r][c-1] == '--' and self.board[r][c-2] == '--' and self.board[r][c-3] == '--':
            if not self.square_under_attack(r, c-1) and not self.square_under_attack(r, c-2):
                moves.append(Move((r, c), (r, c-2), self.board, is_castle_move=True))

class CastleRights():
    def __init__(self, wks, bks, wqs, bqs):
        self.wks = wks
        self.bks = bks
        self.wqs = wqs
        self.bqs = bqs

class Move():
    ranks_to_rows = {"1": 7, "2": 6, "3": 5, "4": 4,
                     "5": 3, "6": 2, "7": 1, "8": 0}
    rows_to_ranks = {v: k for k, v in ranks_to_rows.items()}
    files_to_cols = {"a": 0, "b": 1, "c": 2, "d": 3,
                     "e": 4, "f": 5, "g": 6, "h": 7}
    cols_to_files = {v: k for k, v in files_to_cols.items()}

    def __init__(self, start_sq, end_sq, board, is_enpassant_move=False, is_castle_move=False):
        self.start_row = start_sq[0]
        self.start_col = start_sq[1]
        self.end_row = end_sq[0]
        self.end_col = end_sq[1]
        self.piece_moved = board[self.start_row][self.start_col]
        self.piece_captured = board[self.end_row][self.end_col]
        self.is_pawn_promotion = (self.piece_moved == 'wP' and self.end_row == 0) or (self.piece_moved == 'bP' and self.end_row == 7)
        self.is_enpassant_move = is_enpassant_move
        if self.is_enpassant_move:
            self.piece_captured = 'wP' if self.piece_moved == 'bP' else 'bP'
        self.is_castle_move = is_castle_move
        self.is_capture = self.piece_captured != '--'
        self.move_id = self.start_row * 1000 + self.start_col * 100 + self.end_row * 10 + self.end_col

    def __eq__(self, other):
        if isinstance(other, Move):
            return self.move_id == other.move_id
        return False

    def get_chess_notation(self):
        return self.get_rank_file(self.start_row, self.start_col) + self.get_rank_file(self.end_row, self.end_col)

    def get_rank_file(self, r, c):
        return self.cols_to_files[c] + self.rows_to_ranks[r]

def draw_game_state(screen, gs, valid_moves, square_selected):
    draw_border(screen)
    draw_board(screen)
    highlight_squares(screen, gs, valid_moves, square_selected)
    draw_pieces(screen, gs.board)

def draw_board(screen):
    colors = [pygame.Color("#F3EBD7"), pygame.Color("#A27754")]
    for r in range(DIMENSION):
        for c in range(DIMENSION):
            color = colors[((r+c) % 2)]
            rect = pygame.Rect(
                c*SQ_SIZE + BORDER_SIZE, 
                r*SQ_SIZE + BORDER_SIZE,
                SQ_SIZE, SQ_SIZE
            )
            pygame.draw.rect(screen, color, rect)
            
            # Dessiner le contour
            pygame.draw.rect(screen, BORDER_COLOR, rect, 1)  # Le '1' à la fin indique l'épaisseur du contour
            
def highlight_squares(screen, gs, valid_moves, square_selected):
    if square_selected != ():
        r, c = square_selected
        if gs.board[r][c][0] == ('w' if gs.white_to_move else 'b'):
            s = pygame.Surface((SQ_SIZE, SQ_SIZE))
            s.set_alpha(100)
            s.fill(pygame.Color('blue'))
            screen.blit(s, (c*SQ_SIZE + BORDER_SIZE, r*SQ_SIZE + BORDER_SIZE))
            s.fill(pygame.Color('yellow'))
            for move in valid_moves:
                if move.start_row == r and move.start_col == c:
                    screen.blit(s, (move.end_col*SQ_SIZE + BORDER_SIZE, move.end_row*SQ_SIZE + BORDER_SIZE))
                    
def draw_pieces(screen, board):
    for r in range(DIMENSION):
        for c in range(DIMENSION):
            piece = board[r][c]
            if piece != "--":
                image = IMAGES[piece]
                rect = image.get_rect()
                # Calculer le centre de la case
                center_x = c * SQ_SIZE + BORDER_SIZE + SQ_SIZE // 2
                center_y = r * SQ_SIZE + BORDER_SIZE + SQ_SIZE // 2
                # Utiliser l'offset personnalisé pour chaque type de pièce
                offset_y = PIECE_OFFSETS[piece[1]]
                # Positionner l'image avec le décalage
                rect.center = (center_x, center_y - offset_y)
                screen.blit(image, rect)
                
def draw_border(screen):
    border_color = pygame.Color("#5D4037")  # Couleur de bordure marron foncé
    pygame.draw.rect(screen, border_color, pygame.Rect(0, 0, WIDTH, HEIGHT))
    # Dessiner le "fond" du plateau
    pygame.draw.rect(screen, pygame.Color("#F3EBD7"), pygame.Rect(
        BORDER_SIZE, BORDER_SIZE, 
        WIDTH - 2*BORDER_SIZE, HEIGHT - 2*BORDER_SIZE))
                
def load_images():
    pieces = ['wP', 'wR', 'wN', 'wB', 'wK', 'wQ', 'bP', 'bR', 'bN', 'bB', 'bK', 'bQ']
    for piece in pieces:
        image = pygame.image.load("images/" + piece + ".png")
        IMAGES[piece] = pygame.transform.scale(image, (int(SQ_SIZE * 2.2), int(SQ_SIZE * 2.2)))
        
class OnlineClient:
    def __init__(self, server_ws_url: str):
        if websockets is None:
            raise RuntimeError("websockets package not installed. Run: pip install websockets")
        self.server_ws_url = server_ws_url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.code: Optional[str] = None
        self.color: Optional[str] = None  # 'w' or 'b'
        self.incoming: asyncio.Queue = asyncio.Queue()

    async def connect_and_create(self):
        self.ws = await websockets.connect(self.server_ws_url)
        await self.ws.send(json.dumps({"action": "create"}))
        msg = json.loads(await self.ws.recv())
        if msg.get("type") != "created":
            raise RuntimeError(f"Unexpected server response: {msg}")
        self.code = msg["code"]
        self.color = msg["color"]
        asyncio.create_task(self._reader())

    async def connect_and_join(self, code: str):
        self.ws = await websockets.connect(self.server_ws_url)
        await self.ws.send(json.dumps({"action": "join", "code": code}))
        msg = json.loads(await self.ws.recv())
        if msg.get("type") not in {"joined", "error"}:
            raise RuntimeError(f"Unexpected server response: {msg}")
        if msg.get("type") == "error":
            raise RuntimeError(msg.get("message", "Failed to join"))
        self.code = msg["code"]
        self.color = msg["color"]
        asyncio.create_task(self._reader())

    async def _reader(self):
        try:
            assert self.ws is not None
            while True:
                raw = await self.ws.recv()
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                await self.incoming.put(msg)
        except Exception:
            await self.incoming.put({"type": "disconnected"})

    async def send_move(self, move):
        if self.ws is None:
            return
        payload = {
            "type": "move",
            "move": {
                "from": [move.start_row, move.start_col],
                "to": [move.end_row, move.end_col],
            },
        }
        await self.ws.send(json.dumps(payload))


async def main():
    parser = argparse.ArgumentParser(description="PyChess - local or online play")
    parser.add_argument("--online", action="store_true", help="Enable online multiplayer mode")
    parser.add_argument(
        "--server",
        default=os.environ.get("WS_SERVER_URL", "ws://localhost:8000/ws"),
        help="WebSocket server URL (override with env WS_SERVER_URL)",
    )
    parser.add_argument("--join", dest="join_code", default=None, help="Join an existing game code instead of hosting")
    args = parser.parse_args()
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))  # Mettez cette ligne ici
    clock = pygame.time.Clock()
    screen.fill(pygame.Color("white"))
    gs = GameState()
    valid_moves = gs.get_valid_moves()
    move_made = False
    load_images()
    running = True
    square_selected = ()
    player_clicks = []
    game_over = False

    # Online mode setup
    online: Optional[OnlineClient] = None
    my_color: Optional[str] = None
    if args.online:
        if websockets is None:
            raise SystemExit("Online mode requires 'websockets' package. pip install websockets")
        online = OnlineClient(args.server)
        if args.join_code:
            await online.connect_and_join(args.join_code)
            my_color = online.color
            print(f"Joined game {online.code} as {'White' if my_color=='w' else 'Black'}")
        else:
            await online.connect_and_create()
            my_color = online.color
            print(f"Hosting game. Share code: {online.code}. You are {'White' if my_color=='w' else 'Black'}")
            print("Tip: your friend can join with:")
            print(f"  python main.py --online --server {args.server} --join {online.code}")

    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.MOUSEBUTTONDOWN:
                if not game_over:
                    location = pygame.mouse.get_pos()
                    col = (location[0] - BORDER_SIZE) // SQ_SIZE
                    row = (location[1] - BORDER_SIZE) // SQ_SIZE
                    if 0 <= row < DIMENSION and 0 <= col < DIMENSION:
                        if square_selected == (row, col):
                            square_selected = ()
                            player_clicks = []
                        else:
                            square_selected = (row, col)
                            player_clicks.append(square_selected)
                        if len(player_clicks) == 2:
                            move = Move(player_clicks[0], player_clicks[1], gs.board)
                            # In online mode, enforce turn and color
                            if args.online and my_color is not None:
                                # Check it's my turn and I'm moving my color
                                my_turn = (my_color == 'w' and gs.white_to_move) or (my_color == 'b' and not gs.white_to_move)
                                if not my_turn:
                                    # Not your turn, ignore selection
                                    player_clicks = [square_selected]
                                    continue
                                moving_piece_color = gs.board[player_clicks[0][0]][player_clicks[0][1]][0]
                                if (my_color == 'w' and moving_piece_color != 'w') or (my_color == 'b' and moving_piece_color != 'b'):
                                    player_clicks = [square_selected]
                                    continue
                            for i in range(len(valid_moves)):
                                if move == valid_moves[i]:
                                    gs.make_move(valid_moves[i])
                                    move_made = True
                                    # Send move if online
                                    if args.online and online is not None:
                                        try:
                                            await online.send_move(valid_moves[i])
                                        except Exception:
                                            pass
                                    square_selected = ()
                                    player_clicks = []
                            if not move_made:
                                player_clicks = [square_selected]
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_z:
                        gs.undo_move()
                        move_made = True
                        game_over = False
                    if e.key == pygame.K_r:
                        gs = GameState()
                        valid_moves = gs.get_valid_moves()
                        square_selected = ()
                        player_clicks = []
                        move_made = False
                        game_over = False

            if move_made:
                valid_moves = gs.get_valid_moves()
                move_made = False

            # Handle online incoming messages
            if args.online and online is not None:
                try:
                    # Non-blocking check for incoming messages
                    while True:
                        msg = online.incoming.get_nowait()
                        t = msg.get("type")
                        if t == "start":
                            pass  # Both players connected
                        elif t == "opponent_move":
                            m = msg.get("move", {})
                            frm = m.get("from", [0, 0])
                            to = m.get("to", [0, 0])
                            opp_move = Move((frm[0], frm[1]), (to[0], to[1]), gs.board)
                            # Apply only if legal
                            valids = gs.get_valid_moves()
                            for mv in valids:
                                if mv == opp_move:
                                    gs.make_move(mv)
                                    break
                            valid_moves = gs.get_valid_moves()
                        elif t == "opponent_undo":
                            gs.undo_move()
                            valid_moves = gs.get_valid_moves()
                        elif t == "opponent_reset":
                            gs = GameState()
                            valid_moves = gs.get_valid_moves()
                            square_selected = ()
                            player_clicks = []
                        elif t == "opponent_left":
                            print("Opponent disconnected.")
                        elif t == "disconnected":
                            print("Connection lost.")
                    
                except asyncio.QueueEmpty:
                    pass

            draw_game_state(screen, gs, valid_moves, square_selected)

            if gs.checkmate:
                game_over = True
                if gs.white_to_move:
                    draw_text(screen, "Black wins by checkmate")
                else:
                    draw_text(screen, "White wins by checkmate")
            elif gs.stalemate:
                game_over = True
                draw_text(screen, "Stalemate")

            clock.tick(MAX_FPS)
            pygame.display.flip()
            await asyncio.sleep(0)
            
    
def draw_text(screen, text):
    font = pygame.font.SysFont("Helvitca", 32, True, False)
    text_object = font.render(text, 0, pygame.Color('Gray'))
    text_location = pygame.Rect(0, 0, WIDTH, HEIGHT).move(WIDTH/2 - text_object.get_width()/2, HEIGHT/2 - text_object.get_height()/2)
    screen.blit(text_object, text_location)
    text_object = font.render(text, 0, pygame.Color('Black'))
    screen.blit(text_object, text_location.move(2, 2))

if __name__ == "__main__":
    asyncio.run(main())

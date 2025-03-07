import argparse
import json
from copy import deepcopy
from llm import get_llm_action  # 假设存在的LLM接口

VIDEOCHESS_PROMPT = """
You are playing VideoChess. Strictly follow standard chess rules including all special moves:

1. **Piece Movement**:
   - **King**: 1 square any direction. Castling: Move king 2 squares towards rook (O-O/O-O-O). Requirements:
     - King/rook never moved
     - No pieces between
     - King not in check, doesn't pass through/into check
   - **Queen**: Any direction, any distance
   - **Rook**: Horizontal/vertical, any distance
   - **Bishop**: Diagonal, any distance
   - **Knight**: L-shaped jump (2+1), can leap
   - **Pawn**:
     - Forward 1 (or 2 from start)
     - Capture diagonally
     - En passant: Capture pawn that moved 2 squares beside you
     - Promotion: Must become Queen/Rook/Bishop/Knight at 8th rank

2. **Special Rules**:
   - **Check**: Must escape if king attacked
   - **Checkmate**: No legal moves while in check → lose
   - **Stalemate**: No legal moves, not in check → draw
   - **50-move Rule**: 50 moves without capture/pawn move → draw
   - **3-fold Repetition**: Same position thrice → draw

3. **Notation**:
   - Squares: a1 to h8
   - Pieces: K, Q, R, B, N, P (uppercase=white)
   - Castling: O-O (kingside), O-O-O (queenside)
   - Capture: 'x' (e.g., exd5)
   - Promotion: e8=Q

Examples:
1. e4 (pawn to e4)
2. Nf3 (knight to f3)
3. exd5 (pawn captures d5)
4. O-O (kingside castle)
5. e8=Q (promote to queen)

Current Board:
{board}

Game Status:
Player: {current_player} | Turn: {move_number}
Castling: {castling} | En Passant: {en_passant}
Check: {check}
Legal Moves (SAN): {legal_moves}

Respond ONLY with your move in SAN (e.g., 'e4', 'Nf3', 'O-O'):
"""

class VideoChess:
    def __init__(self):
        self.board = [[None]*8 for _ in range(8)]
        self.current_player = 'white'
        self.castling = {'white': {'K': True, 'Q': True}, 'black': {'K': True, 'Q': True}}
        self.en_passant = None  # (row, col) of target square
        self.move_number = 1
        self.halfmove = 0  # For 50-move rule
        self.history = []  # For 3-fold repetition
        self.check = False
        self._initialize_board()

    def _initialize_board(self):
        # Black pieces (lowercase)
        self.board[0] = ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r']
        self.board[1] = ['p']*8
        # White pieces (uppercase)
        self.board[7] = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
        self.board[6] = ['P']*8

    def get_legal_moves(self):
        moves = []
        for r in range(8):
            for c in range(8):
                piece = self.board[r][c]
                if piece and self._color(piece) == self.current_player:
                    moves += self._piece_moves(r, c)
        # Filter moves leaving king in check
        return [m for m in moves if not self._leaves_check(m)]

    def _color(self, piece):
        return 'white' if piece.isupper() else 'black'

    def _piece_moves(self, row, col):
        piece = self.board[row][col].lower()
        if piece == 'p': return self._pawn_moves(row, col)
        if piece == 'n': return self._knight_moves(row, col)
        if piece == 'b': return self._bishop_moves(row, col)
        if piece == 'r': return self._rook_moves(row, col)
        if piece == 'q': return self._queen_moves(row, col)
        if piece == 'k': return self._king_moves(row, col)
        return []

    def _pawn_moves(self, row, col):
        moves = []
        direction = -1 if self.current_player == 'white' else 1
        start_row = 6 if self.current_player == 'white' else 1

        # Forward moves
        if self._is_empty(row + direction, col):
            moves.append(self._create_move(row, col, row+direction, col))
            if row == start_row and self._is_empty(row + 2*direction, col):
                moves.append(self._create_move(row, col, row + 2*direction, col))

        # Captures
        for dc in (-1, 1):
            if self._is_enemy(row+direction, col+dc):
                moves.append(self._create_move(row, col, row+direction, col+dc))
            # En passant
            if (row + direction, col+dc) == self.en_passant:
                moves.append(self._create_move(row, col, row+direction, col+dc, en_passant=True))

        return moves

    def _knight_moves(self, row, col):
        deltas = [(-2,-1), (-2,1), (-1,-2), (-1,2),
                  (1,-2), (1,2), (2,-1), (2,1)]
        return [self._create_move(row, col, row+dr, col+dc)
                for dr, dc in deltas if self._can_move(row+dr, col+dc)]

    def _bishop_moves(self, row, col):
        return self._slide(row, col, [(-1,-1), (-1,1), (1,-1), (1,1)])

    def _rook_moves(self, row, col):
        return self._slide(row, col, [(-1,0), (1,0), (0,-1), (0,1)])

    def _queen_moves(self, row, col):
        return self._rook_moves(row, col) + self._bishop_moves(row, col)

    def _king_moves(self, row, col):
        moves = [self._create_move(row, col, row+dr, col+dc)
                 for dr in (-1,0,1) for dc in (-1,0,1) 
                 if (dr,dc) != (0,0) and self._can_move(row+dr, col+dc)]
        
        # Castling
        if not self.check and self.castling[self.current_player]['K']:
            if all(self._is_empty(row, c) for c in [5,6]) and not self._attacked(row,5):
                moves.append(self._create_move(row, col, row, 6, castle='K'))
        if not self.check and self.castling[self.current_player]['Q']:
            if all(self._is_empty(row, c) for c in [1,2,3]) and not self._attacked(row,3):
                moves.append(self._create_move(row, col, row, 2, castle='Q'))
        return moves

    def _slide(self, row, col, directions):
        moves = []
        for dr, dc in directions:
            r, c = row+dr, col+dc
            while self._is_valid(r, c):
                if self.board[r][c] is None:
                    moves.append(self._create_move(row, col, r, c))
                else:
                    if self._is_enemy(r, c): 
                        moves.append(self._create_move(row, col, r, c))
                    break
                r += dr
                c += dc
        return moves

    def _create_move(self, r1, c1, r2, c2, **kwargs):
        return {'start': (r1,c1), 'end': (r2,c2), **kwargs}

    def _is_valid(self, r, c):
        return 0 <= r <8 and 0 <= c <8

    def _is_empty(self, r, c):
        return self._is_valid(r,c) and self.board[r][c] is None

    def _is_enemy(self, r, c):
        return self._is_valid(r,c) and self.board[r][c] and self._color(self.board[r][c]) != self.current_player

    def _can_move(self, r, c):
        return self._is_empty(r,c) or self._is_enemy(r,c)

    def _leaves_check(self, move):
        temp = deepcopy(self)
        temp._apply_move(move)
        return temp._in_check(self.current_player)

    def _in_check(self, color):
        king_pos = next((r,c) for r in range(8) for c in range(8)
                     if self.board[r][c] and self.board[r][c].lower() == 'k' 
                     and self._color(self.board[r][c]) == color)
        return any(self._attacks(pos, king_pos) for pos in self._all_enemy_positions(color))

    def _attacks(self, (sr,sc), (tr,tc)):
        piece = self.board[sr][sc].lower()
        dr, dc = tr-sr, tc-sc
        
        if piece == 'p': 
            direction = 1 if self._color(self.board[sr][sc]) == 'black' else -1
            return (dr == direction and abs(dc) ==1)
        if piece == 'n': return (dr**2 + dc**2 ==5)
        if piece == 'k': return max(abs(dr), abs(dc)) ==1
        if piece == 'b': return dr**2 == dc**2 and self._clear_diagonal(sr,sc,tr,tc)
        if piece == 'r': return (dr==0 or dc==0) and self._clear_straight(sr,sc,tr,tc)
        if piece == 'q': return (dr**2 == dc**2 or dr==0 or dc==0) and self._clear_path(sr,sc,tr,tc)
        return False

    def _clear_path(self, r1,c1, r2,c2):
        dr = (r2 - r1)//max(1, abs(r2 - r1))
        dc = (c2 - c1)//max(1, abs(c2 - c1))
        r, c = r1+dr, c1+dc
        while (r,c) != (r2,c2):
            if self.board[r][c]: return False
            r += dr
            c += dc
        return True

    def _all_enemy_positions(self, color):
        enemy = 'black' if color == 'white' else 'white'
        return [(r,c) for r in range(8) for c in range(8)
                if self.board[r][c] and self._color(self.board[r][c]) == enemy]

    def _apply_move(self, move):
        # Update board state
        sr, sc = move['start']
        er, ec = move['end']
        piece = self.board[sr][sc]
        captured = self.board[er][ec]
        
        # Handle special moves
        if 'en_passant' in move:
            captured = self.board[sr][ec]
            self.board[sr][ec] = None
        elif 'castle' in move:
            rook_from = (sr,7) if move['castle'] == 'K' else (sr,0)
            rook_to = (sr,5) if move['castle'] == 'K' else (sr,3)
            self.board[rook_to] = self.board[rook_from]
            self.board[rook_from] = None
        
        # Update castling rights
        if piece.lower() == 'k':
            self.castling[self.current_player] = {'K': False, 'Q': False}
        elif piece.lower() == 'r':
            if sc ==7: self.castling[self.current_player]['K'] = False
            if sc ==0: self.castling[self.current_player]['Q'] = False
        
        # Promotion (auto-queen)
        if piece.lower() == 'p' and er in [0,7]:
            piece = 'Q' if self.current_player == 'white' else 'q'
        
        # Update board
        self.board[sr][sc] = None
        self.board[er][ec] = piece
        
        # Update en passant
        self.en_passant = (er + (1 if self.current_player == 'white' else -1), ec) \
            if piece.lower() == 'p' and abs(sr - er) ==2 else None
        
        # Update game state
        self.current_player = 'black' if self.current_player == 'white' else 'white'
        self.check = self._in_check(self.current_player)
        self.move_number += (1 if self.current_player == 'white' else 0)
        self.halfmove = 0 if piece.lower() == 'p' or captured else self.halfmove +1
        self.history.append(deepcopy(self.board))

    def board_to_str(self):
        symbols = {None: '.', 'R':'♖','N':'♘','B':'♗','Q':'♕','K':'♔','P':'♙',
                   'r':'♜','n':'♞','b':'♝','q':'♛','k':'♚','p':'♟'}
        board_str = "  a b c d e f g h\n"
        for r in range(8):
            line = [f"{8-r} "] + [symbols[self.board[r][c]] for c in range(8)]
            board_str += ' '.join(line) + '\n'
        return board_str

    def play(self, output_file):
        while True:
            # Check game end
            legal_moves = self.get_legal_moves()
            if not legal_moves:
                if self.check:
                    winner = 'Black' if self.current_player == 'white' else 'White'
                    print(f"Checkmate! {winner} wins!")
                else:
                    print("Stalemate! Draw!")
                break
            
            # Generate prompt
            san_moves = [self._to_san(m) for m in legal_moves]
            prompt = VIDEOCHESS_PROMPT.format(
                board=self.board_to_str(),
                current_player=self.current_player,
                move_number=self.move_number,
                castling=self.castling[self.current_player],
                en_passant=self._to_algebraic(self.en_passant),
                check=self.check,
                legal_moves=', '.join(san_moves)
            )
            
            # Get LLM move
            action, reasoning = get_llm_action(prompt, "gpt-4")
            print(f"Move: {action}\nReason: {reasoning}")
            
            # Validate and apply
            move = self._parse_san(action, legal_moves)
            if move:
                self._apply_move(move)
                self._log_move(action, reasoning)
                self._save_log(output_file)
            else:
                print(f"Invalid move! Using first legal move: {san_moves[0]}")
                self._apply_move(legal_moves[0])
                self._save_log(output_file)

    def _to_san(self, move):
        # Simplified SAN conversion
        piece = self.board[move['start'][0]][move['start'][1]].upper()
        if piece == 'P': piece = ''
        file = chr(ord('a') + move['start'][1])
        rank = 8 - move['start'][0]
        capture = 'x' if self.board[move['end'][0]][move['end'][1]] else ''
        dest = chr(ord('a') + move['end'][1]) + str(8 - move['end'][0])
        return f"{piece}{file}{capture}{dest}"

    def _parse_san(self, san, legal_moves):
        # Match SAN to legal move
        for move in legal_moves:
            if self._to_san(move) == san:
                return move
        return None

    def _to_algebraic(self, pos):
        return f"{chr(ord('a')+pos[1])}{8-pos[0]}" if pos else None

    def _log_move(self, action, reasoning):
        self.game_log.append({
            "move": self.move_number,
            "player": self.current_player,
            "action": action,
            "reasoning": reasoning,
            "board": self.board_to_str(),
        })

    def _save_log(self, path):
        with open(path, 'w') as f:
            json.dump(self.game_log, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="videochess_log.json")
    args = parser.parse_args()
    game = VideoChess()
    game.play(args.output)
import argparse
import collections
import copy
import json
import itertools
import random
from openai import OpenAI
import os
from llm import get_llm_action

VideoChecker_prompt = """
You are playing Atari Video Checkers. Game rules:
1. All pieces are initially placed and should move on a 8x8 board using dark squares
2. Move diagonally forward (Kings can move backward)
3. Must capture if possible, prioritize longest chain
4. Reach opponent's back row to promote to King

Current Board (R: Red, RK: Red King, B: Black, BK: Black King):
{board}

Game Status:
Player: {player} | Turn: {turn}
Red Score: {red_score} | Black Score: {black_score}
Legal Moves: {legal_moves}

Your Move (format 'x1,y1->x2,y2->x3,y3'):
"""

class AtariCheckers:
    def __init__(self):
        self.board = [[None for _ in range(8)] for _ in range(8)]
        self.current_player = 'R'
        self.red_score = 0
        self.black_score = 0
        self.turn_count = 1
        self.game_log = []
        self._initialize_board()

    def _initialize_board(self):
        """Initialize pieces in starting positions"""
        for row in range(8):
            for col in range(8):
                if (row + col) % 2 == 1:
                    if row < 3:
                        self.board[row][col] = 'B'
                    elif row > 4:
                        self.board[row][col] = 'R'

    def get_legal_moves(self):
        """Get all legal moves considering forced captures and safety"""
        # Phase 1: Find all capture sequences
        capture_moves = self._find_all_captures()
        if capture_moves:
            max_length = max(len(move) for move in capture_moves)
            return [move for move in capture_moves if len(move) == max_length]
        
        # Phase 2: Find safe regular moves
        return self._find_safe_regular_moves()

    def _find_all_captures(self):
        """Find all possible capture sequences"""
        captures = []
        for r in range(8):
            for c in range(8):
                piece = self.board[r][c]
                if piece and piece[0] == self.current_player[0]:
                    self._recursive_capture_search(r, c, [], captures)
        return captures

    def _recursive_capture_search(self, r, c, path, results):
        """Recursively search for multi-jump captures"""
        piece = self.board[r][c]
        opponent = 'B' if piece[0] == 'R' else 'R'
        directions = [(-1,-1), (-1,1), (1,-1), (1,1)] if 'K' in piece else \
                   [(-1,-1), (-1,1)] if piece == 'R' else [(1,-1), (1,1)]

        max_jumps = []
        for dr, dc in directions:
            jr, jc = r + dr*2, c + dc*2
            if 0 <= jr < 8 and 0 <= jc < 8:
                mr, mc = r + dr, c + dc
                if (self.board[mr][mc] and 
                    self.board[mr][mc][0] == opponent and 
                    not self.board[jr][jc] and 
                    (mr, mc) not in path):
                    
                    # Save original state
                    original = self.board[r][c]
                    captured = self.board[mr][mc]
                    temp_king = False
                    
                    # Make jump
                    self.board[r][c] = None
                    self.board[mr][mc] = None
                    self.board[jr][jc] = original
                    
                    # Check promotion
                    if (original == 'R' and jr == 0) or (original == 'B' and jr == 7):
                        if 'K' not in original:
                            self.board[jr][jc] += 'K'
                            temp_king = True
                    
                    # Recursive search
                    new_path = path + [(mr, mc)]
                    sub_jumps = []
                    self._recursive_capture_search(jr, jc, new_path, sub_jumps)
                    
                    # Restore state
                    self.board[r][c] = original
                    self.board[mr][mc] = captured
                    self.board[jr][jc] = None
                    if temp_king:
                        self.board[jr][jc] = original  # Remove temporary King
                    
                    # Build jump path
                    if sub_jumps:
                        for sj in sub_jumps:
                            full_path = [(r,c)] + sj
                            if len(full_path) > len(max_jumps):
                                max_jumps = full_path
                    else:
                        current_path = [(r,c), (jr,jc)]
                        if len(current_path) > len(max_jumps):
                            max_jumps = current_path
        
        if max_jumps:
            results.append(max_jumps)
            return True
        return False

    def _find_safe_regular_moves(self):
        """Find non-capturing moves that don't expose to immediate capture"""
        safe_moves = []
        for r in range(8):
            for c in range(8):
                piece = self.board[r][c]
                if piece and piece[0] == self.current_player[0]:
                    directions = self._get_move_directions(piece)
                    for dr, dc in directions:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < 8 and 0 <= nc < 8 and not self.board[nr][nc]:
                            if self._is_move_safe(r, c, nr, nc):
                                safe_moves.append([(r,c), (nr,nc)])
        return safe_moves

    def _get_move_directions(self, piece):
        """Get valid movement directions for a piece"""
        if 'K' in piece:
            return [(-1,-1), (-1,1), (1,-1), (1,1)]
        return [(-1,-1), (-1,1)] if piece == 'R' else [(1,-1), (1,1)]

    def _is_move_safe(self, from_r, from_c, to_r, to_c):
        """Check if move doesn't expose piece to immediate capture"""
        original = self.board[from_r][from_c]
        self.board[from_r][from_c] = None
        self.board[to_r][to_c] = original
        
        enemy = 'B' if self.current_player == 'R' else 'R'
        safe = True
        
        for r in range(8):
            for c in range(8):
                piece = self.board[r][c]
                if piece and piece[0] == enemy:
                    if self._can_capture(r, c, to_r, to_c):
                        safe = False
                        break
            if not safe:
                break
        
        self.board[from_r][from_c] = original
        self.board[to_r][to_c] = None
        return safe

    def _can_capture(self, attacker_r, attacker_c, target_r, target_c):
        """Check if piece at (attacker) can capture (target)"""
        dr = target_r - attacker_r
        dc = target_c - attacker_c
        if abs(dr) != 2 or abs(dc) != 2:
            return False
        
        mid_r = attacker_r + dr//2
        mid_c = attacker_c + dc//2
        return (self.board[mid_r][mid_c] and 
                self.board[mid_r][mid_c][0] == self.current_player[0] and
                self.board[target_r][target_c] is None)

    def apply_move(self, move_sequence):
        """Execute a move sequence with potential multi-jumps"""
        path = [tuple(map(int, step.split(','))) for step in move_sequence.split('->')]
        total_captures = []
        current_path = path.copy()
        promotion = False

        while True:
            # Execute single jump/move
            start_r, start_c = current_path[0]
            end_r, end_c = current_path[-1]
            piece = self.board[start_r][start_c]
            
            # Move piece
            self.board[start_r][start_c] = None
            self.board[end_r][end_c] = piece
            
            # Process captures
            captures = []
            for i in range(len(current_path)-1):
                r1, c1 = current_path[i]
                r2, c2 = current_path[i+1]
                if abs(r2 - r1) == 2:
                    mid_r = (r1 + r2) // 2
                    mid_c = (c1 + c2) // 2
                    if self.board[mid_r][mid_c]:
                        captures.append((mid_r, mid_c))
                        self.board[mid_r][mid_c] = None
            total_captures.extend(captures)
            
            # Check promotion
            if not promotion and ((piece == 'R' and end_r == 0) or (piece == 'B' and end_r == 7)):
                if 'K' not in piece:
                    self.board[end_r][end_c] += 'K'
                    promotion = True
            
            # Check for further jumps
            next_jumps = self._get_forced_jumps(end_r, end_c)
            if not next_jumps:
                break
                
            # Continue jumping
            current_path = next_jumps[0]
            move_sequence += f"->{current_path[-1][0]},{current_path[-1][1]}"

        # Update scores
        score = len(total_captures) * 10
        if promotion:
            score += 50
        if self.current_player == 'R':
            self.red_score += score
        else:
            self.black_score += score
            
        # Switch player
        self.current_player = 'B' if self.current_player == 'R' else 'R'
        self.turn_count += 1
        
        return total_captures, score

    def _get_forced_jumps(self, r, c):
        """Check if piece at (r,c) has mandatory jumps"""
        piece = self.board[r][c]
        if not piece:
            return []
        
        opponent = 'B' if piece[0] == 'R' else 'R'
        directions = [(-1,-1), (-1,1), (1,-1), (1,1)] if 'K' in piece else \
                   [(-1,-1), (-1,1)] if piece == 'R' else [(1,-1), (1,1)]
        
        jumps = []
        for dr, dc in directions:
            jr, jc = r + dr*2, c + dc*2
            if 0 <= jr < 8 and 0 <= jc < 8:
                mr, mc = r + dr, c + dc
                if (self.board[mr][mc] and 
                    self.board[mr][mc][0] == opponent and 
                    not self.board[jr][jc]):
                    jumps.append([(r,c), (jr,jc)])
        return jumps

    def check_winner(self):
        """Determine game winner"""
        red_pieces = sum(1 for row in self.board for p in row if p and p[0] == 'R')
        black_pieces = sum(1 for row in self.board for p in row if p and p[0] == 'B')
        
        if red_pieces == 0 or not self._has_legal_moves('R'):
            return 'B'
        if black_pieces == 0 or not self._has_legal_moves('B'):
            return 'R'
        return None

    def _has_legal_moves(self, player):
        original_player = self.current_player
        self.current_player = player
        legal_moves = self.get_legal_moves()
        self.current_player = original_player
        return len(legal_moves) > 0

    def board_to_str(self):
        """Convert board to visual string representation"""
        display = []
        for r, row in enumerate(self.board):
            line = []
            for c, piece in enumerate(row):
                if (r + c) % 2 == 0:
                    line.append('□')
                else:
                    line.append(piece if piece else '·')
            display.append(f"{7-r} {' '.join(line)}")
        display.append("  0 1 2 3 4 5 6 7")
        return '\n'.join(display)

    def play(self, output_file):
        """Main game loop"""
        while True:
            # Get current state
            legal_moves = self.get_legal_moves()
            formatted_moves = ['->'.join(f"{x},{y}" for x,y in move) for move in legal_moves]
            
            # Generate prompt
            prompt = VideoChecker_prompt.format(
                board=self.board_to_str(),
                player=self.current_player,
                turn=self.turn_count,
                red_score=self.red_score,
                black_score=self.black_score,
                legal_moves=formatted_moves
            )
            
            # Get LLM action
            action, reasoning = get_llm_action(prompt, "gpt-4")
            print(f"Chosen move: {action}\nReasoning: {reasoning}")
            
            # Validate and apply move
            if action in formatted_moves:
                captures, score = self.apply_move(action)
                print(f"Captured {len(captures)} pieces! +{score} points")
            else:
                print("Invalid move! Using first legal move")
                action = formatted_moves[0]
                captures, score = self.apply_move(action)
                
            # Log game state
            self.game_log.append({
                "turn": self.turn_count,
                "player": self.current_player,
                "action": action,
                "reasoning": reasoning,
                "captures": len(captures),
                "score_change": score,
                "red_score": self.red_score,
                "black_score": self.black_score,
                "board_state": self.board_to_str()
            })
            
            # Save progress
            with open(output_file, 'w') as f:
                json.dump(self.game_log, f, indent=2)
                
            # Check winner
            winner = self.check_winner()
            if winner:
                print(f"Game Over! Winner: {winner}")
                break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Atari VideoChecker")
    parser.add_argument("--output", type=str, default="VideoChecker_log.json")
    args = parser.parse_args()
    
    game = AtariCheckers()
    game.play(args.output)
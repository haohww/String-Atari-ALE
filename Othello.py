import argparse
import collections
import copy
import json
import itertools
import random
from openai import OpenAI
import os
from llm import get_llm_action

Othello_prompt = """
You are playing Atari Othello. Game rules:
1. Players need to place pieces on a 8x8 board
2. Players alternate placing pieces (Black first)
3. Place piece to outflank opponent's pieces in one or more directions
4. All outflanked pieces are flipped to your color
5. If no valid moves, must pass. Game ends when both pass or board is full.

Current Board (B: Black, W: White):
{board}

Game Status:
Player: {player} | Turn: {turn}
Black Count: {black_count} | White Count: {white_count}
Legal Moves: {legal_moves}

Your Move (format 'x,y'):
"""

class AtariOthello:
    def __init__(self):
        self.board = [[None for _ in range(8)] for _ in range(8)]
        self.current_player = 'B'  # Black starts first
        self.turn_count = 1
        self.game_log = []
        self._initialize_board()

    def _initialize_board(self):
        """Initialize pieces in starting positions"""
        self.board[3][3] = 'W'
        self.board[3][4] = 'B'
        self.board[4][3] = 'B'
        self.board[4][4] = 'W'

    def get_legal_moves(self):
        """Get all valid moves for current player"""
        legal_moves = []
        for row in range(8):
            for col in range(8):
                if self.board[row][col] is None and self._is_valid_move(row, col):
                    legal_moves.append(f"{row},{col}")
        return legal_moves

    def _is_valid_move(self, row, col):
        """Check if placing a piece at (row,col) is valid"""
        if self.board[row][col] is not None:
            return False
        
        directions = [(-1, -1), (-1, 0), (-1, 1),
                      (0, -1),          (0, 1),
                      (1, -1),  (1, 0), (1, 1)]
        opponent = 'W' if self.current_player == 'B' else 'B'
        
        for dr, dc in directions:
            r, c = row + dr, col + dc
            temp_flips = []
            while 0 <= r < 8 and 0 <= c < 8 and self.board[r][c] == opponent:
                temp_flips.append((r, c))
                r += dr
                c += dc
                if 0 <= r < 8 and 0 <= c < 8 and self.board[r][c] == self.current_player:
                    if temp_flips:
                        return True
        return False

    def apply_move(self, move):
        """Execute a move and flip appropriate pieces"""
        row, col = map(int, move.split(','))
        self.board[row][col] = self.current_player
        flipped = self._flip_pieces(row, col)
        return flipped

    def _flip_pieces(self, row, col):
        """Flip opponent's pieces in all valid directions"""
        directions = [(-1, -1), (-1, 0), (-1, 1),
                      (0, -1),          (0, 1),
                      (1, -1),  (1, 0), (1, 1)]
        opponent = 'W' if self.current_player == 'B' else 'B'
        total_flipped = []

        for dr, dc in directions:
            r, c = row + dr, col + dc
            temp_flips = []
            while 0 <= r < 8 and 0 <= c < 8 and self.board[r][c] == opponent:
                temp_flips.append((r, c))
                r += dr
                c += dc

            if 0 <= r < 8 and 0 <= c < 8 and self.board[r][c] == self.current_player:
                for (fr, fc) in temp_flips:
                    self.board[fr][fc] = self.current_player
                total_flipped.extend(temp_flips)

        return len(total_flipped)

    def board_to_str(self):
        """Convert board to visual string representation"""
        display = []
        for r in range(8):
            line = []
            for c in range(8):
                if self.board[r][c] is None:
                    line.append('·')
                else:
                    line.append(self.board[r][c])
            display.append(f"{7-r} {' '.join(line)}")
        display.append("  0 1 2 3 4 5 6 7")  # Column labels
        return '\n'.join(display)

    def get_counts(self):
        """Return current piece counts"""
        black = sum(row.count('B') for row in self.board)
        white = sum(row.count('W') for row in self.board)
        return black, white

    def is_board_full(self):
        """Check if board has no empty spaces"""
        return all(cell is not None for row in self.board for cell in row)

    def play(self, output_file):
        """Main game loop"""
        consecutive_passes = 0
        
        while True:
            # Check game end conditions
            if self.is_board_full():
                break

            legal_moves = self.get_legal_moves()
            black_count, white_count = self.get_counts()
            
            # Handle no legal moves case
            if not legal_moves:
                self.game_log.append({
                    "turn": self.turn_count,
                    "player": self.current_player,
                    "action": "pass",
                    "reasoning": "No legal moves available",
                    "flipped": 0,
                    "black_count": black_count,
                    "white_count": white_count,
                    "board_state": self.board_to_str()
                })
                consecutive_passes += 1
                if consecutive_passes >= 2:
                    break
                self.current_player = 'W' if self.current_player == 'B' else 'B'
                self.turn_count += 1
                continue
            
            consecutive_passes = 0

            # Generate prompt
            prompt = Othello_prompt.format(
                board=self.board_to_str(),
                player=self.current_player,
                turn=self.turn_count,
                black_count=black_count,
                white_count=white_count,
                legal_moves=legal_moves
            )

            # Get LLM action
            action, reasoning = get_llm_action(prompt, "gpt-4")
            print(f"Chosen move: {action}\nReasoning: {reasoning}")

            # Validate and apply move
            if action in legal_moves:
                flipped = self.apply_move(action)
            else:
                print(f"Invalid move! Using first legal move: {legal_moves[0]}")
                action = legal_moves[0]
                flipped = self.apply_move(action)

            # Log game state
            self.game_log.append({
                "turn": self.turn_count,
                "player": self.current_player,
                "action": action,
                "reasoning": reasoning,
                "flipped": flipped,
                "black_count": black_count + (1 if self.current_player == 'B' else 0) + flipped,
                "white_count": white_count + (1 if self.current_player == 'W' else 0) + flipped,
                "board_state": self.board_to_str()
            })

            # Switch player
            self.current_player = 'W' if self.current_player == 'B' else 'B'
            self.turn_count += 1

            # Save progress
            with open(output_file, 'w') as f:
                json.dump(self.game_log, f, indent=2)

        # Determine winner
        black, white = self.get_counts()
        winner = 'Black' if black > white else 'White' if white > black else 'Draw'
        print(f"Game Over! Result: {winner}")
        print(f"Final Score - Black: {black}, White: {white}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Atari Othello")
    parser.add_argument("--output", type=str, default="Othello_log.json")
    args = parser.parse_args()
    
    game = AtariOthello()
    game.play(args.output)
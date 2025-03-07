import argparse
import collections
import random
import json
from llm import get_llm_action

# Tunable params
GATE_CHANCE = 0.25
GAME_COOLDOWN = 3
TREE_MIN = 0
TREE_MAX = 2

skiing_prompt = """You are controlling a skier in a skiing game. Game elements:
S - Your skier (moves horizontally)
T - Trees (avoid collision)
G...G - Gates (pass between the G's to score)

Goal: Pass through gates to score points, avoid trees and gates. Missing a gate deducts points.

Rules:
- Move with LEFT/RIGHT to position the skier.
- Each passed gate gives +5 points.
- Each missed gate gives -1 point.
- Colliding with a tree or gate pole (G) costs 1 HP.
- Initial HP is 3. Losing all HP ends the game.
- The board scrolls up each turn; new obstacles appear at the top.

Action Space: NOOP, LEFT, RIGHT

Current Board:
{board_state}

Game Status:
Turn {turn} | Score: {score} | HP: {hp}
Last Action: {last_action}

Your Action:
"""


class SkiingGame:
    def __init__(self):
        self.grid_height = 11
        self.grid_width = 20
        self.skier_x = self.grid_width // 2  # Start in middle
        self.trees = []
        self.gates = []
        self.score = 0
        self.hp = 1
        self.turn = 0
        self.game_over = False
        self.last_action = "NOOP"
        self.gate_cooldown = 0  # Cooldown for gate generation

        # Initialize board with starting rows
        for y in range(self.grid_height):
            self.generate_new_row(y)

    def generate_new_row(self, y):
        """Generate new row at given y with trees and possibly a gate"""
        gate_x = []
        # Add gate if cooldown is 0 and chance allows
        if self.gate_cooldown == 0 and y == 0:  # Only add gates to new top row
            if random.random() < GATE_CHANCE:  # 25% chance to add gate when possible
                spacing = random.randint(3, 5)
                max_left = self.grid_width - 1 - spacing - 1
                if max_left < 0:
                    return
                left_g = random.randint(0, max_left)
                right_g = left_g + spacing + 1
                self.gates.append((left_g, right_g, y))
                gate_x.append(left_g)
                gate_x.append(right_g)
                self.gate_cooldown = GAME_COOLDOWN  # Prevent gates for next 3 rows

        # Add 0-2 trees
        num_trees = random.randint(TREE_MIN, TREE_MAX)
        for _ in range(num_trees):
            x = random.randint(0, self.grid_width - 1)
            if x not in gate_x:
                self.trees.append((x, y))

    def scroll_board(self):
        """Move all entities down and generate new row"""
        # Move entities down
        self.trees = [(x, y + 1) for (x, y) in self.trees]
        self.gates = [(left, right, y + 1) for (left, right, y) in self.gates]

        # Remove entities out of bounds
        self.trees = [(x, y) for (x, y) in self.trees if y <= self.grid_height]
        self.gates = [
            (left, right, y) for (left, right, y) in self.gates if y <= self.grid_height
        ]

        # Update gate cooldown
        if self.gate_cooldown > 0:
            self.gate_cooldown -= 1

        # Generate new row at top (y=0)
        self.generate_new_row(0)

    def check_collisions(self):
        """Check for collisions and update score/HP"""
        skier_y = self.grid_height - 1

        # Check gates in current row
        current_gates = [gate for gate in self.gates if gate[2] == skier_y]
        for gate in current_gates:
            left_g, right_g, y = gate
            if self.skier_x == left_g or self.skier_x == right_g:
                self.hp -= 1
                print("Hit a pole!")
            elif left_g < self.skier_x < right_g:
                self.score += 5
            else:
                self.score -= 1
            self.gates.remove(gate)

        # Check trees in current row
        current_trees = [tree for tree in self.trees if tree[1] == skier_y]
        for tree in current_trees:
            x, y = tree
            if x == self.skier_x:
                self.hp -= 1
            self.trees.remove(tree)

        # Check for game over
        if self.hp <= 0:
            self.game_over = True

    def grid_to_string(self):
        """Render current state as grid string"""
        grid = []
        for y in range(self.grid_height):
            row = ["."] * self.grid_width
            # Add trees
            for x, ty in self.trees:
                if ty == y:
                    row[x] = "T"
            # Add gates
            for left_g, right_g, gy in self.gates:
                if gy == y:
                    row[left_g] = "G"
                    row[right_g] = "G"
            # Add skier
            if y == self.grid_height - 2:
                if 0 <= self.skier_x < self.grid_width:
                    row[self.skier_x] = "S"
            grid.append(" ".join(row))
        return "\n".join(grid)

    def play(self, output_file):
        """Main game loop"""
        game_dict = collections.defaultdict(list)
        game_count = 0
        while True:
            self.__init__()
            game_count += 1
            game_log = {}

            while not self.game_over:
                self.turn += 1
                board_str = self.grid_to_string()

                prompt = skiing_prompt.format(
                    board_state=board_str,
                    turn=self.turn,
                    score=self.score,
                    hp=self.hp,
                    last_action=self.last_action,
                )

                action, reasoning = get_llm_action(prompt, "gemini")
                print(f"\nTurn {self.turn}")
                print(f"HP: {self.hp} | Score: {self.score}")
                print(board_str)
                print(f"Action: {action}")

                # Process action
                if action == "LEFT":
                    self.skier_x = max(0, self.skier_x - 1)
                elif action == "RIGHT":
                    self.skier_x = min(self.grid_width - 1, self.skier_x + 1)
                self.last_action = action

                # Update game state
                self.scroll_board()
                self.check_collisions()

                # Log state
                game_log = {
                    "input": prompt,
                    "output": action,
                    "turn": self.turn,
                    "reasoning": reasoning,
                    "score": self.score,
                    "hp": self.hp,
                    "state": board_str,
                }
                game_dict[game_count].append(game_log)

                with open(output_file, "w") as f:
                    json.dump(game_dict, f, indent=2)
                if self.game_over:
                    print(f"Game Over! Final Score: {self.score}")
                    break


# Initial game setup
initial_board = """..................
......T...........
........G..G......
...T..............
.....T.....G..G...
..........T.......
..T..T............
.......T..........
..........T.......
..T.....G...G.....
........S.........
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Skiing game")
    parser.add_argument("--output", type=str, default="skiing_log.json")
    args = parser.parse_args()

    game = SkiingGame()
    game.play(args.output)

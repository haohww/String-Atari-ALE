import argparse
import collections
import json
import random
from llm import get_llm_action

# Tunable params
INITIAL_HP = 3
INITIAL_FUEL = 20
NEW_FUEL_EACH_TURN_MIN = 0
NEW_FUEL_EACH_TURN_MAX = 3


riverraid_prompt = """You are piloting a jet in RiverRaid. Game elements:
S - Your jet (moves horizontally)
E - Enemies
! - Your missiles
F - Fuel depots
# - River banks
. - Safe river

Goal: Destroy enemies, collect fuel, and avoid collisions.
Lose if: HP reaches 0 or fuel runs out.

Rules:
1. Move with LEFT/RIGHT (stay between river banks)
2. FIRE to shoot missiles upward
3. River scrolls down each turn - enemies/fuel move down
4. Colliding with bank/enemy costs 1 HP
5. Collect F to refuel completely
6. Score 10 points -> +1 HP
7. Fuel decreases by 1 each turn

Action Space: NOOP, LEFT, RIGHT, FIRE
Fire only when aligned with enemies. Stay between banks (#)!

Current Board:
{board_state}

Game Status:
Turn {turn} | Score: {score} | HP: {hp} | Fuel: {fuel}%
Last Action: {last_action}

Your Action:
"""


class RiverRaidGame:
    def __init__(self):
        self.board = self.parse_grid(initial_board)
        self.score = 0
        self.turn = 0
        self.hp = INITIAL_HP
        self.fuel = INITIAL_FUEL
        self.last_action = "NOOP"
        self.game_over = False
        self.grid_height = 11
        self.grid_width = 20
        self.generate_new_row(0)  # Initial top row

    def parse_grid(self, grid_str):
        """Convert grid string to game state dict"""
        grid = [list(line) for line in grid_str.strip().split("\n")]
        state = {"jet": None, "enemies": [], "missiles": [], "fuel": [], "walls": []}

        for y, row in enumerate(grid):
            for x, char in enumerate(row):
                pos = (x, y)
                if char == "S":
                    state["jet"] = pos
                elif char == "E":
                    state["enemies"].append(pos)
                elif char == "!":
                    state["missiles"].append(pos)
                elif char == "+":
                    state["fuel"].append(pos)
                elif char == "#":
                    state["walls"].append(pos)
        return state

    def generate_new_row(self, y):
        """Generate new row at position y with random enemies/fuel"""
        new_enemy_x = []
        # Create 0-3 enemies
        for _ in range(random.randint(0, 3)):
            x = random.randint(1, self.grid_width - 2)
            new_enemy_x.append(x)
            self.board["enemies"].append((x, y))

        for _ in range(random.randint(NEW_FUEL_EACH_TURN_MIN, NEW_FUEL_EACH_TURN_MAX)):
            x = random.randint(1, self.grid_width - 2)
            if x not in new_enemy_x:
                self.board["fuel"].append((x, y))

    def grid_to_string(self):
        """Render current state as grid string"""
        grid = []
        for y in range(self.grid_height):
            row = ["."] * self.grid_width
            row[0] = "#"  # Left bank
            row[-1] = "#"  # Right bank

            # Draw elements
            for ex, ey in self.board["enemies"]:
                if ey == y:
                    row[ex] = "E"
            for fx, fy in self.board["fuel"]:
                if fy == y:
                    row[fx] = "+"
            for mx, my in self.board["missiles"]:
                if my == y:
                    row[mx] = "!"

            # Draw jet
            jx, jy = self.board["jet"]
            if jy == y:
                row[jx] = "S"

            grid.append(" ".join(row))
        return "\n".join(grid)

    def move_jet(self, action):
        """Process player movement"""
        x, y = self.board["jet"]
        new_pos = (x, y)
        if action == "LEFT":  # Avoid left bank
            if x > 1:
                new_pos = (x - 1, y)
            else:
                self.hp -= 1  # clapsed to left bank
        elif action == "RIGHT":  # Avoid right bank
            if x < self.grid_width - 2:
                new_pos = (x + 1, y)
            else:
                self.hp -= 1  # clapsed to right bank
        else:
            return False

        self.board["jet"] = new_pos
        return True

    def fire_missile(self):
        """Create new missile above jet"""
        x, y = self.board["jet"]
        if y > 0:
            self.board["missiles"].append((x, y))
            return True
        return False

    def scroll_river(self):
        """Scroll all entities down and generate new row"""
        # Move entities
        self.board["enemies"] = [
            (x, y + 1) for (x, y) in self.board["enemies"] if y + 1 < self.grid_height
        ]
        self.board["fuel"] = [
            (x, y + 1) for (x, y) in self.board["fuel"] if y + 1 < self.grid_height
        ]
        self.board["missiles"] = [
            (x, y - 1) for (x, y) in self.board["missiles"] if y - 1 >= 0
        ]

        # Generate new row at top
        self.generate_new_row(0)

    def check_collisions(self):
        """Check for collisions and collect fuel"""
        jx, jy = self.board["jet"]

        # Check fuel collection
        for f in list(self.board["fuel"]):
            if f == (jx, jy):
                self.fuel += 10
                self.board["fuel"].remove(f)

        # Check enemy/bank collision
        if jx in [0, self.grid_width - 1] or any(
            e == (jx, jy) for e in self.board["enemies"]
        ):
            self.hp -= 1

        # Check missile hits
        for missile in list(self.board["missiles"]):
            if missile in self.board["enemies"]:
                self.score += 5
                self.board["enemies"].remove(missile)
                self.board["missiles"].remove(missile)
                if self.score % 10 == 0:
                    self.hp += 1  # Earn HP every 10 points

    def update_game_state(self):
        """Update fuel and check game over"""
        self.fuel = max(0, self.fuel - 1)
        if self.fuel <= 0 or self.hp <= 0:
            self.game_over = True

    def play(self, output_file):
        """Main game loop"""
        game_count = 0
        game_dict = collections.defaultdict(list)
        while True:
            game_count += 1
            self.__init__()
            game_log = {}

            while not self.game_over:
                self.turn += 1
                board_str = self.grid_to_string()

                prompt = riverraid_prompt.format(
                    board_state=board_str,
                    turn=self.turn,
                    score=self.score,
                    hp=self.hp,
                    fuel=self.fuel,
                    last_action=self.last_action,
                )

                # action, reasoning = get_llm_action(prompt, "gemini")
                action, reasoning = get_llm_action(prompt, model="gemini")
                print(f"\nTurn {self.turn}")
                print(f"HP:{self.hp}, fuel:{self.fuel}, score:{self.score}")
                print(board_str)
                print(f"Action: {action}")

                # Process action
                if action == "FIRE":
                    self.fire_missile()
                elif action in ["LEFT", "RIGHT"]:
                    self.move_jet(action)

                self.last_action = action
                self.scroll_river()
                self.check_collisions()
                self.update_game_state()

                # Log state
                game_log = {
                    "input": prompt,
                    "output": action,
                    "turn": self.turn,
                    "reasoning": reasoning,
                    "score": self.score,
                    "hp": self.hp,
                    "fuel": self.fuel,
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
......E...........
........E.........
...E..............
.....+.....E..E...
..........E.......
..+..+............
.......+..........
..........+.......
..S...............
·····BB····BB·····
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run RiverRaid game")
    parser.add_argument("--output", type=str, default="riverraid_log.json")
    args = parser.parse_args()

    game = RiverRaidGame()
    game.play(args.output)

import argparse
import collections
import json
import random
from llm import get_llm_action

# Tunable params
RANDOM_MOVE = 0.3
BOMB_PROBABILITY = 0.2
# Initial game setup
grid = """..................
......E...........
........E.........
...E..............
...........E..E...
..........E.......
..................
..................
..................
..S...............
·····BB····BB·····
"""

airraid_prompt = """You are a defender in the AirRaid game. Game elements:
S - Your ship (moves horizontally)
E - Enemy saucers
! - Your missiles
* - Enemy bombs
B - Protected buildings
. - Empty space

Goal: Protect both buildings from bombs using LEFT/RIGHT movement and FIRE missiles.
Lose condition: Both buildings destroyed.

Rules:
1. Move with LEFT/RIGHT
2. FIRE shoots upward missile
3. In each turn, enemy saucers might:
    a. Drop bombs that destroy buildings
    b. Randomly move to left or right by one column
4. bombs moves down by 1 row each turn, if it hits the building, the building lose 20% HP
5. Missiles destroy enemies and bombs
6. Score points for hits

Action Space: NOOP, LEFT, RIGHT, FIRE
Your missiles will only hit enemy saucers or bombs if you are directly under them, firing missles to a empty colomn makes no sense, make sure you don't waste your missles.


Current Board:
{board_state}

Game Status:
Turn {turn} | Score: {score} | Buildings: {building_health}
Last Action: {last_action}

Your Action:
"""


class AirRaidGame:
    def __init__(self, grid_string):
        self.original_grid = grid_string
        self.board = self.parse_grid(grid_string)
        self.score = 0
        self.turn = 0
        self.history_board = []
        self.building_health = {"left": 100, "right": 100}
        self.last_action = "NOOP"
        self.game_over = False

    def parse_grid(self, grid_str):
        """Convert grid string to game state dict"""
        grid = [list(line) for line in grid_str.strip().split("\n")]
        state = {
            "ship": None,
            "enemies": [],
            "missiles": [],
            "bombs": [],
            "buildings": [],
            "walls": [],
        }

        for y, row in enumerate(grid):
            for x, char in enumerate(row):
                pos = (x, y)
                if char == "S":
                    state["ship"] = pos
                elif char == "E":
                    state["enemies"].append(pos)
                elif char == "!":
                    state["missiles"].append(pos)
                elif char == "*":
                    state["bombs"].append(pos)
                elif char == "B":
                    state["buildings"].append(pos)
                elif char == "#":
                    state["walls"].append(pos)
        return state

    def grid_to_string(self):
        """Render current state as grid string"""
        grid = [["." for _ in range(20)] for _ in range(11)]

        # Draw elements
        # print(self.board)
        for x, y in self.board["walls"]:
            # print(f"x: {x}, y:{y}")
            grid[y][x] = "#"
        for x, y in self.board["buildings"]:
            grid[y][x] = "B"
        for x, y in self.board["enemies"]:
            grid[y][x] = "E"
        for x, y in self.board["missiles"]:
            grid[y][x] = "!"
        for x, y in self.board["bombs"]:
            grid[y][x] = "*"
        if self.board["ship"]:
            x, y = self.board["ship"]
            grid[y][x] = "S"

        return "\n".join(" ".join(row) for row in grid)

    def move_ship(self, action):
        """Process player action"""
        if not self.board["ship"]:
            return False

        x, y = self.board["ship"]
        if action == "LEFT" and x > 0:
            new_pos = (x - 1, y)
        elif action == "RIGHT" and x < 19:
            new_pos = (x + 1, y)
        else:
            return False

        if new_pos not in self.board["walls"]:
            self.board["ship"] = new_pos
            return True
        return False

    def fire_missile(self):
        """Create new missile above ship"""
        if self.board["ship"]:
            x, y = self.board["ship"]
            if y > 0:
                self.board["missiles"].append((x, y - 1))
                return True
        return False

    def update_entities(self):
        """Move missiles/bombs and check collisions"""
        # Missiles move up
        new_missiles = []
        for x, y in self.board["missiles"]:
            if y > 0 and (x, y - 1) not in self.board["walls"]:
                new_pos = (x, y - 1)
                # Check hits
                if new_pos in self.board["enemies"]:
                    self.score += 10
                    self.board["enemies"].remove(new_pos)
                elif new_pos in self.board["bombs"]:
                    self.score += 5
                    self.board["bombs"].remove(new_pos)
                else:
                    new_missiles.append(new_pos)
        self.board["missiles"] = new_missiles

        # Bombs move down
        new_bombs = []
        for x, y in self.board["bombs"]:
            if y < 10 and (x, y + 1) not in self.board["walls"]:
                new_pos = (x, y + 1)
                # Check building hits
                if new_pos in self.board["buildings"]:
                    if x < 10 and self.building_health["left"] > 0:
                        self.building_health["left"] -= 20
                    else:
                        if self.building_health["right"] >= 0:
                            self.building_health["right"] -= 20
                else:
                    new_bombs.append(new_pos)
        self.board["bombs"] = new_bombs

    def enemy_actions(self):
        """Enemy AI: Move and drop bombs"""
        for enemy in list(self.board["enemies"]):
            # Random movement
            if random.random() < RANDOM_MOVE:
                dx = random.choice([-1, 0, 1])
                new_x = enemy[0] + dx
                if 0 <= new_x < 20 and (new_x, enemy[1]) not in self.board["walls"]:
                    self.board["enemies"].remove(enemy)
                    self.board["enemies"].append((new_x, enemy[1]))

            # Drop bombs
            if random.random() < BOMB_PROBABILITY:
                self.board["bombs"].append((enemy[0], enemy[1] + 1))

    def check_game_over(self):
        """Check win/lose conditions"""
        if self.building_health["left"] <= 0 and self.building_health["right"] <= 0:
            self.game_over = True
            return True
        return False

    def play(self, output_file):
        """Main game loop"""
        game_log = collections.defaultdict(list)
        game_count = 0

        while True:
            game_count += 1
            self.__init__(self.original_grid)

            while not self.game_over:
                self.turn += 1
                history_str = ""
                for idx, b in enumerate(self.history_board):
                    history_str += f"\n Turn {idx+1}\n{b}"
                board_str = self.grid_to_string()
                print(board_str)
                self.history_board.append(board_str)
                prompt = airraid_prompt.format(
                    board_state=board_str,
                    turn=self.turn,
                    score=self.score,
                    building_health=f"Left: {self.building_health['left']}% | Right: {self.building_health['right']}%",
                    last_action=self.last_action,
                )

                action, reasoning = get_llm_action(prompt, "gemini")
                print(f"action:{action}, reasoning:{reasoning}")
                print(
                    f"Health: Left: {self.building_health['left']}% | Right: {self.building_health['right']}%"
                )
                print(f"Score: {self.score}")

                # Process action
                if action == "FIRE":
                    self.fire_missile()
                elif action in ["LEFT", "RIGHT"]:
                    self.move_ship(action)

                self.last_action = action
                self.enemy_actions()
                self.update_entities()
                self.game_over = self.check_game_over()

                # Log game state
                game_log[game_count].append(
                    {
                        "input": prompt,
                        "output": action,
                        "turn": self.turn,
                        "reasoning": reasoning,
                        "score": self.score,
                        "buildings": dict(self.building_health),
                        "state": board_str,
                    }
                )

                with open(output_file, "w") as f:
                    json.dump(game_log, f, indent=2)

                if self.game_over:
                    print("Game Over! Final Score:", self.score)
                    break

parser = argparse.ArgumentParser(description="Run AirRaid game")
parser.add_argument("--output", type=str, default="airraid_log.json")
args = parser.parse_args()

game = AirRaidGame(grid)
game.play(args.output)

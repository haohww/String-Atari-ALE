import argparse
import collections
import random
import json

from llm import get_llm_action

# Tunable params
CAR_PROBABILITY = 0.08

chicken_prompt = """You are guiding a chicken across busy traffic lanes. Game elements:
K - Your chicken
C - Cars
> - Empty space on right moving lange
< - Empty space on left moving lange

Goal: Move the chicken UP or DOWN to cross 10 lanes of traffic without getting hit.
Score increases when reaching the top lane. Avoid cars!

Rules:
1. Cars move right in top 5 lanes (0-4) and left in bottom 5 lanes (5-9)
2. Each step, cars move one column in their direction
3. New cars appear at lane starts each turn
4. Colliding with a car ends the game
5. Reach the top lane (0) to score +1 and reset to bottom

Action Space: NOOP, UP, DOWN

Current Board:
{board_state}

Game Status:
Score: {score} | Current Lane: {current_lane}

Your Action:
"""


class ChickenCrossingGame:
    def __init__(self):
        self.grid_rows = 10  # 0-9 (0 is top)
        self.grid_cols = 20
        self.chicken_row = 9  # Start at bottom
        self.chicken_col = self.grid_cols // 2  # Center column
        self.score = 0
        self.game_over = False
        self.cars = collections.defaultdict(list)  # {lane: [columns]}
        self.current_step = 0

        # Initialize some initial cars
        for lane in range(10):
            for column in range(20):
                if random.random() < CAR_PROBABILITY:
                    self.cars[lane].append(column)

    def generate_cars_for_lane(self, lane):
        """Generate new cars for a lane with 30% probability"""
        if random.random() < CAR_PROBABILITY:
            if lane < 5:  # Right-moving lane
                self.cars[lane].append(self.grid_cols - 1)
            else:  # Left-moving lane
                self.cars[lane].append(0)

    def move_cars(self):
        """Update car positions based on lane direction"""
        new_cars = collections.defaultdict(list)

        for lane, columns in self.cars.items():
            for col in columns:
                if lane < 5:  # Move left
                    new_col = col - 1
                    if new_col >= 0:
                        new_cars[lane].append(new_col)
                else:  # Move right
                    new_col = col + 1
                    if new_col < self.grid_cols:
                        new_cars[lane].append(new_col)

        self.cars = new_cars

    def check_collision(self):
        """Check if chicken position matches any car in current lane"""
        return self.chicken_col in self.cars.get(self.chicken_row, [])

    def update_chicken_position(self, action):
        """Process UP/DOWN movement"""
        if action == "UP" and self.chicken_row > 0:
            self.chicken_row -= 1
        elif action == "DOWN" and self.chicken_row < self.grid_rows - 1:
            self.chicken_row += 1

    def check_scoring(self):
        """Handle scoring and reset position when reaching top"""
        if self.chicken_row == 0:
            self.score += 1
            self.chicken_row = 9  # Reset to bottom

    def grid_to_string(self):
        """Render current game state as ASCII grid"""
        grid = []
        for lane in range(self.grid_rows):
            if lane < 5:
                row = ["<"] * self.grid_cols
            else:
                row = [">"] * self.grid_cols
            # Add cars
            for col in self.cars.get(lane, []):
                row[col] = "C"
            # Add chicken if in current lane
            if lane == self.chicken_row:
                row[self.chicken_col] = "K"
            grid.append(" ".join(row))
        return "\n".join(grid)

    def play(self, output_file):
        """Main game loop"""
        game_dict = collections.defaultdict(list)
        game_count = 0
        while True:
            game_count += 1
            self.__init__()
            self.current_step
            game_log = collections.defaultdict(dict)

            while not self.game_over:
                self.current_step += 1

                # Generate new cars for all lanes
                for lane in range(self.grid_rows):
                    self.generate_cars_for_lane(lane)

                # Move existing cars
                self.move_cars()

                # Check for collisions before action
                if self.check_collision():
                    self.game_over = True
                    print(f"Game Over! Final Score: {self.score}")
                    break

                # Render board and get LLM action
                board_str = self.grid_to_string()
                prompt = chicken_prompt.format(
                    board_state=board_str,
                    score=self.score,
                    current_lane=self.chicken_row,
                )

                action, reasoning = get_llm_action(prompt)
                print(f"board:\n{board_str}")
                print(f"turn:{self.current_step} action:{action}")

                # Process action
                self.update_chicken_position(action)

                # Check collisions after movement
                if self.check_collision():
                    self.game_over = True

                # Handle scoring
                self.check_scoring()

                # Log game state
                game_log = {
                    "input": prompt,
                    "output": action,
                    "turn": self.current_step,
                    "reasoning": reasoning,
                    "score": self.score,
                    "current lane": self.chicken_row,
                    "state": board_str,
                }
                game_dict[game_count].append(game_log)

                # Write to output file
                with open(output_file, "w") as f:
                    json.dump(game_dict, f, indent=2)

                if self.game_over:
                    print(f"Game Over! Final Score: {self.score}")
                    break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Chicken Crossing game")
    parser.add_argument("--output", type=str, default="freeway_log.json")
    args = parser.parse_args()

    game = ChickenCrossingGame()
    game.play(args.output)

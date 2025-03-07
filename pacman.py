import argparse
import collections
import copy
import json
import random
from openai import OpenAI
import os

pacman_prompt = """You are a player in a Pac-Man game, where:

# represents walls (impassable),
G/C/R/A/S represents ghosts,
P represents Pac-Man,
x represents empty space (passable),
- represents regular pellets,
o represents power pellets.

Your task is to output an appropriate action from the given action space. Your goal is to score as high as possible without being touched by ghosts.
You can only eat ghosts within 10 moves after eating a power pellet. Every turn you can move one step. End your response with your decided next move.

**Game Rules**:
Control Pac-Man to move within the game interface, eating pellets and power pellets to score points.
After eating a power pellet, Pac-Man will enter power mode and can eat ghosts for the next 10 moves. Otherwise, colliding with a ghost results in death.
If Pac-Man moves into a wall, the move is invalid, and no action is token.

**Scoring Rules**:
Eating a regular pellet earns 1 point.
Eating a power pellet earns 5 points.
Eating a ghost earns 20 points.

**Action Space**:
LEFT, RIGHT, UP, DOWN

**Board State**:
{board_state}

**Current Info**:
This is Turn {turn}.
Your score is {score}. 
{power_mode_info}
**Your Output**:
"""


def get_llm_direction(current_state):
    """
    利用 OpenAI 的 ChatCompletion API，根据当前状态返回一个动作方向，
    模型只需返回 UP, DOWN, LEFT 或 RIGHT 之一，不包含其他文本。
    """

    client = OpenAI(
        base_url="https://aihubmix.com/v1",
        api_key=os.environ["apikey"],
    )

    messages = [{"role": "user", "content": current_state}]

    try:
        response = client.chat.completions.create(
            model="DeepSeek-R1",
            messages=messages,
        )
        print(f"response: {response}")
        direction = response.choices[0].message.content.strip().upper()
        resoning_content = response.choices[0].message.reasoning_content.strip()
        print(f"LLM 决策：{direction}")
        # print(f"LLM 决策理由：{resoning_content}")
    except Exception as e:
        print(f"调用错误: {e}")
        direction = "UP"  # 如果出错，默认返回 UP
        resoning_content = ""
    return direction, resoning_content


class PacManGame:
    def __init__(self, grid_string):
        # 保存初始地图字符串，便于后续重置
        self.original_grid_string = grid_string
        self.board_state = self.board_grid_string_to_dict(grid_string)
        self.score = 0
        self.power_mode_steps = 0  # 吃能量豆后的强力模式步数
        self.last_pacman_direction = None  # 记录上一次 Pac-Man 的移动方向
        self.game_over = False  # 游戏结束标志

        # 如果 grid_string 中包含鬼魂，则取第一个位置作为鬼魂出生点
        if self.board_state["ghost_positions"]:
            spawn_point = self.board_state["ghost_positions"][0]
        else:
            spawn_point = (10, 9)  # 默认出生点

        self.ghost_spawn_point = spawn_point
        # 生成 4 个不同类型的鬼魂
        self.ghosts = [
            {
                "position": spawn_point,
                "type": "chase",
                "alive": True,
                "respawn_timer": 0,
            },
            {
                "position": spawn_point,
                "type": "random",
                "alive": True,
                "respawn_timer": 0,
            },
            {
                "position": spawn_point,
                "type": "ambush",
                "alive": True,
                "respawn_timer": 0,
            },
            {
                "position": spawn_point,
                "type": "scatter",
                "alive": True,
                "respawn_timer": 0,
            },
        ]
        # 从地图中移除初始的鬼魂标记（由我们自己管理）
        self.board_state["ghost_positions"] = []

    def reset_game(self):
        """重置游戏，恢复到初始状态"""
        print("\n====================")
        print("游戏重置！")
        print("====================\n")
        self.__init__(self.original_grid_string)

    def flip_y(self, y):
        """使坐标原点在左下角"""
        return 16 - y  # 适用于 17x21 网格

    def board_grid_string_to_dict(self, grid_string):
        """将字符串形式的 grid board 转换为字典形式"""
        board_state = {
            "pacman_position": None,
            "ghost_positions": [],
            "pellet_positions": [],
            "power_pellet_positions": [],
            "walls": [],
            "action_space": ["LEFT", "RIGHT", "UP", "DOWN"],
        }

        grid = [line.split(" ") for line in grid_string.strip().split("\n")]
        rows, cols = len(grid), len(grid[0])

        def flip_y(y):
            return rows - 1 - y

        for y in range(rows):
            for x in range(cols):
                original_y = flip_y(y)

                if grid[y][x] == "#":
                    board_state["walls"].append((x, original_y))
                elif grid[y][x] == "-":
                    board_state["pellet_positions"].append((x, original_y))
                elif grid[y][x] == "o":
                    board_state["power_pellet_positions"].append((x, original_y))
                elif grid[y][x] == "G":
                    board_state["ghost_positions"].append((x, original_y))
                elif grid[y][x] == "P":
                    board_state["pacman_position"] = (x, original_y)

        return board_state

    def board_dict_to_grid_string(self):
        """显示当前游戏状态"""
        grid_size = (21, 17)
        grid = [["x"] * grid_size[0] for _ in range(grid_size[1])]

        # 绘制墙壁、豆子、能量豆
        for x, y in self.board_state["walls"]:
            grid[self.flip_y(y)][x] = "#"
        for x, y in self.board_state["pellet_positions"]:
            grid[self.flip_y(y)][x] = "-"
        for x, y in self.board_state["power_pellet_positions"]:
            grid[self.flip_y(y)][x] = "o"

        # 定义不同类型鬼魂对应的显示字符
        ghost_symbols = {
            "chase": "C",  # Blinky
            "random": "R",  # Pinky
            "ambush": "A",  # Inky
            "scatter": "S",  # Clyde
        }
        # 绘制存活的鬼魂，使用对应符号而不是统一的 "G"
        for ghost in self.ghosts:
            if ghost["alive"]:
                x, y = ghost["position"]
                symbol = ghost_symbols.get(ghost["type"], "G")
                grid[self.flip_y(y)][x] = symbol

        # 绘制 Pac-Man
        x, y = self.board_state["pacman_position"]
        grid[self.flip_y(y)][x] = "P"

        return "\n".join(" ".join(row) for row in grid)

    def move_pacman(self, direction):
        """Pac-Man 移动逻辑"""
        x, y = self.board_state["pacman_position"]
        move_map = {"UP": (0, 1), "DOWN": (0, -1), "LEFT": (-1, 0), "RIGHT": (1, 0)}

        if direction not in move_map:
            return False  # 无效输入不变

        dx, dy = move_map[direction]
        new_x, new_y = x + dx, y + dy

        if (new_x, new_y) in self.board_state["walls"]:
            return False  # 撞墙不动

        # 记录 Pac-Man 的移动方向（用于“埋伏型”鬼魂预测）
        self.last_pacman_direction = direction

        # 检查是否与鬼魂碰撞（遍历所有存活的鬼魂）
        for ghost in self.ghosts:
            if ghost["alive"] and ghost["position"] == (new_x, new_y):
                if self.power_mode_steps > 0:
                    print("\n👻 你吃掉了一个鬼魂！+20 分！")
                    self.score += 20
                    ghost["alive"] = False
                    ghost["respawn_timer"] = 20  # 复活倒计时 20 步
                else:
                    print("\n💀 Pac-Man 被鬼魂吃掉了！游戏结束，重置游戏！💀")
                    self.game_over = True
                    return False

        # 吃豆子
        if (new_x, new_y) in self.board_state["pellet_positions"]:
            self.board_state["pellet_positions"].remove((new_x, new_y))
            self.score += 1
        elif (new_x, new_y) in self.board_state["power_pellet_positions"]:
            self.board_state["power_pellet_positions"].remove((new_x, new_y))
            self.score += 5
            self.power_mode_steps = 10  # 进入强力模式 10 步

        # 更新 Pac-Man 位置
        self.board_state["pacman_position"] = (new_x, new_y)
        return True

    def move_ghosts(self):
        """鬼魂 AI 逻辑：根据各自类型选择移动策略，同时处理复活机制"""
        pacman_x, pacman_y = self.board_state["pacman_position"]
        move_options = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        move_map = {"UP": (0, 1), "DOWN": (0, -1), "LEFT": (-1, 0), "RIGHT": (1, 0)}

        # 处理鬼魂复活倒计时
        for ghost in self.ghosts:
            if not ghost["alive"]:
                if ghost["respawn_timer"] > 0:
                    ghost["respawn_timer"] -= 1
                if ghost["respawn_timer"] <= 0:
                    ghost["alive"] = True
                    ghost["position"] = self.ghost_spawn_point

        # 定义曼哈顿距离函数
        manhattan = lambda pos, target: abs(pos[0] - target[0]) + abs(
            pos[1] - target[1]
        )

        # 逐个处理每个存活的鬼魂
        for ghost in self.ghosts:
            if not ghost["alive"]:
                continue

            ghost_x, ghost_y = ghost["position"]
            possible_moves = []
            for dx, dy in move_options:
                new_pos = (ghost_x + dx, ghost_y + dy)
                if new_pos not in self.board_state["walls"]:
                    possible_moves.append(new_pos)
            if not possible_moves:
                continue

            chosen_move = None
            ghost_type = ghost["type"]

            if self.power_mode_steps > 20:  ##去除强力模式设定
                # 强力模式下，鬼魂倾向于远离 Pac-Man（50% 概率），否则随机
                if ghost_type in ["chase", "ambush", "scatter"]:
                    prob = 0.5
                    if random.random() < prob:
                        possible_moves.sort(
                            key=lambda pos: -manhattan(pos, (pacman_x, pacman_y))
                        )
                        chosen_move = possible_moves[0]
                    else:
                        chosen_move = random.choice(possible_moves)
                elif ghost_type == "random":
                    chosen_move = random.choice(possible_moves)
            else:
                # 正常模式下，不同类型采取不同策略
                if ghost_type == "chase":
                    prob = 0.7
                    if random.random() < prob:
                        possible_moves.sort(
                            key=lambda pos: manhattan(pos, (pacman_x, pacman_y))
                        )
                        chosen_move = possible_moves[0]
                    else:
                        chosen_move = random.choice(possible_moves)
                elif ghost_type == "random":
                    chosen_move = random.choice(possible_moves)
                elif ghost_type == "ambush":
                    # 利用 Pac-Man 上一次的移动方向预测下一步位置
                    if self.last_pacman_direction in move_map:
                        dx_pred, dy_pred = move_map[self.last_pacman_direction]
                        predicted = (pacman_x + dx_pred, pacman_y + dy_pred)
                        # 如果预测位置为墙，则退回使用 Pac-Man 当前位置
                        if predicted in self.board_state["walls"]:
                            predicted = (pacman_x, pacman_y)
                    else:
                        predicted = (pacman_x, pacman_y)
                    prob = 0.7
                    if random.random() < prob:
                        possible_moves.sort(key=lambda pos: manhattan(pos, predicted))
                        chosen_move = possible_moves[0]
                    else:
                        chosen_move = random.choice(possible_moves)
                elif ghost_type == "scatter":
                    # 散开目标点设为左上角 (0, 16)
                    scatter_target = (0, 16)
                    prob = 0.7
                    if random.random() < prob:
                        possible_moves.sort(
                            key=lambda pos: manhattan(pos, scatter_target)
                        )
                        chosen_move = possible_moves[0]
                    else:
                        chosen_move = random.choice(possible_moves)

            if not chosen_move:
                chosen_move = random.choice(possible_moves)

            # 检查鬼魂移动后是否碰到 Pac-Man
            if chosen_move == (pacman_x, pacman_y):
                if self.power_mode_steps > 0:
                    print("\n👻 你吃掉了一个鬼魂！+20 分！")
                    self.score += 20
                    ghost["alive"] = False
                    ghost["respawn_timer"] = 10
                    continue  # 鬼魂被吃，不更新位置
                else:
                    print("\n💀 Pac-Man 被鬼魂吃掉了！游戏结束，重置游戏！💀")
                    self.game_over = True
                    return

            ghost["position"] = chosen_move

    def play(self, file_name):
        """开始游戏循环，使用 OpenAI API 与 LLM 交互。
        当 Pac-Man 被吃或所有豆子被吃完时，自动重置游戏。
        """
        # 外层循环：每局游戏结束后重置
        game_dict = collections.defaultdict(list)
        game_count = 0

        while True:
            turn_count = 0
            game_count += 1
            self.game_over = False

            # 内层循环：单局游戏
            while True:
                turn_count += 1
                board_state = self.board_dict_to_grid_string()
                if self.power_mode_steps > 0:
                    power_mode_info = (
                        f"⚡ Power mode remaining: {self.power_mode_steps} moves."
                    )
                else:
                    power_mode_info = f"⚡ Power mode: off."
                print("\n当前游戏状态：")
                print(board_state)
                print(f"\n🎯 当前得分: {self.score}")
                print(power_mode_info)
                current_state = pacman_prompt.format(
                    board_state=board_state,
                    turn=turn_count,
                    score=self.score,
                    power_mode_info=power_mode_info,
                )
                hitory_score = copy.deepcopy(self.score)

                # 获取 LLM 返回的方向
                direction, reasoning_content = get_llm_direction(current_state)
                print(f"LLM 返回的方向: {direction}")

                # 如果返回的方向不合法，则忽略本次决策
                if direction not in ["UP", "DOWN", "LEFT", "RIGHT"]:
                    continue

                move_valid = self.move_pacman(direction)

                cell = {
                    "input": current_state,
                    "output": direction,
                    "reasoning_content": reasoning_content,
                    "turn": turn_count,
                    "score": self.score,
                    "power_mode_info": power_mode_info,
                }
                game_dict[game_count].append(cell)
                with open(file_name, "w", encoding="utf-8") as f:
                    json.dump(game_dict, f, ensure_ascii=False, indent=4)

                if self.game_over:
                    break  # Pac-Man 被吃掉，退出当前局

                if self.power_mode_steps > 0:
                    self.power_mode_steps -= 1  # 强力模式步数减少

                self.move_ghosts()

                if self.game_over:
                    break  # 鬼魂移动中碰撞，退出当前局

                # 检查是否所有豆子都已吃完
                if (
                    not self.board_state["pellet_positions"]
                    and not self.board_state["power_pellet_positions"]
                ):
                    print("\n所有豆子已被吃完！游戏结束，重置游戏！")
                    break

            # 本局结束，调用重置方法重新开始游戏
            self.reset_game()


# **初始化游戏**（注意：初始地图中只有一个 G，代表所有鬼魂的出生点）
grid_string = """# # # # # # # # # # # # # # # # # # # # #
# - - - - - - x # - - - # x - - - - - - #
# o # x # x # x # x # x # x # x # x # o #
# - - - # - - - - - x - - - - - # - - - #
# # x # # x # # # x # x # # # x # # x # #
# - - - - - - x # - - - # x - - - - - - #
# x # x # x # x # x # x # x # x # x # x #
# - - - # - - - - x G x - - - - # - - - #
# # x # # x # # # x # x # # # x # # x # #
# - - - - - - x # - - - # x - - - - - - #
# x # x # x # x # x # x # x # x # x # x #
# - - - # - - - - - x - - - - - # - - - #
# # x # # x # # # x # x # # # x # # x # #
# - - - - - - x # - P - # x - - - - - - #
# o # x # x # x # x # x # x # x # x # o #
# - - - # - - - - - x - - - - - # - - - #
# # # # # # # # # # # # # # # # # # # # #"""

# 开始游戏
parser = argparse.ArgumentParser(description="Run the Pac-Man game.")
parser.add_argument(
    "--file_name",
    type=str,
    help="The file name to use for playing the game.",
    default="pacman.json",
)

args = parser.parse_args()
file_name = args.file_name
game = PacManGame(grid_string)
game.play(file_name)

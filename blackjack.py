import json
import random
import collections
import argparse
from llm import get_llm_action

STARTING_BALANCE = 10

class BlackjackGame:
    def __init__(self):
        self.round_number = 0
        self.deck = []
        self.player_hand = []
        self.dealer_hand = []
        self.current_bet = 10
        self.balance = STARTING_BALANCE
        self.game_over = False
        self.player_turn = True
        self.initialize_deck()
        self.shuffle_deck()
        self.deal_initial_cards()

    def initialize_deck(self):
        values = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        self.deck = values * 4  # 4 suits

    def shuffle_deck(self):
        random.shuffle(self.deck)

    def deal_initial_cards(self):
        # Ensure deck has enough cards, reshuffle if needed
        if len(self.deck) < 4:
            self.initialize_deck()
            self.shuffle_deck()
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]

    def calculate_hand_value(self, hand):
        value = 0
        aces = 0
        for card in hand:
            if card in ['J', 'Q', 'K']:
                value += 10
            elif card == 'A':
                aces += 1
                value += 11
            elif card == '10':
                value += 10
            else:
                value += int(card)
        # Adjust for aces if over 21
        while value > 21 and aces > 0:
            value -= 10
            aces -= 1
        return value

    def render_card(self, card, hidden=False):
        if hidden:
            return ['.--.', '|? |', '`--`']
        else:
            # Adjust spacing for 10
            if card == '10':
                return ['.--.', f'|{card}|', '`--`']
            else:
                return ['.--.', f'|{card} |', '`--`']

    def render_hand(self, hand, hide_dealer_card=False):
        lines = ['', '', '']
        for i, card in enumerate(hand):
            if i == 1 and hide_dealer_card and self.player_turn:
                card_lines = self.render_card(card, hidden=True)
            else:
                card_lines = self.render_card(card)
            for j in range(3):
                lines[j] += card_lines[j] + ' '
        return '\n'.join(lines)

    def get_game_state_prompt(self):
        player_value = self.calculate_hand_value(self.player_hand)
        dealer_visible = self.calculate_hand_value([self.dealer_hand[0]])

        prompt = f"""
You are playing Blackjack. Current status:

Dealer's Hand (Visible: {dealer_visible}):
{self.render_hand(self.dealer_hand, hide_dealer_card=True)}


Your Hand (Total: {player_value}):
{self.render_hand(self.player_hand)}


Current Bet: ${self.current_bet} | Balance: ${self.balance}

Rules:
- Aim to reach 21 without busting.
- Dealer shows one card, hits until 17+.
- Aces count as 1 or 11.
- Blackjack (A + 10/J/Q/K) pays 3:2.

Actions:
NOOP: Stay with current hand.
FIRE: Hit (request another card).
UP: Increase bet by $1 (max balance).
DOWN: Decrease bet by $1 (min $1).

Choose action (NOOP/FIRE/UP/DOWN):"""

        return prompt

    def process_action(self, action):
        if action == "FIRE":
            if len(self.deck) == 0:
                self.initialize_deck()
                self.shuffle_deck()
            self.player_hand.append(self.deck.pop())
            if self.calculate_hand_value(self.player_hand) > 21:
                self.game_over = True
        elif action == "UP":
            if self.current_bet < self.balance:
                self.current_bet += 1
        elif action == "DOWN":
            if self.current_bet > 1:
                self.current_bet -= 1
        elif action == "NOOP":
            self.player_turn = False

    def dealer_play(self):
        while self.calculate_hand_value(self.dealer_hand) < 17:
            if len(self.deck) == 0:
                self.initialize_deck()
                self.shuffle_deck()
            self.dealer_hand.append(self.deck.pop())

    def determine_outcome(self):
        player_value = self.calculate_hand_value(self.player_hand)
        dealer_value = self.calculate_hand_value(self.dealer_hand)

        if player_value > 21:
            return "dealer"
        if dealer_value > 21:
            return "player"
        if player_value == dealer_value:
            return "push"
        return "player" if player_value > dealer_value else "dealer"

    def play_round(self):
        while self.player_turn and not self.game_over:
            prompt = self.get_game_state_prompt()
            # player_value = self.calculate_hand_value(self.player_hand)
            # dealer_visible = self.calculate_hand_value([self.dealer_hand[0]])
            # print(f"dealear ")
            print(prompt)
            action, reasoning = get_llm_action(prompt, model="gemini")
            print(f"Action: {action}\nReasoning: {reasoning}")
            
            game_log = {
                "input": prompt,
                "output": action,
                "reasoning_content": reasoning,
                "turn": self.round_number,
                "balance": self.balance,
                "dealer_hand": self.dealer_hand,
                "play_hand": self.player_hand,
            }

            self.process_action(action)
            if self.calculate_hand_value(self.player_hand) > 21 or action == "NOOP":
                self.game_over = True
                

        if self.game_over and self.calculate_hand_value(self.player_hand) > 21:
            print("Bust! You lose this round.")
            self.balance -= self.current_bet
            return game_log

        self.player_turn = False
        self.dealer_play()
        result = self.determine_outcome()

        # Check for Blackjack (A + 10/J/Q/K in first two cards)
        player_blackjack = (len(self.player_hand) == 2 and \
                            (('A' in self.player_hand and '10' in self.player_hand) or \
                             ('A' in self.player_hand and any(c in ['J','Q','K'] for c in self.player_hand))))

        if result == "player":
            if player_blackjack:
                payout = int(self.current_bet * 1.5)
                print(f"Blackjack! You win ${payout}!")
                self.balance += payout
            else:
                print(f"You win ${self.current_bet}!")
                self.balance += self.current_bet
        elif result == "dealer":
            print(f"Dealer wins. You lose ${self.current_bet}.")
            self.balance -= self.current_bet
        else:
            print("Push. Bet returned.")
        print(f"dealer hand: {self.dealer_hand}\nyour hand: {self.player_hand}\n")
        
        print(f"New balance: ${self.balance}\n")
        return game_log

    def play(self, file_name):
        game_dict = collections.defaultdict(list)
        game_count = 0
        while True:
            game_count += 1
            self.__init__()
            
            print(f"Welcome to Blackjack! Starting balance: {STARTING_BALANCE}$")
            while self.balance > 0:
                log = self.play_round()
                game_dict[game_count].append(log)
                with open(file_name, 'w', encoding='utf-8') as f:
                    json.dump(game_dict, f, ensure_ascii=False, indent=4)

                # Reset for new round without affecting balance
                self.round_number += 1
                self.player_hand = []
                self.dealer_hand = []
                self.initialize_deck()
                self.shuffle_deck()
                self.deal_initial_cards()
                self.game_over = False
                self.player_turn = True
                self.current_bet = 10  # Reset bet for new round
                self.balance = max(0, self.balance)  # Prevent negative if last round lost
            print(f"Game over. Final balance: ${self.balance}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Pac-Man game.")
    parser.add_argument("--file_name", type=str, help="The file name to use for playing the game.", default="blackjack_log.json", required=False)

    args = parser.parse_args()
    file_name = args.file_name
    game = BlackjackGame()
    game.play(file_name)
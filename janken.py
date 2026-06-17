import random

CHOICES = ["グー", "チョキ", "パー"]
WINS_AGAINST = {
    "グー": "チョキ",
    "チョキ": "パー",
    "パー": "グー",
}

ART = {
    "グー": [
        "    _____",
        "---'   ____)",
        "      (_____)",
        "      (_____)",
        "      (____)",
        "---.__(___)  ",
    ],
    "チョキ": [
        "    _____",
        "---'   ____)____",
        "          ______)",
        "       __________)",
        "      (____)",
        "---.__(___)      ",
    ],
    "パー": [
        "    _______",
        "---'    ______)____",
        "           _______)",
        "          ________)",
        "         _______)",
        "---.__________)    ",
    ],
}

def print_hands(player, cpu):
    player_art = ART[player]
    cpu_art_raw = ART[cpu]

    # Mirror CPU art (flip horizontally) so hands face each other
    cpu_art = [line[::-1] for line in cpu_art_raw]

    width = 22
    print()
    for p_line, c_line in zip(player_art, cpu_art):
        print(f"  {p_line:<{width}}    {c_line}")
    print(f"  {'あなた: ' + player:<{width}}    CPU: {cpu}")
    print()

def get_result(player, cpu):
    if player == cpu:
        return "あいこ"
    elif WINS_AGAINST[player] == cpu:
        return "あなたの勝ち！"
    else:
        return "CPUの勝ち！"

def main():
    print("=== じゃんけんゲーム ===")
    print("終了するには Ctrl+C を押してください\n")

    wins = losses = draws = 0

    while True:
        print("手を選んでください:")
        for i, c in enumerate(CHOICES, 1):
            print(f"  {i}. {c}")

        try:
            choice = input("番号を入力 (1-3): ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if choice not in ("1", "2", "3"):
            print("1〜3の番号を入力してください\n")
            continue

        player = CHOICES[int(choice) - 1]
        cpu = random.choice(CHOICES)

        print_hands(player, cpu)
        result = get_result(player, cpu)
        print(f"結果: {result}\n")

        if result == "あなたの勝ち！":
            wins += 1
        elif result == "CPUの勝ち！":
            losses += 1
        else:
            draws += 1

    print(f"\n=== 結果 ===")
    print(f"勝ち: {wins}  負け: {losses}  あいこ: {draws}")
    total = wins + losses + draws
    if total > 0:
        print(f"勝率: {wins / total * 100:.1f}%")

if __name__ == "__main__":
    main()

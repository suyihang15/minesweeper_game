"""
扫雷小游戏 - Minesweeper
========================
使用 Python tkinter 实现的经典扫雷游戏。

特性:
- 三种难度：初级(9x9, 10雷)、中级(16x16, 40雷)、高级(16x30, 99雷)
- 首次点击保证安全（点击后再布雷）
- 空格自动展开（Flood Fill）
- 右键循环切换：无标记 → 旗子(🚩) → 问号(❓)
- Chord 双击展开：点击已翻开数字格，若周围旗子数匹配则自动翻开剩余格子
- 左键点击已插旗格子可快速解旗
- Chord 数量不匹配时金色闪烁反馈
- 计时器 & 剩余雷数显示
- 胜利烟花庆祝动画
- 胜利/失败状态显示
"""

import tkinter as tk
from tkinter import messagebox
import math
import random
import time


class Minesweeper:
    """
    扫雷游戏主类

    核心数据结构
    ----------
    board[r][c]    : int   -1=地雷, 0~8=周围地雷数量
    revealed[r][c] : bool  是否已翻开
    flagged[r][c]  : int   0=无标记, 1=旗子, 2=问号
    buttons[r][c]  : Button 对应的 tkinter 按钮对象
    """

    # 难度配置: (行, 列, 雷数)
    LEVELS = {
        "初级": (9, 9, 10),
        "中级": (16, 16, 40),
        "高级": (16, 30, 99),
    }

    # 雷数 1~8 对应的显示颜色
    COLORS = {
        1: "#0000FF",
        2: "#008000",
        3: "#FF0000",
        4: "#000080",
        5: "#800000",
        6: "#008080",
        7: "#000000",
        8: "#808080",
    }

    # 8 方向偏移量 (dr, dc)
    _DIRS = [(-1, -1), (-1, 0), (-1, 1),
             (0, -1),           (0, 1),
             (1, -1),  (1, 0),  (1, 1)]

    def __init__(self, master):
        self.master = master
        self.master.title("扫雷")
        self.master.resizable(False, False)

        self.level = tk.StringVar(value="初级")
        self.rows, self.cols, self.mines_count = self.LEVELS[self.level.get()]

        self.game_over = False
        self.game_started = False
        self.first_click = True
        self.start_time = 0.0
        self.elapsed_time = 0

        self.build_ui()
        self.new_game()

    # ───────────────────── 界面构建 ─────────────────────

    def build_ui(self):
        """构建顶部控制栏和游戏网格容器"""
        top_frame = tk.Frame(self.master)
        top_frame.pack(pady=5)

        tk.Label(top_frame, text="难度:").pack(side=tk.LEFT, padx=5)
        level_menu = tk.OptionMenu(
            top_frame, self.level, *self.LEVELS.keys(),
            command=self.change_level,
        )
        level_menu.config(width=6)
        level_menu.pack(side=tk.LEFT, padx=5)

        self.mine_label = tk.Label(
            top_frame, text=f"💣 {self.mines_count}",
            font=("Arial", 14, "bold"),
        )
        self.mine_label.pack(side=tk.LEFT, padx=20)

        self.reset_btn = tk.Button(
            top_frame, text="😊", font=("Arial", 16),
            width=3, command=self.new_game,
        )
        self.reset_btn.pack(side=tk.LEFT, padx=10)

        self.timer_label = tk.Label(
            top_frame, text="⏱ 0",
            font=("Arial", 14, "bold"),
        )
        self.timer_label.pack(side=tk.LEFT, padx=20)

        self.grid_frame = tk.Frame(self.master)
        self.grid_frame.pack(pady=5)

    def change_level(self, _=None):
        """难度切换回调"""
        self.rows, self.cols, self.mines_count = self.LEVELS[self.level.get()]
        self.mine_label.config(text=f"💣 {self.mines_count}")
        self.new_game()

    def new_game(self):
        """初始化/重置全部游戏状态与界面"""
        self.game_over = False
        self.game_started = False
        self.first_click = True
        self.elapsed_time = 0
        self.timer_label.config(text="⏱ 0")
        self.reset_btn.config(text="😊")

        rows, cols = self.rows, self.cols
        self.board = [[0] * cols for _ in range(rows)]
        self.revealed = [[False] * cols for _ in range(rows)]
        self.flagged = [[0] * cols for _ in range(rows)]
        self.buttons = [[None] * cols for _ in range(rows)]

        # 销毁旧按钮
        for w in self.grid_frame.winfo_children():
            w.destroy()

        self.mine_label.config(text=f"💣 {self.mines_count}")

        # 创建按钮网格
        for r in range(rows):
            for c in range(cols):
                btn = tk.Button(
                    self.grid_frame,
                    width=2, height=1,
                    font=("Arial", 10, "bold"),
                    relief=tk.RAISED,
                    bg="#C0C0C0",
                )
                btn.grid(row=r, column=c, padx=0, pady=0)
                btn.bind("<Button-1>",
                         lambda e, row=r, col=c: self.on_left_click(row, col))
                btn.bind("<Button-3>",
                         lambda e, row=r, col=c: self.on_right_click(row, col))
                self.buttons[r][c] = btn

    # ─────────────── 地雷生成 ───────────────

    def place_mines(self, safe_row, safe_col):
        """
        随机布雷。

        保证 (safe_row, safe_col) 及其 3×3 邻域内没有地雷，
        使玩家首次点击永远不会踩雷。
        """
        rows, cols, mines = self.rows, self.cols, self.mines_count

        # 安全区域: 首次点击位置 + 8 个邻居
        safe_cells = set()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = safe_row + dr, safe_col + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    safe_cells.add((nr, nc))

        # 候选雷位（不在安全区域内的格子）
        candidates = [(r, c) for r in range(rows) for c in range(cols)
                       if (r, c) not in safe_cells]

        n_mines = min(mines, len(candidates))
        mine_positions = random.sample(candidates, n_mines) if n_mines > 0 else []

        for r, c in mine_positions:
            self.board[r][c] = -1

        # 计算每个非雷格子的周围雷数
        for r in range(rows):
            for c in range(cols):
                if self.board[r][c] == -1:
                    continue
                self.board[r][c] = self._count_adjacent_mines(r, c)

    def _count_adjacent_mines(self, row, col):
        """统计 (row, col) 8 邻域内的地雷数量"""
        count = 0
        for dr, dc in self._DIRS:
            nr, nc = row + dr, col + dc
            if 0 <= nr < self.rows and 0 <= nc < self.cols:
                if self.board[nr][nc] == -1:
                    count += 1
        return count

    def _update_mine_counter(self):
        """根据当前旗子数更新剩余雷数显示"""
        flags = sum(1 for r in range(self.rows) for c in range(self.cols)
                    if self.flagged[r][c] == 1)
        self.mine_label.config(text=f"💣 {self.mines_count - flags}")

    # ───────────── 左 / 右键处理 ─────────────

    def on_left_click(self, row, col):
        """
        左键点击:
        1. 已插旗的格子 → 快速解旗（省去右键循环）
        2. 已翻开的数字格 → 触发 Chord 双击展开
        3. 已标记问号/已翻开的空格 → 忽略
        4. 未翻开的格子 → 翻开
        """
        if self.game_over:
            return

        # 快速解旗：左键点击已插旗的格子
        if self.flagged[row][col] == 1:
            self.flagged[row][col] = 0
            self.buttons[row][col].config(text="")
            self._update_mine_counter()
            return

        # Chord: 点击已翻开的数字格
        if self.revealed[row][col] and self.board[row][col] > 0:
            self._do_chord(row, col)
            return

        # 问号标记的、已翻开的 → 不处理
        if self.flagged[row][col] != 0 or self.revealed[row][col]:
            return

        # 首次点击 → 布雷 + 启动计时器
        if self.first_click:
            self.first_click = False
            self.place_mines(row, col)
            self.game_started = True
            self.start_time = time.time()
            self.update_timer()

        if self.board[row][col] == -1:
            # 踩雷
            self.game_over = True
            self.reset_btn.config(text="😵")
            self.buttons[row][col].config(bg="#FF0000", text="💣")
            self._reveal_all_mines()
            return

        self._reveal_cell(row, col)

        if self._check_win():
            self.game_over = True
            self.reset_btn.config(text="😎")
            self._flag_all_mines()
            self._add_fireworks()
            self.master.after(800, lambda: messagebox.showinfo(
                "恭喜", f"你赢了！\n用时: {self.elapsed_time} 秒"))

    def on_right_click(self, row, col):
        """
        右键点击: 循环切换 无标记 → 旗子(🚩) → 问号(❓) → 无标记

        允许在首次左键点击前右键插旗，符合标准扫雷操作习惯。
        """
        if self.game_over or self.revealed[row][col]:
            return

        self.flagged[row][col] = (self.flagged[row][col] + 1) % 3
        btn = self.buttons[row][col]

        if self.flagged[row][col] == 1:
            btn.config(text="🚩", fg="#FF0000")
        elif self.flagged[row][col] == 2:
            btn.config(text="❓", fg="#0000FF")
        else:
            btn.config(text="")

        self._update_mine_counter()

    # ───────────── Chord 双击展开 ─────────────

    def _do_chord(self, row, col):
        """
        Chord 双击展开算法。

        若 (row, col) 是已翻开的数字格，且周围旗子数量 == 该数字，
        说明玩家已正确标记了全部相邻雷，此时自动翻开周围未翻开且未插旗的格子。
        如果标记错误，则翻开地雷导致游戏结束。
        若旗子数量不匹配，给出金色闪烁反馈（250ms）。
        """
        number = self.board[row][col]
        if number <= 0:
            return

        # 统计周围旗子数
        flag_count = 0
        for dr, dc in self._DIRS:
            nr, nc = row + dr, col + dc
            if 0 <= nr < self.rows and 0 <= nc < self.cols:
                if self.flagged[nr][nc] == 1:
                    flag_count += 1

        if flag_count != number:
            # 旗子数量不匹配 → 金色闪烁反馈
            btn = self.buttons[row][col]
            original_bg = btn.cget("bg")
            btn.config(bg="#FFD700")
            self.master.after(250, lambda: btn.config(bg=original_bg))
            return

        # 收集待翻开的邻居（避免在循环中直接翻开地雷）
        to_reveal = []
        mine_hit = False
        for dr, dc in self._DIRS:
            nr, nc = row + dr, col + dc
            if 0 <= nr < self.rows and 0 <= nc < self.cols:
                if not self.revealed[nr][nc] and self.flagged[nr][nc] != 1:
                    if self.board[nr][nc] == -1:
                        mine_hit = True
                    else:
                        to_reveal.append((nr, nc))

        if mine_hit:
            # 踩雷：不翻开任何安全格子，直接展示全部地雷
            self.game_over = True
            self.reset_btn.config(text="😵")
            self._reveal_all_mines()
            return

        # 安全：翻开所有相邻安全格
        for nr, nc in to_reveal:
            self._reveal_cell(nr, nc)

        if self._check_win():
            self.game_over = True
            self.reset_btn.config(text="😎")
            self._flag_all_mines()
            self._add_fireworks()
            self.master.after(800, lambda: messagebox.showinfo(
                "恭喜", f"你赢了！\n用时: {self.elapsed_time} 秒"))

    # ───────────── 翻开 / 展开格子 ─────────────

    def _reveal_cell(self, row, col):
        """
        翻开指定格子。

        若该格子周围雷数为 0（空格），则递归翻开其 8 邻域所有格子，
        使用深度优先展开，类似 Flood Fill 算法。
        旗子和问号标记的格子均受保护，不会被递归翻开。
        """
        if self.revealed[row][col] or self.flagged[row][col] != 0:
            return

        self.revealed[row][col] = True
        btn = self.buttons[row][col]
        btn.config(relief=tk.SUNKEN, bg="#D0D0D0")

        count = self.board[row][col]
        if count > 0:
            btn.config(text=str(count), fg=self.COLORS.get(count, "#000000"))
        elif count == 0:
            # 空格: 递归展开邻域
            btn.config(text="")
            for dr, dc in self._DIRS:
                nr, nc = row + dr, col + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    self._reveal_cell(nr, nc)

    def _reveal_all_mines(self):
        """失败时展示全部地雷位置，并标记错误旗子"""
        for r in range(self.rows):
            for c in range(self.cols):
                # 未标记的地雷 → 显示 💣
                if self.board[r][c] == -1 and self.flagged[r][c] != 1:
                    self.buttons[r][c].config(text="💣", relief=tk.SUNKEN,
                                              bg="#FFC0C0")
                # 标错旗子的位置 → 显示 ❌
                elif self.flagged[r][c] == 1 and self.board[r][c] != -1:
                    self.buttons[r][c].config(text="❌", relief=tk.SUNKEN,
                                              bg="#FFC0C0")

    def _flag_all_mines(self):
        """胜利时给所有地雷插上旗子"""
        for r in range(self.rows):
            for c in range(self.cols):
                if self.board[r][c] == -1:
                    self.buttons[r][c].config(text="🚩", fg="#FF0000")

    # ───────────── 胜负判定 & 计时器 ─────────────

    def _check_win(self):
        """
        胜利条件: 所有非雷格子均已翻开。

        时间复杂度 O(rows × cols)，对于标准最大棋盘 (16×30=480) 开销极小。
        """
        for r in range(self.rows):
            for c in range(self.cols):
                if self.board[r][c] != -1 and not self.revealed[r][c]:
                    return False
        return True

    def update_timer(self):
        """每秒更新一次计时器显示，游戏结束后自动停止"""
        if self.game_over or not self.game_started:
            return
        self.elapsed_time = int(time.time() - self.start_time)
        self.timer_label.config(text=f"⏱ {self.elapsed_time}")
        self.master.after(1000, self.update_timer)

    # ───────────── 胜利烟花动画 ─────────────

    def _add_fireworks(self):
        """
        胜利庆祝：多轮彩色烟花粒子动画。

        使用 tkinter Canvas 覆盖整个窗口，产生多个随机爆发的彩色粒子团，
        粒子受重力影响下落并逐渐缩小消失，最终自动销毁画布。
        """
        canvas = tk.Canvas(self.master, bg="", highlightthickness=0)
        canvas.place(x=0, y=0, relwidth=1, relheight=1)
        canvas.after(50, canvas.lift)

        colors = [
            "#FF0000", "#FFD700", "#00FF00", "#00BFFF",
            "#FF69B4", "#FFA500", "#7B68EE", "#00FF7F",
            "#FFFFFF", "#FF4500", "#00FFFF", "#FF1493",
        ]

        w = self.master.winfo_width()
        h = self.master.winfo_height()
        particles = []

        def create_burst(bx, by):
            """在 (bx, by) 位置产生一次烟花爆发"""
            for _ in range(30):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(2, 9)
                life = random.randint(18, 38)
                color = random.choice(colors)
                size = random.randint(3, 8)
                pid = canvas.create_oval(
                    bx - size, by - size, bx + size, by + size,
                    fill=color, outline=color, width=0,
                )
                particles.append({
                    "id": pid, "x": bx, "y": by,
                    "vx": speed * math.cos(angle),
                    "vy": speed * math.sin(angle) - 3,  # 初始向上偏移
                    "life": life, "max_life": life,
                    "size": size,
                })

        # 多轮爆发，时间错开
        def round1():
            for _ in range(4):
                bx = random.uniform(w * 0.1, w * 0.9)
                by = random.uniform(h * 0.1, h * 0.6)
                create_burst(bx, by)

        def round2():
            for _ in range(3):
                bx = random.uniform(w * 0.15, w * 0.85)
                by = random.uniform(h * 0.2, h * 0.7)
                create_burst(bx, by)

        self.master.after(100, round1)
        self.master.after(600, round2)
        self.master.after(1100, round2)

        def update():
            """逐帧更新粒子位置与大小"""
            for p in particles[:]:
                p["life"] -= 1
                if p["life"] <= 0:
                    canvas.delete(p["id"])
                    particles.remove(p)
                    continue

                # 物理运动：速度 + 重力
                p["x"] += p["vx"]
                p["y"] += p["vy"] + 0.25   # 重力加速度
                p["vy"] *= 0.94            # 空气阻力

                # 逐渐缩小（模拟淡出）
                alpha = p["life"] / p["max_life"]
                s = p["size"] * (0.3 + 0.7 * alpha)
                canvas.coords(
                    p["id"],
                    p["x"] - s, p["y"] - s,
                    p["x"] + s, p["y"] + s,
                )

            if particles:
                self.master.after(30, update)
            else:
                canvas.destroy()

        self.master.after(400, update)


def main():
    root = tk.Tk()
    Minesweeper(root)
    root.mainloop()


if __name__ == "__main__":
    main()

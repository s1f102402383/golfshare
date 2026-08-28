"""配車割り当てアルゴリズム。

NAVITIME API への依存をここには持ち込まず、
「所要時間の表」を入力として受け取る純粋な関数だけを置いている。
そのため API を呼ばずに単体でテスト・比較できる。

用語:
    cost_table: {(passenger.id, driver.id): 所要時間(分)} の辞書。
                経路が取得できなかった組み合わせは UNREACHABLE を入れる。
    seat      : 「ドライバー1人 × 定員1席」の単位。定員3の車は3席に展開する。
"""

import pulp


# 経路が取得できなかった組み合わせに入れる番兵値。
# 実在する所要時間より十分大きく、かつ後から「これは未取得だった」と判別できる。
UNREACHABLE = 999

# ILP で「1人を割り当てずに諦める」ことのコスト。
# UNREACHABLE より十分大きくして、乗せられる人は必ず乗せる方を優先させる。
UNASSIGNED_PENALTY = 10000


def _cost(cost_table, passenger, driver):
    return cost_table.get((passenger.id, driver.id), UNREACHABLE)


def assign_greedy(passengers, drivers, cost_table):
    """貪欲法（改善前の方式）。比較用に残してある。

    全ペアを所要時間の昇順に並べ、先頭から
    「その乗客が未割当」かつ「その車に空席あり」なら確定させる。

    計算量: O(P*D*log(P*D))
    欠点  : 各ペアを局所的にしか見ないため、合計時間が最適にならず、
            アクセスの良い車に人数が偏る。
    """
    pairs = []
    for passenger in passengers:
        for driver in drivers:
            pairs.append((_cost(cost_table, passenger, driver), passenger, driver))
    pairs.sort(key=lambda x: x[0])

    remaining = {driver.id: driver.car_capacity for driver in drivers}
    assignments = {driver.id: [] for driver in drivers}
    assigned = set()

    for minutes, passenger, driver in pairs:
        if passenger.id in assigned:
            continue
        if remaining[driver.id] <= 0:
            continue
        if minutes >= UNREACHABLE:
            # 経路不明の相手に無理やり乗せない
            continue
        assignments[driver.id].append((passenger, minutes))
        remaining[driver.id] -= 1
        assigned.add(passenger.id)

    unassigned = [p for p in passengers if p.id not in assigned]
    return assignments, unassigned


def _build_seats(drivers):
    """ドライバーを定員数だけ「席」に展開する。

    定員3のドライバーAは (A,0) (A,1) (A,2) という3席になる。
    こうすると「乗客 → 席」の1対1対応問題に変換でき、
    ハンガリアン法（linear_sum_assignment）がそのまま使える。
    """
    seats = []
    for driver in drivers:
        for seat_index in range(max(0, driver.car_capacity)):
            seats.append((driver, seat_index))
    return seats


def assign_hungarian(passengers, drivers, cost_table, balance_penalty=0):
    """ハンガリアン法による割り当て。合計所要時間を厳密に最小化する。

    balance_penalty (λ) は「同じ車の n 席目を使うコスト」を
    λ * seat_index だけ割り増しする係数。

        λ = 0  … 純粋に合計所要時間だけを最小化する（人数の偏りは考慮しない）
        λ > 0  … 2人目・3人目と詰めるほど高コストになるので人数が散る

    席ごとにコストを変えても行列の形は変わらないため、
    λ を入れても厳密解のまま解ける（近似ではない）ことがこの方式の利点。

    計算量: O(max(P, S)^3)  ※ S = 総座席数

    scipy はここでしか使わないため import を関数内に置いている。
    本番では ILP(PuLP) を使うので scipy を入れずに動かせる。
    """
    from scipy.optimize import linear_sum_assignment

    seats = _build_seats(drivers)
    assignments = {driver.id: [] for driver in drivers}

    if not passengers or not seats:
        return assignments, list(passengers)

    # コスト行列: 行=乗客, 列=席
    cost_matrix = [
        [
            _cost(cost_table, passenger, driver) + balance_penalty * seat_index
            for driver, seat_index in seats
        ]
        for passenger in passengers
    ]

    # 乗客数と席数が違っても scipy が長方形行列を扱えるので、
    # 少ない方の人数ぶんだけ最適に対応付けてくれる。
    row_indices, col_indices = linear_sum_assignment(cost_matrix)

    assigned = set()
    for row, col in zip(row_indices, col_indices):
        passenger = passengers[row]
        driver, _seat_index = seats[col]
        minutes = _cost(cost_table, passenger, driver)
        if minutes >= UNREACHABLE:
            # 席が余っていて仕方なく組まれた「経路不明」のペアは採用しない
            continue
        assignments[driver.id].append((passenger, minutes))
        assigned.add(passenger.id)

    unassigned = [p for p in passengers if p.id not in assigned]
    return assignments, unassigned


def assign_ilp(passengers, drivers, cost_table, max_spread=1):
    """整数計画（PuLP + CBC）による割り当て。

    ハンガリアン法との決定的な違いは、
    「乗車人数の最大と最小の差を max_spread 以内に収める」を
    ハード制約として書ける点。席ペナルティ λ と違い、
    車どうしの所要時間差がどれだけ大きくても偏りを保証できる。

        max_spread=1 … ほぼ均等（例: 5人3台なら 2,2,1）。通常はこちらを使う。
        max_spread=0 … 完全に同数。人数が車の台数で割り切れないとき、
                       解なしにはならず「あぶれた人を乗せ残す」形で最適化される
                       （5人2台なら 2,2 になり1人が未割当）。実運用では非推奨。

    定式化:
        変数   x[p][d] ∈ {0,1}   乗客pを車dに乗せるか
        目的   Σ 所要時間 * x  +  未割当ペナルティ * (割り当てられなかった人数)
        制約   各乗客は高々1台      Σ_d x[p][d] <= 1
               定員                  Σ_p x[p][d] <= capacity[d]
               偏り                  load_min <= Σ_p x[p][d] <= load_max
                                     load_max - load_min <= max_spread

    解が存在しない場合は None を返すので、呼び出し側でフォールバックする。
    """
    usable_drivers = [d for d in drivers if d.car_capacity > 0]
    assignments = {driver.id: [] for driver in drivers}

    if not passengers or not usable_drivers:
        return assignments, list(passengers)

    problem = pulp.LpProblem("carshare", pulp.LpMinimize)

    # 経路が取れないペアはそもそも変数を作らない（＝選択肢から除外する）
    x = {}
    for passenger in passengers:
        for driver in usable_drivers:
            if _cost(cost_table, passenger, driver) < UNREACHABLE:
                x[(passenger.id, driver.id)] = pulp.LpVariable(
                    f"x_{passenger.id}_{driver.id}", cat="Binary"
                )

    load_max = pulp.LpVariable("load_max", lowBound=0)
    load_min = pulp.LpVariable("load_min", lowBound=0)

    # 目的関数: 合計所要時間 + 乗せられなかった人へのペナルティ
    travel_cost = pulp.lpSum(
        _cost(cost_table, p, d) * x[(p.id, d.id)]
        for p in passengers
        for d in usable_drivers
        if (p.id, d.id) in x
    )
    assigned_count = pulp.lpSum(x.values())
    problem += travel_cost + UNASSIGNED_PENALTY * (len(passengers) - assigned_count)

    # 各乗客が乗るのは高々1台（経路不明の人は0台になりうる）
    for passenger in passengers:
        choices = [
            x[(passenger.id, d.id)] for d in usable_drivers if (passenger.id, d.id) in x
        ]
        if choices:
            problem += pulp.lpSum(choices) <= 1

    # 定員と偏りの制約
    for driver in usable_drivers:
        load = pulp.lpSum(
            x[(p.id, driver.id)] for p in passengers if (p.id, driver.id) in x
        )
        problem += load <= driver.car_capacity
        problem += load <= load_max
        problem += load >= load_min
    problem += load_max - load_min <= max_spread

    status = problem.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        return None

    assigned = set()
    for passenger in passengers:
        for driver in usable_drivers:
            var = x.get((passenger.id, driver.id))
            if var is not None and var.value() is not None and var.value() > 0.5:
                assignments[driver.id].append(
                    (passenger, _cost(cost_table, passenger, driver))
                )
                assigned.add(passenger.id)

    unassigned = [p for p in passengers if p.id not in assigned]
    return assignments, unassigned


def total_minutes(assignments):
    """割り当て結果の合計所要時間。方式どうしの比較に使う。"""
    return sum(minutes for rows in assignments.values() for _p, minutes in rows)


def load_counts(assignments):
    """ドライバーIDごとの乗車人数。偏りの比較に使う。"""
    return {driver_id: len(rows) for driver_id, rows in assignments.items()}

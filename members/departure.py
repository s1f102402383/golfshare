"""NAVITIME が返す出発時刻の妥当性チェック。

このアプリは集合時刻(goal_time)を NAVITIME に渡し、
「集合時刻に間に合うように逆算した出発時刻(from_time)」を受け取っている。

ところが逆算検索は「指定時刻までに着ける最後の便」を時刻表から探す仕組みなので、
集合時刻が早すぎて当日の始発では間に合わない場合、
前日の便まで遡ったり、始発前の非現実的な時刻を返したりすることがある。

そのまま画面に出すと「実際には走っていない列車の時刻」を
正しい情報のように見せてしまうため、ここで疑わしい値を検出する。
"""

from datetime import datetime, timedelta


# 日本の鉄道の始発はおおむね5時台。これより前の出発は実在しないとみなす。
FIRST_TRAIN_HOUR = 4

# 集合時刻より何分以上早く着く経路を「不自然」とみなすか。
# 間に合う便が無いと逆算が極端に早い便を拾うため、その兆候として使う。
MAX_EARLY_ARRIVAL_MINUTES = 120


def parse_from_time(from_time):
    """NAVITIME の "YYYY-MM-DDTHH:MM:SS" を datetime に変換する。

    タイムゾーン付き("+09:00")で返ってくる場合もあるため、
    そこは落として素直な naive datetime として扱う。
    """
    if not from_time:
        return None
    text = str(from_time).strip()
    # "2026-08-30T05:12:00+09:00" -> "2026-08-30T05:12:00"
    if len(text) > 19:
        text = text[:19]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def check_departure(from_time, minutes, round_day, meet_time):
    """出発時刻が信用できるかを判定する。

    戻り値は (信用できるか, 理由メッセージ or None)。
    信用できない場合は呼び出し側で時刻を表示せず、理由を出す。
    """
    departure = parse_from_time(from_time)
    if departure is None:
        return False, "出発時刻を取得できませんでした"

    # 1) 逆算が前日以前まで遡っている
    if departure.date() < round_day:
        return False, "当日の始発では集合時刻に間に合いません"

    # 念のため翌日以降もはじく（通常は起きないが、返り値の取り違えを検出できる）
    if departure.date() > round_day:
        return False, "出発時刻が集合日と一致しません"

    # 2) 始発より前の、実在しない時刻
    if departure.hour < FIRST_TRAIN_HOUR:
        return False, "始発前の時刻のため公共交通機関では移動できません"

    # 3) 集合時刻より大幅に早く着いてしまう
    #    （間に合う便が無く、極端に早い便しか拾えていない兆候）
    if minutes is not None and meet_time is not None:
        meeting = datetime.combine(round_day, meet_time)
        arrival = departure + timedelta(minutes=minutes)
        early_by = (meeting - arrival).total_seconds() / 60
        if early_by > MAX_EARLY_ARRIVAL_MINUTES:
            return False, f"集合時刻の{int(early_by)}分前に到着する便しかありません"
        if early_by < 0:
            return False, "集合時刻に間に合う経路が見つかりません"

    return True, None

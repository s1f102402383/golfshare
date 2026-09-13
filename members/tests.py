"""割り当てアルゴリズムと出発時刻チェックのテスト。

割り当てロジックは NAVITIME API に依存しない純粋な関数として
members/assignment.py に切り出してあるため、
API を呼ばずにここで検証できる。
"""

from datetime import date, time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import DriverPlan, Member, Round
from .assignment import (
    UNREACHABLE,
    assign_greedy,
    assign_hungarian,
    assign_ilp,
    load_counts,
    passenger_seats,
    total_minutes,
)
from .departure import check_departure


class FakePassenger:
    def __init__(self, id):
        self.id = id
        self.name = f"p{id}"

    def __repr__(self):
        return self.name


class FakeDriver:
    def __init__(self, id, car_capacity):
        self.id = id
        self.name = f"D{id}"
        self.car_capacity = car_capacity

    def __repr__(self):
        return self.name


class GreedyVsOptimalTest(SimpleTestCase):
    """貪欲法が最適でないことを示す、改善の根拠となるテスト。"""

    def test_greedy_is_far_from_optimal(self):
        # 同乗1人ずつ(定員2)の車が2台。貪欲法は最短の (p1,A)=1分 を先に確定
        # させるため、p2 が A に乗れなくなり 100分の B に回されてしまう。
        p1, p2 = FakePassenger(1), FakePassenger(2)
        a, b = FakeDriver(10, 2), FakeDriver(11, 2)
        cost = {
            (1, 10): 1, (2, 10): 2,
            (1, 11): 3, (2, 11): 100,
        }

        greedy, _ = assign_greedy([p1, p2], [a, b], cost)
        optimal, _ = assign_hungarian([p1, p2], [a, b], cost)

        self.assertEqual(total_minutes(greedy), 101)
        self.assertEqual(total_minutes(optimal), 5)


class BalanceTest(SimpleTestCase):
    """人数の偏りを、どの方式ならどこまで抑えられるかを固定するテスト。"""

    def _skewed_case(self):
        # 4人全員がAの駅に近く(5分)、Bは遠い(25分)。
        # どちらも定員4＝同乗3人まで乗せられる。
        passengers = [FakePassenger(i) for i in range(1, 5)]
        a, b = FakeDriver(10, 4), FakeDriver(11, 4)
        cost = {}
        for p in passengers:
            cost[(p.id, 10)] = 5
            cost[(p.id, 11)] = 25
        return passengers, [a, b], cost

    def test_hungarian_penalty_cannot_fix_large_gap(self):
        """席ペナルティ λ は「偏りの緩和」はできても「保証」はできない。

        車どうしの所要時間差(20分)が λ より大きいと、
        席を割高にしても同じ車に詰める方が安いままになる。
        PuLP を併用する理由がこれ。
        """
        passengers, drivers, cost = self._skewed_case()

        for penalty in (0, 5, 15):
            assignments, _ = assign_hungarian(
                passengers, drivers, cost, balance_penalty=penalty
            )
            counts = sorted(load_counts(assignments).values())
            self.assertEqual(counts, [1, 3], f"λ={penalty} で偏りが解消してしまった")

    def test_ilp_hard_constraint_fixes_the_skew(self):
        """ILP なら偏りをハード制約にできるので、時間差が大きくても均等になる。"""
        passengers, drivers, cost = self._skewed_case()

        assignments, unassigned = assign_ilp(
            passengers, drivers, cost, max_spread=1
        )

        self.assertEqual(sorted(load_counts(assignments).values()), [2, 2])
        self.assertEqual(unassigned, [])
        # 均等化には合計時間の増加という代償がある(40分 -> 60分)
        self.assertEqual(total_minutes(assignments), 60)

    def test_ilp_without_constraint_matches_optimal_total(self):
        """制約を外せば ILP も合計時間の最適解に一致する（実装の裏取り）。"""
        passengers, drivers, cost = self._skewed_case()

        loose, _ = assign_ilp(passengers, drivers, cost, max_spread=99)
        optimal, _ = assign_hungarian(passengers, drivers, cost)

        self.assertEqual(total_minutes(loose), total_minutes(optimal))


class UnreachableTest(SimpleTestCase):
    """経路が取れない相手に無理やり割り当てないことの確認。"""

    def test_unreachable_passenger_is_reported_not_assigned(self):
        passengers = [FakePassenger(i) for i in range(1, 4)]
        a, b = FakeDriver(10, 3), FakeDriver(11, 3)
        cost = {
            (1, 10): 10, (1, 11): 20,
            (2, 10): 15, (2, 11): 12,
            (3, 10): UNREACHABLE, (3, 11): UNREACHABLE,
        }

        for name, (assignments, unassigned) in {
            "greedy": assign_greedy(passengers, [a, b], cost),
            "hungarian": assign_hungarian(passengers, [a, b], cost),
            "ilp": assign_ilp(passengers, [a, b], cost, max_spread=1),
        }.items():
            self.assertEqual(
                [p.id for p in unassigned], [3], f"{name} が p3 を割り当ててしまった"
            )
            self.assertEqual(total_minutes(assignments), 22, name)


class EdgeCaseTest(SimpleTestCase):
    def test_no_passengers(self):
        drivers = [FakeDriver(10, 4)]
        assignments, unassigned = assign_ilp([], drivers, {}, max_spread=1)
        self.assertEqual(load_counts(assignments), {10: 0})
        self.assertEqual(unassigned, [])

    def test_no_drivers(self):
        passengers = [FakePassenger(1)]
        assignments, unassigned = assign_ilp(passengers, [], {}, max_spread=1)
        self.assertEqual(assignments, {})
        self.assertEqual(unassigned, passengers)

    def test_driver_with_no_spare_seat_is_ignored(self):
        """定員1(運転手のみ)と未入力の0は、近くても同乗者を乗せない。"""
        for capacity in (0, 1):
            passengers = [FakePassenger(1)]
            no_seat, real_car = FakeDriver(10, capacity), FakeDriver(11, 3)
            cost = {(1, 10): 5, (1, 11): 30}

            assignments, unassigned = assign_ilp(
                passengers, [no_seat, real_car], cost, max_spread=1
            )

            self.assertEqual(
                load_counts(assignments), {10: 0, 11: 1}, f"定員{capacity}"
            )
            self.assertEqual(unassigned, [])

    def test_more_passengers_than_seats(self):
        passengers = [FakePassenger(i) for i in range(1, 5)]
        driver = FakeDriver(10, 3)
        cost = {(p.id, 10): 10 for p in passengers}

        assignments, unassigned = assign_ilp(
            passengers, [driver], cost, max_spread=1
        )

        self.assertEqual(load_counts(assignments), {10: 2})
        self.assertEqual(len(unassigned), 2)


class CapacityIncludesDriverTest(SimpleTestCase):
    """car_capacity は運転手を含む乗車定員である、という取り決めの確認。

    以前は「同乗できる人数」として扱っていたため、4人乗りの車に
    4人を同乗させて車内5人になる割り当てが起こりえた。
    """

    def test_passenger_seats_excludes_the_driver(self):
        self.assertEqual(passenger_seats(FakeDriver(10, 4)), 3)
        self.assertEqual(passenger_seats(FakeDriver(10, 1)), 0)
        self.assertEqual(passenger_seats(FakeDriver(10, 0)), 0)

    def test_four_seater_takes_at_most_three_passengers(self):
        # 4人乗り1台に5人が乗りたい。全員その車が最短でも、乗れるのは3人。
        passengers = [FakePassenger(i) for i in range(1, 6)]
        driver = FakeDriver(10, 4)
        cost = {(p.id, 10): 10 for p in passengers}

        for name, result in {
            "greedy": assign_greedy(passengers, [driver], cost),
            "hungarian": assign_hungarian(passengers, [driver], cost),
            "ilp": assign_ilp(passengers, [driver], cost, max_spread=1),
        }.items():
            assignments, unassigned = result
            self.assertEqual(load_counts(assignments), {10: 3}, name)
            self.assertEqual(len(unassigned), 2, name)


class DepartureCheckTest(SimpleTestCase):
    """NAVITIME の逆算が返す、実在しない出発時刻を弾けるかの確認。"""

    DAY = date(2026, 8, 30)
    MEET = time(7, 30)

    def _check(self, from_time, minutes):
        return check_departure(from_time, minutes, self.DAY, self.MEET)

    def test_normal_departure_is_accepted(self):
        ok, reason = self._check("2026-08-30T06:40:00", 50)
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_timezone_suffix_is_accepted(self):
        ok, _ = self._check("2026-08-30T06:40:00+09:00", 50)
        self.assertTrue(ok)

    def test_previous_day_is_rejected(self):
        # 当日の始発では間に合わず、前日の便まで遡ってしまったケース
        ok, reason = self._check("2026-08-29T23:40:00", 50)
        self.assertFalse(ok)
        self.assertIn("始発", reason)

    def test_before_first_train_is_rejected(self):
        ok, reason = self._check("2026-08-30T03:10:00", 50)
        self.assertFalse(ok)
        self.assertIn("始発前", reason)

    def test_arriving_far_too_early_is_rejected(self):
        # 05:00発 + 29分 = 05:29着。集合の 121分前に着く便しかない状態。
        ok, reason = self._check("2026-08-30T05:00:00", 29)
        self.assertFalse(ok)
        self.assertIn("121分前", reason)

    def test_arriving_exactly_at_threshold_is_accepted(self):
        # 120分前ちょうどは許容範囲（境界の挙動を固定しておく）
        ok, _ = self._check("2026-08-30T05:00:00", 30)
        self.assertTrue(ok)

    def test_arriving_after_meeting_time_is_rejected(self):
        ok, reason = self._check("2026-08-30T07:00:00", 60)
        self.assertFalse(ok)
        self.assertIn("間に合う経路", reason)

    def test_missing_or_broken_value_is_rejected(self):
        for value in (None, "", "not-a-time"):
            ok, reason = self._check(value, 50)
            self.assertFalse(ok, value)
            self.assertIsNotNone(reason)


class CarshareViewTest(TestCase):
    """view からテンプレートまでの配線を、NAVITIME を呼ばずに確認する。"""

    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw")
        self.client.force_login(self.user)

        def member(name, station, has_car=False, capacity=0):
            return Member.objects.create(
                user=self.user, name=name, nearest_station=station,
                has_car=has_car, car_capacity=capacity,
            )

        # 全員がAの駅に近く、Bは遠い（偏りが起きる例1と同じ構図）
        self.driver_a = member("Aさん", "A駅", has_car=True, capacity=4)
        self.driver_b = member("Bさん", "B駅", has_car=True, capacity=4)
        self.passengers = [member(f"p{i}", f"P{i}駅") for i in range(1, 5)]

        self.round = Round.objects.create(
            user=self.user, day=date(2026, 8, 30), destination="○○ゴルフ場"
        )
        self.round.members.set([self.driver_a, self.driver_b] + self.passengers)

        for driver in (self.driver_a, self.driver_b):
            DriverPlan.objects.create(
                round=self.round, driver=driver, meet_time=time(7, 30)
            )

    def _get(self):
        return self.client.get(
            reverse("carshare_result", args=[self.round.id])
        )

    @patch("members.views.get_travel_time_cached")
    @patch("members.views.get_station_id_cached")
    def test_assignment_is_balanced_across_cars(self, station, travel):
        station.side_effect = lambda name: f"id-{name}"

        def fake_travel(start_id, goal_id, goal_time):
            # A駅行きは5分、B駅行きは25分
            return (5, "2026-08-30T07:25:00") if goal_id == "id-A駅" \
                else (25, "2026-08-30T07:05:00")

        travel.side_effect = fake_travel

        response = self._get()

        self.assertEqual(response.status_code, 200)
        counts = sorted(
            len(rows) for rows in response.context["assignments"].values()
        )
        # 貪欲法なら [1, 3] になっていたところが、ILP の制約で均等になる
        self.assertEqual(counts, [2, 2])
        self.assertEqual(response.context["unassigned"], [])

    @patch("members.views.get_travel_time_cached")
    @patch("members.views.get_station_id_cached")
    def test_station_lookup_is_hoisted_out_of_the_loop(self, station, travel):
        station.side_effect = lambda name: f"id-{name}"
        travel.return_value = (20, "2026-08-30T07:10:00")

        self._get()

        # 駅は6人ぶん。以前は乗客×ドライバー回引いていた（4×2×2=16回）
        self.assertEqual(station.call_count, 6)

    @patch("members.views.get_travel_time_cached")
    @patch("members.views.get_station_id_cached")
    def test_implausible_departure_is_flagged_not_displayed(self, station, travel):
        station.side_effect = lambda name: f"id-{name}"
        # 逆算が前日まで遡ってしまったケース
        travel.return_value = (50, "2026-08-29T23:40:00")

        response = self._get()

        rows = [r for rows in response.context["assignments"].values() for r in rows]
        self.assertTrue(rows)
        for row in rows:
            self.assertFalse(row["departure_ok"])
            self.assertIn("始発", row["departure_note"])
        # 疑わしい時刻は画面に出さない
        self.assertNotContains(response, "23:40")

    @patch("members.views.get_travel_time_cached")
    @patch("members.views.get_station_id_cached")
    def test_driver_without_meet_time_is_reported(self, station, travel):
        station.side_effect = lambda name: f"id-{name}"
        travel.return_value = (20, "2026-08-30T07:10:00")
        DriverPlan.objects.filter(driver=self.driver_b).delete()

        response = self._get()

        self.assertEqual(
            [d.id for d in response.context["drivers_without_plan"]],
            [self.driver_b.id],
        )

    @patch("members.views.get_travel_time_cached")
    @patch("members.views.get_station_id_cached")
    def test_unroutable_passengers_are_listed(self, station, travel):
        station.return_value = None  # 駅IDが引けない＝経路不明
        travel.return_value = (None, None)

        response = self._get()

        self.assertEqual(len(response.context["unassigned"]), 4)
        self.assertContains(response, "乗る車が決まらなかった人")

    @patch("members.views.get_travel_time_cached")
    @patch("members.views.get_station_id_cached")
    def test_no_api_calls_when_no_driver_has_a_meet_time(self, station, travel):
        """集合時刻が誰も未設定なら、課金対象のAPIを一切呼ばない。"""
        station.side_effect = lambda name: f"id-{name}"
        travel.return_value = (20, "2026-08-30T07:10:00")
        DriverPlan.objects.filter(round=self.round).delete()

        response = self._get()

        self.assertEqual(station.call_count, 0)
        self.assertEqual(travel.call_count, 0)
        self.assertEqual(len(response.context["unassigned"]), 4)
        self.assertEqual(len(response.context["drivers_without_plan"]), 2)

    @patch("members.views.get_travel_time_cached")
    @patch("members.views.get_station_id_cached")
    def test_station_of_driver_without_meet_time_is_not_looked_up(self, station, travel):
        """集合時刻が未設定のドライバーの駅は引かない。"""
        station.side_effect = lambda name: f"id-{name}"
        travel.return_value = (20, "2026-08-30T07:10:00")
        DriverPlan.objects.filter(driver=self.driver_b).delete()

        self._get()

        looked_up = {call.args[0] for call in station.call_args_list}
        self.assertNotIn(self.driver_b.nearest_station, looked_up)
        self.assertIn(self.driver_a.nearest_station, looked_up)


class PageRenderTest(TestCase):
    """画面まわりの土台の確認。UIを作り替えても壊れていないことを見る。"""

    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw-for-test-1234")
        self.client.force_login(self.user)
        self.driver = Member.objects.create(
            user=self.user, name="佐藤", nearest_station="赤羽",
            has_car=True, car_capacity=5,
        )
        self.rider = Member.objects.create(
            user=self.user, name="鈴木", nearest_station="池袋",
        )
        self.round = Round.objects.create(
            user=self.user, day=date(2026, 10, 1), destination="テストGC",
        )
        self.round.members.set([self.driver, self.rider])

    def test_every_page_renders(self):
        pages = [
            ("index", []), ("add_member", []), ("add_round", []),
            ("edit_member", [self.driver.id]), ("signup", []),
        ]
        for name, args in pages:
            with self.subTest(page=name):
                self.assertEqual(
                    self.client.get(reverse(name, args=args)).status_code, 200
                )
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_login_page_has_no_app_menu(self):
        """未ログインの画面に、ログインしないと使えないメニューを出さない。"""
        self.client.logout()
        html = self.client.get(reverse("login")).content.decode()
        self.assertNotIn("メンバー登録", html)
        self.assertNotIn("おでかけ作成", html)

    def test_delete_requires_post(self):
        """削除はPOSTのみ。URLを踏んだだけで消えないようにする。"""
        self.assertEqual(
            self.client.get(
                reverse("delete_member", args=[self.rider.id])
            ).status_code,
            405,
        )
        self.client.post(reverse("delete_member", args=[self.rider.id]))
        self.assertFalse(Member.objects.filter(id=self.rider.id).exists())

        self.client.post(reverse("delete_round", args=[self.round.id]))
        self.assertFalse(Round.objects.filter(id=self.round.id).exists())

    def test_other_users_round_is_hidden(self):
        other = User.objects.create_user("other", password="pw-for-test-1234")
        self.client.force_login(other)
        self.assertEqual(
            self.client.get(
                reverse("carshare_result", args=[self.round.id])
            ).status_code,
            404,
        )

    def test_capacity_is_cleared_when_not_a_driver(self):
        """車のチェックを外したときに、隠れた入力欄の定員が残らないこと。"""
        self.client.post(reverse("add_member"), {
            "name": "田中", "nearest_station": "大宮", "car_capacity": "5",
        })
        self.assertEqual(Member.objects.get(name="田中").car_capacity, 0)

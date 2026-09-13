from django.shortcuts import render,redirect
from .models import Member,Round

from django.contrib.auth.forms import UserCreationForm

from .navitime import get_station_id_cached, get_travel_time_cached
from .models import Member, Round, DriverPlan
from .assignment import assign_ilp, assign_greedy, UNREACHABLE
from .departure import check_departure
class SignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        labels = {'username': 'ユーザー名'}

from django.contrib.auth.decorators import login_required
# Create your views here.

@login_required
def index(request):
    contents = Member.objects.filter(user=request.user)
    rounds = Round.objects.filter(user=request.user)
    return render(request,'members/index.html',{'members': contents,'rounds':rounds})

@login_required
def add_member(request):
    if request.method=='POST':
       Member.objects.create(
           user=request.user,
           name=request.POST['name'],
           nearest_station=request.POST['nearest_station'],
           has_car = request.POST.get('has_car') == 'true',
           car_capacity=request.POST['car_capacity'] or 0,
       )
       return redirect('index')

    else:
        return render(request,'members/add_member.html')

@login_required
def add_round(request):
    if request.method == 'POST':
        round = Round.objects.create(
            user=request.user,
            day=request.POST['day'],
            destination=request.POST['destination'],
        )
        member_ids = request.POST.getlist('members')
        round.members.set(member_ids)

        # 参加者のうち車を出す人だけDriverPlanを作る
        for member in round.members.all():
            if member.has_car:
                meet_time = request.POST.get(f'meet_time_{member.id}')
                if meet_time:
                        DriverPlan.objects.create(
                        round=round,
                        driver=member,
                        meet_time=meet_time,
                    )
        return redirect('index')
    else:
        members = Member.objects.filter(user=request.user)
        return render(request, 'members/add_round.html', {'members': members})





def _gather_travel_times(passengers, drivers, meet_times, day):
    """NAVITIME を呼んで、乗客×ドライバーの所要時間と出発時刻を集める。

    駅IDの取得は二重ループの外に出してある。
    以前はループ内で毎回呼んでいたため、キャッシュが空のとき
    同じ駅を何度も問い合わせていた（P×D回 → 最大 P+D回 に削減）。

    戻り値:
        cost_table {(p.id, d.id): 所要時間(分)}   … 割り当てアルゴリズムへの入力
        info_table {(p.id, d.id): (出発時刻, 妥当か, 理由)} … 画面表示用
    """
    cost_table = {}
    info_table = {}

    # 集合時刻が未設定のドライバーは経路を計算できないので先に外す。
    # 駅IDの取得は課金対象なので、計算に使う分だけに絞ってから引く。
    usable_drivers = [d for d in drivers if meet_times.get(d.id)]
    if not passengers or not usable_drivers:
        return cost_table, info_table

    # 駅名 -> 駅ID をまとめて引く（同じ駅は1回だけ）
    station_ids = {}
    for member in list(passengers) + usable_drivers:
        name = member.nearest_station
        if name not in station_ids:
            station_ids[name] = get_station_id_cached(name)

    for driver in usable_drivers:
        meet_time = meet_times[driver.id]
        goal_time = f"{day}T{meet_time}"
        driver_station = station_ids.get(driver.nearest_station)

        for passenger in passengers:
            passenger_station = station_ids.get(passenger.nearest_station)

            if passenger_station and driver_station:
                minutes, from_time = get_travel_time_cached(
                    passenger_station, driver_station, goal_time
                )
            else:
                minutes, from_time = None, None

            if minutes is None:
                cost_table[(passenger.id, driver.id)] = UNREACHABLE
                info_table[(passenger.id, driver.id)] = (
                    None, False, "経路を取得できませんでした"
                )
                continue

            cost_table[(passenger.id, driver.id)] = minutes
            # 逆算された出発時刻が実在しうる値か検証する（課題B）
            is_valid, reason = check_departure(from_time, minutes, day, meet_time)
            info_table[(passenger.id, driver.id)] = (from_time, is_valid, reason)

    return cost_table, info_table


@login_required
def calculate_carshare(request, round_id):
    #ラウンドを取得
    round=Round.objects.get(id=round_id)

    #ドライバーと乗客を分ける（メンバーの取得は1回のクエリで済ませる）
    members = list(round.members.all())
    drivers = [m for m in members if m.has_car]
    passengers = [m for m in members if not m.has_car]

    # 運転手ごとの集合時刻を辞書にしておく
    meet_times = {}
    for plan in DriverPlan.objects.filter(round=round):
        meet_times[plan.driver.id] = plan.meet_time

    cost_table, info_table = _gather_travel_times(
        passengers, drivers, meet_times, round.day
    )

    # 合計所要時間を最小化しつつ、乗車人数の差が1人以内に収まるよう割り当てる。
    # 万一 CBC が動かない環境でも画面が出るよう、外部依存のない貪欲法に落とす。
    result = assign_ilp(passengers, drivers, cost_table, max_spread=1)
    if result is None:
        result = assign_greedy(passengers, drivers, cost_table)
    assigned_by_driver, unassigned = result

    # テンプレートが扱いやすいよう、ドライバーオブジェクトをキーにして
    # 出発時刻とその妥当性を付け直す
    assignments = {}
    for driver in drivers:
        rows = []
        for passenger, minutes in assigned_by_driver.get(driver.id, []):
            from_time, is_valid, reason = info_table.get(
                (passenger.id, driver.id), (None, False, None)
            )
            rows.append({
                'passenger': passenger,
                'minutes': minutes,
                'from_time': from_time,
                'departure_ok': is_valid,
                'departure_note': reason,
            })
        assignments[driver] = rows

    # 集合時刻が未設定のドライバーは経路計算の対象外になるので画面で知らせる
    drivers_without_plan = [d for d in drivers if not meet_times.get(d.id)]

    return render(request, 'members/result.html', {
        'assignments': assignments,
        'round': round,
        'unassigned': unassigned,
        'drivers_without_plan': drivers_without_plan,
    })

    
def signup(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = SignupForm()
    return render(request, 'members/signup.html', {'form': form})


@login_required
def delete_member(request, member_id):
    member = Member.objects.get(id=member_id, user=request.user)
    member.delete()
    return redirect('index')


@login_required
def edit_member(request,member_id):
    member=Member.objects.get(id=member_id,user=request.user)
    if request.method=='POST':
        member.name=request.POST['name']
        member.nearest_station = request.POST['nearest_station']
        member.has_car = request.POST.get('has_car') == 'true'
        member.car_capacity = request.POST['car_capacity'] or 0
        member.save()
        return redirect('index')

    else:
        return render(request,'members/edit_member.html', {'member': member})


@login_required
def delete_round(request, round_id):
    round = Round.objects.get(id=round_id, user=request.user)
    round.delete()
    return redirect('index')
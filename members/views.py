from django.shortcuts import render,redirect
from .models import Member,Round

from django.contrib.auth.forms import UserCreationForm

from .navitime import get_station_id_cached, get_travel_time_cached
from .models import Member, Round, DriverPlan
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





@login_required
def calculate_carshare(request, round_id):
    #ラウンドを取得
    round=Round.objects.get(id=round_id)

    #ドライバーと乗客を分ける

    drivers = [m for m in round.members.all() if m.has_car]
    passengers = [m for m in round.members.all() if not m.has_car]

    # 運転手ごとの集合時刻を辞書にしておく
    meet_times = {}
    for plan in DriverPlan.objects.filter(round=round):
        meet_times[plan.driver.id] = plan.meet_time

    traveltime = []
    for passenger in passengers:
        for driver in drivers:
            meet_time = meet_times.get(driver.id)
            if not meet_time:
                continue

            start_time = f"{round.day}T{meet_time}"

            passenger_id = get_station_id_cached(passenger.nearest_station)
            driver_id = get_station_id_cached(driver.nearest_station)

            if passenger_id and driver_id:
                tm = get_travel_time_cached(passenger_id, driver_id, start_time)
            else:
                tm = None

            if tm is None:
                tm = 999

            traveltime.append((tm, passenger, driver))
    

    #ドライバーごとに乗客を割り当て
    traveltime.sort(key=lambda x: x[0])
    # ドライバーごとの残席数
    remaining={}
    for driver in drivers:
        remaining[driver]=driver.car_capacity

    #各ドライバーに対して空のリストを用意している
    assignments = {}
    for driver in drivers:
        assignments[driver] = []

    assigned = set()

    for tm, passenger, driver in traveltime:
        if passenger in assigned:
            continue #割り当て済みならスキップ
        if remaining[driver]>0:
            assignments[driver].append((passenger,tm))
            remaining[driver]-=1
            assigned.add(passenger)

    return render(request,'members/result.html',{'assignments':assignments,'round':round})

    
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
from django.shortcuts import render,redirect
from .models import Member,Round
# Create your views here.

def index(request):
    contents=Member.objects.all()
    rounds=Round.objects.all()
    return render(request,'members/index.html',{'members': contents,'rounds':rounds})


def add_member(request):
    if request.method=='POST':
       Member.objects.create(
           name=request.POST['name'],
           nearest_station=request.POST['nearest_station'],
           has_car = request.POST.get('has_car') == 'true',
           car_capacity=request.POST['car_capacity']
       )
       return redirect('index')

    else:
        return render(request,'members/add_member.html')


def add_round(request):
    if request.method=='POST':
      round=Round.objects.create(
          day=request.POST['day'],
          
          gather_station=request.POST['gather_station'],
          gather_time=request.POST['gather_time']
      )
      ##いったん保存してから別途追加
      round.members.set(request.POST.getlist('members'))
      return redirect('index')

    else:
        members=Member.objects.all()
        return render(request,'members/add_round.html',{'members':members})




        
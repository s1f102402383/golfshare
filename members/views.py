from django.shortcuts import render,redirect
from .models import Member
# Create your views here.

def index(request):
    contents=Member.objects.all()

    return render(request,'members/index.html',{'members': contents})


def add_member(request):
    if request.method=='POST':
       Member.objects.create(
           name=request.POST['name'],
           nearest_station=request.POST['nearest_station'],
           has_car=request.POST['has_car'],
           car_capacity=request.POST['car_capacity']
       )
       return redirect('index')

    else:
        return render(request,'add_member.html')


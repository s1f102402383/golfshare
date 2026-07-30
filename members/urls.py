from django.urls import path
from . import views

urlpatterns=[
    path('',views.index,name='index'),
    path('add/', views.add_member, name='add_member'),
    path('round/add/',views.add_round,name='add_round'),
    path('round/<int:round_id>/result/',views.calculate_carshare,name='carshare_result'),
]

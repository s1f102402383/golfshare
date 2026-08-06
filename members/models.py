from django.db import models
from django.contrib.auth.models import User


# Create your models here.

class Member(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    #on_delete=models.CASCADEの意味： Userが削除されたら、そのUserの部員データも一緒に削除する。
    name=models.CharField(max_length=100)
    nearest_station=models.CharField(max_length=100)
    has_car=models.BooleanField(default=False)
    car_capacity=models.IntegerField(default=0)


class Round(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    day=models.DateField()
    #このmemberはラウンドに参加する人を表す
    members=models.ManyToManyField(Member)
    destination=models.CharField(max_length=100)

class DriverPlan(models.Model):
    round=models.ForeignKey(Round,on_delete=models.CASCADE)
    driver=models.ForeignKey(Member,on_delete=models.CASCADE)
    meet_time=models.TimeField()


#同じ駅の使いまわしを防ぐキャッシュ
class StationCache(models.Model):
    station_name = models.CharField(max_length=100, unique=True)
    station_id = models.CharField(max_length=20)


class TravelTimeCache(models.Model):
    start_id = models.CharField(max_length=20)
    goal_id = models.CharField(max_length=20)
    goal_time = models.CharField(max_length=30)
    minutes = models.IntegerField()
    from_time = models.CharField(max_length=40)

    class Meta:
        unique_together = ('start_id', 'goal_id', 'goal_time')



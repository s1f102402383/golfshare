from django.db import models

# Create your models here.

class Member(models.Model):
    name=models.CharField(max_length=100)
    nearest_station=models.CharField(max_length=100)
    has_car=models.BooleanField(default=False)
    car_capacity=models.IntegerField(default=0)


class Round(models.Model):
    day=models.DateField()
    #このmemberはラウンドに参加する人を表す
    members=models.ManyToManyField(Member)
    gather_station=models.CharField(max_length=100)
    gather_time=models.TimeField()


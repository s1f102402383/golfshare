from django.db import models

# Create your models here.

class Member(models.Model):
    name=models.CharField(max_length=100)
    nearest_station=models.CharField(max_length=100)
    has_car=models.BooleanField(default=False)
    car_capacity=models.IntegerField(default=0)
    

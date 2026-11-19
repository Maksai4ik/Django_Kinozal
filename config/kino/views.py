from django.shortcuts import render
from django.utils import timezone
from .models import Session


def index(request):
    # берем только сеансы которые еще не начались
    sessions = Session.objects.filter(starts_at__gte=timezone.now()).order_by('starts_at')
    return render(request, 'index.html', {'sessions': sessions})
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from .forms import ProfileForm, RegisterForm
from .models import Session
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from .models import Booking, Session

def index(request):
    # Берем только те сеансы, которые еще не начались
    sessions = Session.objects.filter(starts_at__gte=timezone.now()).order_by("starts_at")
    return render(request, "index.html", {"sessions": sessions})


def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Регистрация прошла успешно!")
            return redirect("index")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {"form": form})


@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Профиль обновлён")
            return redirect("profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "registration/profile.html", {"form": form})

def session_detail(request, pk):
    now = timezone.now()

    # Берем сеанс вместе с фильмом и залом одним запросом (select_related), чтобы не делать лишних запросов к БД
    session = get_object_or_404(
        Session.objects.select_related("movie", "hall"),
        pk=pk,
    )

    # Все места в зале, отсортированные по ряду и номеру
    seats = session.hall.seats.order_by("row", "number")

    # Цены этого сеанса по категориям (например, {'standard': 300, 'vip': 500})
    prices_by_category = {
        item.category: item.price
        for item in session.prices.all()
    }

    # Находим id мест, которые сейчас заняты на этом сеансе:
    # - либо бронь уже оплачена (paid)
    # - либо бронь удерживается (held) и срок удержания еще не прошел (expires_at > now)
    busy_seat_ids = set(
        Booking.objects.filter(
            session=session,
        )
        .filter(
            Q(status=Booking.Status.PAID)
            | Q(status=Booking.Status.HELD, expires_at__gt=now)
        )
        .values_list("seat_id", flat=True)
    )

    # Группируем места по рядам, чтобы в шаблоне было удобно рисовать ряды зала
    rows_map = {}
    for seat in seats:
        rows_map.setdefault(seat.row, []).append({
            "seat": seat,
            "is_busy": seat.id in busy_seat_ids,
            "price": prices_by_category.get(seat.category),
        })

    rows = sorted(rows_map.items(), key=lambda item: item[0])

    return render(
        request,
        "session_detail.html",
        {
            "session": session,
            "rows": rows,
            "prices_by_category": prices_by_category,
            "busy_seat_ids": busy_seat_ids,
        },
    )
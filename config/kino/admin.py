from django.contrib import admin
from .forms import MovieAdminForm
from .models import (
    Booking,
    Genre,
    Hall,
    Movie,
    Review,
    Seat,
    Session,
    SessionPrice,
    Ticket,
)

# Регистрируем все модели, чтобы они появились в админке
admin.site.register(Genre)


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    form = MovieAdminForm


admin.site.register(Hall)
admin.site.register(Seat)
admin.site.register(Session)
admin.site.register(SessionPrice)
admin.site.register(Booking)
admin.site.register(Ticket)
admin.site.register(Review)
from django.contrib import admin
from .models import Genre, Movie, Hall, Seat, Session, Booking, Ticket, Review

# Регистрируем все модели, чтобы они появились в админке
admin.site.register(Genre)
admin.site.register(Movie)
admin.site.register(Hall)
admin.site.register(Seat)
admin.site.register(Session)
admin.site.register(Booking)
admin.site.register(Ticket)
admin.site.register(Review)
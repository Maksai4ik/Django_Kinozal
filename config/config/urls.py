from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from kino import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.index, name="index"),  # Главная страница
    path("login/", views.StaffLoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path("profile/", views.profile, name="profile"),
    path("sessions/<int:pk>/", views.session_detail, name="session_detail"),
    path("sessions/<int:pk>/seats/availability/", views.session_seat_availability, name="session_seat_availability"),
    path("sessions/<int:session_id>/seats/book/", views.book_seats, name="book_seats"),
    path("sessions/<int:session_id>/seats/<int:seat_id>/book/", views.book_seat, name="book_seat"),
    path("bookings/", views.my_bookings, name="my_bookings"),
    path("bookings/<int:pk>/cancel/", views.cancel_booking, name="cancel_booking"),
    path("bookings/<int:pk>/pay/", views.pay_booking, name="pay_booking"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("movies/<int:pk>/", views.movie_detail, name="movie_detail"),
    path("cashier/bookings/", views.cashier_bookings, name="cashier_bookings"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
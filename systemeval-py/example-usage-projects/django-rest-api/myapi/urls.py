from django.urls import path

from myapi.views import ItemListView, health_check

urlpatterns = [
    path("api/health/", health_check),
    path("api/items/", ItemListView.as_view()),
]

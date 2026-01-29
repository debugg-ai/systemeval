from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.views import APIView


def health_check(request):
    return JsonResponse({"status": "ok"})


class ItemListView(APIView):
    def get(self, request):
        items = [
            {"id": 1, "name": "Widget"},
            {"id": 2, "name": "Gadget"},
        ]
        return Response(items)

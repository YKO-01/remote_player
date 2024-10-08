from django.urls import path, re_path
from .consumers import RoomConsumer
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/rooms/$', RoomConsumer.as_asgi()),
    # path('ws/game/', consumers.GameRoomConsumer.as_asgi()),
    re_path(r'ws/game/(?P<room_name>\w+)/$', consumers.GameRoomConsumer.as_asgi()),
    # path('ws/singlegame/', consumers.SingleGameConsumer.as_asgi()),
    # path('tournament/<str:room_name>/', TournamentConsumer.as_asgi()),
    # path('tournament/', RoomConsumer.as_asgi()),
]
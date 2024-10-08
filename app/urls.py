from django.urls import path, include
from . import views

urlpatterns = [
    path('rooms', views.indexs, name='indexs'),
    path('rooms/create-room/', views.create_room, name='create_room'),
    path('rooms/rooms-list/', views.rooms_list, name='rooms_list'),
    path('join-room/', views.join_room, name='join_room'),
    path('leave-room/', views.leave_room, name='leave_room'),
    path('', views.index, name='index'),
    path('login/', views.loginUser, name='loginUser'),
    path('signup/', views.signup, name='signup'),
    path('tournament/', views.room, name='room'),
    path('tournament/<str:room_name>/', views.tournament, name='tournament'),
    path('game/', views.index, name='index'),
    path('game/room1/', views.index, name='index'),

]

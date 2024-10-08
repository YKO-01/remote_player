import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async
from channels.generic.websocket import WebsocketConsumer
# from .models import Room, Player


class RoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        self.room_group_name = 'room_group'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        await self.create_room_if_none()
        # await self.room_update()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'room_update',
            }
        )

    async def disconnect(self, close_code):
        # pass
        await self.leave_from_all_rooms()
        # await self.channel_layer.group_discard(
        #     self.room_group_name,
        #     self.channel_name
        # )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')
        room_id = data.get('room_id')
        nickname = data.get('nickname')

        if action == 'join':
            res = await self.join_room(room_id, nickname)
            if res['room_is_full']:
                matches = res['matches']
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'match_update',
                        'room_id': room_id,
                        'matches': res['matches']
                    }
                )
            else:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'room_update',
                    }
                )
        elif action == 'leave':
            await self.leave_room(room_id)

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'room_update',
                })
    
    @database_sync_to_async
    def create_room_if_none(self):
        from .models import Room
        if Room.objects.count() == 0:
            Room.objects.create(name='room1')

    @database_sync_to_async
    def join_room(self, room_id, nickname):
        from .models import Room
        try:
            print('room_id===================>', room_id, flush=True)
            room = Room.objects.get(id=room_id)
            print('room===================>', room.name, flush=True)
            room.add_player(self.user, nickname)
            print('room count===================>', room.count, flush=True)
            if room.is_full:
                matches = room.start_matches()
                return {'room_is_full': True, 'matches': matches}
            return {'room_is_full': False, 'matches': []}
        except Room.DoesNotExist:
            pass

    @database_sync_to_async
    def leave_room(self, room_id):
        from .models import Room
        try:
            room = Room.objects.get(id=room_id)
            room.remove_player(self.user)
            print('room count===================>', room.count, flush=True)
            if room.count == 0:
                room.delete()
        except Room.DoesNotExist:
            pass

    @database_sync_to_async
    def leave_from_all_rooms(self):
        from .models import Room
        rooms = Room.objects.all()
        for room in rooms:
            room.remove_player(self.user)
            if room.count == 0:
                room.delete()
    
    async def room_update(self, event):
        room_data = await self.get_data_room()
        await self.send(text_data=json.dumps({
            'type': 'room_update',
            'rooms': room_data
        }))

    @database_sync_to_async
    def get_data_room(self):
        from .models import Room, Player
        rooms = Room.objects.all()
        data = []
        for room in rooms:
            data.append({
                'id': room.id,
                'name': room.name,
                'players': [{'username': player.username, 'nickname': player.nickname, 'is_current_user': player == self.user} for player in room.players.all()],
                'is_full': room.is_full,
            })
        return data

    def get_data_matches(slef, matches):
        data = []
        for match in matches:
            data.append({
                'player1': match.player1.username,
                'player2': match.player2.username,
                'id': match.id,
                # 'winner': match.winner.username if match.winner else None,
            })
        return data

    async def match_update(self, event):
        room_id = event['room_id']
        matches = event['matches']
        print('matches===================>', matches, flush=True)
        data = self.get_data_matches(matches)
        data_rooms = await self.get_data_room()
        for match in data:
            print('match of :', match.get('player1'), 'vs', match.get('player2'), flush=True)
        await self.send(text_data=json.dumps({
            'type': 'match_update',
            'room_id': room_id,
            'matches': data,
            'rooms': data_rooms
        }))

import json
from channels.generic.websocket import AsyncWebsocketConsumer
import re

class GameRoomConsumer(AsyncWebsocketConsumer):
    rooms = {}  # Class-level dictionary to store room information

    @classmethod
    def get_room_name(cls, room_name):
        # Sanitize the room name to ensure it's valid
        return re.sub(r'[^a-zA-Z0-9_-]', '', room_name)[:99]

    async def connect(self):
        raw_room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_name = self.get_room_name(raw_room_name)
        self.room_group_name = f'game_{self.room_name}'
        
        # Initialize room if it doesn't exist
        if self.room_group_name not in self.rooms:
            self.rooms[self.room_group_name] = {
                'players': 0,
                'left_score': 0,
                'right_score': 0,
                'ball_position': {'x': 400, 'y': 300},
                'left_paddle_y': 250,
                'right_paddle_y': 250,
            }

        # Add the player to the room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        
        # Increment the player count
        self.rooms[self.room_group_name]['players'] += 1
        
        # Accept the WebSocket connection
        await self.accept()

        # Send initial game state to the new player
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'send_game_state'
            }
        )
        # await self.send_game_state()

    async def disconnect(self, close_code):
        # Decrement the player count
        self.rooms[self.room_group_name]['players'] -= 1

        # Remove the player from the room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

        # If no players left, remove the room
        if self.rooms[self.room_group_name]['players'] == 0:
            del self.rooms[self.room_group_name]

    async def receive(self, text_data):
        data = json.loads(text_data)

        if 'paddle_move' in data:
            await self.handle_paddle_move(data['paddle_move'])
        elif 'ball_position' in data:
            await self.handle_ball_position(data['ball_position'])
        elif 'score_update' in data:
            await self.handle_score_update(data['score_update'])

    async def handle_paddle_move(self, paddle_move):
        print('paddle type ', paddle_move['player'])
        player = paddle_move['player']
        y = paddle_move['y']
        self.rooms[self.room_group_name][f'{player}_paddle_y'] = y
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_paddle_move',
                'paddle_move': paddle_move
            }
        )

    async def handle_ball_position(self, ball_position):
        self.rooms[self.room_group_name]['ball_position'] = ball_position
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_ball_position',
                'ball_position': ball_position
            }
        )

    async def handle_score_update(self, score_update):
        self.rooms[self.room_group_name]['left_score'] = score_update['left_score']
        self.rooms[self.room_group_name]['right_score'] = score_update['right_score']
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_score_update',
                'score_update': score_update
            }
        )

    async def broadcast_paddle_move(self, event):
        await self.send(text_data=json.dumps({
            'type': 'paddle_move',
            'paddle_move': event['paddle_move']
        }))

    async def broadcast_ball_position(self, event):
        await self.send(text_data=json.dumps({
            'type': 'ball_position',
            'ball_position': event['ball_position']
        }))

    async def broadcast_score_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'score_update',
            'score_update': event['score_update']
        }))

    async def send_game_state(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            'game_state': {
                'players': self.rooms[self.room_group_name]['players'],
                'left_score': self.rooms[self.room_group_name]['left_score'],
                'right_score': self.rooms[self.room_group_name]['right_score'],
                'ball_position': self.rooms[self.room_group_name]['ball_position'],
                'left_paddle_y': self.rooms[self.room_group_name]['left_paddle_y'],
                'right_paddle_y': self.rooms[self.room_group_name]['right_paddle_y'],
            }
        }))
# class GameRoomConsumer(AsyncWebsocketConsumer):
#     player_count = 0  # Class-level variable to track the number of players

#     async def connect(self):
#         self.room_group_name = 'game_room'
        
#         # Add the player to the room group
#         await self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name
#         )
        
#         # Increment the player count when a player connects
#         GameRoomConsumer.player_count += 1
        
#         # Accept the WebSocket connection
#         await self.accept()

#         # Broadcast the updated player count to all clients in the room
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'player_count_update',
#                 'playerCount': GameRoomConsumer.player_count
#             }
#         )

#     async def disconnect(self, close_code):
#         # Decrement the player count when a player disconnects
#         GameRoomConsumer.player_count -= 1

#         # Remove the player from the room group
#         await self.channel_layer.group_discard(
#             self.room_group_name,
#             self.channel_name
#         )

#         # Broadcast the updated player count to all clients in the room
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'player_count_update',
#                 'playerCount': GameRoomConsumer.player_count
#             }
#         )

#     # Receive messages from WebSocket (client sends score and paddle updates)
#     async def receive(self, text_data):
#         data = json.loads(text_data)

#         left_paddle_move = data.get('leftPaddleMove')
#         right_paddle_move = data.get('rightPaddleMove')
#         left_score = data.get('leftScore')
#         right_score = data.get('rightScore')

#         # Broadcast the updated scores to the room
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'score_update',
#                 'leftScore': left_score,
#                 'rightScore': right_score
#             }
#         )

#         # Broadcast left paddle movement
#         if left_paddle_move is not None:
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'paddle_move',
#                     'leftPaddleMove': left_paddle_move
#                 }
#             )

#         # Broadcast right paddle movement
#         if right_paddle_move is not None:
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'right_paddle_move',
#                     'rightPaddleMove': right_paddle_move
#                 }
#             )
#     # Handler for broadcasting score updates
#     async def score_update(self, event):
#         left_score = event['leftScore']
#         right_score = event['rightScore']

#         # Send the updated scores to WebSocket clients
#         await self.send(text_data=json.dumps({
#             'leftScore': left_score,
#             'rightScore': right_score
#         }))

#     # Handler for broadcasting player count updates
#     async def player_count_update(self, event):
#         player_count = event['playerCount']

#         # Send the player count to WebSocket clients
#         await self.send(text_data=json.dumps({
#             'playerCount': player_count
#         }))


#     # Receive paddle movement from the room group
#     async def paddle_move(self, event):
#         left_paddle_move = event['leftPaddleMove']

#         # Send the left paddle movement to WebSocket
#         await self.send(text_data=json.dumps({
#             'leftPaddleMove': left_paddle_move
#         }))
#     # Handle right paddle movement
#     async def right_paddle_move(self, event):
#         right_paddle_move = event['rightPaddleMove']

#         # Send the right paddle movement to the client
#         await self.send(text_data=json.dumps({
#             'rightPaddleMove': right_paddle_move
#         }))

# class GameRoomConsumer(AsyncWebsocketConsumer):
#     player_count = 0  # Class-level variable to track the number of players

#     async def connect(self):
#         self.room_group_name = 'game_room'
        
#         # Add the player to the room group
#         await self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name
#         )
        
#         # Increment the player count when a player connects
#         GameRoomConsumer.player_count += 1
        
#         # Accept the WebSocket connection
#         await self.accept()

#         # Broadcast the updated player count to all clients in the room
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'player_count_update',
#                 'playerCount': GameRoomConsumer.player_count
#             }
#         )

#     async def disconnect(self, close_code):
#         # Decrement the player count when a player disconnects
#         GameRoomConsumer.player_count -= 1

#         # Remove the player from the room group
#         await self.channel_layer.group_discard(
#             self.room_group_name,
#             self.channel_name
#         )

#         # Broadcast the updated player count to all clients in the room
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'player_count_update',
#                 'playerCount': GameRoomConsumer.player_count
#             }
#         )

#     # Receive messages from WebSocket (client sends score updates)
#     async def receive(self, text_data):
#         data = json.loads(text_data)
#         left_score = data.get('leftScore')
#         right_score = data.get('rightScore')

#         # Broadcast the updated scores to the room
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'score_update',
#                 'leftScore': left_score,
#                 'rightScore': right_score
#             }
#         )

#     # Handler for broadcasting player count updates
#     async def player_count_update(self, event):
#         player_count = event['playerCount']

#         # Send the player count to WebSocket clients
#         await self.send(text_data=json.dumps({
#             'playerCount': player_count
#         }))

#     # Handler for broadcasting score updates
#     async def score_update(self, event):
#         left_score = event['leftScore']
#         right_score = event['rightScore']

#         # Send the updated scores to WebSocket clients
#         await self.send(text_data=json.dumps({
#             'leftScore': left_score,
#             'rightScore': right_score
#         }))

# class GameRoomConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.room_group_name = 'game_room'
        
#         # Add player to the room group
#         await self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name
#         )
        
#         # Accept the connection
#         await self.accept()

#         # Update player count on connection
#         self.scope['player_count'] = self.scope.get('player_count', 0) + 2

#         # Broadcast player count to all clients
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'player_count_update',
#                 'playerCount': self.scope['player_count']
#             }
#         )

#     async def disconnect(self, close_code):
#         # Update player count on disconnection
#         self.scope['player_count'] -= 1

#         # Leave the room group
#         await self.channel_layer.group_discard(
#             self.room_group_name,
#             self.channel_name
#         )

#         # Broadcast player count to all clients
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'player_count_update',
#                 'playerCount': self.scope['player_count']
#             }
#         )

#     # Receive message and update player count
#     async def player_count_update(self, event):
#         player_count = event['playerCount']

#         # Send player count to WebSocket
#         await self.send(text_data=json.dumps({
#             'playerCount': player_count
#         }))


# class GameRoomConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.user = self.scope['user']
#         self.room_group_name = 'game_room'
        
#         # Join the room group
#         await self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name
#         )
        
#         # Accept WebSocket connection
#         await self.accept()
    
#     async def disconnect(self, close_code):
#         # Leave the room group
#         await self.channel_layer.group_discard(
#             self.room_group_name,
#             self.channel_name
#         )
    
#     async def receive(self, text_data):
#         data = json.loads(text_data)
#         left_score = data['leftScore']
#         right_score = data['rightScore']

#         # Broadcast the updated score to the room group
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'update_score',
#                 'leftScore': left_score,
#                 'rightScore': right_score,
#             }
#         )
    
#     # Receive score updates from the room group and send to WebSocket
#     async def update_score(self, event):
#         left_score = event['leftScore']
#         right_score = event['rightScore']

#         # Send the score to WebSocket
#         await self.send(text_data=json.dumps({
#             'leftScore': left_score,
#             'rightScore': right_score
#         }))



# class TournamentConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         from .models import Room, Player
#         room_name = self.scope['url_route']['kwargs']['room_name']
#         username = self.scope['user']
#         self.room_group_name = f'room_{room_name}'

#         await self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name
#         )
#         await self.accept()
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'handle_join_room',
#                 'message': 'has joined the room',
#                 'room_name': room_name,
#                 'username': username
#             }
#         )

#     async def disconnect(self, close_code):
#         username = self.scope['user']
#         room_name = self.scope['url_route']['kwargs']['room_name']
#         await self.channel_layer.group_discard(
#             self.room_group_name,
#             self.channel_name
#         )

#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'handle_left_room',
#                 'message': 'has left the room',
#                 'username': username,
#                 'room_name': room_name
#             }
#         )

#     async def receive(self, text_data):
#         text_data_json = json.loads(text_data)
#         message = text_data_json['message']
#         # player = Player.objects.get(username=self.username)
#         username = text_data_json['username']
#         print('username===================>', username, flush=True)

#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'room_massage',
#                 'message': message,
#                 'username': username
#             }
#         )

#     async def room_massage(self, event):
#         message = event['message']
#         username = event['username']

#         await self.send(text_data=json.dumps({
#             'message': message,
#             'username': username
#         }))

#     async def handle_join_room(self, event):
#         from .models import Room, Player
#         room_name = event['room_name']
#         username = event['username']
#         message = event["message"]
#         if await sync_to_async(Room.objects.filter(name=room_name).exists)():
#             print('room exists', flush=True)
#             room = await sync_to_async(Room.objects.get)(name=room_name)
#             if await sync_to_async(room.players.filter(username=username).exists)():
#                 pass
#             else:
#                 player = await sync_to_async(Player.objects.get)(username=username)
#                 await sync_to_async(room.players.add)(player)
#                 room.count += 1
#                 await sync_to_async(room.save)()
#                 message = f'{username} {event["message"]}'
#                 await self.send(text_data=json.dumps({
#                     'status': 'joined',
#                     'message': message,
#                     'username': player.username
#                 }))

#     async def handle_left_room(self, event):
#         from .models import Room, Player
#         room_name = event['room_name']
#         user = event['username']
#         username = event['username']
#         room = await sync_to_async(Room.objects.get)(name=room_name)
#         player = await sync_to_async(Player.objects.get)(username=user)
#         await sync_to_async(room.players.remove)(player)
#         print('player removed from room', flush=True)
#         room.count -= 1
#         await sync_to_async(room.save)()
#         message = f'{username} {event["message"]}'
#         await self.send(text_data=json.dumps({
#             'status': 'left',
#             'message': message,
#             'username': player.username
#         }))


# class RoomConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         print(self.scope['user'], ' is conneted ', flush=True)
#         self.room_group_name = 'room_group'
#         await self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name
#         )
#         await self.accept()
#     async def disconnect(self, close_code):
#         await self.channel_layer.group_discard(
#             self.room_group_name,
#             self.channel_name
#         )
#     async def receive(self, text_data):
#         text_data_json = json.loads(text_data)
#         room_name = text_data_json['room_name']
#         print('room_name===================>', room_name, flush=True)
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'room_message',
#                 'room_name': room_name
#             }
#         )
#     async def room_message(self, event):
#         from .models import Room
#         room_name = event['room_name']
#         if await sync_to_async(Room.objects.filter(name=room_name).exists)():
#             pass
#             # print('room exists 0', flush=True)
#             # room = await sync_to_async(Room.objects.get)(name=room_name)
#             # print('data send to room is ===================>', room_name, flush=True)
#             # await self.send(text_data=json.dumps({
#             #     'room_name': room_name,
#             #     'nbr_of_player': room.count
#             # }))
#         else:
#             room = await sync_to_async(Room.objects.create)(name=room_name)
#             # room.count += 1
#             await sync_to_async(room.save)()
#             room = await sync_to_async(Room.objects.get)(name=room_name)
#             print('data send to room is ===================>', room_name, flush=True)
#             await self.send(text_data=json.dumps({
#                 'room_name': room_name,
#                 'nbr_of_player': room.count
#             }))
        # try:
        #     room = await sync_to_async(Room.objects.get)(name=room_name)
        #     if room:
        #         return
        # except Exception as e:
        #     room = await sync_to_async(Room.objects.create)(name=room_name)
        #     room.count += 1
        #     await sync_to_async(room.save)()

        #     print('data send to room is ===================>', room_name, flush=True)
        #     await self.send(text_data=json.dumps({
        #         'room_name': room_name,
        #         'nbr_of_player': room.count
        #     }))

# class ChatConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         print('connected===================>', flush=True)
#         partner = self.scope['url_route']['kwargs']['partner']
#         self.room_group_name = f'room_{partner}'

#         await self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name
#         )
#         await self.accept()

#         username = self.scope['user']
#         print('username in socket===================>', username, flush=True)
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'join_chat',
#                 'message': f'{username} has joined the chat',
#             }
#         )

#     async def disconnect(self, close_code):
#         await self.channel_layer.group_discard(
#             self.room_group_name,
#             self.channel_name
#         )

#     async def receive(self, text_data):
#         text_data_json = json.loads(text_data)
#         message = text_data_json['message']
#         # player = Player.objects.get(username=self.username)
#         username = text_data_json['username']
#         print('username===================>', username, flush=True)

#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'chat_message',
#                 'message': message,
#                 'username': username
#             }
#         )

#     async def chat_message(self, event):
#         message = event['message']
#         username = event['username']

#         await self.send(text_data=json.dumps({
#             'message': message,
#             'username': username
#         }))

#     async def join_chat(self, event):
#         # username = event['username']
#         message = event['message']

#         # Send the "user connected" message to the WebSocket
#         await self.send(text_data=json.dumps({
#             'message': message,
#             # 'username': username
#         }))
# class ChatConsumer(aWebsocketConsumer):
#     def connect(self):
#         print('connected')
#         self.room_group_name = 'chat_room'

#         self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name
#         )
#         self.accept()

#     def disconnect(self, close_code):
#         self.channel_layer.group_discard(
#             self.room_group_name,
#             self.channel_name
#         )

#     def receive(self, text_data):
#         text_data_json = json.loads(text_data)
#         message = text_data_json['message']

#         self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'chat_message',
#                 'message': message
#             }
#         )

#     def chat_message(self, event):
#         message = event['message']

#         self.send(text_data=json.dumps({
#             'message': message
#         }))
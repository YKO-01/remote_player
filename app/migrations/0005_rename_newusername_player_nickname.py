# Generated by Django 4.2.15 on 2024-09-09 22:25

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0004_player_newusername'),
    ]

    operations = [
        migrations.RenameField(
            model_name='player',
            old_name='newusername',
            new_name='nickname',
        ),
    ]
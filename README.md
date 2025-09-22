# archive-bot
A discord bot which archives unused chats. Has optional mode with some miscellaneous features.

Use !helpme for command information

## Bot link
https://discord.com/oauth2/authorize?client_id=1413580438470922320&permissions=8&integration_type=0&scope=bot

## Self-Hosting
1. Clone repository or download as a zip file and extract
2. Create empty json files ```last_message_time.json```, ```last_user_time.json``` and ```settings.json``` in the same folder as ```main.py```
3. Enter file content as ```{}```
4. Create a bot on the [Discord developer portal](https://discord.com/developers)
5. Create ```.env``` file in the same folder as ```main.py```
6. In ```.env```, enter your token with ```DISCORD_TOKEN=[insert token here]```
7. Run replace first line of ```start-bot.ps1``` with your cloned repository path
8. Run ```start-bot.ps1```
9. Optionally set ```start-bot.ps1``` to run on start-up

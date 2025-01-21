# Anonymous Discord Polls
A simple anonymous poll bot for Discord. Bot admins are unable to tell who voted for what.

# Setup
1. Install Python3
2. Create a Python venv `python -m venv env`
3. Activate venv `source env/bin/activate` (linux) or `env/Scripts/activate` (windows)
4. Install requirements `python -m pip install requirements.txt`
5. Rename `example.env` to `.env`
6. Replace `DISCORD_BOT_TOKEN = "TOKEN_HERE"` with your token as `TOKEN_HERE`
7. Replace `DATABASE_NAME = "NAME_HERE"` to literally anything as `NAME_HERE` 
8. Give your Discord bot the Members privileged intent on the developer portal.
9. Run the bot with `python anon-polls.py`.
10. To run it constantly look into `nohup` or `screen` (linux) :3

# Public bot
For those of you who just want to use it without figuring out what the hell a Linux is:

🔗 Invite link: https://discord.com/oauth2/authorize?client_id=1214561094333374494&scope=bot&permissions=18432




PRs are welcome.

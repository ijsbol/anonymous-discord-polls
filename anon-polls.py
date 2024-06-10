from ast import literal_eval
from os import getenv
from re import search
from sys import exit as sys_exit
from typing import (
    Any,
    Dict,
    Final,
    List,
    Optional,
    Tuple,
    Union,
    cast,
)

from aiosqlite import connect as aio_connect
from disnake import (
    Colour,
    CustomActivity,
    Embed,
    Forbidden,
    GuildCommandInteraction,
    HTTPException,
    Intents,
    MessageInteraction,
    NotFound,
    Status,
    TextChannel,
    Thread,
)
from disnake.ext.commands import (
    AutoShardedInteractionBot,
    Param,
    guild_only,
)
from disnake.ext.tasks import loop
from disnake.ui import View, Button
from disnake.utils import utcnow
from dotenv import load_dotenv
from sqlite3 import Connection, Error, Row
from sqlite3 import connect as sync_connect


load_dotenv()


DISCORD_BOT_TOKEN: Final[Optional[str]] = getenv("DISCORD_BOT_TOKEN")
DATABASE_NAME: Final[Optional[str]] = getenv("DATABASE_NAME")

assert DISCORD_BOT_TOKEN is not None
assert DATABASE_NAME is not None


if getenv("PROXY_URL"):
    from disnake.http import Route
    Route.BASE = getenv("PROXY_URL") 


DURATION_REGEX_PATTERNS: Final[List[Tuple[str, int]]] = [
    (r"([0-9]+)(seconds|second|secs|sec|s)", 1),
    (r"([0-9]+)(minutes|minute|mins|min|m)", 60),
    (r"([0-9]+)(hours|hour|hrs|hr|h)", 60 * 60),
    (r"([0-9]+)(days|day|dys|dy|d)", 24 * 60 * 60),
]


sqlite_connection: Union[bool, Connection] = False


def check_sqlite_connection() -> None:
    try:
        sqlite_connection = sync_connect(DATABASE_NAME)
        cursor = sqlite_connection.cursor()
        print("Database created and Successfully Connected to SQLite")

        sqlite_select_query = "select sqlite_version();"
        cursor.execute(sqlite_select_query)
        record = cursor.fetchall()
        print(f"SQLite Database Version is: {record}")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                expires_timestamp   INTEGER NOT NULL,
                message_id          TEXT NOT NULL,
                channel_id          TEXT NOT NULL,
                votes_data_dict     TEXT NOT NULL
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS voters (
                user_id     TEXT NOT NULL,
                poll_id     TEXT NOT NULL
            );
        """)

        cursor.close()
    except Error as error:
        print(f"[SQLite Error] Error while connecting to SQLite {error}")
        sys_exit(-1)
    except Exception as error:
        print(f"[Unknown Error] Error on DB loading: {error}")
        sys_exit(-1)


class Bot(AutoShardedInteractionBot):
    is_first_connect: bool = True


bot = Bot(
    intents=Intents(guilds=True),
    status=Status.do_not_disturb,
    activity=CustomActivity(
        name="Custom Status",
        state="/anon-poll",
    ),
)


def convert_str_duration_to_int(duration: str) -> int:
    """Convert a `str` representation of a duration to an `int` of seconds."""
    duration = duration.replace(" ", "")
    duration_in_seconds = 0
    for pattern, multiply_offset in DURATION_REGEX_PATTERNS:
        found = search(pattern, duration)
        if found is None:
            continue

        found_number = int(found.group(1))
        duration_in_seconds += found_number * multiply_offset

    return duration_in_seconds


@loop(seconds=30, reconnect=True)
async def check_expired_polls() -> None:
    await bot.wait_until_ready()

    timestamp_now = int(utcnow().timestamp())
    query = """
        SELECT message_id, channel_id, votes_data_dict FROM polls
            WHERE expires_timestamp <= ?
    """
    args = (timestamp_now,)
    async with aio_connect(DATABASE_NAME) as db:
        db.row_factory = Row
        data = await db.execute_fetchall(query, args)
        data = cast(Optional[List[Dict[str, Any]]], data)

    if data is None:
        return

    poll_ids: List[int] = []

    for expired_poll in data:
        message_id = int(expired_poll["message_id"])
        poll_ids.append(message_id)
        channel_id = int(expired_poll["channel_id"])
        votes_data_dict = literal_eval(expired_poll["votes_data_dict"])

        channel = bot.get_channel(channel_id)
        if (
            channel is None
            or not isinstance(channel, (TextChannel, Thread))
        ):
            continue

        try:
            message = await channel.fetch_message(message_id)
        except:
            continue

        view = View()
        for option, votes in votes_data_dict.items():
            view.add_item(Button(label=f"{option}: {votes}"))
        try:
            await message.edit(view=view)
        except:
            continue

    # Delete expired polls and vote data.
    query_2 = """
        DELETE FROM polls
            WHERE expires_timestamp <= ?
    """
    args_2 = (timestamp_now,)
    async with aio_connect(DATABASE_NAME) as db:
        await db.execute(query_2, args_2)
        for poll_id in poll_ids:
            query_3 = """
                DELETE FROM voters
                    WHERE poll_id=?
            """
            args_3 = (poll_id,)
            await db.execute(query_3, args_3)
        await db.commit()


@bot.listen("on_ready")
async def on_ready() -> None:
    if bot.is_first_connect:
        bot.is_first_connect = False
        check_expired_polls.start()


@bot.listen("on_message_interaction")
async def on_message_interaction(interaction: MessageInteraction) -> None:
    if (
        interaction.guild is None
        or interaction.component.custom_id is None
    ):
        return

    await interaction.response.defer(ephemeral=True, with_message=True)

    query = """
        SELECT user_id FROM voters
            WHERE poll_id=?
                AND user_id=?
    """
    args = (interaction.message.id, interaction.user.id)
    async with aio_connect(DATABASE_NAME) as db:
        db.row_factory = Row
        data = await db.execute_fetchall(query, args)
        data = cast(Optional[List[Dict[str, Any]]], data)
        if data is not None and len(data) > 0:
            await interaction.edit_original_response(
                content="You have already voted on this poll.",
            )
            return

        query_2 = """
            INSERT INTO voters (user_id, poll_id)
                VALUES (?, ?)
        """
        args_2 = (interaction.user.id, interaction.message.id)
        await db.execute_insert(query_2, args_2)

        query_3 = """
            SELECT votes_data_dict FROM polls
                WHERE message_id=?
        """
        args_3 = (interaction.message.id,)
        data_3 = await db.execute_fetchall(query_3, args_3)
        data_3 = cast(Optional[List[Dict[str, Any]]], data_3)
        assert data_3 is not None
        votes_data_dict = literal_eval(data_3[0]["votes_data_dict"])
        votes_data_dict[interaction.component.label] += 1  # type: ignore[reportAttributeAccessIssue]

        query_4 = """
            UPDATE polls SET votes_data_dict=?
                WHERE message_id=?
        """
        args_4 = (str(votes_data_dict), interaction.message.id)
        await db.execute(query_4, args_4)
        await db.commit()

    await interaction.edit_original_response(
        content="Your vote has been recorded."
    )


@guild_only()
@bot.slash_command(
    name="anon-poll",
    description="Create an anonymous poll",
)
async def anon_poll_cmd(
    inter: GuildCommandInteraction,
    expire_time: str,
    poll_topic: str = Param(min_length=2, max_length=100),
    option_0: str = Param(min_length=1, max_length=100),
    option_1: str = Param(min_length=1, max_length=100),
    option_2: Optional[str] = Param(min_length=1, max_length=100, default=None),
    option_3: Optional[str] = Param(min_length=1, max_length=100, default=None),
    option_4: Optional[str] = Param(min_length=1, max_length=100, default=None),
    option_5: Optional[str] = Param(min_length=1, max_length=100, default=None),
    option_6: Optional[str] = Param(min_length=1, max_length=100, default=None),
    option_7: Optional[str] = Param(min_length=1, max_length=100, default=None),
    option_8: Optional[str] = Param(min_length=1, max_length=100, default=None),
    option_9: Optional[str] = Param(min_length=1, max_length=100, default=None),
) -> None:
    await inter.response.send_message(
        ephemeral=True,
        content="Sending poll...",
    )

    expire_time_offset = convert_str_duration_to_int(expire_time)
    expire_timestamp = int(utcnow().timestamp() + expire_time_offset)
    options_raw = [
        option_0, option_1, option_2, option_3, option_4,
        option_5, option_6, option_7, option_8, option_9,
    ]
    options_clean = [option for option in options_raw if option is not None]

    view = View()
    for option in options_clean:
        view.add_item(Button(label=option))

    embed = Embed(
        title=poll_topic,
        description=f"> This poll ends <t:{expire_timestamp}:R> (<t:{expire_timestamp}:F>).",
        colour=Colour.dark_orange(),
    )
    embed.set_footer(
        text="This is an anonymous poll - You cannot change your vote.",
        icon_url=bot.user.display_avatar.url,
    )

    poll_message = await inter.followup.send(
        embed=embed,
        view=view,
        wait=True,
    )

    votes_data_dict: Dict[str, int] = {
        option: 0 for option in options_clean
    }

    query = """
        INSERT INTO polls (expires_timestamp, message_id, channel_id, votes_data_dict)
            VALUES (?, ?, ?, ?)
    """
    args = (expire_timestamp, poll_message.id, poll_message.channel.id, str(votes_data_dict))
    async with aio_connect(DATABASE_NAME) as db:
        await db.execute(query, args)
        await db.commit()


if __name__ == "__main__":
    check_sqlite_connection()
    bot.run(DISCORD_BOT_TOKEN)

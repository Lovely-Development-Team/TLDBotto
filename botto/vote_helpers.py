from typing import Union

from discord import Message, User, Member

from botto.config import PingDisallowedRole

VOTE_EMOJI = (
    "0️⃣",
    "1️⃣",
    "2️⃣",
    "3️⃣",
    "4️⃣",
    "5️⃣",
    "6️⃣",
    "7️⃣",
    "8️⃣",
    "9️⃣",
    "🅰️",
    "🅱️",
    "✅",
    "❎",
    "❌",
    "👍",
    "👎",
    "💬",
    "🙌",
    "🙋‍♀️"
    "🙋"
    "🙋‍♂️"
)


def is_voting_message(message: Message) -> bool:
    return message.content.lstrip().startswith("🗳️")


async def extract_voted_users(
    message: Message, excluded_user_ids: set[str]
) -> set[User]:
    reacted_users = set()
    for reaction in message.reactions:
        if reaction.emoji not in VOTE_EMOJI:
            continue
        users = await reaction.users().flatten()
        reacted_users |= set(u for u in users if str(u.id) not in excluded_user_ids)

    return reacted_users


def guild_voting_member(message: Message, excluded_user_ids: set[str]) -> set[Member]:
    return set(
        [
            member
            for member in message.channel.members
            if not member.bot and str(member.id) not in excluded_user_ids
        ]
    )


def can_ping_vote(
    author: Union[Member, User], disallowed_roles: set[PingDisallowedRole]
) -> bool:
    if author.roles is None:
        return False
    for disallowed_role in disallowed_roles:
        if any(
            (role.id == disallowed_role.role_id or role.name == disallowed_role.name)
            for role in author.roles
        ):
            return False
    else:
        return True

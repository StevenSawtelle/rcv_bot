import discord
from discord.ext import commands
import asyncio

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def ranked_poll(ctx, title: str, rankings: int, *options):
    """Create a ranked-choice voting poll."""
    if len(options) < 2:
        await ctx.send("You need at least two options to create a ranked poll!")
        return
    if len(options) > 10:
        await ctx.send("You can only have up to 10 options.")
        return
    if rankings < 1 or rankings > len(options):
        await ctx.send("Rankings must be at least 1 and no more than the number of options.")
        return

    options_text = "\n".join(f"{i + 1}. {option}" for i, option in enumerate(options))
    options_embed = discord.Embed(
        title=title, description=f"Available options:\n{options_text}", color=0x00ff00
    )
    await ctx.send(embed=options_embed)

    poll_data = {
        "options": options,
        "votes": {i: {} for i in range(rankings)},
        "user_reactions": {i: {} for i in range(rankings)},  # Track reactions by user for each rank
    }
    poll_messages = []

    for rank in range(1, rankings + 1):
        rank_embed = discord.Embed(
            title=f"Rank {rank}",
            description="React with the emoji corresponding to your choice. You can only select one option.",
            color=0x0000ff,
        )
        message = await ctx.send(embed=rank_embed)
        poll_messages.append(message)

        emojis = [f"{i + 1}\u20E3" for i in range(len(options))]
        for emoji in emojis:
            await message.add_reaction(emoji)

    results_embed = discord.Embed(
        title="Current Results",
        description="Results will update as votes are cast.",
        color=0xffa500,
    )
    results_message = await ctx.send(embed=results_embed)

    poll_data["poll_messages"] = poll_messages
    poll_data["results_message"] = results_message
    bot.poll_data[results_message.id] = poll_data

@bot.event
async def on_reaction_add(reaction, user):
    """Handle reactions for ranking slots and enforce one reaction per user."""
    if user.bot:
        return

    # Find the poll
    for poll_id, poll in bot.poll_data.items():
        if reaction.message.id in [msg.id for msg in poll["poll_messages"]]:
            break
    else:
        return

    rank_index = poll["poll_messages"].index(reaction.message)
    message = poll["poll_messages"][rank_index]
    
    try:
        # Remove any existing reactions from this user on this ranking message
        if user.id in poll["user_reactions"][rank_index]:
            old_emoji = poll["user_reactions"][rank_index][user.id]
            if old_emoji != str(reaction.emoji):
                await message.remove_reaction(old_emoji, user)

        # Update the tracking of user reactions
        poll["user_reactions"][rank_index][user.id] = str(reaction.emoji)

        # Record the vote
        emoji_index = [f"{i + 1}\u20E3" for i in range(len(poll["options"]))].index(reaction.emoji)
        option = poll["options"][emoji_index]
        poll["votes"][rank_index][user.id] = option

        await update_results_message(poll)
        
    except (discord.HTTPException, discord.Forbidden, discord.NotFound, TypeError) as e:
        print(f"Error handling reaction: {e}")

@bot.event
async def on_reaction_remove(reaction, user):
    """Handle the removal of reactions to update votes."""
    if user.bot:
        return

    for poll_id, poll in bot.poll_data.items():
        if reaction.message.id in [msg.id for msg in poll["poll_messages"]]:
            break
    else:
        return

    rank_index = poll["poll_messages"].index(reaction.message)

    # Remove the user's reaction tracking
    if user.id in poll["user_reactions"][rank_index]:
        del poll["user_reactions"][rank_index][user.id]

    # Remove the vote
    if user.id in poll["votes"][rank_index]:
        del poll["votes"][rank_index][user.id]

    await update_results_message(poll)

async def update_results_message(poll):
    """Update the live results message with a bar graph, elimination rounds, and sorted order."""
    rankings = {user_id: [] for rank_votes in poll["votes"].values() for user_id in rank_votes.keys()}
    for rank, rank_votes in poll["votes"].items():
        for user_id, option in rank_votes.items():
            rankings[user_id].append(option)

    winner, final_vote_counts, elimination_order = ranked_choice_voting(poll["options"], rankings)

    color_blocks = {
        1: '🟩',
        2: '🟨',
        3: '🟦',
        4: '🟥',
        5: '🟧',
        6: '🟪',
        7: '🟫',
        8: '🟩🟩',
        9: '🟨🟨',
        10: '🟦🟦',
    }

    max_votes = max(final_vote_counts.values(), default=1)
    sorted_options = []

    elimination_round_dict = {option: round for option, round in elimination_order}

    if winner:
        sorted_options.append((winner, final_vote_counts[winner], 0))

    for option, count in final_vote_counts.items():
        if option != winner:
            round_eliminated = elimination_round_dict.get(option, len(poll["options"]) + 1)
            sorted_options.append((option, count, round_eliminated))

    graph = ""
    for option, count, round_eliminated in sorted_options:
        vote_rank = min(count, 10)
        emoji = color_blocks.get(vote_rank, '⬛')
        graph += f"{option}: {count} votes {emoji * (count * 10 // max_votes)}"
        if round_eliminated == 0:
            graph += " (Winner)"
        else:
            graph += f" (Eliminated in Round {round_eliminated})"
        graph += "\n"

    results_embed = discord.Embed(
        title="Current Results (Ranked Choice Voting)",
        description=graph,
        color=0xffa500
    )
    await poll["results_message"].edit(embed=results_embed)

def ranked_choice_voting(options, rankings):
    """Perform ranked-choice voting."""
    vote_counts = {option: 0 for option in options}
    elimination_order = []
    round_number = 1

    while True:
        for votes in rankings.values():
            if votes:
                vote_counts[votes[0]] += 1

        total_votes = sum(vote_counts.values())
        for option, count in vote_counts.items():
            if count > total_votes / 2:
                return option, vote_counts, elimination_order

        min_votes = min(vote_counts.values())
        eliminated = [option for option, count in vote_counts.items() if count == min_votes]

        if len(eliminated) == len(vote_counts):
            return None, vote_counts, elimination_order

        for option in eliminated:
            elimination_order.append((option, round_number))
            del vote_counts[option]
            for user_id in rankings.keys():
                if option in rankings[user_id]:
                    rankings[user_id].remove(option)

        vote_counts = {option: 0 for option in vote_counts.keys()}
        round_number += 1

bot.poll_data = {}
bot.run("")
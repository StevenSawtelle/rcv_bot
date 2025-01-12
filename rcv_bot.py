import discord
from discord.ext import commands
import asyncio

intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # Enable message content access
intents.reactions = True  # Enable reaction events

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

    # Initial message: show poll options
    options_text = "\n".join(f"{i + 1}. {option}" for i, option in enumerate(options))
    options_embed = discord.Embed(
        title=title, description=f"Available options:\n{options_text}", color=0x00ff00
    )
    await ctx.send(embed=options_embed)

    # Create ranking messages
    poll_data = {
        "options": options,
        "votes": {i: {} for i in range(rankings)},  # Votes by ranking slot
    }
    poll_messages = []

    for rank in range(1, rankings + 1):
        rank_embed = discord.Embed(
            title=f"Rank {rank}",
            description="React with the emoji corresponding to your choice.",
            color=0x0000ff,
        )
        message = await ctx.send(embed=rank_embed)
        poll_messages.append(message)

        # Add reactions for the options
        emojis = [f"{i + 1}\u20E3" for i in range(len(options))]
        for emoji in emojis:
            await message.add_reaction(emoji)

    # Create a live results message
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
    """Handle reactions for ranking slots."""
    if user.bot:
        return

    # Find the poll
    for poll_id, poll in bot.poll_data.items():
        if reaction.message.id in [msg.id for msg in poll["poll_messages"]]:
            break
    else:
        return

    rank_index = poll["poll_messages"].index(reaction.message)
    emoji_index = [f"{i + 1}\u20E3" for i in range(len(poll["options"]))].index(reaction.emoji)
    option = poll["options"][emoji_index]

    # Record the vote
    if user.id not in poll["votes"][rank_index]:
        poll["votes"][rank_index][user.id] = option
    else:
        poll["votes"][rank_index][user.id] = option  # Overwrite existing vote

    # Update live results
    await update_results_message(poll)

@bot.event
async def on_reaction_remove(reaction, user):
    """Handle the removal of reactions to update votes."""
    print("remove called")
    if user.bot:
        return

    # Identify the poll associated with the reaction
    for poll_id, poll in bot.poll_data.items():
        if reaction.message.id in [msg.id for msg in poll["poll_messages"]]:
            break
    else:
        return  # Reaction is not part of any tracked poll

    # Determine which ranking slot the reaction was in
    rank_index = poll["poll_messages"].index(reaction.message)
    print("rank_index, ", rank_index)

    # Map the reaction emoji to the corresponding option
    try:
        emoji_index = [f"{i + 1}\u20E3" for i in range(len(poll["options"]))].index(reaction.emoji)
    except ValueError:
        print("The reaction emoji is not relevant to the poll")
        return  

    option = poll["options"][emoji_index]
    print("option", option)

    # Remove the user's vote for this specific option in the ranking slot
    if user.id in poll["votes"][rank_index] and poll["votes"][rank_index][user.id] == option:
        del poll["votes"][rank_index][user.id]

    # Update the results message to reflect the change
    await update_results_message(poll)



async def update_results_message(poll):
    """Update the live results message with a bar graph, elimination rounds, and sorted order."""
    # Collect all user rankings
    rankings = {user_id: [] for rank_votes in poll["votes"].values() for user_id in rank_votes.keys()}
    for rank, rank_votes in poll["votes"].items():
        for user_id, option in rank_votes.items():
            rankings[user_id].append(option)

    # Perform ranked-choice voting
    winner, final_vote_counts, elimination_order = ranked_choice_voting(poll["options"], rankings)

    # Define color blocks for each vote rank
    color_blocks = {
        1: '🟩',  # Green Square for first-place votes
        2: '🟨',  # Yellow Square for second-place votes
        3: '🟦',  # Blue Square for third-place votes
        4: '🟥',  # Red Square for fourth-place votes
        5: '🟧',  # Orange Square for fifth-place votes
        6: '🟪',  # Purple Square for sixth-place votes
        7: '🟫',  # Brown Square for seventh-place votes
        8: '🟩🟩',  # Double Green Square for eighth-place votes
        9: '🟨🟨',  # Double Yellow Square for ninth-place votes
        10: '🟦🟦',  # Double Blue Square for tenth-place votes
    }

    # Build the results as a bar graph
    max_votes = max(final_vote_counts.values(), default=1)
    sorted_options = []

    # Sort options by the elimination round and then the vote count for the winner
    elimination_round_dict = {option: round for option, round in elimination_order}

    # First, include the winner at the top
    if winner:
        sorted_options.append((winner, final_vote_counts[winner], 0))  # Winner in round 0

    # Then add the eliminated options sorted by round of elimination
    for option, count in final_vote_counts.items():
        if option != winner:
            round_eliminated = elimination_round_dict.get(option, len(poll["options"]) + 1)
            sorted_options.append((option, count, round_eliminated))

    # Generate the graph with elimination round and bar
    graph = ""
    for option, count, round_eliminated in sorted_options:
        # Determine the emoji for the vote rank
        vote_rank = min(count, 10)  # Limit to 10 to avoid exceeding the color_blocks dictionary
        emoji = color_blocks.get(vote_rank, '⬛')  # Default to black square if rank exceeds 10
        graph += f"{option}: {count} votes {emoji * (count * 10 // max_votes)}"
        if round_eliminated == 0:
            graph += " (Winner)"
        else:
            graph += f" (Eliminated in Round {round_eliminated})"
        graph += "\n"

    # Update the live results message
    results_embed = discord.Embed(
        title="Current Results (Ranked Choice Voting)",
        description=graph,
        color=0xffa500
    )
    await poll["results_message"].edit(embed=results_embed)





def ranked_choice_voting(options, rankings):
    """
    Perform ranked-choice voting.
    
    :param options: List of options in the poll.
    :param rankings: Dictionary of user rankings {user_id: [rank1, rank2, ...]}.
    :return: (winner, vote_counts, elimination_order)
    """
    vote_counts = {option: 0 for option in options}
    elimination_order = []
    round_number = 1

    while True:
        # Tally first-choice votes
        for votes in rankings.values():
            if votes:  # Check if the user still has valid rankings
                vote_counts[votes[0]] += 1

        # Check for a majority
        total_votes = sum(vote_counts.values())
        for option, count in vote_counts.items():
            if count > total_votes / 2:
                return option, vote_counts, elimination_order

        # Find the option(s) with the fewest votes
        min_votes = min(vote_counts.values())
        eliminated = [option for option, count in vote_counts.items() if count == min_votes]

        if len(eliminated) == len(vote_counts):
            # If all remaining options are tied, return no clear winner
            return None, vote_counts, elimination_order

        # Eliminate the option(s) with the fewest votes
        for option in eliminated:
            elimination_order.append((option, round_number))  # Track the round of elimination
            del vote_counts[option]
            for user_id in rankings.keys():
                if option in rankings[user_id]:
                    rankings[user_id].remove(option)

        # Reset vote counts for the next round
        vote_counts = {option: 0 for option in vote_counts.keys()}
        round_number += 1


bot.poll_data = {}
bot.run("token")

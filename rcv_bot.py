import discord
import matplotlib.pyplot as plt
import io
from discord.ext import commands
import asyncio
from copy import deepcopy
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def simulate_votes(ctx):
    poll_id = list(bot.poll_data.keys())[0]  # Get the first poll (adjust as needed)
    poll = bot.poll_data[poll_id]
    
    # Ensure options align with poll's actual options
    options = poll["options"]  # This should match the parsed options from the poll
    simulated_rankings = {
        1: [options[0], options[1], options[2], options[3]], # e f g c
        2: [options[0], options[1], options[2], options[3]], # e f g c
        3: [options[0], options[1], options[2], options[3]], # e f g c
        4: [options[1], options[0], options[2], options[3]], # f e g c
        5: [options[1], options[0], options[2], options[3]], # f e g c
        6: [options[1], options[0], options[2], options[3]], # f e g c
        7: [options[2], options[0], options[1], options[3]], # g e f c
        8: [options[2], options[0], options[1], options[3]], # g e f c
        9: [options[3], options[1], options[0], options[2]], # c f e g
    }

    for user_id, ranks in simulated_rankings.items():
        for rank, option in enumerate(ranks):
            poll["votes"].setdefault(rank, {})[user_id] = option

    await update_results_message(poll)
    await ctx.send("Simulated votes added and results updated!")


@bot.command()
async def ranked_poll(ctx, title: str, rankings: int, *raw_options):
    """Create a ranked-choice voting poll with options formatted with backslashes."""
    # Validate input
    if len(raw_options) < 2:
        await ctx.send("You need at least two options to create a ranked poll!")
        return
    if len(raw_options) > 10:
        await ctx.send("You can only have up to 10 options.")
        return
    if rankings < 1 or rankings > len(raw_options):
        await ctx.send("Rankings must be at least 1 and no more than the number of options.")
        return

    # Parse options
    options = [opt.strip() for opt in ' '.join(raw_options).split('\\') if opt.strip()]
    logging.debug(f"Parsed options: {options}")
    
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
    options_embed = discord.Embed(title=title, description=f"Available options:\n{options_text}", color=0x00ff00)
    
    # Create poll message and thread
    poll_message = await ctx.send(embed=options_embed)
    poll_thread = await poll_message.create_thread(name=f"Poll - {title}")

    poll_data = {
        "options": options,
        "votes": {i: {} for i in range(rankings)},
        "user_reactions": {i: {} for i in range(rankings)},
    }
    poll_messages = []
    for rank in range(1, rankings + 1):
        rank_embed = discord.Embed(
            title=f"Rank {rank}",
            description="React with the emoji corresponding to your choice. You can only select one option.",
            color=0x0000ff,
        )
        rank_message = await poll_thread.send(embed=rank_embed)
        poll_messages.append(rank_message)

        emojis = [f"{i + 1}\u20E3" for i in range(len(options))]

        await rank_message.clear_reactions()

        for emoji in emojis:
            try:
                await rank_message.add_reaction(emoji)
            except discord.Forbidden:
                print("Bot lacks permission to manage reactions.")

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
    """Handle reactions for ranking slots and enforce one reaction per user, no additional reactions, and no duplicate votes."""
    if user.bot:
        return

    # Log reaction details
    logging.debug(f"Reaction added: {reaction.emoji} by {user.name}")

    for poll_id, poll in bot.poll_data.items():
        if reaction.message.id in [msg.id for msg in poll["poll_messages"]]:
            break
    else:
        return

    rank_index = poll["poll_messages"].index(reaction.message)
    message = poll["poll_messages"][rank_index]

    allowed_emojis = [f"{i + 1}\u20E3" for i in range(len(poll["options"]))]
    if str(reaction.emoji) not in allowed_emojis:
        await message.remove_reaction(reaction.emoji, user)
        return

    try:
        # Track user's voted options
        voted_options = set([poll["votes"][rank][user.id] for rank in range(len(poll["votes"])) if user.id in poll["votes"][rank]])

        emoji_index = allowed_emojis.index(reaction.emoji)
        option = poll["options"][emoji_index]
        
        # Log the user's vote attempt
        logging.debug(f"User {user.name} is voting for {option} in rank {rank_index + 1}")

        if option in voted_options:
            await message.remove_reaction(reaction.emoji, user)
            await user.send(f"You cannot vote for the same option in multiple ranks!")
            return

        # Remove previous reactions
        if user.id in poll["user_reactions"][rank_index]:
            old_emoji = poll["user_reactions"][rank_index][user.id]
            if old_emoji != str(reaction.emoji):
                await message.remove_reaction(old_emoji, user)

        # Update user reactions
        poll["user_reactions"][rank_index][user.id] = str(reaction.emoji)
        poll["votes"][rank_index][user.id] = option

        await update_results_message(poll)
        
    except Exception as e:
        logging.error(f"Error handling reaction: {e}")


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

    # Log the removal of a reaction
    logging.debug(f"Reaction removed: {reaction.emoji} by {user.name}")

    if user.id in poll["user_reactions"][rank_index]:
        del poll["user_reactions"][rank_index][user.id]

    if user.id in poll["votes"][rank_index]:
        del poll["votes"][rank_index][user.id]

    await update_results_message(poll)


async def update_results_message(poll):
    """Update the live results message with a dynamically generated bar chart."""
    rankings = {user_id: [] for rank_votes in poll["votes"].values() for user_id in rank_votes.keys()}
    for rank, rank_votes in poll["votes"].items():
        for user_id, option in rank_votes.items():
            rankings[user_id].append(option)

    winners, final_rankings, elimination_order = ranked_choice_voting(poll["options"], rankings)

    # Prepare data for the bar chart
    final_rankings.sort(key=lambda x: (-x[2], x[1]))  # Sort by votes (desc), then by rank (asc)
    options = [opt for opt, _, _ in final_rankings]
    votes = [v for _, _, v in final_rankings]

    # Create the bar chart with improved aesthetics
    plt.figure(figsize=(12, 8))
    bars = plt.barh(options, votes, color="cornflowerblue", edgecolor="black")

    # Add value labels to the bars
    for bar in bars:
        plt.text(
            bar.get_width() + 0.1,  # Position slightly to the right of the bar
            bar.get_y() + bar.get_height() / 2,  # Center vertically
            f"{int(bar.get_width())}",  # Display the vote count
            va="center",
            fontsize=10,
            color="black",
        )

    # Enhance axis labels and title
    plt.xlabel("Votes", fontsize=14, weight="bold")
    plt.ylabel("Options", fontsize=14, weight="bold")
    plt.title("Poll Results", fontsize=16, weight="bold")

    # Adjust layout for better readability
    plt.gca().invert_yaxis()  # Invert y-axis to show the highest vote at the top
    plt.grid(axis="x", linestyle="--", alpha=0.7)
    plt.tight_layout()

    # Save the plot to a BytesIO object
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=300)
    buf.seek(0)
    plt.close()

    # Generate elimination details
    elimination_details = "\n".join(f"Round {round_num}: {option}" for option, round_num in elimination_order)

    # Send the bar chart as an image in the embed
    file = discord.File(buf, filename="results.png")
    results_embed = discord.Embed(
        title="Current Poll Results",
        description=f"See the attached chart for the current standings.\n\nElimination Details:\n{elimination_details}",
        color=0xffa500,
    )
    results_embed.set_image(url="attachment://results.png")

    await poll["results_message"].edit(embed=results_embed, attachments=[file])



def ranked_choice_voting(options, rankings):
    """Perform ranked-choice voting with detailed logging for debugging."""
    remaining_options = list(options)
    elimination_order = []
    final_rankings = []
    round_number = 1
    current_rankings = deepcopy(rankings)
    
    while remaining_options:
        vote_counts = {option: 0 for option in remaining_options}
        for voter_ranks in current_rankings.values():
            for option in voter_ranks:
                if option in remaining_options:
                    vote_counts[option] += 1
                    break

        total_votes = sum(vote_counts.values())
        if total_votes == 0:
            rank = len(options) - len(final_rankings)
            final_rankings.extend((opt, rank, 0) for opt in remaining_options)
            for option in remaining_options:
                elimination_order.append((option, round_number))
            break

        majority_threshold = total_votes / 2
        winners = [opt for opt, count in vote_counts.items() if count > majority_threshold]
        
        # Log vote counts and winners
        logging.debug(f"Round {round_number}: Vote counts: {vote_counts}")
        logging.debug(f"Round {round_number}: Winners: {winners}")

        if winners:
            rank = len(options) - len(final_rankings)
            final_rankings.extend((opt, rank, vote_counts[opt]) for opt in winners)
            remaining = set(remaining_options) - set(winners)
            remaining_sorted = sorted(remaining, key=lambda x: vote_counts[x], reverse=True)
            for option in remaining_sorted:
                final_rankings.append((option, rank + 1, vote_counts[option]))
                elimination_order.append((option, round_number))
            return winners, final_rankings, elimination_order

        min_votes = min(vote_counts.values())
        to_eliminate = [opt for opt, count in vote_counts.items() if count == min_votes]

        rank = len(options) - len(final_rankings)
        for option in to_eliminate:
            final_rankings.append((option, rank, vote_counts[option]))
            elimination_order.append((option, round_number))
            remaining_options.remove(option)
        
        round_number += 1
        
        if len(remaining_options) == 1:
            winner = remaining_options[0]
            final_rankings.append((winner, 1, vote_counts[winner]))
            return [winner], final_rankings, elimination_order
    
    return [], final_rankings, elimination_order


# Read bot token from a secret file
with open("secret.txt", "r") as file:
    bot_token = file.read().strip()

bot.poll_data = {}
bot.run(bot_token)
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

# font for charts
plt.rcParams["font.family"] = "American Typewriter"  # Replace with a fun font available in your environment

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def simulate_votes(ctx, choice):
    poll_id = list(bot.poll_data.keys())[0]  # Get the first poll (adjust as needed)
    poll = bot.poll_data[poll_id]
    
    # Ensure options align with poll's actual options
    options = poll["options"]  # This should match the parsed options from the poll
    #basic test
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
    if choice == '2':
        # tie breaker test
        simulated_rankings = {
            1: [options[0], options[1], options[2], options[3]], # e f g c
            2: [options[0], options[1], options[2], options[3]], # e f g c
            3: [options[0], options[1], options[2], options[3]], # e f g c
            4: [options[1], options[0], options[2], options[3]], # f e g c
            5: [options[1], options[0], options[2], options[3]], # f e g c
            6: [options[1], options[0], options[2], options[3]], # f e g c
            7: [options[2], options[0], options[1], options[3]], # g e f c
            8: [options[2], options[0], options[1], options[3]], # g e f c
            9: [options[3], options[2], options[1], options[0]], # c g f e
        }

    for user_id, ranks in simulated_rankings.items():
        for rank, option in enumerate(ranks):
            poll["votes"].setdefault(rank, {})[user_id] = option

    await update_results_message(poll)
    # await ctx.send("Simulated votes added and results updated!")


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
    results_thread = await results_message.create_thread(name="Poll Results")


    poll_data["poll_messages"] = poll_messages
    poll_data["results_message"] = results_message
    poll_data["results_thread"] = results_thread
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
    """Update the thread with messages showing the vote spread at each round."""
    rankings = {user_id: [] for rank_votes in poll["votes"].values() for user_id in rank_votes.keys()}
    for rank, rank_votes in poll["votes"].items():
        for user_id, option in rank_votes.items():
            rankings[user_id].append(option)

    winners, final_rankings, elimination_order, all_vote_counts = ranked_choice_voting(poll["options"], rankings)

    # Assign consistent colors to options
    options_color_map = {option: plt.cm.tab10(i % 10) for i, option in enumerate(poll["options"])}

    # Update the main results message
    results_embed = discord.Embed(
        title="Current Results",
        description=f"Current winner is {winners[0]}! See thread for round-by-round breakdown.",
        color=0xffa500
    )
    await poll["results_message"].edit(embed=results_embed)

    # Maintain a list of result messages to update or create new ones if necessary
    if "result_messages" not in poll:
        poll["result_messages"] = []

    for round_index, round_data in enumerate(elimination_order):
        round_num = round_index + 1

        options = [item[0] for item in final_rankings]
        vote_counts = [all_vote_counts[round_index].get(option, 0) for option in options]

        # Sort options and vote_counts by vote_counts in descending order
        sorted_data = sorted(zip(options, vote_counts), key=lambda x: x[1], reverse=True)
        sorted_options, sorted_vote_counts = zip(*sorted_data)

        eliminated_option = round_data[0]  # Get the eliminated option for this round

        # Generate the bar chart
        plt.figure(figsize=(8, 6))
        bars = plt.barh(
            sorted_options,
            sorted_vote_counts,
            color=[options_color_map[option] for option in sorted_options],
            edgecolor="black"
        )

        # Adjust text inside the bounding box of the graph
        for bar in bars:
            plt.text(
                bar.get_width() - 0.2 if bar.get_width() > 0.5 else bar.get_width() + 0.2,
                bar.get_y() + bar.get_height() / 2,
                f"{int(bar.get_width())}",
                va="center",
                ha="right" if bar.get_width() > 0.5 else "left",
                fontsize=12,
                weight="bold",
                color="darkblue"
            )

        # Wrap long option text on spaces only
        def wrap_text(text, width=20):
            words = text.split()
            lines, current_line = [], ""
            for word in words:
                if len(current_line) + len(word) + 1 > width:
                    lines.append(current_line.strip())
                    current_line = word
                else:
                    current_line += " " + word
            lines.append(current_line.strip())
            return "\n".join(lines)

        wrapped_options = [wrap_text(opt, width=20) for opt in sorted_options]
        plt.gca().set_yticks(range(len(wrapped_options)))
        plt.gca().set_yticklabels(wrapped_options, fontsize=12, color="darkblue", weight="bold")

        plt.xlabel("Votes", fontsize=16, weight="bold", labelpad=10, color="darkblue")
        plt.ylabel("Options", fontsize=16, weight="bold", labelpad=10, color="darkblue")
        plt.title(f"Poll Results - Round {round_num}", fontsize=20, weight="bold", color="navy")
        plt.gca().invert_yaxis()
        plt.gca().xaxis.set_major_locator(plt.MaxNLocator(integer=True))
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=200)
        buf.seek(0)
        plt.close()

        # Update an existing message or send a new one
        if round_index < len(poll["result_messages"]):
            message_to_edit = poll["result_messages"][round_index]
            file = discord.File(buf, filename=f"results_round_{round_num}.png")
            embed = discord.Embed(
                title=f"Poll Results - Round {round_num}",
                description=f"{eliminated_option} eliminated. Vote distribution for this round:",
                color=0xffa500,
            )
            embed.set_image(url=f"attachment://results_round_{round_num}.png")
            await message_to_edit.edit(embed=embed, attachments=[file])
        else:
            file = discord.File(buf, filename=f"results_round_{round_num}.png")
            embed = discord.Embed(
                title=f"Poll Results - Round {round_num}",
                description=f"{eliminated_option} eliminated. Vote distribution for this round:",
                color=0xffa500,
            )
            embed.set_image(url=f"attachment://results_round_{round_num}.png")
            new_message = await poll["results_thread"].send(embed=embed, file=file)
            poll["result_messages"].append(new_message)


def ranked_choice_voting(options, rankings):
    """Perform ranked-choice voting with cumulative ranking for tie-breaking."""
    remaining_options = list(options)
    elimination_order = []
    final_rankings = []
    round_number = 1
    current_rankings = deepcopy(rankings)
    all_vote_counts = []

    while remaining_options:
        vote_counts = {option: 0 for option in remaining_options}
        for voter_ranks in current_rankings.values():
            for option in voter_ranks:
                if option in remaining_options:
                    vote_counts[option] += 1
                    break
        all_vote_counts.append(vote_counts)

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
            return winners, final_rankings, elimination_order, all_vote_counts

        min_votes = min(vote_counts.values())
        to_eliminate = [opt for opt, count in vote_counts.items() if count == min_votes]

        if len(to_eliminate) > 1:
            # Handle ties using cumulative ranking
            cumulative_rankings = {option: 0 for option in options}
            for voter_ranks in rankings.values():
                for position, option in enumerate(voter_ranks):
                    cumulative_rankings[option] += len(options) - position

            print("cumulative_rankings")
            print(cumulative_rankings)

            to_eliminate = [
                min(to_eliminate, key=lambda opt: cumulative_rankings[opt])
            ]
            print("to_eliminate")
            print(to_eliminate)


        rank = len(options) - len(final_rankings)
        for option in to_eliminate:
            final_rankings.append((option, rank, vote_counts[option]))
            elimination_order.append((option, round_number))
            remaining_options.remove(option)

        round_number += 1

        if len(remaining_options) == 1:
            winner = remaining_options[0]
            final_rankings.append((winner, 1, vote_counts[winner]))
            return [winner], final_rankings, elimination_order, all_vote_counts

    return [], final_rankings, elimination_order, all_vote_counts


# Read bot token from a secret file
with open("secret.txt", "r") as file:
    bot_token = file.read().strip()

bot.poll_data = {}
bot.run(bot_token)
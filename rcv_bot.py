import discord
from discord.ext import commands
import asyncio
from copy import deepcopy

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
    """Handle reactions for ranking slots and enforce one reaction per user, no additional reactions, and no duplicate votes for the same option."""
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
    
    # List of allowed emojis for this poll
    allowed_emojis = [f"{i + 1}\u20E3" for i in range(len(poll["options"]))]

    # If the reaction is not allowed, remove it
    if str(reaction.emoji) not in allowed_emojis:
        await message.remove_reaction(reaction.emoji, user)
        return

    try:
        # Track all options that the user has voted for in any rank
        voted_options = set([poll["votes"][rank][user.id] for rank in range(len(poll["votes"])) if user.id in poll["votes"][rank]])

        # If the user has already voted for this option in another rank, remove the reaction and send a message
        emoji_index = allowed_emojis.index(reaction.emoji)
        option = poll["options"][emoji_index]
        if option in voted_options:
            await message.remove_reaction(reaction.emoji, user)
            await user.send(f"You cannot vote for the same option in multiple ranks!")
            return

        # Remove any existing reactions from this user on this ranking message
        if user.id in poll["user_reactions"][rank_index]:
            old_emoji = poll["user_reactions"][rank_index][user.id]
            if old_emoji != str(reaction.emoji):
                await message.remove_reaction(old_emoji, user)

        # Update the tracking of user reactions
        poll["user_reactions"][rank_index][user.id] = str(reaction.emoji)

        # Record the vote
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
    """Update the live results message with proper tie handling and ordering."""
    rankings = {user_id: [] for rank_votes in poll["votes"].values() for user_id in rank_votes.keys()}
    for rank, rank_votes in poll["votes"].items():
        for user_id, option in rank_votes.items():
            rankings[user_id].append(option)

    winners, final_rankings, elimination_order = ranked_choice_voting(poll["options"], rankings)

    # Create results display
    graph = ""
    max_votes = max((votes for _, _, votes in final_rankings), default=1)
    
    # Group results by rank
    rank_groups = {}
    for option, rank, votes in final_rankings:
        if rank not in rank_groups:
            rank_groups[rank] = []
        rank_groups[rank].append((option, votes))
    
    # Display results in order of rank
    for rank in sorted(rank_groups.keys()):
        options_in_rank = rank_groups[rank]
        
        # Sort options within same rank by votes
        options_in_rank.sort(key=lambda x: (-x[1], x[0]))  # Sort by votes (desc) then name
        
        for option, votes in options_in_rank:
            # Create vote bar
            vote_percentage = votes * 10 // max(max_votes, 1)
            bar = "🟩" * max(1, vote_percentage)
            
            # Add status label
            if option in winners:
                status = " (Winner)"
                if len(winners) > 1:
                    status = " (Tied Winner)"
            else:
                round_eliminated = next(round_num for opt, round_num in elimination_order if opt == option)
                status = f" (Eliminated in Round {round_eliminated}"
                
                # Check for ties in same elimination round
                same_round = [opt for opt, rnd in elimination_order if rnd == round_eliminated]
                if len(same_round) > 1:
                    status += " - Tied"
                status += ")"
            
            graph += f"{option}: {votes} votes {bar}{status}\n"
    
    results_embed = discord.Embed(
        title="Current Results (Ranked Choice Voting)",
        description=graph,
        color=0xffa500
    )
    await poll["results_message"].edit(embed=results_embed)

def get_preference_count(option, rank, rankings):
    """Count how many times an option appears at a specific rank."""
    count = 0
    for voter_ranks in rankings.values():
        if len(voter_ranks) > rank and voter_ranks[rank] == option:
            count += 1
    return count

def break_tie(tied_options, rankings, round_number):
    """
    Break ties by looking at next preference votes.
    Returns the options in order from should-be-eliminated-first to should-be-eliminated-last.
    """
    max_rank = max(len(ranks) for ranks in rankings.values())
    
    # For each rank level, get counts for each tied option
    for rank in range(max_rank):
        rank_counts = {option: get_preference_count(option, rank, rankings) for option in tied_options}
        
        # If counts differ at this rank, sort by these counts
        if len(set(rank_counts.values())) > 1:
            return sorted(tied_options, key=lambda x: rank_counts[x])
    
    # If we get here, it's a true tie at all ranks
    return sorted(tied_options)  # Sort alphabetically for consistent ordering

def ranked_choice_voting(options, rankings):
    """
    Perform ranked-choice voting with proper tie detection and ordering.
    Returns:
    - winners: List of winning options (can be multiple in case of tie)
    - final_rankings: List of tuples (options, rank, votes) in order of finish
    - elimination_order: List of (option, round_number) in order of elimination
    """
    remaining_options = list(options)
    elimination_order = []
    final_rankings = []
    round_number = 1
    current_rankings = deepcopy(rankings)
    
    while remaining_options:
        # Count first-choice votes
        vote_counts = {option: 0 for option in remaining_options}
        for voter_ranks in current_rankings.values():
            for option in voter_ranks:
                if option in remaining_options:
                    vote_counts[option] += 1
                    break
        
        total_votes = sum(vote_counts.values())
        if total_votes == 0:
            # No more valid votes, remaining options are tied for last
            rank = len(options) - len(final_rankings)
            final_rankings.extend((opt, rank, 0) for opt in remaining_options)
            for option in remaining_options:
                elimination_order.append((option, round_number))
            break
        
        # Check for winners (options with > 50% of votes)
        majority_threshold = total_votes / 2
        winners = [opt for opt, count in vote_counts.items() if count > majority_threshold]
        
        if winners:
            # We have winner(s)
            rank = len(options) - len(final_rankings)
            final_rankings.extend((opt, rank, vote_counts[opt]) for opt in winners)
            
            # Rank remaining options by their final vote counts
            remaining = set(remaining_options) - set(winners)
            if remaining:
                remaining_sorted = sorted(remaining, key=lambda x: vote_counts[x], reverse=True)
                current_votes = None
                current_rank = rank + 1
                
                for option in remaining_sorted:
                    if current_votes != vote_counts[option]:
                        current_votes = vote_counts[option]
                        current_rank = len(options) - len(final_rankings)
                    final_rankings.append((option, current_rank, vote_counts[option]))
                    elimination_order.append((option, round_number))
            
            return winners, final_rankings, elimination_order
        
        # Find options with fewest votes
        min_votes = min(vote_counts.values())
        to_eliminate = [opt for opt, count in vote_counts.items() if count == min_votes]
        
        # All options with same minimum votes are eliminated together
        rank = len(options) - len(final_rankings)
        for option in to_eliminate:
            final_rankings.append((option, rank, vote_counts[option]))
            elimination_order.append((option, round_number))
            remaining_options.remove(option)
        
        round_number += 1
        
        # If only one option remains, it's the winner
        if len(remaining_options) == 1:
            winner = remaining_options[0]
            final_rankings.append((winner, 1, vote_counts[winner]))
            return [winner], final_rankings, elimination_order
    
    return [], final_rankings, elimination_order



bot.poll_data = {}
bot.run("")
import discord
from discord.ext import commands, tasks 
import json
import os
import asyncio
from datetime import datetime, timedelta
import random
import time
import itertools

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)

BUX_FILE = 'bux.json'
BACKUP_DIR = "backups"
LAST_BACKUP_FILE = os.path.join(BACKUP_DIR, "last_backup.txt")

if not os.path.exists(BUX_FILE):
    with open(BUX_FILE, 'w') as f:
        json.dump({}, f, indent=4)

if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

def load_bux():
    try:
        with open(BUX_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        print("Error: Invalid or missing bux.json. Returning empty data.")
        return {}

def save_bux(data):
    with open(BUX_FILE, 'w') as f:
        json.dump(data, f, indent=4)

@bot.command()
async def d(ctx):
    """Claim daily bux."""
    user_id = str(ctx.author.id)
    bux_data = load_bux()
    now = datetime.utcnow()
    
    if user_id not in bux_data:
        bux_data[user_id] = {"username": ctx.author.name, "bux": 300, "last_claimed": now.strftime('%Y-%m-%d')}
        save_bux(bux_data)
        await ctx.send(f"Welcome {ctx.author.name}! You've received your first 300 bux. I'll automatically claim from now on.")
        return

    last_claimed = datetime.strptime(bux_data[user_id]["last_claimed"], '%Y-%m-%d')
    time_since_claim = now - last_claimed
    
    if time_since_claim < timedelta(days=1):
        time_left = timedelta(days=1) - time_since_claim
        hours, minutes = divmod(time_left.seconds, 3600)[0], divmod(time_left.seconds, 60)[0] % 60
        await ctx.send(f"You've already claimed your daily bux! Next claim in **{hours}h {minutes}m**. If you're bankrupt, try !b.")
        return
    
    bux_data[user_id]["bux"] += 300
    bux_data[user_id]["last_claimed"] = now.strftime('%Y-%m-%d')
    save_bux(bux_data)
    
    await ctx.send(f"{ctx.author.name}, you've received your daily 300 bux!")

@tasks.loop(hours=1)
async def daily_reward_task():
    """Process daily bux rewards and backups."""
    bux_data = load_bux()
    now = datetime.utcnow()
    
    try:
        with open(LAST_BACKUP_FILE, 'r') as file:
            last_backup = datetime.strptime(file.read().strip(), '%Y-%m-%d')
    except (FileNotFoundError, ValueError):
        last_backup = None

    if last_backup is None or now - last_backup >= timedelta(days=1):
        backup_filename = f"backup_{now.strftime('%Y-%m-%d')}.json"
        with open(os.path.join(BACKUP_DIR, backup_filename), 'w') as file:
            json.dump(bux_data, file)
        with open(LAST_BACKUP_FILE, 'w') as file:
            file.write(now.strftime('%Y-%m-%d'))
        
        backups = sorted(os.listdir(BACKUP_DIR))
        for old_backup in backups[:-5]:
            os.remove(os.path.join(BACKUP_DIR, old_backup))
    
    for user_id, data in bux_data.items():
        if now - datetime.strptime(data["last_claimed"], '%Y-%m-%d') >= timedelta(days=1):
            data["bux"] += 300
            data["last_claimed"] = now.strftime('%Y-%m-%d')
    
    save_bux(bux_data)
    print("Daily bux reward task completed.")

@bot.event
async def on_ready():
    await daily_event()
    print(f'Logged in as {bot.user}')
    if not daily_reward_task.is_running():
        daily_reward_task.start()

@bot.command()
async def c(ctx, member: discord.Member, bet: int):
    """!c <user> <amount> ( Challenge a user to a unique bet on your own with amount )"""
    player_id, opponent_id = ctx.author.id, member.id
    user_id, opponent_user_id = str(player_id), str(opponent_id)
    
    if is_in_bet(player_id) or is_in_bet(opponent_id):
        await ctx.send(f"{ctx.author.mention if is_in_bet(player_id) else member.mention} is already in an open bet.")
        return

    if not check_bux_entry(user_id):
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with !d before betting.")
        return

    if bet <= 0:
        await ctx.send("You must bet a positive amount of bux!")
        return
    
    if member == ctx.author:
        bet = 0
        await ctx.send(f"You're challenging yourself! Bet set to 0.")

    bux_data = load_bux()
    if bux_data.get(user_id, {}).get("bux", 0) < bet:
        await ctx.send("You don't have enough bux for this bet.")
        return

    bet_message = await ctx.send(f"{member.mention}, {ctx.author.mention} challenged you to a bet of {bet} bux! React with ✅ to accept or ❌ to decline.")
    await bet_message.add_reaction('✅')
    await bet_message.add_reaction('❌')

    def check_acceptance(reaction, user):
        return (
            user == member and str(reaction.emoji) in ['✅', '❌'] 
            and check_bux_entry(opponent_user_id) and has_enough_bux(opponent_user_id, bet)
        )

    try:
        reaction, _ = await bot.wait_for('reaction_add', check=check_acceptance, timeout=60.0)

        if str(reaction.emoji) == '✅':
            await ctx.send(f"{member.mention} accepted the bet! Both players must now react to determine the winner.")
            open_bets[player_id] = open_bets[opponent_id] = True  

            bet_message = await ctx.send(f"React ⚔️ for {ctx.author.mention} or 🛡️ for {member.mention}. Both must react the same or the bet is voided!")
            await bet_message.add_reaction('⚔️')
            await bet_message.add_reaction('🛡️')

            votes = {}

            def check_vote(reaction, user):
                return user in [ctx.author, member] and str(reaction.emoji) in ['⚔️', '🛡️']

            try:
                for _ in range(2):  # Wait for both players' votes
                    reaction, user = await bot.wait_for('reaction_add', check=check_vote)
                    votes[user.id] = str(reaction.emoji)

                if votes.get(player_id) == votes.get(opponent_id):  # Both agreed
                    winner = ctx.author if votes[player_id] == '⚔️' else member
                    loser = member if winner == ctx.author else ctx.author
                    await ctx.send(f"{winner.mention} wins the bet of {bet} bux!")

                    bux_data[user_id]["bux"] += bet if winner == ctx.author else -bet
                    bux_data[opponent_user_id]["bux"] += bet if winner == member else -bet
                    save_bux(bux_data)
                    await assign_role_based_on_bux(ctx, ctx.author)
                    await assign_role_based_on_bux(ctx, member)
                
                else:  # Players disagreed → Bet voided with a penalty
                    for user in [user_id, opponent_user_id]:
                        bux_data[user]["bux"] = max(0, bux_data[user]["bux"] - 25)
                    save_bux(bux_data)
                    await ctx.send("Bet voided! A 25 bux penalty has been applied to both players for flaking.")
                    
            except asyncio.TimeoutError:
                await ctx.send("Bet voided due to inactivity.")
        
        else:
            await ctx.send(f"{member.mention} declined the bet.")

    except asyncio.TimeoutError:
        await ctx.send(f"{member.mention} did not respond in time. Bet expired.")

    finally:
        open_bets[player_id] = open_bets[opponent_id] = False  


def has_enough_bux(user_id: str, amount: int) -> bool:
    """Checks if a user has enough bux to participate in a bet."""
    return load_bux().get(user_id, {}).get("bux", 0) >= amount

@bot.command()
async def h(ctx):
    """Custom help command. *** USE THIS FOR HELP ***"""
    help_message = """
        ***Ranks***
- Grandmaster🏆 30,000 bux
- Emerald❇️ 15,000 bux
- Diamond💎 7,000 bux
- Gold🏅  3,000 bux
- Silver🥈 1,000 bux
- Bronze🥉 0 bux

**How it works** : **Bot Commands**
- :moneybag:  **Daily**: `!d`  Claim your daily 300 Bux and it will automatically claim after, this is how you start! .)
- :boxing_glove: **Challenge**: `!c <user> <amount>` ( Bet a user to a unique bet (anything) and agree on a winner or pay fees ) 
- :ninja_tone1: **Steal**: `!s` (Attempt to steal, win a prize, or face a penalty.)
- :black_joker: **Blackjack**: `!bj` `<amount>` ( Bet on a game of blackjack )
- :basketball: **Parley** `!p` `<amount>` ( Place a parley on 3 players to get the most points )
- :money_with_wings: **Bank**: `!b` (Check the amount of bux you have) If your at 0 bux u can get welfare!. 
- 🏆**Leaderboards**: `!l` (Check your rank on the leaderboards.)
- :grey_question: **Help**: `!h` ( Shows this )
    """
    await ctx.send(help_message)

    
async def assign_role_based_on_bux(ctx, member):

    bux_data = load_bux()
    user_id = str(member.id)

    if user_id not in bux_data:
        await ctx.send(f"{member.mention} doesn't have any bux data.")
        return

    bux = bux_data[user_id]["bux"]
    
    role_name = (
        "Grandmaster🏆" if bux >= 30000 else
        "Emerald❇️" if bux >= 15000 else
        "Diamond💎" if bux >= 7000 else
        "Gold🏅" if bux >= 3000 else
        "Silver🥈" if bux >= 1000 else
        "Bronze🥉"
    )

    role = discord.utils.get(ctx.guild.roles, name=role_name)

    if not role:
        role = await ctx.guild.create_role(name=role_name, mentionable=True)

    current_role = next((r for r in member.roles if r.name == role_name), None)

    if current_role:
        return

    for rank in ["Grandmaster🏆", "Emerald❇️", "Diamond💎", "Gold🏅", "Silver🥈", "Bronze🥉"]:
        if current_role := next((r for r in member.roles if r.name == rank), None):
            await member.remove_roles(current_role)
            break

    await member.add_roles(role)
    await ctx.send(f"{member.mention} is now {role_name}!")

last_cooldown_message = {}

@bot.event
async def on_command_error(ctx, error):

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"You're missing `{error.param}` :D")
    
    elif isinstance(error, commands.BadArgument):
        await ctx.send("That's invalid, try again :D")
    
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("That command doesn't exist :P")
    
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("Stop tryna cheat :o")
    
    elif isinstance(error, commands.CommandOnCooldown):
        user_id = ctx.author.id
        current_time = time.time()

        last_message_time = last_cooldown_message.get(user_id, 0)

        if current_time - last_message_time >= 60:
            await ctx.send(f"{ctx.author.mention}, you are on cooldown! Try again in {round(error.retry_after, 2)} seconds.")
            last_cooldown_message[user_id] = current_time  # Update the timestamp

    else:
        await ctx.send("An unexpected error occurred.")
        raise error 

@bot.command()
async def addbux(ctx, member: discord.Member, bux: int):
    """Admin only command to add bux to a user"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You do not have the required permissions to use this command.")
        return

    bux_data = load_bux()
    user_id = str(member.id)

    if user_id not in bux_data:
        bux_data[user_id] = {"username": member.name, "bux": 0, "last_claimed": ""}

    bux_data[user_id]["bux"] += bux
    save_bux(bux_data)

    await ctx.send(f"Added {bux} bux to {member.name}.")

@bot.command()
async def removebux(ctx, member: discord.Member, bux: int):
    """Admin only command to remove bux from a user"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You do not have the required permissions to use this command.")
        return

    bux_data = load_bux()
    user_id = str(member.id)

    if user_id not in bux_data or bux_data[user_id]["bux"] < bux:
        await ctx.send(f"{member.name} doesn't have enough bux to remove.")
        return

    bux_data[user_id]["bux"] -= bux
    save_bux(bux_data)

    await ctx.send(f"Removed {bux} bux from {member.name}.")


@bot.command()
async def l(ctx):
    """!l (Check your rank on the leaderboards.)"""
    user_id = str(ctx.author.id)
    
    if not check_bux_entry(user_id):
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with `!d`")
        return

    bux_data = load_bux()
    sorted_bux = sorted(bux_data.items(), key=lambda x: x[1]["bux"], reverse=True)
    user_rank = next((index + 1 for index, (uid, _) in enumerate(sorted_bux) if uid == user_id), None)
    top_7 = sorted_bux[:7]
    leaderboard_message = "🏆 **Top 7** 🏆\n\n"
    rank = 1
    cached_members = {member.id: member for member in ctx.guild.members}

    for uid, data in top_7:
    
        user = await bot.fetch_user(uid)
        member = cached_members.get(uid) or await ctx.guild.fetch_member(uid)
        bux = data["bux"]
        leaderboard_message += f"**{rank}. {user.mention}** - {bux} bux\n"
        rank += 1

        await assign_role_based_on_bux(ctx, member)

    if user_rank:
        leaderboard_message += f"\n🔹 {ctx.author.mention}, you are ranked **#{user_rank}** on the leaderboard."

    await ctx.send(leaderboard_message)

open_bets = {}  # Format: {player_id: True/False}

def is_in_bet(player_id):
    return open_bets.get(player_id, False)  # Returns True if in an open bet, else False

def check_bux_entry(user_id):
    """Returns True if the user has an entry in bux_data, False otherwise."""
    bux_data = load_bux()
    return str(user_id) in bux_data

@bot.command()
async def b(ctx):
    """!b (Check the amount of bux you have) If your at 0 bux u can get welfare!"""
    user_id = str(ctx.author.id)

    if not check_bux_entry(user_id):
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with `!d`.")
        return

    bux_data = load_bux()

    if user_id in bux_data:
        bux = bux_data[user_id]["bux"]
        await ctx.send(f"{ctx.author.name}, you have {bux} bux.")
        
        if bux <= 0:
            await ctx.send(f"{ctx.author.name}, was approved for welfare and received 100 bux.")
            bux_data[user_id]["bux"] += 100  # Add welfare bux
            save_bux(bux_data)  # Save the updated bux data
            await assign_role_based_on_bux(ctx, ctx.author)  # Reassign roles based on updated bux


import random

@bot.command()
async def s(ctx, target: discord.User):
    """!s (Attempt to steal from another player, win a prize, or face a penalty.)"""

    player_id = ctx.author.id  
    player_name = ctx.author.name
    target_id = target.id
    target_name = target.name
    target_mention = target.mention  # Get the mention for the target player

    if not check_bux_entry(player_id):
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with `!d` before you can steal.")
        return

    bux_data = load_bux()

    if str(player_id) not in bux_data:
        await ctx.send("You don't have any bux to steal!")
        return

    if is_in_bet(player_id):
        await ctx.send(f"{ctx.author.mention}, you already have an open bet. Please wait until it's settled.")
        return  

    if str(target_id) not in bux_data or bux_data[str(target_id)]["bux"] <= 0:
        await ctx.send(f"{target_name} is broke! Try again in a minute!")
        return

    outcomes = [
        {"chance": 0.01, "result": "prize", "amount": 1000, "message": f"{player_name} got away with stealing **1000 bux** from {target_mention}!"}, 
        {"chance": 0.05, "result": "prize", "amount": 750, "message": f"{player_name} successfully stole **750 bux** from {target_mention}!"}, 
        {"chance": 0.10, "result": "prize", "amount": 500, "message": f"{player_name} snuck away with **500 bux** from {target_mention}!"}, 
        {"chance": 0.50, "result": "penalty", "amount": 250, "message": f"{player_name} tried to steal from {target_mention} but {target_mention} got the better of them and robbed them of **250 bux**!"},  
        {"chance": 0.25, "result": "penalty", "amount": 500, "message": f"{player_name} was caught stealing from {target_mention} and had to pay **500 bux** as a fine!"}, 
        {"chance": 0.10, "result": "penalty", "amount": 750, "message": f"{player_name} got arrested for stealing from {target_mention} and had to pay **750 bux** for bail!"}
    ]

    roll = random.random()
    cumulative_chance = 0
    outcome = None
    for o in outcomes:
        cumulative_chance += o["chance"]
        if roll < cumulative_chance:
            outcome = o
            break

    if outcome is None:
        outcome = {"result": "penalty", "amount": 0, "message": f"{player_name} failed to steal, no rewards or penalties!"}

    if outcome["result"] == "prize":
        if bux_data[str(target_id)]["bux"] >= outcome["amount"]:
            bux_data[str(target_id)]["bux"] -= outcome["amount"]
            bux_data[str(player_id)]["bux"] += outcome["amount"]
            save_bux(bux_data)
            await ctx.send(outcome["message"])
        else:
            await ctx.send(f"{target_name} doesn't have enough bux to steal!")

    elif outcome["result"] == "penalty":
        penalty_amount = outcome["amount"]
        if bux_data[str(player_id)]["bux"] >= penalty_amount:
            bux_data[str(player_id)]["bux"] -= penalty_amount
            bux_data[str(target_id)]["bux"] += penalty_amount
        else:
            penalty_amount = bux_data[str(player_id)]["bux"]
            bux_data[str(player_id)]["bux"] = 0
            bux_data[str(target_id)]["bux"] += penalty_amount

        save_bux(bux_data)
        await ctx.send(outcome["message"])

    if bux_data[str(player_id)]["bux"] == 0:
        await ctx.send(f"{player_name}, you have no more bux left!")

    await ctx.send(f"{player_name}, currently has {bux_data[str(player_id)]['bux']} bux")
    await assign_role_based_on_bux(ctx, ctx.author)

@bot.command()
async def bj(ctx, bet: int):
    """!bj <amount> ( Bet on a game of blackjack )"""

    player_id = ctx.author.id  
    user_id = str(ctx.author.id)

    # Ensure player has a bux entry
    if not check_bux_entry(user_id):
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with !d before you can play.")
        return

    # Check if player is already in a bet
    if is_in_bet(player_id):
        await ctx.send(f"{ctx.author.mention}, you already have an open bet. Please wait until it's settled.")
        return  

    if bet <= 0:
        await ctx.send("You must bet a positive amount of bux!")
        return

    bux_data = load_bux()

    if user_id not in bux_data or bux_data[user_id]["bux"] < bet:
        await ctx.send("You don't have enough bux for this bet.")
        return
    
    # Deduct bux from player
    bux_data[str(player_id)]["bux"] -= bet
    save_bux(bux_data)

    # Define card deck and point values
    deck = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"] * 4
    random.shuffle(deck)

    def calculate_points(hand):
        """Calculate the total points for a hand of cards."""
        points = 0
        ace_count = 0
        for card in hand:
            if card in ["J", "Q", "K"]:
                points += 10
            elif card == "A":
                points += 11
                ace_count += 1
            else:
                points += int(card)
        
        # Adjust for Aces
        while points > 21 and ace_count:
            points -= 10
            ace_count -= 1
        return points

    # Deal initial hands
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    # Check if player has Blackjack right away (Ace + 10-point card)
    if calculate_points(player_hand) == 21:
        player_hand_str = " ".join(player_hand)
        dealer_hand_str = dealer_hand[0] + " ?"
        await ctx.send(f"**Blackjack!**\nYour cards: {player_hand_str}\nDealer's cards: {dealer_hand_str}")
        await ctx.send(f"{ctx.author.mention} wins 2.5x the bet! You win {bet * 2.5} bux!")
        bux_data[str(player_id)]["bux"] += bet * 2.5
        save_bux(bux_data)
        return

    # Show the hands (player's cards, dealer's face-up card)
    player_hand_str = " ".join(player_hand)
    dealer_hand_str = dealer_hand[0] + " ?"
    
    await ctx.send(f"**Blackjack!**\nYour cards: {player_hand_str}\nDealer's cards: {dealer_hand_str}")
    open_bets[player_id] = True

    # Track if player has doubled down
    doubled_down = False

    # Player's turn
    while calculate_points(player_hand) < 21:
        # Send the reaction prompt only once
        await ctx.send(f"Your current hand: {player_hand_str} (Total: {calculate_points(player_hand)})")

        # Add reaction choices
        options_message = await ctx.send("React with ✅ to hit, ❌ to stay, or 💰 to double down.")
        await options_message.add_reaction("✅")
        await options_message.add_reaction("❌")
        await options_message.add_reaction("💰")

        def check(reaction, user):
            return user.id == player_id and str(reaction.emoji) in ["✅", "❌", "💰"]

        try:
            reaction, _ = await bot.wait_for("reaction_add", check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await ctx.send("You took too long! You stand.")
            break
        
        if str(reaction.emoji) == "✅":  # Player chooses to hit
            player_hand.append(deck.pop())
            player_hand_str = " ".join(player_hand)
            if calculate_points(player_hand) > 21:
                await ctx.send(f"**Busted!** Your hand: {player_hand_str} (Total: {calculate_points(player_hand)})")
                await ctx.send(f"{ctx.author.mention} lost the bet of {bet} bux.")
                open_bets[player_id] = False
                return
        elif str(reaction.emoji) == "💰":  # Player chooses to double down
            if bux_data[str(player_id)]["bux"] < bet:
                # If the player doesn't have enough for a double down, count it as a hit
                await ctx.send("You don't have enough bux to double down. This will be counted as a hit.")
                player_hand.append(deck.pop())  # Draw one more card (same as hitting)
                player_hand_str = " ".join(player_hand)
                await ctx.send(f"Your hand: {player_hand_str} (Total: {calculate_points(player_hand)})")
                break  # Proceed to ask for hit or stay again
            else:
                # Deduct additional bet for double down
                bux_data[str(player_id)]["bux"] -= bet
                save_bux(bux_data)
                player_hand.append(deck.pop())  # Draw one more card
                player_hand_str = " ".join(player_hand)
                await ctx.send(f"You chose to double down! Your hand: {player_hand_str} (Total: {calculate_points(player_hand)})")
                doubled_down = True
                break  # End player's turn immediately after doubling down
        else:  # Player chooses to stand
            break

    # Dealer's turn
    dealer_hand_str = " ".join(dealer_hand)
    dealer_points = calculate_points(dealer_hand)
    await ctx.send(f"Dealer's cards: {dealer_hand_str} (Total: {dealer_points})")

    while dealer_points < 17:
        dealer_hand.append(deck.pop())
        dealer_points = calculate_points(dealer_hand)
        dealer_hand_str = " ".join(dealer_hand)
        await ctx.send(f"Dealer draws: {dealer_hand[-1]}\nDealer's hand: {dealer_hand_str} (Total: {dealer_points})")

    # Determine the winner
    player_points = calculate_points(player_hand)
    if player_points > 21:
        # Player busts
        await ctx.send(f"{ctx.author.mention} lost the bet of {bet} bux. You busted!")
    elif dealer_points > 21:
        # Dealer busts
        if doubled_down:
            await ctx.send(f"Dealer busted! {ctx.author.mention} wins {bet * 4} bux!")
            # Award 4x the bet if player doubled down
            bux_data[str(player_id)]["bux"] += bet * 4
        else:
            await ctx.send(f"Dealer busted! {ctx.author.mention} wins {bet * 2} bux!")
            # Award 2x the bet if player did not double down
            bux_data[str(player_id)]["bux"] += bet * 2
        save_bux(bux_data)
    elif player_points > dealer_points:
        # Player wins
        if doubled_down:
            # Player wins 4x the bet if doubled down
            await ctx.send(f"{ctx.author.mention} wins {bet * 4} bux!")
            bux_data[str(player_id)]["bux"] += bet * 4
        else:
            await ctx.send(f"{ctx.author.mention} wins {bet * 2} bux!")
            bux_data[str(player_id)]["bux"] += bet * 2
        save_bux(bux_data)
    elif player_points == dealer_points:
        # Tie
        await ctx.send(f"{ctx.author.mention}, it's a tie! You get your {bet} bux back.")
        # Return the original bet to the player
        bux_data[str(player_id)]["bux"] += bet
        save_bux(bux_data)
    else:
        # Dealer wins
        if doubled_down:
            await ctx.send(f"Dealer wins! {ctx.author.mention} lost the bet of {bet * 2} bux.")
        else:
            await ctx.send(f"Dealer wins! {ctx.author.mention} lost the bet of {bet} bux.")

    
    open_bets[player_id] = False  # Remove player from open bets after the game is over
    await assign_role_based_on_bux(ctx, ctx.author)

#Parleys
GAMER_NAMES = [
    "Sir Lag-a-Lot", "Camp Master 3000", "No Scope Nancy", "AFK Andy", "The Ping King",
    "Disconnect Dave", "Wallhack Walter", "Potato PC Pete", "Loot Goblin", "Respawn Randy",
    "Teabag Tony"
]

def generate_gamers():
    return [
        {'id': i, 'name': GAMER_NAMES[i-1], 'points': 0} for i in range(1, 12)
    ]

def load_parleys():
    if os.path.exists('parleys.json'):
        with open('parleys.json', 'r') as f:
            return json.load(f)
    return {}

def save_parleys(data):
    with open('parleys.json', 'w') as f:
        json.dump(data, f, indent=4)
def save_gamers(gamers):
    with open('gamers.json', 'w') as f:
        json.dump(gamers, f, indent=4)

def load_gamers():
    if os.path.exists('gamers.json'):
        with open('gamers.json', 'r') as f:
            return json.load(f)
    return []

@bot.command()
async def p(ctx, amount: int):
    """"Place a parley on 3 players to get the most points"""
    user_id = str(ctx.author.id)
    user_name = ctx.author.name  
    bux_data = load_bux()
    parleys = load_parleys()

    if user_id in parleys:
        await ctx.send(f"{ctx.author.mention}, you've already placed a bet today.")
        return

    if user_id not in bux_data or bux_data[user_id]['bux'] < amount:
        await ctx.send("You don't have enough bux.")
        return
    
    if not check_bux_entry(user_id):
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with `!d`.")
        return

    bux_data[user_id]['bux'] -= amount  # Deduct the bet immediately
    save_bux(bux_data)

    gamers = load_gamers()
    if not gamers:  
        gamers = generate_gamers()
        save_gamers(gamers) 

    gamer_list = "\n".join([f"{i}. {g['name']}" for i, g in enumerate(gamers, start=1)])

    await ctx.send(f"{ctx.author.mention}, check your DMs to place your parley! 📩")
    await ctx.author.send(f"Gamers List:\n{gamer_list}\n\nPick 3 different gamers (use numbers):\nExample: 1 2 3")

    def check(msg):
        return msg.author == ctx.author and msg.content.replace(" ", "").isdigit()

    try:
        msg = await bot.wait_for('message', check=check, timeout=30)
        chosen = list(map(int, msg.content.split()))
        if len(chosen) != 3 or any(g not in range(1, 15) for g in chosen):
            await ctx.author.send("Invalid selection. Bet canceled.")
            return
        
        parleys[user_id] = {'name': user_name, 'bet': amount, 'gamers': chosen}
        save_parleys(parleys)
        await ctx.author.send(f"Bet placed on gamers {chosen}. Good luck!")

    except asyncio.TimeoutError:
        await ctx.author.send("Time expired. Bet canceled.")
        bux_data[user_id]['bux'] += amount  # Add bet back immediately 
        save_bux(bux_data)


def calculate_best_combinations(gamers):
    combinations = list(itertools.combinations(gamers, 3))
    combo_scores = [(combo, sum(g['points'] for g in combo)) for combo in combinations]
    combo_scores.sort(key=lambda x: x[1], reverse=True)
    return combo_scores

async def daily_event():
    while True:
        gamers = generate_gamers()
        for gamer in gamers:
            gamer['points'] = random.randint(1, 30)
        save_gamers(gamers)

        # Sort gamers by points in descending order before displaying the leaderboard
        leaderboard = "\n".join(
            [f"{g['name']} (ID: {g['id']}): {g['points']} points" for g in sorted(gamers, key=lambda x: x['points'], reverse=True)]
        )

        channel = discord.utils.get(bot.get_all_channels(), name="challenger-bot🥊")
        if channel:
            await channel.send(f"Today's leaderboard:\n{leaderboard}")

        best_combos = calculate_best_combinations(gamers)
        bux_data = load_bux()
        results_message = "Daily Results:\n"
        for user_id, bet in load_parleys().items():
            chosen_combo = [gamers[g-1] for g in bet['gamers']]
            chosen_combo_score = sum(g['points'] for g in chosen_combo)
            
            ranking_position = next((i for i, (combo, score) in enumerate(best_combos) if score == chosen_combo_score), None)
            if ranking_position is not None:
                if ranking_position < 7:
                    multiplier = max(7 - ranking_position, 0)  # 1st = 7x, 2nd = 6x, ..., 7th = 1x
                else:
                    multiplier = max(0.99 - 0.01 * (ranking_position - 7), 0)  # Decreasing multiplier after 7th place
                winnings = round(bet['bet'] * multiplier, 2)
                bux_data[user_id] = bux_data.get(user_id, {'bux': 0})
                bux_data[user_id]['bux'] += winnings
                results_message += f"{bet['name']} placed a bet on gamers {bet['gamers']} and scored {chosen_combo_score} points! They finished {ranking_position + 1}!\n"
                results_message += f"Winner multiplier: {multiplier}x, Winnings: {winnings} bux!\n"
            else:
                results_message += f"{bet['name']}, your bet didn't win. Better luck next time!\n"
        
        save_bux(bux_data)
        
        if channel:
            await channel.send(results_message)

        save_parleys({})
        await asyncio.sleep(6 * 60 * 60)


@bot.command()
async def sp(ctx):
    """Start the parley early (Parleys will start every hour after)"""
    await ctx.send("Starting the event now...")
    await daily_event()

bot.run('Your Token Here')

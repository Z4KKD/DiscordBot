import discord # type: ignore
from discord.ext import commands, tasks  # type: ignore
import json
import os
import asyncio
from datetime import datetime, timedelta
import random
import time
import itertools
import threading

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)

BUX_DIRECTORY = "bux_data/"
GAMERS_FILE = 'gamers.json'
PARLEY_DIRECTORY = "parley_data/"
bux_lock = threading.Lock()
gamers_lock = threading.Lock()
parley_lock = threading.Lock()


if not os.path.exists(BUX_DIRECTORY):
    os.makedirs(BUX_DIRECTORY)

if not os.path.exists(PARLEY_DIRECTORY):
    os.makedirs(PARLEY_DIRECTORY)

def load_bux(user_id: str) -> dict: 
    """Load a specific user's bux data. If the file doesn't exist, return a default structure."""
    user_file = os.path.join(BUX_DIRECTORY, f"{user_id}.json")

    if not os.path.exists(user_file):
        return {"username": "Unknown", "bux": 0, "last_claimed": "2000-01-01"}  # Default for new users

    with open(user_file, "r") as file:
        return json.load(file)

def save_bux(user_id, data):
    """Save the Bux data for a specific user, ensuring all Bux values are rounded."""
    user_file = os.path.join(BUX_DIRECTORY, f"{user_id}.json")
    
    with bux_lock:  # Lock for thread-safe operations
        data["bux"] = round(data["bux"])  # Ensure Bux is a whole number
        
        with open(user_file, 'w') as f:
            json.dump(data, f, indent=4)

# Daily Command
@bot.command()
async def d(ctx):
    """Claim your daily Bux (you need to manually claim it with !d)"""
    user_id = str(ctx.author.id)
    now = datetime.utcnow().strftime('%Y-%m-%d')

    user_data = load_bux(user_id)
    if user_data["username"] == "Unknown":
        user_data = {
            "username": ctx.author.name,  # Set the username when a new user claims
            "bux": 25000,  # Give them the daily reward immediately
            "last_claimed": now
        }
        save_bux(user_id, user_data)
        await ctx.send(f"{ctx.author.mention}, welcome! You claimed your first daily 25000 bux! 🎉")
        return

    if user_data.get("last_claimed") == now:
        await ctx.send(f"{ctx.author.mention}, you already claimed your daily bux today! Come back tomorrow.")
        return
    
    user_data["bux"] += 25000
    user_data["last_claimed"] = now
    save_bux(user_id, user_data)

    await ctx.send(f"{ctx.author.mention}, you claimed your daily 25000 bux! 🎉")

#Give
@bot.command()
async def g(ctx, member: discord.Member, amount: float):
    """!g <user> <amount> (Give a specified amount of bux to another user)"""
    giver_id = str(ctx.author.id)
    receiver_id = str(member.id)
    player_id = ctx.author.id
    giver_data = load_bux(giver_id)
    receiver_data = load_bux(receiver_id)

    if is_in_bet(player_id):
        await ctx.send(f"{ctx.author.mention}, you already have an open bet. Please wait until it's settled.")
        return  

    if giver_data["bux"] < amount:
        await ctx.send(f"{ctx.author.mention}, you don't have enough bux to give this amount.")
        return

    if amount <= 0:
        await ctx.send("You must give a positive amount of bux!")
        return

    if giver_id == receiver_id:
        await ctx.send(f"{ctx.author.mention}, you can't do that! 😅")
        return

    giver_data["bux"] -= amount
    receiver_data["bux"] += amount

    save_bux(giver_id, giver_data)
    save_bux(receiver_id, receiver_data)

    await ctx.send(f"{ctx.author.mention} has successfully given {amount} bux to {member.mention}! 🎉")
    await assign_role_based_on_bux(ctx, ctx.author)
    await assign_role_based_on_bux(ctx, member)
    

def has_enough_bux(user_id: str, amount: float) -> bool:
    """Checks if a user has enough bux to participate in a bet."""
    return load_bux(user_id)["bux"] >= amount


#Help
@bot.command()
async def h(ctx):
    """Custom help command. *** USE THIS FOR HELP ***"""
    help_message = """
        ***Ranks***     
- Challenger🥊 3,000,000,000,000,000 bux 
- High Roller💳 150,000,000,000,000 bux
- Grandmaster🏆 9,999,999,999,999 bux 
- Master⭐ 730,420,420,420 bux
- Champion👑 69,420,420,420 bux
- Lucky🍀 7,777,777,777 bux
- Obsidian🐱‍👤 1,993,730,420 bux
- Diamond💎 150,000,000 bux
- Emerald❇️ 30,000,000 bux
- Ruby🩸 7,000,000 bux
- Platinum🎖️ 1,750,000 bux
- Gold🏅 500,000 bux
- Silver🥈 150,000 bux
- Bronze🥉 50,000 bux
- Brokie🐀 0 bux

**How it works** : **Bot Commands**
- :moneybag:  **Daily**: `!d`  ( Claim your daily Bux and it will automatically claim after, this is how you start! )
- :green_heart:  **Give**: `!g <user> <amount>` ( Give a specified amount of bux to another user ) 
- :black_joker: **Blackjack**: `!bj` `<amount>` ( Bet on a game of blackjack! )
- :basketball: **Parley** `!p` `<amount>` ( Place a parley on 3 players to get the most points! )
- :ninja_tone1: **Unlocker** `!u` `<amount>` ( Unlock a safe by guessing a 4-digit password! ) 
- :slot_machine: **Jackpot** `!j` `<amount>` `<amount_of_spins>` ( Jackpot slot machine with a progressive jackpot. Spin and try your luck!  )
- :arrow_up_down: **High/Low** `!hl` `<amount>` ( Play a high/low card game with increasing multipliers. )
- :money_with_wings: **Bank**: `!b` (Check the amount of bux you have. If your broke you'll get welfare! )
- 🏆 **Leaderboards**: `!l` ( Check your rank on the leaderboards! )
- :grey_question: **Help**: `!h` ( Shows this )
    """
    await ctx.send(help_message)

#AssignRoles    
async def assign_role_based_on_bux(ctx, member):
    user_id = str(member.id)
    user_data = load_bux(user_id)
    if not user_data:
        await ctx.send(f"{member.mention} doesn't have any bux data.")
        return

    bux = user_data.get("bux", 0)
    role_name = get_role_name(bux)
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        role = await ctx.guild.create_role(name=role_name, mentionable=True)

    rank_roles = [
        "Challenger🥊", "High Roller💳", "Grandmaster🏆", "Master⭐", "Champion👑", 
        "Lucky🍀", "Obsidian🐱‍👤", "Diamond💎", "Emerald❇️", "Ruby🩸", "Platinum🎖️", 
        "Gold🏅", "Silver🥈", "Bronze🥉", "Brokie🐀"
    ]
    roles_to_remove = [r for r in member.roles if r.name in rank_roles and r.name != role_name]
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove)  # Remove all previous rank roles

    if role not in member.roles:
        await member.add_roles(role)
        await ctx.send(f"{member.mention} is now {role_name}!")

#GetRoles
def get_role_name(bux):
    """Returns the role name based on the amount of bux."""
    if bux >= 3_000_000_000_000_000:
        return "Challenger🥊"
    elif bux >= 150_000_000_000_000:
        return "High Roller💳"
    elif bux >= 9_999_999_999_999:
        return "Grandmaster🏆"
    elif bux >= 730_420_420_420:
        return "Master⭐"
    elif bux >= 69_420_420_420:
        return "Champion👑"
    elif bux >= 7_777_777_777:
        return "Lucky🍀"
    elif bux >= 1_993_730_420:
        return "Obsidian🐱‍👤"
    elif bux >= 150_000_000:
        return "Diamond💎"
    elif bux >= 30_000_000:
        return "Emerald❇️"
    elif bux >= 7_000_000:
        return "Ruby🩸"
    elif bux >= 1_750_000:
        return "Platinum🎖️"
    elif bux >= 500_000:
        return "Gold🏅"
    elif bux >= 150_000:
        return "Silver🥈"
    elif bux >= 50_000:
        return "Bronze🥉"
    else:
        return "Brokie🐀"

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

        if current_time - last_message_time >= 5:
            await ctx.send(f"{ctx.author.mention}, you are on cooldown! Try again in {round(error.retry_after, 2)} seconds.")
            last_cooldown_message[user_id] = current_time  # Update the timestamp

    else:
        await ctx.send("An unexpected error occurred.")
        raise error 
    
# AddBux Command
@bot.command()
async def ab(ctx, bux: float, member: discord.Member = None):
    """Admin only command to add bux to a user or all users !ab <amount> <user> (no user for all)"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You do not have the required permissions to use this command.")
        return

    if bux <= 0:
        await ctx.send("You must add a positive amount of bux!")
        return

    if member:
        user_id = str(member.id)
        user_data = load_bux(user_id)
        user_data["bux"] += bux
        formatted_bux = f"{bux:,.2f}"  # Add a decimal format
        await ctx.send(f"Added {formatted_bux} bux to {member.name}.")
        save_bux(user_id, user_data)
    else:
        bux_data = load_bux()  # Load all bux data
        for user_id, user_data in bux_data.items():
            user_data["bux"] += bux
            save_bux(user_id, user_data)  # Save each user's updated data

        formatted_bux = f"{bux:,.2f}" 
        await ctx.send(f"Added {formatted_bux} bux to all users.")


# RemoveBux Command
@bot.command()
async def rb(ctx, bux: float, member: discord.Member = None):
    """Admin only command to remove bux from a user or all users !rb <amount> <user> (no user for all)"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You do not have the required permissions to use this command.")
        return

    if bux <= 0:
        await ctx.send("You must remove a positive amount of bux!")
        return

    if member:
        user_id = str(member.id)
        user_data = load_bux(user_id)
        
        if user_data["bux"] < bux:
            await ctx.send(f"{member.name} doesn't have enough bux to remove.")
            return
    
        user_data["bux"] -= bux
        formatted_bux = f"{bux:,.2f}" 
        await ctx.send(f"Removed {formatted_bux} bux from {member.name}.")
        save_bux(user_id, user_data)
    else:
        bux_data = load_bux()  # Load all bux data
        for user_id, user_data in bux_data.items():
            if user_data["bux"] >= bux:
                user_data["bux"] -= bux
                save_bux(user_id, user_data)  # Save each user's updated data
        
        formatted_bux = f"{bux:,.2f}" 
        await ctx.send(f"Removed {formatted_bux} bux from all users.")

# Leaderboard Command
@bot.command()
async def l(ctx):
    """!l (Check your rank on the leaderboards.)"""
    user_id = str(ctx.author.id)

    if not check_bux_entry(user_id):
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with `!d`")
        return

    leaderboard_data = []
    for filename in os.listdir(BUX_DIRECTORY):
        if filename.endswith(".json"):
            user_id_from_file = filename.replace(".json", "")
            user_data = load_bux(user_id_from_file)
            leaderboard_data.append((user_id_from_file, user_data["bux"]))
    
    sorted_bux = sorted(leaderboard_data, key=lambda x: x[1], reverse=True)
    user_rank = next((index + 1 for index, (uid, _) in enumerate(sorted_bux) if uid == user_id), None)
    top_7 = sorted_bux[:7]
    leaderboard_message = "🏆 **Top 7** 🏆\n\n"
    rank = 1

    await assign_role_based_on_bux(ctx, ctx.author)

    for uid, bux in top_7:
        user = await bot.fetch_user(uid)
        formatted_bux = f"{bux:,.2f}"
        leaderboard_message += f"**{rank}. {user.name}** - {formatted_bux} bux\n"
        rank += 1

    if user_rank:
        leaderboard_message += f"\n🔹 {ctx.author.mention}, you are ranked **#{user_rank}** on the leaderboard."

    await ctx.send(leaderboard_message)

open_bets = {}  # Format: {player_id: True/False}

def is_in_bet(player_id):
    return open_bets.get(player_id, False)  # Returns True if in an open bet, else False

def check_bux_entry(user_id: str):
    """Returns True if the user has an entry in bux data, False otherwise."""
    user_data = load_bux(user_id)
    return user_data.get("username") != "Unknown"  # If the username is 'Unknown', they haven't been registered yet.


#Balance
@bot.command()
async def b(ctx):
    """!b (Check the amount of bux you have) If you're broke, you'll get welfare!"""
    user_id = str(ctx.author.id)
    user_data = load_bux(user_id)

    if user_data["username"] == "Unknown":
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with `!d`.")  # Ensure they have data
        return

    bux = user_data["bux"]
    formatted_bux = f"{bux:,}" 
    await ctx.send(f"{ctx.author.name}, you have {formatted_bux} bux.")
    
    # Welfare
    if bux <= 2500:
        welfare_bux = 5000
        await ctx.send(f"{ctx.author.name}, was approved for welfare and received {welfare_bux} bux.")
        user_data["bux"] += welfare_bux  # Add welfare bux

        if random.random() < 0.07:  # 7% chance to get 5000 bux
            bonus_bux = 10000
            user_data["bux"] += bonus_bux
            await ctx.send(f"{ctx.author.name}, did some dirty deeds and earned {bonus_bux} bux.")

        if random.random() < 0.03:  # 3% chance to get 50000 bux
            bonus_bux = 30000
            user_data["bux"] += bonus_bux
            await ctx.send(f"{ctx.author.name}, robbed the welfare office and gained {bonus_bux} bux!")

        save_bux(user_id, user_data)  # Save the updated user data

    await assign_role_based_on_bux(ctx, ctx.author)


#BlackJack
@bot.command()
async def bj(ctx, bet: float):
    """!bj <amount> ( Bet on a game of blackjack )"""

    player_id = ctx.author.id  
    user_id = str(ctx.author.id)

    if not check_bux_entry(user_id):
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with !d before you can play.")
        return

    if is_in_bet(player_id):
        await ctx.send(f"{ctx.author.mention}, you already have an open bet. Please wait until it's settled.")
        return  

    if bet <= 0:
        await ctx.send("You must bet a positive amount of bux!")
        return
    
    bux_data = load_bux(user_id)

    if bux_data["bux"] < bet:
        await ctx.send("You don't have enough bux for this bet.")
        return
    
    bux_data["bux"] -= bet
    save_bux(user_id, bux_data)  # Save the updated bux data

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
        
        while points > 21 and ace_count:
            points -= 10
            ace_count -= 1
        return points

    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    if calculate_points(player_hand) == 21:
        player_hand_str = " ".join(player_hand)
        dealer_hand_str = dealer_hand[0] + " ?"
        await ctx.send(f"**Blackjack!**\nYour cards: {player_hand_str}\nDealer's cards: {dealer_hand_str}")
        await ctx.send(f"{ctx.author.mention} wins 2.5x the bet! You win {bet * 2.5} bux!")
        bux_data["bux"] += bet * 2.5
        save_bux(user_id, bux_data)
        return

    player_hand_str = " ".join(player_hand)
    dealer_hand_str = dealer_hand[0] + " ?"
    
    await ctx.send(f"**Blackjack!**\nYour cards: {player_hand_str}\nDealer's cards: {dealer_hand_str}")
    open_bets[player_id] = True
    doubled_down = False

    while calculate_points(player_hand) < 21:
        await ctx.send(f"Your current hand: {player_hand_str} (Total: {calculate_points(player_hand)})")
        options_message = await ctx.send("React with ✅ to hit, ❌ to stay, or 💰 to double down.")
        await options_message.add_reaction("✅")
        await options_message.add_reaction("❌")
        await options_message.add_reaction("💰")

        def check(reaction, user):
            return user.id == player_id and str(reaction.emoji) in ["✅", "❌", "💰"]

        try:
            reaction, _ = await bot.wait_for("reaction_add", check=check, timeout=300.0)
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
            if bux_data["bux"] < bet:
                await ctx.send("You don't have enough bux to double down. This will be counted as a hit.")
                player_hand.append(deck.pop())  # Draw one more card (same as hitting)
                player_hand_str = " ".join(player_hand)
                await ctx.send(f"Your hand: {player_hand_str} (Total: {calculate_points(player_hand)})")
                break  # Proceed to ask for hit or stay again
            else:
                bux_data["bux"] -= bet
                save_bux(user_id, bux_data)
                player_hand.append(deck.pop())  # Draw one more card
                player_hand_str = " ".join(player_hand)
                await ctx.send(f"You chose to double down! Your hand: {player_hand_str} (Total: {calculate_points(player_hand)})")
                doubled_down = True
                break  # End player's turn immediately after doubling down
        else:  # Player chooses to stand
            break

    dealer_hand_str = " ".join(dealer_hand)
    dealer_points = calculate_points(dealer_hand)
    await ctx.send(f"Dealer's cards: {dealer_hand_str} (Total: {dealer_points})")

    while dealer_points < 17:
        dealer_hand.append(deck.pop())
        dealer_points = calculate_points(dealer_hand)
        dealer_hand_str = " ".join(dealer_hand)
        await ctx.send(f"Dealer draws: {dealer_hand[-1]}\nDealer's hand: {dealer_hand_str} (Total: {dealer_points})")

    player_points = calculate_points(player_hand)
    if player_points > 21:         # Player busts
        await ctx.send(f"{ctx.author.mention} lost the bet of {bet} bux. You busted!")
    elif dealer_points > 21:        # Dealer busts
        if doubled_down:
            await ctx.send(f"Dealer busted! {ctx.author.mention} wins {bet * 4} bux!")
            bux_data["bux"] += bet * 4  # Award 4x the bet if player doubled down
        else:
            await ctx.send(f"Dealer busted! {ctx.author.mention} wins {bet * 2} bux!") 
            bux_data["bux"] += bet * 2 # Award 2x the bet if player did not double down
        save_bux(user_id, bux_data)
    elif player_points > dealer_points:         # Player wins
        if doubled_down:
            await ctx.send(f"{ctx.author.mention} wins {bet * 4} bux!")
            bux_data["bux"] += bet * 4 # Player wins 4x the bet if doubled down
        else:
            await ctx.send(f"{ctx.author.mention} wins {bet * 2} bux!")
            bux_data["bux"] += bet * 2
        save_bux(user_id, bux_data)
    elif player_points == dealer_points:         # Tie
        refund_amount = bet * 2 if doubled_down else bet  # Refund full amount if doubled down
        await ctx.send(f"{ctx.author.mention}, it's a tie! You get your {refund_amount} bux back.")
        bux_data["bux"] += refund_amount
        save_bux(user_id, bux_data)

    else:
        if doubled_down:         # Dealer wins
            await ctx.send(f"Dealer wins! {ctx.author.mention} lost the bet of {bet * 2} bux.")
        else:
            await ctx.send(f"Dealer wins! {ctx.author.mention} lost the bet of {bet} bux.")
    
    open_bets[player_id] = False  # Remove player from open bets after the game is over
    await assign_role_based_on_bux(ctx, ctx.author)


# Unlocker
@bot.command()
async def u(ctx, bet: float):
    """!u <amount> (Unlock a safe by guessing a 4-digit password)"""

    player_id = ctx.author.id  
    user_id = str(ctx.author.id)

    if not check_bux_entry(user_id):
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with !d before you can play.")
        return
    
    if is_in_bet(player_id):
        await ctx.send(f"{ctx.author.mention}, you already have an open bet. Please wait until it's settled.")
        return  

    if bet <= 0:
        await ctx.send("You must bet a positive amount of bux!")
        return

    bux_data = load_bux(user_id)  # Load the user's bux data

    if not bux_data:  # If user data does not exist
        await ctx.send(f"{ctx.author.mention}, you don't have any bux data. Please claim your daily reward first with !d.")
        return

    if bux_data["bux"] < bet:
        await ctx.send(f"{ctx.author.mention}, you don't have enough bux for this bet. You currently have {bux_data['bux']} bux.")
        return

    bux_data["bux"] -= bet
    save_bux(user_id, bux_data)  # Save the updated bux data

    code = [random.randint(0, 9) for _ in range(4)]  # Generate 4-digit code
    attempts = 0
    max_attempts = 5
    reward_multipliers = [4, 3, 2, 1.5, 0.75]  # Adjusted reward multipliers

    def give_feedback(guess):
        feedback = []
        for i in range(4):
            if guess[i] == code[i]:
                feedback.append("✅")  # Correct digit in right position
            elif guess[i] in code:
                feedback.append("🔄")  # Correct digit, wrong position
            else:
                feedback.append("❌")  # Incorrect digit
        return "".join(feedback)

    await ctx.send(f"{ctx.author.mention}, check your DMs! You are about to try to unlock a safe!")

    try:
        dm_channel = await ctx.author.create_dm()
        await dm_channel.send(f"**Welcome to Unlocker!**\nYou have {max_attempts} attempts to guess the 4-digit code. Enter the code without spaces or dashes. Good luck!")
        await dm_channel.send(" ✅ Correct digit in right position 🔄 Correct digit, wrong position ❌ Incorrect digit ")
        await dm_channel.send("  Reward based on attempts: 1st = x4, 2nd = x3, 3rd = x2, 4th = x1.5, 5th = x0.75 ")

    except Exception:
        await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Please ensure you have DMs open for me.")
        return

    while attempts < max_attempts:
        await dm_channel.send(f"Attempt {attempts + 1}/{max_attempts}: Enter a 4-digit code:")

        def check(message):
            return (message.author.id == player_id and 
                    message.content.isdigit() and 
                    len(message.content) == 4)
        
        try:
            message = await bot.wait_for('message', check=check, timeout=600.0)
        except asyncio.TimeoutError:
            await dm_channel.send("You took too long! The game ends.")
            bux_data["bux"] += bet  # Refund the bet amount if the player timed out
            save_bux(user_id, bux_data)  # Save the updated bux data
            break

        guess = [int(digit) for digit in message.content]
        attempts += 1

        feedback = give_feedback(guess)
        
        if guess == code:
            reward = bet * reward_multipliers[attempts - 1]  # Adjusted reward calculation
            await dm_channel.send(f"**Unlocked!** You win {reward} bux!")
            bux_data["bux"] += reward  # Add the reward to the player's bux
            save_bux(user_id, bux_data)  # Save the updated bux data
            break
        elif attempts == max_attempts:
            await dm_channel.send(f"**Game Over!** You failed to crack the code. The correct code was: {''.join(map(str, code))}.")
            break
        else:
            await dm_channel.send(f"Feedback: {feedback} - Keep guessing!")

    open_bets[player_id] = False  # Remove player from open bets after the game is over
    await assign_role_based_on_bux(ctx, ctx.author)

#Jackpot
symbol_pool = (
    ["🍋"] * 35 +  # 35% chance
    ["🍀"] * 25 +  # 25% chance
    ["🍒"] * 20 +  # 20% chance
    ["💎"] * 15 +  # 15% chance
    ["7️⃣"] * 5    # 5% chance
)

@bot.command()
@commands.cooldown(3, 15, commands.BucketType.user)
async def j(ctx, bet_amount: float, spins: int = 1):
    """!j <bet_amount> <spins> (Jackpot slot machine, Spin multiple times, progressive jackpot)"""

    user_id = str(ctx.author.id)
    player_id = ctx.author.id

    if not check_bux_entry(user_id):
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with !d before you can play.")
        return
    
    if is_in_bet(player_id):
        await ctx.send(f"{ctx.author.mention}, you already have an open bet. Please wait until it's settled.")
        return  

    if spins < 1 or spins > 25:
        return

    total_cost = bet_amount * spins
    bux_data = load_bux(user_id)  # Load the user's bux data

    if bux_data["bux"] < total_cost:
        await ctx.send(f"{ctx.author.mention}, you don't have enough bux for {spins} spins. (Cost: {total_cost} bux)")
        return
    bux_data["bux"] -= total_cost
    save_bux(user_id, bux_data)  # Save the updated bux data
    payout_multipliers = {
        "7️⃣": 37,
        "💎": 17,
        "🍒": 13,
        "🍀": 11,
        "🍋": 7
    }
    partial_payout_multipliers = {
        "💎": 7,  
        "7️⃣": 11  
    }

    total_payout = 0
    results = []
    jackpot_chance = 0.000100
    jackpot_win = bet_amount * 73

    for _ in range(spins):    # Perform the spins
        if random.random() < jackpot_chance:         # Check for the progressive jackpot
            total_payout = jackpot_win
            results.append(f"🎉 **Progressive Jackpot!** 🎉\n{ctx.author.mention} won {jackpot_win} bux!")
            break

        reel_1 = random.choice(symbol_pool)
        reel_2 = random.choice(symbol_pool)
        reel_3 = random.choice(symbol_pool)

        payout = 0        # Determine winnings based on full match or partial match
        if reel_1 == reel_2 == reel_3:
            payout = bet_amount * payout_multipliers[reel_1]
        elif reel_1 == reel_2:  # Two matching symbols
            payout = bet_amount * partial_payout_multipliers.get(reel_1, 0)
        elif reel_2 == reel_3:  # Two matching symbols
            payout = bet_amount * partial_payout_multipliers.get(reel_2, 0)
        elif reel_1 == reel_3:  # Two matching symbols
            payout = bet_amount * partial_payout_multipliers.get(reel_1, 0)

        total_payout += payout
        results.append(f"{reel_1} | {reel_2} | {reel_3} {'✅' if payout > 0 else '❌'}")

    bux_data["bux"] += total_payout
    save_bux(user_id, bux_data)  # Save the updated bux data
    await assign_role_based_on_bux(ctx, ctx.author)

    summary = (
        f"🎰 **Slot Machine Results** 🎰\n"
        f"Bet per spin: **{bet_amount}** bux | Total Spins: **{spins}** | Total Cost: **{total_cost}** bux\n"
        f"**Total Payout:** {total_payout} bux\n\n"
        + "\n".join(results[:25]) + ("\n...and more!" if spins > 25 else "")
    )
    await ctx.send(f"{ctx.author.mention}\n{summary}")

#High'n'Low
@bot.command()
async def hl(ctx, bet: float):
    """!hl <amount> - Play a high/low card game with increasing multipliers."""
    
    player_id = ctx.author.id  
    user_id = str(ctx.author.id)

    if not check_bux_entry(user_id):
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with !d before you can play.")
        return

    if is_in_bet(player_id):
        await ctx.send(f"{ctx.author.mention}, you already have an open bet. Please wait until it's settled.")
        return  

    if bet <= 0:
        await ctx.send("You must bet a positive amount of bux!")
        return
    
    bux_data = load_bux(user_id)

    if bux_data["bux"] < bet:
        await ctx.send("You don't have enough bux for this bet.")
        return

    open_bets[player_id] = True  # Mark player as having an open bet

    try:
        bux_data["bux"] -= bet  # Deduct initial bet
        save_bux(user_id, bux_data)

        deck = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"] * 4
        random.shuffle(deck)

        def card_value(card):
            """Convert face cards into numerical values for comparison."""
            values = {"J": 11, "Q": 12, "K": 13, "A": 14}  # Face card values
            if card in values:
                return values[card]  # Return mapped value if it's a face card
            return int(card)  # Convert to int if it's a number


        current_card = deck.pop()
        multiplier = 2  # Starts at 2x after 3 correct rounds
        correct_guesses = 0

        await ctx.send(f"{ctx.author.mention}, starting card is **{current_card}**. React with ⬆️ for Higher or ⬇️ for Lower.")

        while True:
            next_card = deck.pop()

            options_message = await ctx.send(f"Current card: **{current_card}**\nReact with ⬆️ for Higher or ⬇️ for Lower.")
            await options_message.add_reaction("⬆️")
            await options_message.add_reaction("⬇️")

            def check(reaction, user):
                return user.id == player_id and str(reaction.emoji) in ["⬆️", "⬇️"]

            try:
                reaction, _ = await bot.wait_for("reaction_add", check=check, timeout=60.0)
            except asyncio.TimeoutError:
                await ctx.send(f"{ctx.author.mention}, you took too long! You lost your bet of {bet} bux.")
                return

            guess = "higher" if str(reaction.emoji) == "⬆️" else "lower"
            current_value = card_value(current_card)
            next_value = card_value(next_card)

            if (guess == "higher" and next_value > current_value) or (guess == "lower" and next_value < current_value):
                correct_guesses += 1
                await ctx.send(f"✅ Correct! Next card was **{next_card}**.")

                if correct_guesses % 3 == 0:  # Every 3 correct guesses, allow cash-out
                    await ctx.send(f"You've won **{multiplier}x** your bet so far! React with 💰 to cash out or 🔄 to continue.")
                    cashout_message = await ctx.send("💰 = Cash Out | 🔄 = Keep Going")
                    await cashout_message.add_reaction("💰")
                    await cashout_message.add_reaction("🔄")

                    def cashout_check(reaction, user):
                        return user.id == player_id and str(reaction.emoji) in ["💰", "🔄"]

                    try:
                        reaction, _ = await bot.wait_for("reaction_add", check=cashout_check, timeout=300.0)
                    except asyncio.TimeoutError:
                        await ctx.send(f"{ctx.author.mention}, time ran out! You got refunded.")
                        bux_data["bux"] += bet
                        return

                    if str(reaction.emoji) == "💰":
                        winnings = bet * multiplier
                        bux_data["bux"] += winnings
                        save_bux(user_id, bux_data)
                        await ctx.send(f"{ctx.author.mention}, you cashed out and won **{winnings} bux!**")
                        return
                    else:
                        multiplier *= 2  # Increase the multiplier
                        await ctx.send(f"🔥 You continue! New multiplier is **{multiplier}x**.")

                current_card = next_card  # Move to next round

            elif current_value == next_value:
                await ctx.send(f"😬 Tie! The next card was also **{next_card}**. You get a free retry!")

            else:
                await ctx.send(f"❌ Wrong! The next card was **{next_card}**. You lost your bet of {bet} bux.")
                return

    finally:
        open_bets[player_id] = False  # Ensure the bet is cleared even if there's an error


#Parleys
GAMER_NAMES = [
    "Sanctus", "Scriptjb", "DadonDabs", "Meto", "StrangleMyDangle",
    "Gekiez", "Z4KKD", "Shutout", "Chris Pratt", "Shellcity",
    "Krypt1k"
]

def generate_gamers():
    return [
        {'id': i, 'name': GAMER_NAMES[i-1], 'points': 0} for i in range(1, 12)
    ]

def load_user_parley(user_id):
    """Load a specific user's parley data."""
    user_file = os.path.join(PARLEY_DIRECTORY, f"{user_id}.json")
    
    if os.path.exists(user_file):
        with open(user_file, 'r') as f:
            return json.load(f)
    else:
        return None  # No data for this user

def save_user_parley(user_id, data):
    """Save a specific user's parley data."""
    user_file = os.path.join(PARLEY_DIRECTORY, f"{user_id}.json")
    
    with parley_lock:
        with open(user_file, 'w') as f:
            json.dump(data, f, indent=4)

def load_gamers():
    """Loads the gamers data."""
    with gamers_lock:  # Lock for thread-safe operations
        if os.path.exists(GAMERS_FILE):
            with open(GAMERS_FILE, 'r') as f:
                return json.load(f)
        return []

def save_gamers(gamers):
    """Saves the gamers data safely."""
    with gamers_lock:  # Lock for thread-safe operations
        with open(GAMERS_FILE, 'w') as f:
            json.dump(gamers, f, indent=4)

@bot.command()
async def p(ctx, amount: float):
    """Place a parley on 3 players to get the most points"""
    user_id = str(ctx.author.id)
    player_id = ctx.author.id
    user_name = ctx.author.name  
    bux_data = load_bux(user_id)
    user_parley = load_user_parley(user_id)

    if user_parley:
        await ctx.send(f"{ctx.author.mention}, you've already placed a bet today.")
        return

    if bux_data["bux"] < amount:
        await ctx.send(f"{ctx.author.mention}, you don't have enough bux.")
        return
    
    if not check_bux_entry(user_id):
        await ctx.send(f"{ctx.author.mention}, you need to claim your daily first with `!d`.")
        return
    
    if is_in_bet(player_id):
        await ctx.send(f"{ctx.author.mention}, you already have an open bet. Please wait until it's settled.")
        return  
    
    bux_data["bux"] -= amount
    save_bux(user_id, bux_data)  # Save the updated bux data

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
        msg = await bot.wait_for('message', check=check, timeout=600)
        chosen = list(map(int, msg.content.split()))
        
        if len(chosen) != 3 or any(g not in range(1, len(gamers) + 1) for g in chosen):
            await ctx.author.send("Invalid selection. Bet canceled.")
            bux_data["bux"] += amount             # Refund the bet if the selection was invalid
            save_bux(user_id, bux_data)  # Save the updated bux data
            return
        
        user_parley = {'name': user_name, 'bet': amount, 'gamers': chosen}    
        save_user_parley(user_id, user_parley)  # Save the user's parley
        await ctx.author.send(f"Bet placed on gamers {chosen}. Good luck!")
        await assign_role_based_on_bux(ctx, ctx.author)

    except asyncio.TimeoutError:
        await ctx.author.send("Time expired. Bet canceled.")
        bux_data["bux"] += amount        # Refund the bet if the time expired
        save_bux(user_id, bux_data)  # Save the updated bux data
        await assign_role_based_on_bux(ctx, ctx.author)

def calculate_best_combinations(gamers):
    combinations = list(itertools.combinations(gamers, 3))
    combo_scores = [(combo, sum(g['points'] for g in combo)) for combo in combinations]
    combo_scores.sort(key=lambda x: x[1], reverse=True)
    return combo_scores

async def daily_event():
    while True:
        gamers = generate_gamers()
        for gamer in gamers:
            gamer['points'] = random.randint(1, 37)
        save_gamers(gamers)


        leaderboard = "\n".join(         # Sort gamers by points in descending order before displaying the leaderboard
            [f"{g['name']} (ID: {g['id']}): {g['points']} points" for g in sorted(gamers, key=lambda x: x['points'], reverse=True)]
        )

        channel = discord.utils.get(bot.get_all_channels(), name="challenger-parley🥊")
        if channel:
            await channel.send(f"Today's leaderboard:\n{leaderboard}")

        best_combos = calculate_best_combinations(gamers)

        results_message = "Daily Results:\n"

        for filename in os.listdir(PARLEY_DIRECTORY):         # Iterate over all user files and calculate results
            user_id = filename.replace(".json", "")
            user_parley = load_user_parley(user_id)

            if user_parley:
                chosen_combo = [gamers[g-1] for g in user_parley['gamers']]
                chosen_combo_score = sum(g['points'] for g in chosen_combo)
                
                ranking_position = next((i for i, (combo, score) in enumerate(best_combos) if score == chosen_combo_score), None)
                if ranking_position is not None:
                    if ranking_position < 20:
                        multiplier = max(20 - ranking_position, 0) 
                    else:
                        multiplier = max(0.99 - 0.01 * (ranking_position - 20), 0)  
                    winnings = round(user_parley['bet'] * multiplier, 2)
                    bux_data = load_bux(user_id)
                    bux_data['bux'] += winnings
                    save_bux(user_id, bux_data)
                    results_message += f"{user_parley['name']} placed a bet on gamers {user_parley['gamers']} and scored {chosen_combo_score} points! They finished {ranking_position + 1}!\n"
                    results_message += f"Winner multiplier: {multiplier}x, Winnings: {winnings} bux!\n"
                else:
                    results_message += f"{user_parley['name']}, your bet didn't win. Better luck next time!\n"
        if channel:
            await channel.send(results_message)

        for filename in os.listdir(PARLEY_DIRECTORY):        # Clean up the parley files
            os.remove(os.path.join(PARLEY_DIRECTORY, filename))

        await asyncio.sleep(6 * 60 * 60)

@bot.command()
async def sp(ctx):
    """Start the parley early (Parleys will start every hour after)"""
    await ctx.send("Starting the event now...")
    await daily_event()

@bot.event
async def on_ready():
    await daily_event()

bot.run('Your Token Here')

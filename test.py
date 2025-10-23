import requests
import json
from bs4 import BeautifulSoup
import random
import time
import os
import asyncio
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

USER_PRESENCE_MAP = {
    0: "Offline",
    1: "Online",
    2: "In-Game",
    3: "In-Studio",
    4: "Invisible"
}

TOKEN = "Y" 

def get_user_agent():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0"
    ]
    return random.choice(user_agents)

def request_with_retries(url, headers, max_retries=None):
    retries = 0
    while True:
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                wait_time = int(response.headers.get('Retry-After', 5))
                print(f"Rate limited. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                retries += 1
            else:
                if max_retries and retries >= max_retries:
                    print(f"Failed to fetch {url} after {max_retries} retries. Status code: {response.status_code}")
                    return None
                retries += 1
                print(f"Request failed with status {response.status_code}. Retrying in 5s... ({retries})")
                time.sleep(5)
        except requests.RequestException as e:
            print(f"Request exception for {url}: {e}")
            if max_retries and retries >= max_retries:
                return None
            retries += 1
            time.sleep(5)

def search_by_username(username):
    url = f"https://users.roblox.com/v1/users/search?keyword={username}&limit=10"
    headers = {'User-Agent': get_user_agent()}
    response = request_with_retries(url, headers)
     
    if response and response.status_code == 200:
        data = response.json()
        if data['data']:
            if 'id' in data['data'][0]:
                return data['data'][0]['id']
            elif 'userId' in data['data'][0]:
                return data['data'][0]['userId']
    
    try:
        url = f"https://www.roblox.com/users/profile?username={username}"
        headers = {'User-Agent': get_user_agent()}
        response = requests.get(url, headers=headers, allow_redirects=True)
        
        if response.status_code == 200 and 'users' in response.url:
            parts = response.url.split('/')
            for i, part in enumerate(parts):
                if part == 'users' and i + 1 < len(parts):
                    user_id = parts[i + 1]
                    if user_id.isdigit():
                        return user_id
    except Exception as e:
        print(f"Error in redirect search for {username}: {e}")
        pass
   
    return None

def get_previous_usernames(user_id):
    url = f"https://users.roblox.com/v1/users/{user_id}/username-history?limit=100&sortOrder=Asc"
    headers = {'User-Agent': get_user_agent()}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        return [entry['name'] for entry in data['data']]
    
    return []

def get_groups(user_id):
    url = f"https://groups.roblox.com/v2/users/{user_id}/groups/roles"
    headers = {'User-Agent': get_user_agent()}
    response = requests.get(url, headers=headers)
    
    groups = []
    if response.status_code == 200:
        data = response.json()
        for group in data['data']:
            group_id = group['group']['id']
            group_owner_info = [False, False, False]
            
            url_v1 = f"https://groups.roblox.com/v1/groups/{group_id}"
            response_v1 = requests.get(url_v1, headers=headers)
            
            if response_v1.status_code == 200:
                data_v1 = response_v1.json()
                if data_v1.get('owner'):
                    if data_v1['owner'].get('username'):
                        group_owner_info = [
                            data_v1['owner']['username'],
                            data_v1['owner']['userId'],
                            data_v1['owner'].get('hasVerifiedBadge', False)
                        ]
            
            groups.append({
                'name': group['group']['name'],
                'link': f"https://www.roblox.com/groups/{group_id}",
                'members': group['group']['memberCount'],
                'owner_username': group_owner_info[0],
                'owner_id': group_owner_info[1],
                'owner_verified': group_owner_info[2]
            })
    
    return groups

def get_about_me(user_id):
    url = f"https://www.roblox.com/users/{user_id}/profile"
    headers = {'User-Agent': get_user_agent()}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        about_me = soup.find('span', class_='profile-about-content-text linkify')
        if about_me:
            return about_me.text.strip()
        else:
            about_me_div = soup.find('div', class_='profile-about-content')
            if about_me_div:
                about_me_span = about_me_div.find('span')
                if about_me_span:
                    return about_me_span.text.strip()
    
    return "Not available"

def get_entity_list(user_id, entity_type):
    entities = set()  
    cursor = ""
    
    while True:
        url = f"https://friends.roblox.com/v1/users/{user_id}/{entity_type}?limit=100&cursor={cursor}"
        headers = {'User-Agent': get_user_agent()}
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            for entity in data['data']:
                if 'displayName' in entity:
                    name = entity.get('displayName') or entity.get('username', 'Usuario sin nombre')
                    entity_id = entity.get('id', '')
                elif 'name' in entity:
                    name = entity['name']
                    entity_id = entity['id']
                elif 'user' in entity and isinstance(entity['user'], dict):
                    user_data = entity['user']
                    name = user_data.get('displayName') or user_data.get('name', 'Usuario sin nombre')
                    entity_id = user_data.get('id', '')
                else:
                    available_keys = list(entity.keys())
                    name = f"Usuario {available_keys}"
                    entity_id = entity.get('id', '')
                
                if entity_id:
                    entities.add((name, f"https://www.roblox.com/users/{entity_id}/profile"))
            
            cursor = data.get('nextPageCursor')
            if not cursor:
                break
        else:
            if response.status_code == 429:
                wait_time = int(response.headers.get('Retry-After', 5))
                print(f"Rate limited on {entity_type}. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                print(f"Failed to get {entity_type}. Status: {response.status_code}")
                break
        
        time.sleep(1)
    
    return [{'name': name, 'url': url} for name, url in entities]

def get_presence(user_id, headers):
    url = "https://presence.roblox.com/v1/presence/users"
    payload = {"userIds": [int(user_id)]} 
    
    retries = 0
    max_retries = 3

    while retries < max_retries:
        try:
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("userPresences") and len(data["userPresences"]) > 0:
                    presence_data = data["userPresences"][0]
                    presence_type = presence_data.get("userPresenceType")
                    
                    return {
                        "status": USER_PRESENCE_MAP.get(presence_type, f"Unknown ({presence_type})"),
                        "last_location": presence_data.get("lastLocation", "N/A"),
                        "place_id": presence_data.get("placeId"),
                        "last_online": presence_data.get("lastOnline")
                    }
                return None
            elif response.status_code == 429:
                wait_time = int(response.headers.get('Retry-After', 5))
                print(f"Rate limited on presence API. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                retries += 1
            else:
                print(f"Failed to get presence. Status: {response.status_code}, Response: {response.text}")
                return None
        except requests.RequestException as e:
            print(f"Error during presence request: {e}")
            time.sleep(5)
            retries += 1
    
    print("Failed to get presence after retries.")
    return None

def get_user_info(identifier):
    if identifier.isdigit():
        user_id = identifier
    else:
        user_id = search_by_username(identifier)
   
    if not user_id:
        return None
   
    user_url = f"https://users.roblox.com/v1/users/{user_id}"
    headers = {'User-Agent': get_user_agent()}
    user_response = request_with_retries(user_url, headers)
   
    if user_response and user_response.status_code == 200:
        user_data = user_response.json()
       
        friends_url = f"https://friends.roblox.com/v1/users/{user_id}/friends/count"
        friends_response = requests.get(friends_url, headers=headers)
        friends_count = friends_response.json()['count'] if friends_response.status_code == 200 else 0
       
        followers_url = f"https://friends.roblox.com/v1/users/{user_id}/followers/count"
        followings_url = f"https://friends.roblox.com/v1/users/{user_id}/followings/count"
        followers_response = requests.get(followers_url, headers=headers)
        followings_response = requests.get(followings_url, headers=headers)
        followers_count = followers_response.json()['count'] if followers_response.status_code == 200 else 0
        followings_count = followings_response.json()['count'] if followers_response.status_code == 200 else 0
       
        presence_info = get_presence(user_id, headers)
        
        previous_usernames = get_previous_usernames(user_id)
        groups = get_groups(user_id)
        about_me = get_about_me(user_id)
        friends = get_entity_list(user_id, "friends")
        followers = get_entity_list(user_id, "followers")
        followings = get_entity_list(user_id, "followings")
        
        user_info_data = {
            'user_id': user_id,
            'alias': user_data['name'],
            'display_name': user_data['displayName'],
            'description': user_data.get('description', ''),
            'is_banned': user_data.get('isBanned', False),
            'has_verified_badge': user_data.get('hasVerifiedBadge', False),
            'friends': friends_count,
            'followers': followers_count,
            'following': followings_count,
            'join_date': user_data['created'],
            'previous_usernames': previous_usernames,
            'groups': groups,
            'about_me': about_me,
            'friends_list': friends,
            'followers_list': followers,
            'following_list': followings
        }
        
        if presence_info:
            user_info_data['presence_status'] = presence_info.get('status', 'N/A')
            user_info_data['last_location'] = presence_info.get('last_location', 'N/A')
            user_info_data['current_place_id'] = presence_info.get('place_id')
            user_info_data['last_online_timestamp'] = presence_info.get('last_online')
        else:
            user_info_data['presence_status'] = 'Error fetching presence'
            user_info_data['last_location'] = 'N/A'
            user_info_data['current_place_id'] = None
            user_info_data['last_online_timestamp'] = 'N/A'
        
        return user_info_data
   
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hi! Send me a Roblox username or ID to get information.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    identifier = update.message.text
    
    await update.message.reply_text(
        "Processing your request. This may take a few minutes due to API limitations. Please be patient."
    )

    try:
        loop = asyncio.get_running_loop()
        user_info = await loop.run_in_executor(None, get_user_info, identifier)
    except Exception as e:
        print(f"Error in get_user_info for {identifier}: {e}")
        await update.message.reply_text(f"An error occurred while searching: {e}")
        return

    if user_info:
        lines = [
            "Roblox user information:",
            "",
            f"User_id: {user_info['user_id']}",
            f"Alias: {user_info['alias']}",
            f"Display_name: {user_info['display_name']}",
            f"Description: {user_info['description']}",
            f"Is_banned: {user_info['is_banned']}",
            f"Has_verified_badge: {user_info['has_verified_badge']}",
            f"Friends: {user_info['friends']}",
            f"Followers: {user_info['followers']}",
            f"Following: {user_info['following']}",
            f"Join_date: {user_info['join_date']}",
            f"Previous_usernames: {', '.join(user_info['previous_usernames']) if user_info['previous_usernames'] else ''}",
            f"About_me: {user_info['about_me']}",
            "",
            "userPresence:",
            f"lastLocation: {user_info.get('last_location', '')}",
            f"placeId: {user_info.get('current_place_id', '')}",
            "",
            f"Profile URL: https://www.roblox.com/users/{user_info['user_id']}/profile"
        ]
        
        message_text = "\n".join(lines)
        await update.message.reply_text(message_text)
        
        json_filename = f"{user_info['user_id']}_{user_info['alias']}_info.json"
        
        try:
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(user_info, f, indent=4, ensure_ascii=False)
            
            with open(json_filename, 'rb') as f:
                await update.message.reply_document(document=InputFile(f))
            
            os.remove(json_filename)
            
        except IOError as e:
            print(f"Error writing or sending JSON file: {e}")
            await update.message.reply_text(f"Error creating JSON file: {e}")
        
    else:
        await update.message.reply_text("User not found.")

def main() -> None:
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("="*50)
        print("ERROR: Please add your Telegram Bot Token to the script.")
        print("Open roblox_bot.py and replace 'YOUR_BOT_TOKEN_HERE' with your token.")
        print("="*50)
        return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running... Press Ctrl-C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()

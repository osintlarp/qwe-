import requests
import json
from bs4 import BeautifulSoup
import random
import time
import argparse

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
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                wait_time = int(response.headers.get('Retry-After', 5))
                time.sleep(wait_time)
                retries += 1
            else:
                if max_retries and retries >= max_retries:
                    return None
                retries += 1
                time.sleep(5)
        except requests.RequestException:
            if max_retries and retries >= max_retries:
                return None
            retries += 1
            time.sleep(5)


def search_by_username(username):
    url = f"https://users.roblox.com/v1/users/search?keyword={username}&limit=10"
    headers = {'User-Agent': get_user_agent()}
    response = request_with_retries(url, headers)
     
    if response and response.status_code == 200:
        try:
            data = response.json()
            if data.get('data'):
                if 'id' in data['data'][0]:
                    return data['data'][0]['id']
                elif 'userId' in data['data'][0]:
                    return data['data'][0]['userId']
        except (json.JSONDecodeError, IndexError, KeyError):
            pass # Continue to next method
    
    try:
        url = f"https://www.roblox.com/users/profile?username={username}"
        headers = {'User-Agent': get_user_agent()}
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        
        if response.status_code == 200 and 'users' in response.url:
            parts = response.url.split('/')
            for i, part in enumerate(parts):
                if part == 'users' and i + 1 < len(parts):
                    user_id = parts[i + 1]
                    if user_id.isdigit():
                        return user_id
    except requests.RequestException:
        pass
   
    return None

def get_previous_usernames(user_id):
    url = f"https://users.roblox.com/v1/users/{user_id}/username-history?limit=100&sortOrder=Asc"
    headers = {'User-Agent': get_user_agent()}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return [entry['name'] for entry in data.get('data', [])]
    except (requests.RequestException, json.JSONDecodeError):
        pass
    
    return []

def get_groups(user_id):
    url = f"https://groups.roblox.com/v2/users/{user_id}/groups/roles"
    headers = {'User-Agent': get_user_agent()}
    groups = []
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            for group in data.get('data', []):
                if 'group' in group:
                    groups.append({
                        'name': group['group'].get('name', 'N/A'),
                        'link': f"https://www.roblox.com/groups/{group['group'].get('id')}",
                        'members': group['group'].get('memberCount', 0)
                    })
    except (requests.RequestException, json.JSONDecodeError):
        pass
    
    return groups

def get_about_me(user_id):
    url = f"https://www.roblox.com/users/{user_id}/profile"
    headers = {'User-Agent': get_user_agent()}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
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
    except requests.RequestException:
        pass
    
    return "Not available"

def get_entity_list(user_id, entity_type):
    entities = set()  
    cursor = ""
    
    while True:
        url = f"https://friends.roblox.com/v1/users/{user_id}/{entity_type}?limit=100&cursor={cursor}"
        headers = {'User-Agent': get_user_agent()}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                for entity in data.get('data', []):
                    entity_id = None
                    name = None

                    # Check for nested 'user' object first
                    if 'user' in entity and isinstance(entity['user'], dict):
                        user_data = entity['user']
                        entity_id = user_data.get('id')
                        name = user_data.get('displayName') or user_data.get('name')
                    
                    # Check for flat structure
                    elif 'id' in entity:
                        entity_id = entity.get('id')
                        name = entity.get('displayName') or entity.get('username') or entity.get('name')

                    # Apply fallback rule: if no name, use ID
                    if entity_id:
                        if not name:  # This catches None or empty strings
                            name = str(entity_id)
                        
                        entities.add((name, f"https://www.roblox.com/users/{entity_id}/profile"))
                
                cursor = data.get('nextPageCursor')
                if not cursor:
                    break
            else:
                break # Exit loop on bad status code
        
        except (requests.RequestException, json.JSONDecodeError):
            break # Exit loop on request error
        
        time.sleep(1)
    
    return [{'name': name, 'url': url} for name, url in entities]

def get_game_passes(user_id):
    """Fetches game passes based on the user's example logic."""
    headers = {'User-Agent': get_user_agent()}
    
    try:
        # 1. Get user's games
        games_url = f"https://games.roblox.com/v2/users/{user_id}/games?accessFilter=2&limit=10&sortOrder=Asc"
        games_response = requests.get(games_url, headers=headers, timeout=10)
        
        if games_response.status_code != 200:
            return []  # Failed to get games
        
        user_data = games_response.json()
        game_ids = [game["id"] for game in user_data.get("data", []) if "id" in game]
        
        if not game_ids:
            return []  # No games found
            
        return_data = []
        for game_id in game_ids:
            # 2. Get game passes for each game
            passes_url = f"https://games.roblox.com/v1/games/{str(game_id)}/game-passes?limit=100&sortOrder=Asc"
            try:
                passes_response = requests.get(passes_url, headers=headers, timeout=10)
                
                if passes_response.status_code == 200:
                    game_data = passes_response.json()
                    if not game_data.get("data"):
                        continue
                    
                    # 3. Filter game passes
                    for game_pass in game_data["data"]:
                        if game_pass.get("sellerId") is not None:
                            return_data.append(game_pass)
                
                time.sleep(0.5)  # Be nice to the API
            
            except (requests.RequestException, json.JSONDecodeError):
                continue # Skip this game on error
        
        return return_data
        
    except (requests.RequestException, json.JSONDecodeError):
        return []  # Return empty list on any initial request error

def get_user_info(identifier):
    if identifier.isdigit():
        user_id = identifier
    else:
        user_id = search_by_username(identifier)
   
    if not user_id:
        return None
   
    user_url = f"https://users.roblox.com/v1/users/{user_id}"
    headers = {'User-Agent': get_user_agent()}
    
    try:
        user_response = requests.get(user_url, headers=headers, timeout=10)
    except requests.RequestException:
        return None # Failed to get core user data

    if user_response.status_code == 200:
        try:
            user_data = user_response.json()
        except json.JSONDecodeError:
            return None # Failed to parse user data

        # Helper to safely fetch counts
        def get_count(url, headers):
            try:
                r = requests.get(url, headers=headers, timeout=5)
                if r.status_code == 200:
                    return r.json().get('count', 0)
            except (requests.RequestException, json.JSONDecodeError):
                pass
            return 0

        friends_url = f"https://friends.roblox.com/v1/users/{user_id}/friends/count"
        friends_count = get_count(friends_url, headers)
       
        followers_url = f"https://friends.roblox.com/v1/users/{user_id}/followers/count"
        followers_count = get_count(followers_url, headers)

        followings_url = f"https://friends.roblox.com/v1/users/{user_id}/followings/count"
        followings_count = get_count(followings_url, headers)
       
        previous_usernames = get_previous_usernames(user_id)
        groups = get_groups(user_id)
        about_me = get_about_me(user_id)
        friends = get_entity_list(user_id, "friends")
        followers = get_entity_list(user_id, "followers")
        followings = get_entity_list(user_id, "followings")
        game_passes = get_game_passes(user_id) # Fetch game pass "infos"
        
        return {
            'user_id': user_id,
            'alias': user_data.get('name', 'N/A'),
            'display_name': user_data.get('displayName', 'N/A'),
            'description': user_data.get('description', ''),
            'is_banned': user_data.get('isBanned', False),
            'has_verified_badge': user_data.get('hasVerifiedBadge', False),
            'friends': friends_count,
            'followers': followers_count,
            'following': followings_count,
            'join_date': user_data.get('created', 'N/A'),
            'previous_usernames': previous_usernames,
            'groups': groups,
            'about_me': about_me,
            'friends_list': friends,
            'followers_list': followers,
            'following_list': followings,
            'game_passes': game_passes  # Add game passes to the output
        }
   
    return None

def main():
    parser = argparse.ArgumentParser(description='Get information about a Roblox user.')
    parser.add_argument('identifier', help='Roblox username or ID')
    args = parser.parse_args()

    user_info = get_user_info(args.identifier)
   
    if user_info:
        print(f"User ID: {user_info['user_id']}")
        print(f"Alias: {user_info['alias']}")
        print(f"Display Name: {user_info['display_name']}")
        print(f"Description: {user_info['description']}")
        print(f"Banned: {'Yes' if user_info['is_banned'] else 'No'}")
        print(f"Verified Badge: {'Yes' if user_info['has_verified_badge'] else 'No'}")
        print(f"Friends: {user_info['friends']}")
        print(f"Followers: {user_info['followers']}")
        print(f"Following: {user_info['following']}")
        print(f"Join Date: {user_info['join_date']}")
        print(f"Previous Usernames: {', '.join(user_info['previous_usernames']) if user_info['previous_usernames'] else 'None detected'}")
        print(f"\nAbout Me: {user_info['about_me']}")
        
        print("\nGroups:")
        for group in user_info['groups']:
            print(f"- {group['name']} ({group['members']} members)")
            print(f"  Link: {group['link']}")
        
        print(f"\nFound {len(user_info['game_passes'])} game passes.")

        # Define a JSON filename based on the user
        json_filename = f"{user_info['user_id']}_{user_info['alias']}_info.json"
        
        # Write all collected data to a single JSON file
        try:
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(user_info, f, indent=4, ensure_ascii=False)
            print(f"\nSuccessfully exported all user information to '{json_filename}'")
        except IOError as e:
            print(f"\nError writing to JSON file: {e}")
        
    else:
        print("User not found.")

if __name__ == '__main__':
    main()

import os
import json
import logging
from datetime import datetime

# --- Configuration (Consider using a config file or environment variables) ---
GOOGLE_WORKSPACE_CONFIG = {
    'domain': "yourcorpdomain.com",
    'admin_scopes': ['https://www.googleapis.com/auth/admin.directory.user',
                      'https://www.googleapis.com/auth/admin.directory.group'],
    'service_account_file': '/path/to/your/gworkspace_service_account_key.json',
    'default_org_unit': '/Users',  # Example OU
    'onboarding_group_email': 'all-employees@yourcorpdomain.com'
}

ZOOM_CONFIG = {
    'api_key': os.environ.get("ZOOM_CORP_API_KEY"),
    'api_secret': os.environ.get("ZOOM_CORP_API_SECRET"),
    'default_group_id': 'YOUR_CORP_ZOOM_GROUP_ID' # Optional
}

DROPBOX_CONFIG = {
    'access_token': os.environ.get("DROPBOX_CORP_ACCESS_TOKEN"),
    'onboarding_folder_path': '/Company Shared/New Starters'
}

SLACK_CONFIG = {
    'bot_token': os.environ.get("SLACK_CORP_BOT_TOKEN"),
    'welcome_channel': '#general-announcements'
}

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def onboard_google_workspace(user_data, config):
    """Provisions a Google Workspace account."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        config['service_account_file'], scopes=config['admin_scopes'])
    directory_service = build('admin', 'directory_v1', credentials=creds)

    email = user_data['email']
    first_name = user_data['first_name']
    last_name = user_data['last_name']
    password = user_data.get('password', 'DefaultWelcome1!') # Generate a better one
    org_unit = user_data.get('org_unit', config['default_org_unit'])

    try:
        user_body = {
            'primaryEmail': email,
            'name': {'givenName': first_name, 'familyName': last_name},
            'password': password,
            'orgUnitPath': org_unit,
            'changePasswordAtNextLogin': True
        }
        new_user = directory_service.users().insert(domain=config['domain'], body=user_body).execute()
        logging.info(f"Google Workspace user created: {new_user['primaryEmail']}")

        # Add to default onboarding group
        group_member_body = {'email': email, 'role': 'MEMBER'}
        directory_service.groups().insert(groupKey=config['onboarding_group_email'], body=group_member_body).execute()
        logging.info(f"User {email} added to group {config['onboarding_group_email']}")
        return True
    except Exception as e:
        logging.error(f"Error during Google Workspace onboarding for {email}: {e}")
        return False

def onboard_zoom(user_data, config):
    """Adds the user to Zoom (assumes account exists or SSO)."""
    import requests
    import json

    api_key = config['api_key']
    api_secret = config['api_secret']
    email = user_data['email']
    base_url = "https://api.zoom.us/v2"

    def generate_jwt(api_key, api_secret):
        # ... (Secure JWT generation logic using a library like PyJWT) ...
        import jwt
        payload = {
            'iss': api_key,
            'exp': datetime.utcnow() + timedelta(seconds=30) # Short expiry
        }
        return jwt.encode(payload, api_secret, algorithm='HS256')

    jwt_token = generate_jwt(api_key, api_secret)
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }

    # Check if user exists (by email) - Zoom API might have a specific endpoint
    user_list_url = f"{base_url}/users"
    try:
        response = requests.get(user_list_url, headers=headers, params={'status': 'active', 'page_size': 100}) # Adjust params
        response.raise_for_status()
        zoom_users_data = response.json()
        user_exists = any(user.get('email') == email for user in zoom_users_data.get('users', []))
        if user_exists:
            logging.info(f"Zoom user {email} already exists.")
            # Optionally add to a specific Zoom group if config['default_group_id'] is set
            if config.get('default_group_id'):
                group_url = f"{base_url}/groups/{config['default_group_id']}/members"
                add_payload = {'members': [{'email': email}]}
                add_response = requests.post(group_url, headers=headers, json=add_payload)
                add_response.raise_for_status()
                logging.info(f"User {email} added to Zoom group {config['default_group_id']}")
            return True
        else:
            logging.warning(f"Zoom user {email} not found. Account creation might be manual or via SSO.")
            return True # Or handle account creation via API if needed
    except Exception as e:
        logging.error(f"Error interacting with Zoom API for {email}: {e}")
        return False

def onboard_dropbox(user_data, config):
    """Grants access to a shared Dropbox folder."""
    import requests
    import json

    access_token = config['access_token']
    email = user_data['email']
    folder_path = config['onboarding_folder_path']

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "share_path": folder_path,
        "members": [{"member": {".tag": "email", "email": email}, "access_level": "viewer"}] # Adjust access level
    }

    try:
        url = "https://api.dropboxapi.com/2/sharing/add_folder_member"
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        logging.info(f"Invited {email} to Dropbox folder: {folder_path}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Error inviting {email} to Dropbox folder: {e}")
        return False
    except json.JSONDecodeError:
        logging.error(f"Error decoding Dropbox response for {email}: {e}")
        return False

def welcome_slack_user(user_data, config):
    """Welcomes the new user in a Slack channel."""
    import requests
    import json

    bot_token = config['bot_token']
    channel_name = config['welcome_channel']
    email = user_data['email']
    first_name = user_data['first_name']
    last_name = user_data['last_name']

    slack_api_url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json",
    }
    welcome_message = f"Welcome to the team, <mailto:{email}|{first_name} {last_name}>! Please introduce yourself in this channel."

    payload = {
        "channel": channel_name,
        "text": welcome_message
    }

    try:
        response = requests.post(slack_api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        response_data = response.json()
        if response_data.get("ok"):
            logging.info(f"Welcome message sent to {channel_name} for {email}")
            return True
        else:
            logging.error(f"Failed to send welcome message to Slack for {email}: {response_data.get('error')}")
            return False
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending message to Slack for {email}: {e}")
        return False
    except json.JSONDecodeError:
        logging.error(f"Error decoding Slack response for {email}: {e}")
        return False

if __name__ == "__main__":
    new_employee_data = {
        'email': "newhire123@yourcorpdomain.com",
        'first_name': "John",
        'last_name': "Doe",
        'org_unit': '/Users/New Employees' # Optional
    }

    logging.info(f"Starting onboarding process for {new_employee_data['email']}")

    gworkspace_success = onboard_google_workspace(new_employee_data, GOOGLE_WORKSPACE_CONFIG)
    zoom_success = onboard_zoom(new_employee_data, ZOOM_CONFIG)
    dropbox_success = onboard_dropbox(new_employee_data, DROPBOX_CONFIG)
    slack_success = welcome_slack_user(new_employee_data, SLACK_CONFIG)

    if all([gworkspace_success, zoom_success, dropbox_success, slack_success]):
        logging.info(f"Onboarding process completed successfully for {new_employee_data['email']}")
    else:
        logging.warning(f"Onboarding process completed for {new_employee_data['email']} with some potential failures. Check logs for details.")
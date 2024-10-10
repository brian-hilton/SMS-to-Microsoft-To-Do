import time
import os
import base64
import webbrowser
import asyncio
import configparser
import httpx
from msgraph.generated.models.o_data_errors.o_data_error import ODataError
from graph import Graph
from config.settings import TASK_LIST_ID
from config.settings import SMS_CONTACTS
UNKNOWN_SENDER = 'UNKNOWN'

# TODO Implement white list using env file
# TODO Create status schedule to send an email confirming the app is running

async def main():
    # Load settings
    config = configparser.ConfigParser()
    config.read(['config/config.cfg', 'config/config.dev.cfg'])
    azure_settings = config['azure']
    time_delay = 10      # May adjust as necessary, time is in seconds

    # create graph instance
    graph: Graph = Graph(azure_settings)
    webbrowser.open('https://microsoft.com/devicelogin', new=0)

    # Login using device code (code provided in terminal, browser page should open automatically to enter code)
    await login_user(graph)

    # Fetch most recent email: Returns a list of 10 emails; each email is a dictionary with fields described below
    current_emails = await get_latest_emails(graph) 
    current_email = current_emails[0]   
    print('Latest email: ', current_email['SMS_Body'])
    print('Sender:', current_email['Sender'])
    print('Message ID: ', current_email['MessageID'][-12:], '\n')

    while True:
        try:
            time.sleep(time_delay)

            is_new_mail = await check_for_new_email(graph, current_emails)
            if is_new_mail[0] == True:
                new_emails = await post_service(graph, current_emails)
                current_emails = new_emails
            else:
                print(f'No new mail... {time.asctime(time.localtime())}')
                
        except httpx.HTTPStatusError as exc:
            print(f'Reached an HTTP error: {exc}')

        except asyncio.TimeoutError as timeout:
            print(f'Async request timed out {timeout}')
        
        except Exception as exc:
            print(f'An unexpected error occured: {exc}')
            

async def login_user(graph: Graph):
    """Uses device code authorization to login"""
    user = await graph.get_user()
    if user:
        print('User:', user.display_name)
        # For Work/school accounts, email is in mail property
        # Personal accounts, email is in userPrincipalName
        print('Email:', user.mail or user.user_principal_name, '\n')

async def display_access_token(graph: Graph):
    token = await graph.get_user_token()
    print('User token:', token, '\n')

async def list_inbox(graph: Graph):
    message_page = await graph.get_inbox()
    if message_page and message_page.value:
        # Output each message's details
        for message in message_page.value:
            print('Message:', message.subject)
            if (
                message.from_ and
                message.from_.email_address
            ):
                print('  From:', message.from_.email_address.name or 'NONE')
            else:
                print('  From: NONE')
            print('  Status:', 'Read' if message.is_read else 'Unread')
            print('  Received:', message.received_date_time)

        # If @odata.nextLink is present
        more_available = message_page.odata_next_link is not None
        print('\nMore messages available?', more_available, '\n')

async def send_mail(graph: Graph):
    # Send mail to the signed-in user
    # Get the user for their email address
    user = await graph.get_user()
    if user:
        user_email = user.mail or user.user_principal_name

        await graph.send_mail('Testing Microsoft Graph', 'Hello world!', user_email or '')
        print('Mail sent.\n')

async def get_todo_lists(graph: Graph):
    todo_lists = await graph.get_lists()
    if todo_lists:
        print(todo_lists)

async def post_todo_task_from_email(graph: Graph, email):
    """Pass in latest email"""

    task_title = ''
    email_subject = email['Subject']
    sender_name = email['Sender']
    message_id = email['MessageID']
    attachments = await graph.get_attachments(message_id)
    filtered_attachments = []

    # find plain/text attachments to use for task title
    if attachments:
        for attachment in attachments:
            content_type = attachment.content_type
            content_bytes = attachment.content_bytes

            if content_type == 'text/plain':
                decoded_text = base64.b64decode(content_bytes).decode('utf-8')
                task_title = decoded_text.strip()
            else:
                filtered_attachments.append(attachment)

        if not task_title:
            task_title = 'image'

        task_title = task_title + ', ' + sender_name
        result = await graph.post_task(TASK_LIST_ID, task_title)
        print('\t' + task_title + ' uploaded to Microsoft To List ID:', str(TASK_LIST_ID[:10]))
        print(f'\tUploaded on {time.asctime(time.localtime())}', '\n')

        # If we have image attachments, upload as file attachment
        if filtered_attachments:
            await graph.post_attachments(TASK_LIST_ID, result.id, filtered_attachments)
            print("\tImage uploading. Request may take a minute to process.", '\n')
        
    
    else:
        if email_subject != 'EMPTY SUBJECT':
            task_title = email_subject + ', ' + sender_name
        else:
            task_title = 'No subject or attachments found. ' + sender_name

        await graph.post_task(TASK_LIST_ID, task_title, attachments)

async def post_service(graph: Graph, current_emails):
    """Handle posting task when we know we have at least one new email. Return the new list of emails"""
    # First call count_new_emails, then iterate through, saving and posting each time
    unchecked_emails = await get_latest_emails(graph)
    new_email_list = await count_new_emails(current_emails, unchecked_emails)

    for email in new_email_list:
        print('\t' + 'New message: ' + email['SMS_Body'] + '\n' + '\t' + 'From: ' + email['Sender'])
        await save_attachments_by_message_id(graph, email['MessageID'], email['SMS_Body'])
        await post_todo_task_from_email(graph, email)
    
    return unchecked_emails


async def count_new_emails(curr_list, new_list):
    """Identify how many new emails were received since last check, Return list of new emails"""
    prev_ids = {d['MessageID'] for d in curr_list}
    new_ids = {d['MessageID'] for d in new_list}
    ids = list(new_ids - prev_ids)

    unauthorized_message_count = 0

    for email in new_list:
        if email['Sender'] == UNKNOWN_SENDER:
            #print(email['Sender'])
            unauthorized_message_count += 1


    new_email_list = [email for email in new_list if email['MessageID'] in ids and email['Sender'] != UNKNOWN_SENDER]
    print()
    
    if len(new_email_list) == 0:
        print('Unauthorized sender. Message will not be uploaded.', '\n')
        return new_email_list

    if unauthorized_message_count > 0:
        print('Detected', str(unauthorized_message_count), 'unauthorized messages. Deploying counter-virus.')

    print('Found', str(len(new_email_list)), 'new emails!') 
    return new_email_list

async def get_latest_emails(graph: Graph):
    """Obtain 10 latest emails and store in list. Emails are stored as dictionaries with four values: Subject, sender, message id, and SMS_Body (from downloaded file)"""

    # We only want to store the subject, sender and messageID (in that order)
    email_list = []

    message_page = await graph.get_inbox()
    if message_page and message_page.value:
        for message in message_page.value:
            curr_email = {
                'Subject': 'EMPTY SUBJECT',
                'Sender': message.from_.email_address.name,
                'MessageID': 'NO messageID found',
                'SMS_Body': 'No SMS Body'
            }

            if message.subject:
                curr_email['Subject'] = message.subject
            
            if (message.from_ and message.from_.email_address):
                sender = message.from_.email_address.name
                if sender[:10] in SMS_CONTACTS:
                    curr_email['Sender'] = SMS_CONTACTS[sender[:10]]
                else:
                    curr_email['Sender'] = UNKNOWN_SENDER
                               

            curr_email['SMS_Body'] = await graph.get_attachments(message.id, True) 
            if type(curr_email['SMS_Body']) != str:
                curr_email['SMS_Body'] = 'Image'

            # Grab unique part of message id (last 12 characters)
            # curr_email.append(message.id[-12:]) Entire message ID needed for later logic so no longer need to slice
            curr_email['MessageID'] = message.id
        
            email_list.append(curr_email)
    
        return email_list

async def check_for_new_email(graph: Graph, current_emails):
    current_email = current_emails[0]
    latest_emails = await get_latest_emails(graph)
    latest_email = latest_emails[0]

    # Compare email id
    if latest_email['MessageID'] == current_email['MessageID']:
        return [False]
    else:
        return [True, latest_email]

async def save_attachments_by_message_id(graph: Graph, message_id: str, SMS_Body: str):
        """Save attachments locally to the correct subfolder within attachments. Does not return anything or upload any attachments, this is done elsewhere"""
        attachment_dir = await create_attachment_folder()
        attachments = await graph.get_attachments(message_id)
        file_type_count = {'jpg': 0,
                           'gif': 0,
                           'png': 0,
                           'bmp': 0,
                           'txt': 0
                           }

        if attachments:
            for attachment in attachments:
                name = attachment.name
                extension = name[-3:]
                file_count = file_type_count[extension]
                file_name = SMS_Body[:9] + '_' + message_id[-8:-4] + '_' + str(file_count) + '.' + extension        # Concatenate the SMS_Body with the unique part of the message id and a #count in case there are multiple files of the same type in one message.
                file_type_count[extension] += 1

                attachment_content = attachment.content_bytes
                
                if attachment_content:
                    file_content = base64.b64decode(attachment_content)
                    file_path = os.path.join(attachment_dir, file_name)

                    with open(file_path, 'wb') as f:
                        f.write(file_content)
                    print(f'\tSaved to {file_path}')
                    print('\t' + message_id[-12:])

async def create_attachment_folder():
    months = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
    t = time.localtime()
    day = t.tm_mday
    month = t.tm_mon
    year = t.tm_year
    month_dir = f"{months[month - 1]}_{t.tm_year}"
    day_dir = f"{month}_{day}_{year}"

    if not os.path.isdir(f'attachments/{month_dir}'):
        os.makedirs(f'attachments/{month_dir}')
    
    if not os.path.isdir(f'attachments/{month_dir}/{day_dir}'):
        os.makedirs(f'attachments/{month_dir}/{day_dir}')
    
    return f'attachments/{month_dir}/{day_dir}'

# Run main
asyncio.run(main())

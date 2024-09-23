import time
import os
import base64
import webbrowser
import asyncio
import configparser
import random
from msgraph.generated.models.o_data_errors.o_data_error import ODataError
from graph import Graph
from config.settings import TASK_LIST_ID

# TODO Implement white list using env file
# TODO Configure env to grab from local csv
# TODO Create status schedule to send an email confirming the app is running

async def main():

    # Load settings
    config = configparser.ConfigParser()
    config.read(['config/config.cfg', 'config/config.dev.cfg'])
    azure_settings = config['azure']
    time_delay = 5      # May adjust as necessary, time is in seconds

    # create graph instance
    graph: Graph = Graph(azure_settings)
    webbrowser.open('https://microsoft.com/devicelogin', new=0)

    # Login using device code (code provided in terminal, browser page should open automatically to enter code)
    await login_user(graph)

    # Fetch most recent email: The 0th index is the rng id, each index after that follows the email dictionary structure created below
    latest_emails = await get_latest_emails(graph)    
    most_recent_email = latest_emails[1]

    print('Latest email: ', most_recent_email['SMS Body'])
    print('Sender:', most_recent_email['Sender'])
    print('Message ID: ', most_recent_email['MessageID'][-12:])
    
    while True:
        time.sleep(time_delay)

        # is_new_mail is a list consiting of: boolean to determine if theres a new mesage in inbox. If there is, the second element contains the message resource
        is_new_mail = await check_for_new_email(graph, most_recent_email)
        if is_new_mail[0] == True:
            print('We have new mail! Posting to Microsoft To Do.')
            most_recent_email = is_new_mail[1]
            await save_attachments_by_message_id(graph, most_recent_email['MessageID'])
            await post_todo_task_from_email(graph, most_recent_email)   #TODO Finish necessary functions to upload To Do task with proper title
        else:
            print('No new mail...')

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
    #TODO We are getting the plain text attachment, now we need to handle images and upload as a To Do taskFileAttachment
    #TODO fileAttachments handled in separate function as the task id is required for the upload
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

        task_title = task_title + ', ' + sender_name
        result = await graph.post_task(TASK_LIST_ID, task_title)
        print(task_title, 'uploaded to', str(TASK_LIST_ID[:10]))

        # If we have image attachments, upload as file attachment
        if filtered_attachments:
            await graph.post_attachments(TASK_LIST_ID, result.id, filtered_attachments)
            print("Image uploading. Request may take a minute to process.")
        
    
    else:
        if email_subject != 'EMPTY SUBJECT':
            task_title = email_subject + ', ' + sender_name
        else:
            task_title = 'No subject or attachments found. ' + sender_name

        await graph.post_task(TASK_LIST_ID, task_title, attachments)

async def get_latest_emails(graph: Graph):
    """Obtain 10 latest emails and store in list. Emails are stored as dictionaries with four values: Subject, sender, message id, and sms body (from downloaded file)"""

    # We only want to store the subject, sender and messageID (in that order)
    # Also store a random id at the beginning of email list in case more than one message is received between ticks
    email_list = []
    email_list.append(random.random())

    message_page = await graph.get_inbox()
    if message_page and message_page.value:
        for message in message_page.value:
            curr_email = {
                'Subject': 'EMPTY SUBJECT',
                'Sender': 'EMPTY SENDER FIELD',
                'MessageID': 'NO messageID found',
                'SMS Body': 'No SMS body'
            }

            if message.subject:
                curr_email['Subject'] = message.subject
            
            if (message.from_ and message.from_.email_address):
                curr_email['Sender'] = message.from_.email_address.name   

            curr_email['SMS Body'] = await graph.get_attachments(message.id, True)     

            # Grab unique part of message id (last 12 characters)
            # curr_email.append(message.id[-12:]) Entire message ID needed for later logic so no longer need to slice
            curr_email['MessageID'] = message.id
        
            email_list.append(curr_email)
    
        return email_list

async def check_for_new_email(graph: Graph, most_recent_email):
    latest_emails = await get_latest_emails(graph)
    latest_email = latest_emails[1]

    # Compare email id
    if latest_email['MessageID'] == most_recent_email['MessageID']:
        return [False]
    else:
        return [True, latest_email]

# TODO Fix file overwrite issue; add naming convention using sender and/or date&time
async def save_attachments_by_message_id(graph: Graph, message_id: str):
        """Save attachments locally to the correct subfolder within attachments. Does not return anything or upload any attachments, this is done elsewhere"""
        attachment_dir = await create_attachment_folder()
        attachments = await graph.get_attachments(message_id)
        if attachments:
            for attachment in attachments:
                
                attachment_name = attachment.name
                attachment_content = attachment.content_bytes
                
                if attachment_content:
                    file_content = base64.b64decode(attachment_content)
                    file_path = os.path.join(attachment_dir, attachment_name)

                    with open(file_path, 'wb') as f:
                        f.write(file_content)
                    print(f'Saved {attachment_name} to {file_path}')

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

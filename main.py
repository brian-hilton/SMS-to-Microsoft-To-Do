import time
import json
import os
import signal
import httpx
import asyncio
from graph import GraphClient
from config.settings import CLIENT_ID
from config.settings import CLIENT_SECRET
from config.settings import TENANT_ID

UNKNOWN_SENDER = 'UNKNOWN'

# TODO Implement white list using env file
# TODO Create status schedule to send an email confirming the app is running

def handle_sigterm(*args):
    print("Shutting down gracefully...")
    exit(0)


signal.signal(signal.SIGTERM, handle_sigterm)

async def main():

    # Create GraphClient instance
    graph: GraphClient = GraphClient(CLIENT_ID, CLIENT_SECRET, TENANT_ID)
    time_delay = 90
    print('Initiating To Do Service')
    await graph.get_user_messages()

    curr_messages = graph.get_curr_messages()
    curr_message = curr_messages[0]
    sender = curr_message['Sender']
    message = curr_message['SMS_Body']
    print(f'{message}, from {sender}')

    while True:
        
        try:
            await post_service(graph)

        except httpx.HTTPStatusError as exc:
            print(f'Reached an HTTP error: {exc}')

        except asyncio.TimeoutError as timeout:
            print(f'Async request timed out {timeout}')
        
        except Exception as exc:
            print(f'An unexpected error occured: {exc}')
            
        time.sleep(time_delay)

async def check_for_new_messages(graph):
    """Make graph call to obtain 10 most recent emails and compare to local message collection. Returns any new messages"""
    prev_messages = graph.get_curr_messages()
    await graph.get_user_messages()
    new_messages = graph.get_curr_messages()

    prev_message = prev_messages[0]
    new_message = new_messages[0]

    if prev_message['MessageID'] != new_message['MessageID']:
        prev_ids = {d['MessageID'] for d in prev_messages}
        new_ids = {d['MessageID'] for d in new_messages}
        ids = list(new_ids - prev_ids)

        new_message_list = [message for message in new_messages if message['MessageID'] in ids and message['Whitelisted'] == True]
        return new_message_list

async def post_service(graph):
    new_messages = await check_for_new_messages(graph)
    if new_messages:
        for message in new_messages:
            await graph.post_task(message)

    else:
        print(f'No new messages... {time.asctime(time.localtime())}')
    
async def print_user_lists(graph):
    todo_lists = await graph.get_user_todo_lists()
    if todo_lists:
        print(json.dumps(todo_lists, indent=4))

async def post_task_todo(graph):
    messages = await graph.get_user_messages()
    await graph.post_task(messages[0])

async def print_messages(graph):
    curr_messages = await graph.get_user_messages()
    for message in curr_messages:
        print(message['SMS_Body'], 'From:', message['Sender'])
    
# Run main
asyncio.run(main())

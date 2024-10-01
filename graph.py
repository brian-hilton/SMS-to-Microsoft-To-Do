
from configparser import SectionProxy
from config.settings import TASK_LIST_ID
import json
import base64
import io
from azure.identity import DeviceCodeCredential, TokenCachePersistenceOptions
from msgraph import GraphServiceClient
from msgraph.generated.users.item.user_item_request_builder import UserItemRequestBuilder
from msgraph.generated.users.item.mail_folders.item.messages.messages_request_builder import (
    MessagesRequestBuilder)
from msgraph.generated.users.item.send_mail.send_mail_post_request_body import (
    SendMailPostRequestBody)
from msgraph.generated.models.message import Message
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.recipient import Recipient
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.todo_task import TodoTask
from msgraph.generated.models.linked_resource import LinkedResource
from msgraph.generated.models.task_file_attachment import TaskFileAttachment

class Graph:
    settings: SectionProxy
    device_code_credential: DeviceCodeCredential
    user_client: GraphServiceClient

    def __init__(self, config: SectionProxy):
        self.settings = config
        client_id = self.settings['clientId']
        tenant_id = self.settings['tenantId']
        graph_scopes = self.settings['graphUserScopes'].split(' ')
        token_cache_options = TokenCachePersistenceOptions(allow_unencrypted_storage=True)


        self.device_code_credential = DeviceCodeCredential(client_id, tenant_id=tenant_id, cache_persistence=token_cache_options)
        self.user_client = GraphServiceClient(self.device_code_credential, graph_scopes)
        


    async def get_user_token(self):
        graph_scopes = self.settings['graphUserScopes']
        access_token = self.device_code_credential.get_token(graph_scopes)
        return access_token.token



    async def get_user(self):
        # Only request specific properties using $select
        query_params = UserItemRequestBuilder.UserItemRequestBuilderGetQueryParameters(
            select=['displayName', 'mail', 'userPrincipalName']
        )

        request_config = UserItemRequestBuilder.UserItemRequestBuilderGetRequestConfiguration(
            query_parameters=query_params
        )

        user = await self.user_client.me.get(request_configuration=request_config)
        return user

    async def get_inbox(self):
        query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
            # Only request specific properties
            select=['from', 'isRead', 'receivedDateTime', 'subject'],
            # Get at most 10 results
            top=10,
            # Sort by received time, newest first
            orderby=['receivedDateTime DESC']
        )
        request_config = MessagesRequestBuilder.MessagesRequestBuilderGetRequestConfiguration(
            query_parameters= query_params
        )

        messages = await self.user_client.me.mail_folders.by_mail_folder_id('inbox').messages.get(
                request_configuration=request_config)
        return messages
    
    # If only wanting to get SMS body for showing in terminal, pass in True for sms_only
    async def get_attachments(self, message_id, sms_only=False):
        """Return list of attachments"""
        if sms_only:
            messages = await self.user_client.me.messages.by_message_id(message_id).attachments.get()
            attachments = messages.value
            if isinstance(attachments, list) and attachments:
                for attachment in attachments:
                    if attachment.content_type == 'text/plain':
                        return base64.b64decode(attachment.content_bytes).decode('utf-8').strip()
            else:
                return 'Not found'


        attachment_collection = await self.user_client.me.messages.by_message_id(message_id).attachments.get()
        if attachment_collection:
            attachments = attachment_collection.value
            if isinstance(attachments, list) and attachments:
                return attachments
            else:
                return None
        else:
            return None

    async def send_mail(self, subject: str, body: str, recipient: str):
        message = Message()
        message.subject = subject

        message.body = ItemBody()
        message.body.content_type = BodyType.Text
        message.body.content = body

        to_recipient = Recipient()
        to_recipient.email_address = EmailAddress()
        to_recipient.email_address.address = recipient
        message.to_recipients = []
        message.to_recipients.append(to_recipient)

        request_body = SendMailPostRequestBody()
        request_body.message = message

        await self.user_client.me.send_mail.post(body=request_body)
    
    async def get_lists(self):
        todo_lists = await self.user_client.me.todo.lists.get()
        return todo_lists

    async def post_task(self, list_id: str, task_title: str):
        task = TodoTask()
        task.title = task_title
        result = await self.user_client.me.todo.lists.by_todo_task_list_id(list_id).tasks.post(task)
        return result

    async def post_attachments(self, list_id, task_id, attachments: list = None):
        request_body = None
        if task_id and attachments:
            for attachment in attachments:
                if attachment.content_type != 'text/plain':         # We've already handled text attachment
                    request_body = TaskFileAttachment( 
                        odata_type = "#microsoft.graph.taskFileAttachment",
                        name = attachment.name,
                        content_type = attachment.content_type,
                        content_bytes = base64.urlsafe_b64decode(attachment.content_bytes)
                    )
                if request_body != None:
                    result = await self.user_client.me.todo.lists.by_todo_task_list_id(list_id).tasks.by_todo_task_id(task_id).attachments.post(request_body)
        else:
            print('Unable to complete attachment upload')
        
        return result
        
            


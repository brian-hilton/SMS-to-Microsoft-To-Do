from config.settings import TASK_LIST_ID, USER_ID, SMS_CONTACTS
import base64
import msal
import httpx
import requests
import mimetypes

class GraphClient:
    def __init__(self, client_id, client_secret, tenant_id):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.authority = f"https://login.microsoftonline.com/{tenant_id}"
        self.scope = ["https://graph.microsoft.com/.default"]
        self.app = msal.ConfidentialClientApplication(
            client_id,
            authority = self.authority,
            client_credential = client_secret
        )
        self.access_token = None
        self.messages = []

    def update_curr_messages(self, new_messages):
        self.messages = new_messages
    
    def get_curr_messages(self):
        return self.messages
    
    def get_access_token(self):
        if self.access_token:
            return self.access_token
        
        result = self.app.acquire_token_for_client(scopes=self.scope)

        if "access_token" in result:
            self.access_token = result["access_token"]
            return self.access_token
        else:
            raise Exception("Failed to obtain access token: " + str(result.get("error")))
    
    async def get_users(self):
        access_token = self.get_access_token()
        headers = {
            'Authorization': 'Bearer ' + access_token
        }
        async with httpx.AsyncClient() as client:
            response = await client.get("https://graph.microsoft.com/v1.0/users", headers=headers)
            return response.json()
        
    async def get_user_messages(self):
        """Get 10 most recent emails from inbox and return array of reformated messages."""
        access_token = self.get_access_token()
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        url = f'https://graph.microsoft.com/v1.0/users/{USER_ID}/mailFolders/inbox/messages'
        params = {
            "$expand": "attachments"
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            raw_messages = response.json()
            transformed_messages = []
            sms_content = ''

            for raw_message in raw_messages['value']:
                # Handle getting sms body from attachment to add into transformed message
                image_attachment_array = []
                sms_content = 'No SMS body found'
                attachments = raw_message.get('attachments', [])
                if attachments:
                    for attachment in attachments:
                        if attachment.get('contentType') == 'text/plain':
                            sms_content = await self.download_attachment(raw_message['id'], attachment['id'], headers)
                        if attachment.get('contentType', '').startswith('image/'):
                            image_attachment_array.append([attachment['id'], attachment.get('contentType')])

                
                # Store all relevant parts of message
                transformed_msg = {
                    'MessageID': raw_message.get('id'),
                    'Sender': raw_message.get('from', {}).get('emailAddress', {}).get('address'),
                    'Subject': raw_message.get('subject'),
                    'Body': raw_message.get('body', {}).get('content'),
                    'SMS_Body': sms_content,
                    'ReceivedDateTime': raw_message.get('receivedDateTime'),
                    'Whitelisted': False,
                    'AttachmentArray': image_attachment_array
                    # Each image array element contains a pair: the data bytes for an image attachment, and the contentType
                }

                # Make sure sender is in contacts
                if transformed_msg['Sender'][:10] in SMS_CONTACTS:
                    transformed_msg['Sender'] = SMS_CONTACTS[transformed_msg['Sender'][:10]]
                    transformed_msg['Whitelisted'] = True


                transformed_messages.append(transformed_msg)
            self.messages = transformed_messages
        
        else:
            print(f'Error: {response.status_code} - {response.text}')
            return []
    
    async def download_attachment(self, message_id, attachment_id, headers):
        """Download text file attachment and return decoded text to use as To Do Task title"""
        attachment_url = f"https://graph.microsoft.com/v1.0/users/{USER_ID}/messages/{message_id}/attachments/{attachment_id}/$value"
        response = requests.get(attachment_url, headers=headers)
        decoded_message = 'sms body'

        if response.status_code == 200:
            attachment_content = response.content
            try:
                decoded_message = attachment_content.decode('utf-8')

            except UnicodeDecodeError:
                print('Unable to decode attachment')

            return decoded_message
        
        else:
            print(f'Failed to download attachment: {response.status_code}')
            return None
    
    async def download_images(self, message):
        """ Return array of image attachments prepped for To Do upload"""
        attachment_array = []
        
        access_token = self.get_access_token()
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        message_id = message['MessageID']
        
        for attachment_item in message['AttachmentArray']:
            attachment_id = attachment_item[0]
            attachment_url = f"https://graph.microsoft.com/v1.0/users/{USER_ID}/messages/{message_id}/attachments/{attachment_id}/$value"
            response = requests.get(attachment_url, headers=headers)

            if response.status_code == 200:
                image_bytes = response.content
                encoded_image = base64.b64encode(image_bytes).decode('utf-8')

                content_type = response.headers.get('Content-Type')
                file_extension = mimetypes.guess_extension(content_type)
                file_name = f'image{file_extension}'

                attachment_data = {
                    "@odata.type": "#microsoft.graph.taskFileAttachment",
                    "name": file_name,
                    "contentBytes": encoded_image,
                    "contentType": attachment_item[1]
                }

                attachment_array.append(attachment_data)

            else:
                print(f'Error: {response.status_code}, {response.text}')

        return attachment_array

    async def post_task(self, message):
        """Upload task to microsoft To Do. Uses the sms body from the message as the task title and returns the task id to upload image attachments afterwards"""
        
        # First, check if message was received from whitelisted sender
        if message['Whitelisted'] == False:
            return 'Unauthorized sender. Task will not be uploaded'


        todo_url = f"https://graph.microsoft.com/v1.0/users/{USER_ID}/todo/lists/{TASK_LIST_ID}/tasks"
        access_token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }


        task_title = message['SMS_Body'] + ', ' + message['Sender']
        task_data = {
            'title': task_title
        }

        response = requests.post(todo_url, headers=headers, json=task_data)

        if response.status_code == 201:
            print('Task created successfully!')
            task_id = response.json().get("id")  # Save the task ID for attaching files later
            if len(message['AttachmentArray']) > 0:
                await self.upload_image(message, task_id, headers)
        
        else:
            print(f"Failed to create task. Status code: {response.status_code}")
            print(response.json())
            return 'Failed to upload task'

    async def upload_image(self, message, task_id, headers):
        """ Use attachment id to get image and post to a created to do task """

        to_do_attachment_url = f"https://graph.microsoft.com/v1.0/users/{USER_ID}/todo/lists/{TASK_LIST_ID}/tasks/{task_id}/attachments"
        
        attachment_collection = await self.download_images(message)

        for attachment_item in attachment_collection:
            attach_response = requests.post(to_do_attachment_url, headers=headers, json=attachment_item)

            if attach_response.status_code == 201:
                print(f"Image uploaded to task successfully!")
            else:
                print(f"Failed to attach image: {attach_response.status_code}, {attach_response.text}")
        
    async def get_user_todo_lists(self):
        url = f'https://graph.microsoft.com/v1.0/users/{USER_ID}/todo/lists'
        access_token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.json().get('value', [])
        
        else:
            print(f'Error: {response.status_code}, {response.text}')
            return None
        
            

"""Note: Any time headers are passed in a request, they must be defined as: headers=headers
This is because headers is a keyword argument and tells python to use my headers variable for the headers parameter"""
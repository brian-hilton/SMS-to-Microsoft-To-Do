import os
import ast
from dotenv import load_dotenv
from config.helper import load_sms_contacts_from_csv
from config.helper import load_contacts_from_env

load_dotenv()

TASK_LIST_ID = os.getenv('TASK_LIST_ID')
SCHEDULING_LIST_ID = os.getenv('SCHEDULING_LIST_ID')
SMS_CONTACTS = load_contacts_from_env()
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
TENANT_ID = os.getenv('TENANT_ID')
USER_ID = os.getenv('USER_ID')

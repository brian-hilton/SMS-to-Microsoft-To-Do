import os
import ast
from dotenv import load_dotenv
from config.helper import load_sms_contacts_from_csv
from config.helper import load_contacts_from_env

load_dotenv()

TASK_LIST_ID = os.getenv('TASK_LIST_ID')
contacts_csv_path = os.getenv('CONTACTS_CSV_PATH')
SMS_CONTACTS = load_contacts_from_env()

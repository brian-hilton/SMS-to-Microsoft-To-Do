import csv
import os
import io

def load_sms_contacts_from_csv(csv_file):
    contacts = {}
    with open(csv_file, mode='r') as file:
        csv_reader = csv.DictReader(file)
        #print(csv_reader.fieldnames)
        for row in csv_reader:
            contacts[row['phone_number'].strip()] = row['name'].strip()

    return contacts

# who is 'Doobs'?

def load_contacts_from_env():
    contacts_string = os.getenv('CONTACTS')
    contacts_io = io.StringIO(contacts_string)

    csv_reader = csv.DictReader(contacts_io)
    contacts_dict = {}

    for row in csv_reader:
        contacts_dict[row['phone_number']] = row['name']
    
    return contacts_dict
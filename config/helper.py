import csv

def load_sms_contacts_from_csv(csv_file):
    contacts = {}
    with open(csv_file, mode='r') as file:
        csv_reader = csv.DictReader(file)
        #print(csv_reader.fieldnames)
        for row in csv_reader:
            contacts[row['phone_number'].strip()] = row['name'].strip()

    return contacts
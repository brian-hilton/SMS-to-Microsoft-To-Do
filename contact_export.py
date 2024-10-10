import csv
import io

def csv_to_string(file_path):
    with open(file_path, 'r') as csv_file:
        csv_reader = csv.reader(csv_file)

        output = io.StringIO()
        csv_writer = csv.writer(output)

        for row in csv_reader:
            csv_writer.writerow(row)

        return output.getvalue().strip()

file_path = 'config/contacts.csv'
csv_string = csv_to_string(file_path)
print(csv_string)
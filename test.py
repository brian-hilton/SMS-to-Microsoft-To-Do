# Testing file naming procedure

files = ['image.jpg', 'image.jpg', 'picture.bmp', 'photo.jpg', 'dog.png', 'dog.png']
file_names = []

# print(f'\tSaved {a} to {b} at {curr_time}')
file_type_count = { 'jpg': 0,
                    'gif': 0,
                    'png': 0,
                    'bmp': 0
                    }

for file in files:
    extension = file[-3:]
    file_count = file_type_count[extension]
    file_name = file[:-4] + str(file_count) + '.' + extension
    file_names.append(file_name)
    file_type_count[extension] += 1

print(file_type_count)
print(file_names)
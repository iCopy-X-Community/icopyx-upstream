#!/usr/bin/env python3

import csv

columns=set()
bom=[]
with open('bom.txt') as csv_file:
    csv_reader = csv.reader(csv_file, delimiter=',')
    for row in csv_reader:
        for cell in row:
            title = cell[:cell.index(':')]
            columns.add(title)

with open('bom.txt') as csv_file:
    csv_reader = csv.reader(csv_file, delimiter=',')
    for row in csv_reader:
        d = dict.fromkeys(columns, '')
        for cell in row:
            title, data = cell[:cell.index(':')], cell[cell.index(':')+2:]
            d[title] = data
        bom.append(d)

#print(sorted(list(columns)))
# Choose in which order to display columns:
priocolumns=[
 'Comment',
 'Description',
 'Footprint',
 'Library Name',
 'Library Reference'
]
columns=priocolumns+sorted(list(columns-set(priocolumns)))

bom.sort(key=lambda d:d['Comment'])

with open('bom.csv', mode='w') as csv_file:
    writer = csv.DictWriter(csv_file, fieldnames=columns)
    writer.writeheader()
    writer.writerows(bom)
